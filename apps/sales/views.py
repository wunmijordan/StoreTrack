from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SaleForm, SaleItemFormSet
from .models import Sale


def today():
    return timezone.localdate()


@login_required
def sales_list(request):
    sales = list(Sale.objects.prefetch_related("items__finished_good"))
    total_revenue = sum((s.total for s in sales), Decimal("0"))
    return render(request, "sales/sales_list.html", {"sales": sales, "total_revenue": total_revenue})


@login_required
def sale_form(request):
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
                qty = f.cleaned_data["qty"]
                if qty > good.stock:
                    shortages.append({"name": good.name, "needed": qty, "have": good.stock, "short": qty - good.stock})
            if shortages and not force:
                return render(request, "sales/sale_form.html", {"form": form, "formset": formset, "shortages": shortages})
            with transaction.atomic():
                sale = form.save(commit=False)
                sale.business = request.business
                sale.save()
                formset.instance = sale
                formset.save()
                for item in sale.items.select_related("finished_good"):
                    good = item.finished_good
                    good.stock = good.stock - item.qty
                    good.save()
            messages.success(request, "Sale recorded.")
            return redirect("sales_list")
    else:
        form = SaleForm(initial={"date": today(), "customer": "Walk-in"})
        formset = SaleItemFormSet(instance=Sale())
    return render(request, "sales/sale_form.html", {"form": form, "formset": formset})


@login_required
def sale_delete(request, pk):
    obj = get_object_or_404(Sale, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("sales_list")
