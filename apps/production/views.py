from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from procurement.models import RawMaterialCostSnapshot

from .forms import OrderForm, OrderItemFormSet, ProductionCompletionForm, ProductionQualityCheckForm, ProductionReconciliationForm
from .models import Order, OrderItem, OrderMaterialUsage, ProductionBatch, ProductionBatchReconciliation, ProductionQualityCheck, ProductionCostSnapshot, ProductionCostLine
from sales.models import CustomerProductPrice
from inventory.models import FinishedGood
from inventory.services import (
    record_raw_material_movement,
    record_finished_good_movement,
)
from inventory.models import StockMovement
from core.invoice import production_order_pdf
from core.services import record_cash, audit
from core.models import FinancialTransaction


def today():
    return timezone.localdate()


@login_required
def orders_list(request):
    orders = Order.objects.prefetch_related("items__finished_good")
    return render(request, "production/orders_list.html", {"orders": orders})


def _price_map():
    """Return base channel prices and all customer overrides for the current business.

    The customer override map is display-only. The authoritative price snapshot
    is resolved server-side when each OrderItem is saved.
    """
    goods = list(FinishedGood.objects.all().prefetch_related("channel_prices"))
    products = {}
    for g in goods:
        channel_prices = {
            str(row.channel): f"{row.price}"
            for row in g.channel_prices.all()
        }
        products[str(g.pk)] = {
            "name": g.name,
            # Keep the three layers separate for the form's display resolver:
            # customer agreement -> exact channel price -> product default.
            "default": f"{g.selling_price}",
            "channel_prices": channel_prices,
            "physical_store_valid": g.stock is not None and g.reorder_level is not None and g.reorder_level > 0,
        }
    customer_overrides = {}
    for row in CustomerProductPrice.objects.select_related("customer").all():
        customer_overrides.setdefault(str(row.customer_id), {}).setdefault(str(row.finished_good_id), {})[row.channel] = f"{row.price}"
    return {"products": products, "customer_overrides": customer_overrides}


@login_required
def order_form(request, pk=None):
    obj = get_object_or_404(Order, pk=pk) if pk else None
    if obj and obj.status != "pending":
        messages.error(request, "Only pending orders can be edited.")
        return redirect("order_detail", pk=obj.pk)
    if request.method == "POST":
        form = OrderForm(request.POST, instance=obj)
        store_replenishment = (
            request.POST.get("order_type") == "physical_store"
            and request.POST.get("production_destination", "store") == "store"
        )
        formset = OrderItemFormSet(
            request.POST, instance=obj if obj else Order(),
            store_replenishment=store_replenishment,
            order_type=request.POST.get("order_type"),
        )
        has_items = formset.is_valid() and any(
            f.cleaned_data and not f.cleaned_data.get("DELETE") for f in formset.forms
        )
        if form.is_valid() and formset.is_valid() and not has_items:
            messages.error(request, "Add at least one product.")
        elif form.is_valid() and has_items:
            order_type = form.cleaned_data.get("order_type")
            order = form.save(commit=False)
            order.business = request.business
            if obj is None:
                order.created_by = request.user
            if order.customer:
                # A selected master customer remains authoritative for the
                # historical customer snapshot and customer-specific pricing.
                order.customer_name = order.customer.name
                order.customer_region = order.customer.region
                order.customer_group = order.customer.customer_group
            elif order.order_type == "online":
                # Ad-hoc online buyers do not need to exist in Customer master.
                # Keep any optional free-text snapshot supplied on the order.
                order.customer_name = (order.customer_name or "").strip()
                order.customer_region = (order.customer_region or "").strip()
                order.customer_group = (order.customer_group or "").strip()
            else:
                order.customer_name = ""
                order.customer_region = ""
                order.customer_group = ""
            if order.order_type == "physical_store":
                # Physical Store Orders are production/restock requests only.
                # Direct sales, payment method and cash account belong to the
                # Sales form, not this order workflow.
                order.transaction_type = "paid"
                order.unpaid_description = ""
                order.customer_payment_status = "paid"
                order.customer_payment_method = ""
                order.customer_payment_account = None
                order.payment_method = ""
                order.account = None
            elif order.customer_payment_status == "unpaid":
                # A receivable has no payment method/account yet.
                order.customer_payment_method = ""
                order.customer_payment_account = None
                order.payment_method = ""
                order.account = None
                order.transaction_type = "unpaid"
                order.unpaid_description = "Customer receivable — payment to be recorded through Finance."
            order.save()
            formset.instance = order
            items = formset.save(commit=False)
            for item in items:
                item.price = item.finished_good.selling_price_for(order.order_type, order.customer)
                if order.order_type == "physical_store":
                    item.production_batch_qty = Decimal("0")
                    item.production_piece_qty = Decimal("0")
                item.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            # Cash is recorded only when the completed customer order creates
            # its Sale record. This prevents an order from counting the same
            # payment twice (once at order creation and again at completion).
            messages.success(request, "Order updated." if obj else "Order created — approve it from the Orders page when ready.")
            return redirect("order_detail", pk=order.pk)
    else:
        form = OrderForm(instance=obj, initial=None if obj else {"date": today(), "order_type": "distribution"})
        store_replenishment = bool(
            obj and obj.order_type == "physical_store" and obj.production_destination == "store"
        )
        formset = OrderItemFormSet(
            instance=obj, store_replenishment=store_replenishment,
            order_type=(obj.order_type if obj else "distribution"),
        )
    prices = _price_map()
    return render(request, "production/order_form.html", {"form": form, "formset": formset, "prices": prices, "obj": obj})


def _material_release_plan(order, post_data=None):
    """Return flexible controls, per-item usage snapshots, and total release.

    Recipe quantities remain fixed unless the RecipeItem is explicitly marked
    flexible. Flexible values are entered as quantity per batch at approval.
    """
    flexible_rows = []
    usage_entries = []
    aggregated = {}
    errors = []

    items = list(order.items.select_related("finished_good").prefetch_related(
        "finished_good__recipe_items__raw_material",
        "finished_good__production_materials__raw_material",
    ))
    for item in items:
        good = item.finished_good
        upb = good.units_per_batch or Decimal("1")
        multiplier = item.effective_production_batch_qty + (item.effective_production_piece_qty / upb)
        per_material = {}
        links = [(link, True) for link in good.recipe_items.all()]
        links += [(link, False) for link in good.production_materials.all()]

        for link, is_recipe in links:
            planned_per_batch = link.qty_per_batch
            actual_per_batch = planned_per_batch
            flexible = bool(is_recipe and getattr(link, "flexible_usage", False))
            input_name = f"flex_qty_{item.pk}_{link.pk}" if flexible else None

            if flexible and post_data is not None:
                raw = post_data.get(input_name)
                if raw not in (None, ""):
                    try:
                        actual_per_batch = Decimal(str(raw))
                        if actual_per_batch < 0:
                            raise ValueError
                    except Exception:
                        errors.append(
                            f"Enter a valid non-negative quantity for {link.raw_material.name} in {good.name}."
                        )
                        actual_per_batch = planned_per_batch

            if flexible:
                flexible_rows.append({
                    "item": item,
                    "good": good,
                    "material": link.raw_material,
                    "input_name": input_name,
                    "planned_per_batch": planned_per_batch,
                    "actual_per_batch": actual_per_batch,
                    "multiplier": multiplier,
                    "usage_unit": link.raw_material.usage_unit,
                })

            material_row = per_material.setdefault(link.raw_material_id, {
                "order": order,
                "order_item": item,
                "raw_material": link.raw_material,
                "planned_quantity": Decimal("0"),
                "actual_quantity": Decimal("0"),
                "flexible": False,
            })
            material_row["planned_quantity"] += planned_per_batch * multiplier
            material_row["actual_quantity"] += actual_per_batch * multiplier
            material_row["flexible"] = material_row["flexible"] or flexible

        usage_entries.extend(per_material.values())
        for material_row in per_material.values():
            mat = material_row["raw_material"]
            current = aggregated.get(mat.pk)
            if current:
                current[1] += material_row["actual_quantity"]
            else:
                aggregated[mat.pk] = [mat, material_row["actual_quantity"]]

    return flexible_rows, usage_entries, aggregated, errors


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    shortages = order.shortages() if order.status == "pending" else []
    flexible_usages = _material_release_plan(order)[0] if order.status == "pending" else []
    batches = order.production_batches.select_related("finished_good").prefetch_related("quality_check")
    return render(request, "production/order_detail.html", {"order": order, "shortages": shortages, "batches": batches, "flexible_usages": flexible_usages})


@login_required
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method != "POST" or order.status != "pending":
        return redirect("order_detail", pk=pk)
    force = request.POST.get("force") == "1"
    flexible_usages, usage_entries, aggregated, errors = _material_release_plan(order, request.POST)
    if errors:
        for error in errors:
            messages.error(request, error)
        return render(request, "production/order_detail.html", {
            "order": order, "shortages": order.shortages(), "confirm_approve": False,
            "flexible_usages": flexible_usages,
            "batches": order.production_batches.select_related("finished_good").prefetch_related("quality_check"),
        })
    shortages = []
    for mat, needed in aggregated.values():
        if needed > mat.stock:
            shortages.append({
                "name": mat.name, "category": mat.get_category_display(), "usage_unit": mat.usage_unit,
                "needed": needed, "have": mat.stock, "short": needed - mat.stock,
            })
    if shortages and not force:
        return render(request, "production/order_detail.html", {
            "order": order, "shortages": shortages, "confirm_approve": True,
            "flexible_usages": flexible_usages,
            "batches": order.production_batches.select_related("finished_good").prefetch_related("quality_check"),
        })
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.status != "pending":
            return redirect("order_detail", pk=pk)
        for entry in usage_entries:
            OrderMaterialUsage.objects.create(business=order.business, created_by=request.user, **entry)
        for mat, needed in aggregated.values():
            material_cost, _ = _latest_material_cost(mat, order.date)
            record_raw_material_movement(
                mat, -needed, StockMovement.RAW_CONSUMPTION,
                note=f"Materials released for order #{order.pk}", reference=f"PROD-{order.pk}", unit_value=material_cost,
            )
        order.status = "approved"
        order.approved_date = today()
        order.save()
        audit(request.business, request.user, "approve", order, f"Order #{order.pk} approved", {
            "flexible_materials": [
                {"product": r["good"].name, "material": r["material"].name, "qty_per_batch": str(r["actual_per_batch"])}
                for r in flexible_usages
            ]
        })
    messages.success(request, "Order approved — raw materials released for production.")
    return redirect("order_detail", pk=pk)


@login_required
def order_reject(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status == "pending":
        order.status = "rejected"
        order.save()
        audit(request.business, request.user, "reject", order, f"Order #{order.pk} rejected")
        messages.success(request, "Order rejected.")
    return redirect("orders_list")


def _latest_material_cost(material, production_date):
    snapshot = RawMaterialCostSnapshot.objects.filter(
        raw_material=material, effective_date__lte=production_date
    ).order_by("-effective_date", "-id").first()
    if snapshot:
        return snapshot.usage_unit_cost, "latest_procurement"
    # Legacy/manual fallback for materials that predate historical snapshots.
    return material.cost_per_unit, "legacy_current_cost"


def _create_production_cost_snapshot(order, item, batch):
    good = item.finished_good
    production_date = batch.production_date
    upb = good.units_per_batch or Decimal("1")
    links = list(good.recipe_items.select_related("raw_material")) + list(good.production_materials.select_related("raw_material"))
    piece_factor = item.effective_production_piece_qty / upb
    total_batch_multiplier = item.effective_production_batch_qty + piece_factor
    released_usages = list(item.material_usages.select_related("raw_material"))
    total_cost = Decimal("0")
    sources = set()
    snapshot = ProductionCostSnapshot.objects.create(
        business=order.business, order=order, order_item=item, production_batch=batch, finished_good=good,
        production_date=production_date, produced_units=batch.saleable_units,
        batch_number=batch.batch_number, expiry_date=batch.expiry_date,
    )
    cost_rows = released_usages if released_usages else [
        type("RecipeCostRow", (), {"raw_material": link.raw_material, "actual_quantity": link.qty_per_batch * total_batch_multiplier})
        for link in links
    ]
    for usage in cost_rows:
        qty = usage.actual_quantity
        unit_cost, source = _latest_material_cost(usage.raw_material, production_date)
        line_total = qty * unit_cost
        total_cost += line_total
        sources.add(source)
        ProductionCostLine.objects.create(
            snapshot=snapshot, raw_material=usage.raw_material, quantity=qty,
            usage_unit_cost=unit_cost, total_cost=line_total, source=source,
        )
    snapshot.total_cost = total_cost
    snapshot.unit_cost = total_cost / batch.saleable_units if batch.saleable_units else Decimal("0")
    snapshot.cost_source = "latest_procurement" if sources == {"latest_procurement"} else "latest_procurement_with_legacy_fallback"
    snapshot.save(update_fields=["total_cost", "unit_cost", "cost_source"])
    batch.total_cost = total_cost
    batch.unit_cost = snapshot.unit_cost
    batch.save(update_fields=["total_cost", "unit_cost", "updated_at"])
    return snapshot


@login_required
def order_complete(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if order.status != "approved":
        return redirect("orders_list")

    items = list(order.items.select_related("finished_good"))
    completion_forms = []
    channel_code = {
        "physical_store": "P",
        "distribution": "D",
        "online": "O",
    }.get(order.order_type, "P")
    date_code = today().strftime("%y%m%d")
    for item_index, item in enumerate(items, start=1):
        # Channel + short date + order number + product position in that
        # order. The final segment is the product identifier within the order,
        # so a multi-product order remains traceable without duplicated suffixes.
        default_batch = f"{channel_code}{date_code}-{order.pk}-{item_index}"
        completion_forms.append(
            (item, ProductionCompletionForm(
                request.POST or None,
                prefix=f"item-{item.pk}",
                planned_units=item.production_total_units,
                required_units=item.total_units,
                customer_order=order.order_type in ("distribution", "online"),
                initial={
                    "produced_units": f"{Decimal(item.production_total_units).quantize(Decimal('0.01')):.2f}",
                    "batch_number": default_batch,
                    "planned_offcut_to_stock": item.planned_overproduction_units,
                },
            ))
        )

    if request.method == "POST":
        valid = all(form.is_valid() for _, form in completion_forms)
        if valid:
            with transaction.atomic():
                order.completed_date = today()
                for item, form in completion_forms:
                    produced = form.cleaned_data["produced_units"]
                    wastage = form.cleaned_data["wastage_units"]
                    saleable = form.cleaned_data["saleable_units"]
                    batch = ProductionBatch.objects.create(
                        business=order.business,
                        created_by=request.user,
                        order=order,
                        order_item=item,
                        finished_good=item.finished_good,
                        production_date=order.completed_date,
                        batch_number=form.cleaned_data["batch_number"],
                        expiry_date=form.cleaned_data.get("expiry_date"),
                        planned_units=item.production_total_units,
                        ordered_units=item.total_units,
                        planned_surplus_stock_units=form.cleaned_data.get("planned_surplus_stock_units") or Decimal("0"),
                        planned_surplus_customer_units=form.cleaned_data.get("planned_surplus_customer_units") or Decimal("0"),
                        planned_surplus_customer=form.cleaned_data.get("planned_offcut_customer"),
                        planned_surplus_customer_channel=form.cleaned_data.get("planned_offcut_channel") or "",
                        produced_units=produced,
                        wastage_units=wastage,
                        wastage_reason=form.cleaned_data.get("wastage_reason", ""),
                        shortage_flag=(
                            order.order_type in ("distribution", "online")
                            and form.cleaned_data.get("flag_shortage", False)
                        ),
                        shortage_reason=(
                            form.cleaned_data.get("shortage_reason", "")
                            if order.order_type in ("distribution", "online")
                            else ""
                        ),
                        excess_stock_units=form.cleaned_data.get("excess_to_stock") or Decimal("0"),
                        excess_non_stock_units=form.cleaned_data.get("excess_to_non_stock") or Decimal("0"),
                        excess_non_stock_purpose=(form.cleaned_data.get("excess_non_stock_purpose") or "").strip(),
                    )
                    ProductionQualityCheck.objects.create(
                        business=order.business,
                        created_by=request.user,
                        batch=batch,
                        status=form.cleaned_data["qc_status"],
                        checked_by=request.user if form.cleaned_data["qc_status"] != "pending" else None,
                        checked_at=timezone.now() if form.cleaned_data["qc_status"] != "pending" else None,
                        notes=form.cleaned_data.get("qc_notes", ""),
                    )
                    snapshot = _create_production_cost_snapshot(order, item, batch)
                    good = item.finished_good
                    planned = Decimal(item.production_total_units)
                    ordered = Decimal(item.total_units)
                    customer_committed = min(saleable, ordered) if order.order_type in ("distribution", "online") else Decimal("0")
                    destination_committed = min(saleable, planned) if order.order_type == "physical_store" else customer_committed
                    planned_surplus_stock = batch.planned_surplus_stock_units
                    planned_surplus_customer = batch.planned_surplus_customer_units
                    excess_stock = batch.excess_stock_units
                    excess_non_stock = batch.excess_non_stock_units
                    good.total_produced += saleable

                    if wastage:
                        record_finished_good_movement(
                            good, -wastage, StockMovement.FG_WASTAGE,
                            note=form.cleaned_data.get("wastage_reason") or f"Production wastage for batch {batch.batch_number}",
                            reference=batch.batch_number, affects_stock=False, unit_value=snapshot.unit_cost,
                        )

                    # Record the planned/committed portion according to the
                    # order's original destination. Excess is handled
                    # separately below so it cannot silently inflate customer
                    # deliveries or shelf stock.
                    if destination_committed > 0:
                        if order.order_type == "physical_store" and order.production_destination == "store":
                            record_finished_good_movement(
                                good, destination_committed, StockMovement.FG_PRODUCTION,
                                note=f"Planned store production — batch {batch.batch_number}",
                                reference=batch.batch_number, affects_stock=True, unit_value=snapshot.unit_cost,
                            )
                        else:
                            record_finished_good_movement(
                                good, destination_committed, StockMovement.FG_PRODUCTION,
                                note=(
                                    f"Non-stock production ({order.non_stock_purpose}) — batch {batch.batch_number}"
                                    if order.order_type == "physical_store" and order.production_destination == "non_stock"
                                    else f"Customer-order production batch {batch.batch_number}"
                                ),
                                reference=batch.batch_number, affects_stock=False, unit_value=snapshot.unit_cost,
                            )
                            if order.order_type in ("distribution", "online"):
                                good.total_delivered_to_customers += customer_committed

                    if planned_surplus_stock > 0:
                        record_finished_good_movement(
                            good, planned_surplus_stock, StockMovement.FG_PRODUCTION,
                            note=f"Planned customer-order offcut retained in Physical Store stock — batch {batch.batch_number}",
                            reference=batch.batch_number, affects_stock=True, unit_value=snapshot.unit_cost,
                        )

                    if planned_surplus_customer > 0:
                        from sales.models import Sale, SaleItem
                        customer = batch.planned_surplus_customer
                        channel = batch.planned_surplus_customer_channel
                        price = good.selling_price_for(channel, customer=customer)
                        upb = good.units_per_batch or Decimal("1")
                        alloc_batches = (planned_surplus_customer // upb) if upb else Decimal("0")
                        alloc_pieces = planned_surplus_customer - (alloc_batches * upb)
                        offcut_sale = Sale.objects.create(
                            business=order.business, date=order.completed_date,
                            customer=customer.name, customer_master=customer,
                            transaction_type="unpaid",
                            unpaid_description=f"Planned production offcut from order #{order.pk} — receivable",
                            account=None, payment_method="Transfer",
                            source=f"{channel}_order", linked_order=order, created_by=request.user,
                        )
                        SaleItem.objects.create(
                            sale=offcut_sale, finished_good=good, batch_qty=alloc_batches, piece_qty=alloc_pieces,
                            discount=Decimal("0"), price=price, unit_cost=snapshot.unit_cost, production_batch=batch,
                        )
                        batch.planned_surplus_sale = offcut_sale
                        batch.save(update_fields=["planned_surplus_sale", "updated_at"])
                        record_finished_good_movement(
                            good, planned_surplus_customer, StockMovement.FG_PRODUCTION,
                            note=f"Planned offcut allocated to {customer.name} via {channel.title()} — batch {batch.batch_number}",
                            reference=batch.batch_number, affects_stock=False, unit_value=snapshot.unit_cost,
                        )
                        good.total_delivered_to_customers += planned_surplus_customer

                    if excess_stock > 0:
                        record_finished_good_movement(
                            good, excess_stock, StockMovement.FG_PRODUCTION,
                            note=f"Excess production retained in Physical Store stock — batch {batch.batch_number}",
                            reference=batch.batch_number, affects_stock=True, unit_value=snapshot.unit_cost,
                        )

                    if excess_non_stock > 0:
                        record_finished_good_movement(
                            good, excess_non_stock, StockMovement.FG_PRODUCTION,
                            note=f"Excess production for {batch.excess_non_stock_purpose} — batch {batch.batch_number}",
                            reference=batch.batch_number, affects_stock=False, unit_value=snapshot.unit_cost,
                        )

                    update_fields = ["total_produced"]
                    if order.order_type in ("distribution", "online"):
                        update_fields.append("total_delivered_to_customers")
                    good.save(update_fields=update_fields)

                order.status = "completed"
                order.save(update_fields=["status", "completed_date", "updated_at"])

                if order.order_type in ("distribution", "online"):
                    from sales.models import Sale, SaleItem
                    sale = Sale.objects.create(
                        business=order.business,
                        date=order.completed_date,
                        customer=order.customer.name if order.customer else order.customer_name,
                        customer_master=order.customer,
                        payment_method=order.payment_method,
                        transaction_type=("paid" if order.customer_payment_status == "paid" else "unpaid"),
                        unpaid_description=("" if order.customer_payment_status == "paid" else "Customer receivable — payment to be recorded through Finance."),
                        account=order.customer_payment_account if order.customer_payment_status == "paid" else None,
                        source=f"{order.order_type}_order",
                        linked_order=order,
                        created_by=request.user,
                    )
                    for item, form in completion_forms:
                        snapshot = item.cost_snapshots.order_by("-id").first()
                        batch = item.production_batches.order_by("-id").first()
                        SaleItem.objects.create(
                            sale=sale, finished_good=item.finished_good,
                            batch_qty=item.batch_qty, piece_qty=item.piece_qty,
                            discount=item.discount, price=item.price,
                            unit_cost=snapshot.unit_cost if snapshot else None,
                            production_batch=batch,
                        )
                    if sale.transaction_type == "paid":
                        record_cash(
                            request.business, request.user, date=sale.date, amount=sale.total,
                            transaction_type=FinancialTransaction.INCOME, category="Customer order payment",
                            description=f"Payment received for order #{order.pk}", payment_method=sale.payment_method,
                            reference=f"ORDER-{order.pk}", account=order.customer_payment_account,
                        )
                audit(
                    order.business, request.user, "complete", order, f"Order #{order.pk} completed",
                    {
                        "channel": order.order_type,
                        "customer_payment_status": order.customer_payment_status if order.order_type in ("distribution", "online") else None,
                        "customer": (order.customer.name if order.customer else order.customer_name) if order.order_type in ("distribution", "online") else None,
                        "planned_offcut_to_stock": str(sum((f.cleaned_data.get("planned_surplus_stock_units") or Decimal("0") for _, f in completion_forms), Decimal("0"))),
                        "planned_offcut_to_customer": str(sum((f.cleaned_data.get("planned_surplus_customer_units") or Decimal("0") for _, f in completion_forms), Decimal("0"))),
                        "planned_offcut_customers": [f.cleaned_data["planned_offcut_customer"].name for _, f in completion_forms if f.cleaned_data.get("planned_offcut_customer")],
                        "excess_to_stock": str(sum((f.cleaned_data.get("excess_to_stock") or Decimal("0") for _, f in completion_forms), Decimal("0"))),
                        "excess_to_non_stock": str(sum((f.cleaned_data.get("excess_to_non_stock") or Decimal("0") for _, f in completion_forms), Decimal("0"))),
                        "non_stock_excess_purposes": [
                            f.cleaned_data.get("excess_non_stock_purpose", "").strip()
                            for _, f in completion_forms
                            if (f.cleaned_data.get("excess_to_non_stock") or Decimal("0")) > 0
                        ],
                    },
                )

            messages.success(request, "Production completed and batch records created.")
            return redirect("order_detail", pk=pk)

    return render(request, "production/order_complete.html", {
        "order": order,
        "completion_forms": completion_forms,
    })


@login_required
def production_batches(request):
    # One row per production order. Products/batches are nested under the
    # order so multi-product orders are not fragmented into separate rows.
    from django.db.models import Prefetch
    batches_qs = ProductionBatch.objects.filter(is_reversed=False).select_related(
        "finished_good", "quality_check"
    ).prefetch_related("sale_items__sale")
    orders = Order.objects.filter(
        production_batches__isnull=False, production_batches__is_reversed=False
    ).distinct().select_related("customer").prefetch_related(
        "items__finished_good",
        Prefetch("production_batches", queryset=batches_qs),
    )
    return render(request, "production/batches_list.html", {"orders": orders})


@login_required
def production_batch_detail(request, pk):
    batch = get_object_or_404(
        ProductionBatch.objects.select_related(
            "finished_good", "order", "order_item", "order__customer", "quality_check"
        ).prefetch_related(
            "cost_snapshots__lines__raw_material",
            "sale_items__sale",
            "reconciliation_in__source_batch__order",
            "reconciliation_out__target_batch__order",
            "order__items__finished_good",
        ),
        pk=pk,
    )
    recon_form = ProductionReconciliationForm(target_batch=batch) if batch.shortage_flag else None
    return render(request, "production/batch_detail.html", {
        "batch": batch,
        "qc_form": ProductionQualityCheckForm(instance=batch.quality_check),
        "recon_form": recon_form,
    })


@login_required
def production_batch_reconcile(request, pk):
    batch = get_object_or_404(
        ProductionBatch.objects.select_related("order", "finished_good"),
        pk=pk,
    )
    if request.method != "POST":
        return redirect("production_batch_detail", pk=pk)

    form = ProductionReconciliationForm(request.POST, target_batch=batch)
    if form.is_valid():
        source = form.cleaned_data["source_batch"]
        quantity = form.cleaned_data["quantity"]
        with transaction.atomic():
            # Re-check the live surplus/shortage inside the transaction so two
            # users cannot allocate the same surplus concurrently.
            source = ProductionBatch.objects.select_for_update().select_related("finished_good", "order").get(pk=source.pk)
            target = ProductionBatch.objects.select_for_update().select_related("finished_good", "order").get(pk=batch.pk)
            source_good = FinishedGood.objects.select_for_update().get(pk=source.finished_good_id)
            outgoing = sum((r.quantity for r in source.reconciliation_out.all()), Decimal("0"))
            retained_surplus = max(
                Decimal("0"),
                source.planned_surplus_stock_units + source.excess_stock_units - outgoing,
            )
            live_stock = max(Decimal("0"), Decimal(source_good.stock or 0))
            live_available = min(retained_surplus, live_stock)
            if quantity > live_available:
                form.add_error("quantity", f"Only {live_available:.2f} units remain available from that source batch/stock pool.")
            elif quantity > target.outstanding_shortage_units:
                form.add_error("quantity", f"Only {target.outstanding_shortage_units:.2f} units remain to be reconciled.")
            else:
                ProductionBatchReconciliation.objects.create(
                    business=target.business,
                    created_by=request.user,
                    source_batch=source,
                    target_batch=target,
                    quantity=quantity,
                    reason=form.cleaned_data["reason"].strip(),
                )
                # Reconciliation fulfils the target customer order from
                # excess that was deliberately retained as physical shelf
                # stock. The source may be from any production channel, so
                # remove the allocated units from stock and increase customer
                # delivery analytics without creating a second sale or
                # production event.
                record_finished_good_movement(
                    source_good, -quantity, StockMovement.ADJUSTMENT,
                    note=f"Shortage reconciliation to batch {target.batch_number} from {source.batch_number}",
                    reference=f"RECON-{source.batch_number}-{target.batch_number}",
                    affects_stock=True, unit_value=source.unit_cost,
                )
                target.finished_good.total_delivered_to_customers += quantity
                target.finished_good.save(update_fields=["total_delivered_to_customers", "updated_at"])
                audit(
                    request.business,
                    request.user,
                    "reconcile_shortage",
                    target,
                    f"{quantity:.2f} units reconciled from {source.batch_number} to {target.batch_number}",
                    {
                        "source_batch": source.batch_number,
                        "quantity": str(quantity),
                        "reason": form.cleaned_data["reason"].strip(),
                        "source_channel": source.order.order_type,
                        "target_channel": target.order.order_type,
                    },
                )
                messages.success(request, f"{quantity:.2f} units reconciled from {source.batch_number}.")
                return redirect("production_batch_detail", pk=pk)

    return render(request, "production/batch_detail.html", {
        "batch": batch,
        "qc_form": ProductionQualityCheckForm(instance=batch.quality_check),
        "recon_form": form,
    })


@login_required
def production_batch_qc(request, pk):
    batch = get_object_or_404(ProductionBatch, pk=pk)
    if request.method != "POST":
        return redirect("production_batch_detail", pk=pk)
    form = ProductionQualityCheckForm(request.POST, instance=batch.quality_check)
    if form.is_valid():
        with transaction.atomic():
            qc = form.save(commit=False)
            qc.business = batch.business
            qc.created_by = request.user if not qc.pk else qc.created_by
            qc.checked_by = request.user
            qc.checked_at = timezone.now()
            qc.batch = batch
            qc.save()
            audit(request.business, request.user, "quality_check", batch, f"Quality check updated for batch {batch.batch_number}", {"status": qc.status})
        messages.success(request, "Quality check updated.")
        return redirect("production_batch_detail", pk=pk)
    return render(request, "production/batch_detail.html", {"batch": batch, "qc_form": form})

@login_required
def order_reverse(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("material_usages__raw_material", "production_batches__finished_good"), pk=pk)
    if request.method != "POST":
        return redirect("order_detail", pk=pk)
    if order.status != "completed":
        messages.error(request, "Only completed orders can be reversed.")
        return redirect("order_detail", pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "Give a reason for reversing this completed order.")
        return redirect("order_detail", pk=pk)

    batches = list(order.production_batches.select_related("finished_good", "planned_surplus_sale"))
    batch_ids = [b.pk for b in batches]
    if ProductionBatchReconciliation.objects.filter(Q(source_batch_id__in=batch_ids) | Q(target_batch_id__in=batch_ids)).exists():
        messages.error(request, "This order cannot be reversed automatically because one of its batches has already been used in shortage reconciliation. Reverse/reconcile that downstream allocation first.")
        return redirect("order_detail", pk=pk)

    from sales.models import Sale
    related_sales = Sale.objects.filter(Q(linked_order=order) | Q(items__production_batch_id__in=batch_ids)).distinct().prefetch_related("payments")
    if any(sale.payments.exists() for sale in related_sales):
        messages.error(request, "This order cannot be reversed automatically because a linked sale already has customer payments. Reverse those payments first.")
        return redirect("order_detail", pk=pk)

    stock_to_remove = {}
    for batch in batches:
        good = batch.finished_good
        qty = batch.planned_surplus_stock_units + batch.excess_stock_units
        if order.order_type == "physical_store" and order.production_destination == "store":
            qty += min(batch.saleable_units, batch.planned_units)
        if qty > 0:
            stock_to_remove[good.pk] = stock_to_remove.get(good.pk, Decimal("0")) + qty
    for good_id, qty in stock_to_remove.items():
        good = FinishedGood.objects.get(pk=good_id)
        if good.stock is None or Decimal(good.stock) < qty:
            messages.error(request, f"Cannot reverse: {good.name} needs {qty:.2f} units available in shelf stock, but only {Decimal(good.stock or 0):.2f} remain. Restore/reconcile downstream stock usage first.")
            return redirect("order_detail", pk=pk)

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=pk)
        if order.status != "completed":
            messages.error(request, "Order status changed before reversal could be applied.")
            return redirect("order_detail", pk=pk)
        raw_totals = {}
        for usage in order.material_usages.select_related("raw_material"):
            raw_totals.setdefault(usage.raw_material_id, [usage.raw_material, Decimal("0")])[1] += usage.actual_quantity
        for material, qty in raw_totals.values():
            if qty > 0:
                record_raw_material_movement(material, qty, StockMovement.ADJUSTMENT, note=f"Reversal of raw-material release for order #{order.pk}", reference=f"REV-ORDER-{order.pk}")
        for batch in order.production_batches.select_for_update().select_related("finished_good"):
            good = batch.finished_good
            remove_from_stock = batch.planned_surplus_stock_units + batch.excess_stock_units
            if order.order_type == "physical_store" and order.production_destination == "store":
                remove_from_stock += min(batch.saleable_units, batch.planned_units)
            if remove_from_stock > 0:
                record_finished_good_movement(good, -remove_from_stock, StockMovement.ADJUSTMENT, note=f"Reversal of finished-good stock from order #{order.pk} — batch {batch.batch_number}", reference=f"REV-{batch.batch_number}", affects_stock=True, unit_value=batch.unit_cost)
            good.total_produced = max(Decimal("0"), Decimal(good.total_produced or 0) - batch.saleable_units)
            delivered = Decimal("0")
            if order.order_type in ("distribution", "online"):
                delivered += min(batch.saleable_units, batch.ordered_units or batch.planned_units)
            delivered += batch.planned_surplus_customer_units
            if delivered:
                good.total_delivered_to_customers = max(Decimal("0"), Decimal(good.total_delivered_to_customers or 0) - delivered)
                good.save(update_fields=["total_produced", "total_delivered_to_customers"])
            else:
                good.save(update_fields=["total_produced"])
            batch.is_reversed = True
            batch.save(update_fields=["is_reversed", "updated_at"])
        txs = FinancialTransaction.objects.select_for_update().filter(business=order.business, reference=f"ORDER-{order.pk}", reversed=False)
        for tx in txs:
            reverse_type = FinancialTransaction.OUTFLOW if tx.transaction_type == FinancialTransaction.INCOME else FinancialTransaction.INCOME
            FinancialTransaction.objects.create(business=tx.business, created_by=request.user, date=today(), transaction_type=reverse_type, amount=tx.amount, category=f"Reversal: {tx.category}"[:80], description=f"Reversal of {tx.description}"[:255], payment_method=tx.payment_method, reference=f"REV-{tx.reference}"[:80], account=tx.account, reversal_of=tx)
            tx.reversed = True
            tx.save(update_fields=["reversed", "updated_at"])
        Sale.objects.filter(Q(linked_order=order) | Q(items__production_batch_id__in=batch_ids)).distinct().delete()
        order.status = "reversed"
        order.reversed_at = timezone.now()
        order.reversed_by = request.user
        order.reversed_reason = reason
        order.save(update_fields=["status", "reversed_at", "reversed_by", "reversed_reason", "updated_at"])
        audit(order.business, request.user, "reverse", order, f"Completed order #{order.pk} reversed", {"reason": reason})
    messages.success(request, "Order reversed. Raw materials and reversible stock/cash effects have been restored. The reversed order can now be deleted if you no longer need it.")
    return redirect("order_detail", pk=pk)


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status in ("pending", "rejected", "reversed"):
        if order.status == "reversed":
            deleted_id = order.pk
            reason = order.reversed_reason
            order.production_batches.all().delete()
            order.cost_snapshots.all().delete()
            audit(order.business, request.user, "delete", None, f"Reversed order #{deleted_id} permanently deleted", {"order_id": deleted_id, "reversal_reason": reason})
        order.delete()
        messages.success(request, "Removed.")
    else:
        messages.error(request, "Only pending, rejected, or already-reversed orders can be deleted.")
    return redirect("orders_list")

@login_required
def order_invoice(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__finished_good"), pk=pk)
    return production_order_pdf(order)
