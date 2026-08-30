from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SaleForm, SaleItemFormSet
from .models import Sale
from inventory.models import FinishedGood
from production.models import ProductionCostSnapshot
from inventory.services import record_finished_good_movement
from inventory.models import StockMovement
from core.invoice import sale_invoice_pdf
from core.services import record_cash, audit
from core.models import FinancialTransaction


def today():
    return timezone.localdate()


@login_required
def sales_list(request):
    sales = list(Sale.objects.prefetch_related("items__finished_good"))
    total_revenue = sum((s.total for s in sales if s.transaction_type == "paid"), Decimal("0"))
    unpaid_value = sum((s.total for s in sales if s.transaction_type == "unpaid"), Decimal("0"))
    return render(request, "sales/sales_list.html", {"sales": sales, "total_revenue": total_revenue, "unpaid_value": unpaid_value})


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
                if good.stock is None:
                    shortages.append({"name": good.name, "unit": good.unit, "needed": total_units, "have": 0, "short": total_units, "message": "Not configured for physical-store stock."})
                elif total_units > good.stock:
                    shortages.append({"name": good.name, "unit": good.unit, "needed": total_units, "have": good.stock, "short": total_units - good.stock})
            if shortages and not force:
                prices = {str(g.pk): f"{g.selling_price_for('physical_store')}" for g in FinishedGood.objects.all().prefetch_related("channel_prices")}
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
                    item.price = item.finished_good.selling_price_for("physical_store")
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()
                for item in sale.items.select_related("finished_good"):
                    good = item.finished_good
                    latest_cost = ProductionCostSnapshot.objects.filter(
                        finished_good=good, production_date__lte=sale.date
                    ).order_by("-production_date", "-id").first()
                    item.unit_cost = latest_cost.unit_cost if latest_cost else None
                    item.save(update_fields=["unit_cost"])
                    record_finished_good_movement(
                        good,
                        -item.total_units,
                        StockMovement.FG_SALE,
                        note="Walk-in sale",
                        affects_stock=True,
                    )

                if sale.transaction_type == "paid":
                    record_cash(request.business, request.user, date=sale.date, amount=sale.total, transaction_type=FinancialTransaction.INCOME, category="Sales revenue", description=f"Sale #{sale.pk}", payment_method=sale.payment_method, reference=f"SALE-{sale.pk}", account=sale.account)
                audit(request.business, request.user, "create", sale, f"Sale #{sale.pk} recorded", {"transaction_type": sale.transaction_type, "unpaid_reason": sale.unpaid_description})
            messages.success(request, "Sale recorded.")
            return redirect("sales_list")
    else:
        form = SaleForm(initial={"date": today(), "customer": "Walk-in"})
        formset = SaleItemFormSet(instance=Sale())
    prices = {str(g.pk): f"{g.selling_price_for('physical_store')}" for g in FinishedGood.objects.all().prefetch_related("channel_prices")}
    return render(request, "sales/sale_form.html", {"form": form, "formset": formset, "prices": prices})


@login_required
def sale_delete(request, pk):
    obj = get_object_or_404(Sale, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("sales_list")

@login_required
def sale_invoice(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related("items__finished_good"), pk=pk)
    return sale_invoice_pdf(sale)
