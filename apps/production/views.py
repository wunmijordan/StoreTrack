from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import get_random_string

from procurement.models import RawMaterialCostSnapshot

from .forms import OrderForm, OrderItemFormSet
from .models import Order, OrderItem, ProductionCostSnapshot, ProductionCostLine
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
    return {
        str(g.pk): {
            "physical_store": f"{g.selling_price_for('physical_store')}",
            "distribution": f"{g.selling_price_for('distribution')}",
            "online": f"{g.selling_price_for('online')}",
        }
        for g in FinishedGood.objects.all().prefetch_related("channel_prices")
    }


@login_required
def order_form(request, pk=None):
    obj = get_object_or_404(Order, pk=pk) if pk else None
    if obj and obj.status != "pending":
        messages.error(request, "Only pending orders can be edited.")
        return redirect("order_detail", pk=obj.pk)
    if request.method == "POST":
        form = OrderForm(request.POST, instance=obj)
        formset = OrderItemFormSet(request.POST, instance=obj if obj else Order())
        has_items = formset.is_valid() and any(
            f.cleaned_data and not f.cleaned_data.get("DELETE") for f in formset.forms
        )
        if form.is_valid() and formset.is_valid() and not has_items:
            messages.error(request, "Add at least one product.")
        elif form.is_valid() and has_items:
            order_type = form.cleaned_data.get("order_type")
            physical_transaction = form.cleaned_data.get("transaction_type")
            if order_type == "physical_store" and physical_transaction == "paid":
                unstocked = [
                    f.cleaned_data["finished_good"].name
                    for f in formset.forms
                    if f.cleaned_data and not f.cleaned_data.get("DELETE")
                    and f.cleaned_data.get("finished_good")
                    and (
                        f.cleaned_data["finished_good"].stock is None
                        or f.cleaned_data["finished_good"].reorder_level is None
                        or f.cleaned_data["finished_good"].reorder_level <= 0
                    )
                ]
                if unstocked:
                    form.add_error("transaction_type", "Paid physical-store restocks can only use products configured for physical-store stock (positive reorder level).")
                    return render(request, "production/order_form.html", {"form": form, "formset": formset, "prices": _price_map(), "obj": obj})
            order = form.save(commit=False)
            order.business = request.business
            if obj is None:
                order.created_by = request.user
            order.save()
            formset.instance = order
            items = formset.save(commit=False)
            for item in items:
                item.price = item.finished_good.selling_price_for(order.order_type)
                item.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            if obj is None and order.order_type in ("distribution", "online") and order.customer_payment_status == "paid":
                record_cash(
                    request.business, request.user, date=order.date, amount=order.total,
                    transaction_type=FinancialTransaction.INCOME, category="Customer order payment",
                    description=f"Payment received for order #{order.pk}", payment_method=order.customer_payment_method,
                    reference=f"ORDER-{order.pk}", account=order.customer_payment_account,
                )
            messages.success(request, "Order updated." if obj else "Order created — approve it from the Orders page when ready.")
            return redirect("order_detail", pk=order.pk)
    else:
        form = OrderForm(instance=obj, initial=None if obj else {"date": today(), "order_type": "distribution"})
        formset = OrderItemFormSet(instance=obj)
    prices = _price_map()
    return render(request, "production/order_form.html", {"form": form, "formset": formset, "prices": prices, "obj": obj})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    shortages = order.shortages() if order.status == "pending" else []
    return render(request, "production/order_detail.html", {"order": order, "shortages": shortages})


@login_required
def order_approve(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method != "POST" or order.status != "pending":
        return redirect("order_detail", pk=pk)
    force = request.POST.get("force") == "1"
    shortages = order.shortages()
    if shortages and not force:
        return render(request, "production/order_detail.html", {"order": order, "shortages": shortages, "confirm_approve": True})
    with transaction.atomic():
        materials = {}
        for mat, needed in order.material_requirements().values():
            materials[mat.id] = (mat, materials.get(mat.id, (mat, Decimal("0")))[1] + needed)
        for mat, needed in materials.values():
            material_cost, _ = _latest_material_cost(mat, order.date)
            record_raw_material_movement(
                mat, -needed, StockMovement.RAW_CONSUMPTION,
                note=f"Materials released for order #{order.pk}", reference=f"PROD-{order.pk}", unit_value=material_cost,
            )
        order.status = "approved"
        order.approved_date = today()
        order.save()
        audit(request.business, request.user, "approve", order, f"Order #{order.pk} approved")
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


def _create_production_cost_snapshot(order, item):
    good = item.finished_good
    production_date = order.completed_date or today()
    upb = good.units_per_batch or Decimal("1")
    links = list(good.recipe_items.select_related("raw_material")) + list(good.production_materials.select_related("raw_material"))
    piece_factor = item.piece_qty / upb
    total_batch_multiplier = item.batch_qty + piece_factor
    total_cost = Decimal("0")
    sources = set()
    snapshot = ProductionCostSnapshot.objects.create(
        business=order.business, order=order, order_item=item, finished_good=good,
        production_date=production_date, produced_units=item.total_units,
        batch_number=f"B{production_date.strftime('%Y%m%d')}-{order.pk}-{item.pk}",
    )
    for link in links:
        qty = link.qty_per_batch * total_batch_multiplier
        unit_cost, source = _latest_material_cost(link.raw_material, production_date)
        line_total = qty * unit_cost
        total_cost += line_total
        sources.add(source)
        ProductionCostLine.objects.create(
            snapshot=snapshot, raw_material=link.raw_material, quantity=qty,
            usage_unit_cost=unit_cost, total_cost=line_total, source=source,
        )
    snapshot.total_cost = total_cost
    snapshot.unit_cost = total_cost / item.total_units if item.total_units else Decimal("0")
    snapshot.cost_source = "latest_procurement" if sources == {"latest_procurement"} else "latest_procurement_with_legacy_fallback"
    snapshot.save(update_fields=["total_cost", "unit_cost", "cost_source"])
    return snapshot


@login_required
def order_complete(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if request.method != "POST" or order.status != "approved":
        return redirect("orders_list")

    with transaction.atomic():
        for item in order.items.select_related("finished_good"):
            good = item.finished_good

            # Freeze the production cost before any later procurement can change it.
            snapshot = _create_production_cost_snapshot(order, item)

            # Every completed order represents completed production.
            good.total_produced += item.total_units

            if order.order_type == "physical_store":
                if order.transaction_type == "paid":
                    # Paid physical-store orders are genuine shelf restocks and
                    # therefore require physical-store stock configuration.
                    record_finished_good_movement(
                        good, item.total_units, StockMovement.FG_PRODUCTION,
                        note=f"Production completed for order #{order.pk}", reference=f"PROD-{order.pk}",
                        affects_stock=True, unit_value=snapshot.unit_cost if snapshot else good.est_cost,
                    )
                else:
                    # Unpaid physical-store production is an intentional non-cash
                    # issue (staff/charity/service). It may use a product that is
                    # not configured for shelf stock, because the finished goods
                    # never become shelf inventory.
                    record_finished_good_movement(
                        good, item.total_units, StockMovement.FG_UNPAID_ISSUE,
                        note=f"Unpaid product issue: {order.unpaid_description}", reference=f"ISSUE-{order.pk}",
                        affects_stock=False, unit_value=snapshot.unit_cost if snapshot else good.est_cost,
                    )
                good.save(update_fields=["total_produced"])
            else:
                # Production happened, but the finished goods went directly to
                # the customer and never entered physical shelf stock.
                record_finished_good_movement(
                    good,
                    item.total_units,
                    StockMovement.FG_PRODUCTION,
                    note=f"Customer-order production completed for order #{order.pk}",
                    affects_stock=False,
                )
                good.total_delivered_to_customers += item.total_units
                good.save(update_fields=["total_produced", "total_delivered_to_customers"])

        order.status = "completed"
        order.completed_date = today()
        order.save()

        if order.order_type in ("distribution", "online"):
            from sales.models import Sale, SaleItem

            sale = Sale.objects.create(
                business=order.business,
                date=order.completed_date,
                customer=order.customer_name,
                payment_method=order.payment_method,
                transaction_type=(order.transaction_type if order.order_type == "physical_store" else ("paid" if order.customer_payment_status == "paid" else "unpaid")),
                unpaid_description=(order.unpaid_description if order.order_type == "physical_store" else ("" if order.customer_payment_status == "paid" else "Customer receivable — payment to be recorded through Finance.")),
                account=(order.account if order.order_type == "physical_store" else order.customer_payment_account),
                source=f"{order.order_type}_order",
                linked_order=order,
                created_by=request.user,
            )

            for item in order.items.all():
                snapshot = item.cost_snapshots.order_by("-id").first()
                SaleItem.objects.create(
                    sale=sale,
                    finished_good=item.finished_good,
                    batch_qty=item.batch_qty,
                    piece_qty=item.piece_qty,
                    discount=item.discount,
                    price=item.price,
                    unit_cost=snapshot.unit_cost if snapshot else None,
                )

            if sale.transaction_type == "paid" and order.order_type == "physical_store":
                record_cash(order.business, request.user, date=sale.date, amount=sale.total, transaction_type=FinancialTransaction.INCOME, category="Sales revenue", description=f"Sale #{sale.pk}", payment_method=sale.payment_method, reference=f"SALE-{sale.pk}", account=getattr(sale, "account", None))
            audit(order.business, request.user, "complete", order, f"Order #{order.pk} completed", {"transaction_type": order.transaction_type, "unpaid_reason": order.unpaid_description})

    if order.order_type in ("distribution", "online"):
        messages.success(
            request,
            "Order completed — added to the Sales list as fulfilled.",
        )
    else:
        messages.success(
            request,
            "Order completed — stock updated.",
        )

    return redirect("orders_list")


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status in ("pending", "rejected"):
        order.delete()
        messages.success(request, "Removed.")
    return redirect("orders_list")

@login_required
def order_invoice(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items__finished_good"), pk=pk)
    return production_order_pdf(order)
