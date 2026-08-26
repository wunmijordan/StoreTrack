from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate

from .forms import RawMaterialForm, FinishedGoodForm, FinishedGoodChannelPriceFormSet, RecipeItemFormSet, ProductionMaterialFormSet
from .models import RawMaterial, FinishedGood, StockMovement



@login_required
def inventory(request):
    return render(request, "inventory/inventory.html", {
        "raw_materials": RawMaterial.objects.all(),
        "finished_goods": FinishedGood.objects.all(),
    })


@login_required
def raw_material_form(request, pk=None):
    obj = get_object_or_404(RawMaterial, pk=pk) if pk else None
    if request.method == "POST":
        form = RawMaterialForm(request.POST, instance=obj)
        if form.is_valid():
            m = form.save(commit=False)
            m.business = request.business
            if obj is None:
                m.created_by = request.user
            m.save()
            messages.success(request, "Raw material saved.")
            return redirect("inventory")
    else:
        form = RawMaterialForm(instance=obj)
    return render(request, "inventory/rawmaterial_form.html", {"form": form, "obj": obj})


@login_required
def raw_material_delete(request, pk):
    obj = get_object_or_404(RawMaterial, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("inventory")


@login_required
def finished_good_form(request, pk=None):
    obj = get_object_or_404(FinishedGood, pk=pk) if pk else None
    if request.method == "POST":
        form = FinishedGoodForm(request.POST, instance=obj)
        formset = RecipeItemFormSet(request.POST, instance=obj if obj else FinishedGood(), prefix="recipe_items")
        production_formset = ProductionMaterialFormSet(request.POST, instance=obj if obj else FinishedGood(), prefix="production_materials")
        channel_price_formset = FinishedGoodChannelPriceFormSet(request.POST, instance=obj if obj else FinishedGood(), prefix="channel_prices")
        if form.is_valid() and formset.is_valid() and production_formset.is_valid() and channel_price_formset.is_valid():
            good = form.save(commit=False)
            good.business = request.business
            if obj is None:
                good.created_by = request.user
            good.save()
            formset.instance = good
            production_formset.instance = good
            channel_price_formset.instance = good
            formset.save()
            production_formset.save()
            channel_price_formset.save()
            messages.success(request, "Product saved.")
            return redirect("inventory")
    else:
        form = FinishedGoodForm(instance=obj)
        formset = RecipeItemFormSet(instance=obj, prefix="recipe_items")
        production_formset = ProductionMaterialFormSet(instance=obj, prefix="production_materials")
        channel_price_formset = FinishedGoodChannelPriceFormSet(instance=obj, prefix="channel_prices")
    return render(request, "inventory/finishedgood_form.html", {
        "form": form,
        "formset": formset,
        "production_formset": production_formset,
        "channel_price_formset": channel_price_formset,
        "obj": obj,
    })


@login_required
def finished_good_delete(request, pk):
    obj = get_object_or_404(FinishedGood, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("inventory")


@login_required
def stock_history(request, kind, pk):
    if kind == "raw":
        item = get_object_or_404(
            RawMaterial,
            pk=pk,
            business=request.business,
        )
        movements = item.stock_movements.all()
        factor = item.total_conversion_factor or Decimal("1")
        purchase_unit = item.purchase_unit or item.usage_unit
        usage_unit = item.usage_unit
        name = item.name

        # Raw materials do not have production.
        is_finished_good = False
        total_produced = None
        total_delivered = None

    elif kind == "finished":
        item = get_object_or_404(
            FinishedGood,
            pk=pk,
            business=request.business,
        )
        movements = item.stock_movements.all()
        factor = Decimal("1")
        purchase_unit = item.unit
        usage_unit = item.unit
        name = item.name

        is_finished_good = True
        total_produced = item.total_produced
        total_delivered = item.total_delivered_to_customers

    else:
        return JsonResponse(
            {"error": "Invalid stock history type."},
            status=400,
        )

    days = (
        movements
        .values("occurred_at__date")
        .annotate(
            inflow=Sum(
                "quantity",
                filter=Q(
                    affects_stock=True,
                    quantity__gt=0,
                ),
            ),
            outflow=Sum(
                "quantity",
                filter=Q(
                    affects_stock=True,
                    quantity__lt=0,
                ),
            ),
        )
    )

    # Only finished goods get production data.
    if is_finished_good:
        days = days.annotate(
            production=Sum(
                "quantity",
                filter=Q(
                    movement_type=StockMovement.FG_PRODUCTION,
                ),
            ),
            customer_production=Sum(
                "quantity",
                filter=Q(
                    movement_type=StockMovement.FG_PRODUCTION,
                    affects_stock=False,
                ),
            ),
        )
    else:
        days = days.annotate(
            production=Sum(
                "quantity",
                filter=Q(pk__isnull=True),
            ),
            customer_production=Sum(
                "quantity",
                filter=Q(pk__isnull=True),
            ),
        )

    days = days.order_by("occurred_at__date")

    data = []
    previous_closing = None

    for day in days:
        date = day["occurred_at__date"]

        day_movements = movements.filter(
            occurred_at__date=date,
            affects_stock=True,
        ).order_by("occurred_at")

        first_movement = day_movements.first()
        last_movement = day_movements.last()

        if first_movement:
            opening = first_movement.balance_after - first_movement.quantity
            closing = last_movement.balance_after
            previous_closing = closing
        else:
            # Production/customer-order movements that do not affect
            # physical stock do not change opening or closing stock.
            opening = (
                previous_closing
                if previous_closing is not None
                else item.stock
            )
            closing = opening

        row = {
            "date": date.isoformat(),
            "opening": str(opening),
            "inflow": str(day["inflow"] or Decimal("0")),
            "outflow": str(day["outflow"] or Decimal("0")),
            "closing": str(closing),
            "closing_purchase_units": str(
                (closing / factor).quantize(Decimal("0.01"))
            ),
        }

        if is_finished_good:
            row["production"] = str(
                day["production"] or Decimal("0")
            )
            row["customer_production"] = str(
                day["customer_production"] or Decimal("0")
            )

        data.append(row)

    response = {
        "kind": kind,
        "name": name,
        "purchase_unit": purchase_unit,
        "usage_unit": usage_unit,
        "factor": str(factor),
        "total_produced": (
            str(total_produced)
            if total_produced is not None
            else None
        ),
        "total_delivered_to_customers": (
            str(total_delivered)
            if total_delivered is not None
            else None
        ),
        "data": data,
    }

    return JsonResponse(response)