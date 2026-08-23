from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SaleForm, SaleItemFormSet
from .models import Sale
from inventory.models import FinishedGood
from inventory.services import record_finished_good_movement
from inventory.models import StockMovement


def today():
    return timezone.localdate()


@login_required
def sales_list(request):
    sales = list(Sale.objects.prefetch_related("items__finished_good"))
    total_revenue = sum((s.total for s in sales), Decimal("0"))
    return render(request, "sales/sales_list.html", {"sales": sales, "total_revenue": total_revenue})


@login_required
def sale_form(request):
    """Physical store stock only — immediate, deducts from existing shelf
    stock right away. For a customer order or a physical store restock
    (production needed first), use the Orders page instead."""
    if request.method == "POST":
        form = SaleForm(request.POST)
        formset = SaleItemFormSet(request.POST, instance=Sale())
        if form.is_valid() and formset.is_valid():
            force = request.POST.get("force") == "1"
            shortages = []
            for f in formset.forms:
                if not f.cleaned_data or f.cleaned_data.get("DELETE"):
                    continue
                good = f.cleaned_data["finished_good"]
                upb = good.units_per_batch or Decimal("1")
                total_units = (f.cleaned_data.get("batch_qty") or Decimal("0")) * upb + (f.cleaned_data.get("piece_qty") or Decimal("0"))
                if total_units > good.stock:
                    shortages.append({"name": good.name, "needed": total_units, "have": good.stock, "short": total_units - good.stock})
            if shortages and not force:
                prices = {str(g.pk): f"{g.selling_price}" for g in FinishedGood.objects.all()}
                return render(request, "sales/sale_form.html", {"form": form, "formset": formset, "shortages": shortages, "prices": prices})
            with transaction.atomic():
                sale = form.save(commit=False)
                sale.business = request.business
                sale.created_by = request.user
                sale.source = "walkin"
                sale.save()
                formset.instance = sale
                items = formset.save(commit=False)
                for item in items:
                    item.price = item.finished_good.selling_price
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()
                for item in sale.items.select_related("finished_good"):
                    good = item.finished_good
                    record_finished_good_movement(
                        good,
                        -item.total_units,
                        StockMovement.FG_SALE,
                        note="Walk-in sale",
                        affects_stock=True,
                    )
            messages.success(request, "Sale recorded.")
            return redirect("sales_list")
    else:
        form = SaleForm(initial={"date": today(), "customer": "Walk-in"})
        formset = SaleItemFormSet(instance=Sale())
    prices = {str(g.pk): f"{g.selling_price}" for g in FinishedGood.objects.all()}
    return render(request, "sales/sale_form.html", {"form": form, "formset": formset, "prices": prices})


@login_required
def sale_delete(request, pk):
    obj = get_object_or_404(Sale, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("sales_list")