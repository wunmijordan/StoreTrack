from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from .models import PurchaseOrder


def today():
    return timezone.localdate()


@login_required
def procurement_list(request):
    return render(request, "procurement/procurement_list.html", {
        "orders": PurchaseOrder.objects.prefetch_related("items__raw_material")
    })


@login_required
def po_form(request, pk=None):
    obj = get_object_or_404(PurchaseOrder, pk=pk) if pk else None
    if obj and obj.status == "received":
        messages.error(request, "This purchase order has already been received and can't be edited.")
        return redirect("procurement_list")
    if request.method == "POST":
        form = PurchaseOrderForm(request.POST, instance=obj)
        if form.is_valid():
            po = form.save(commit=False)
            po.business = request.business
            po.save()
            formset = PurchaseOrderItemFormSet(request.POST, instance=po)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Purchase order saved.")
                return redirect("procurement_list")
        else:
            formset = PurchaseOrderItemFormSet(request.POST, instance=obj if obj else PurchaseOrder())
    else:
        form = PurchaseOrderForm(instance=obj, initial=None if obj else {"date": today()})
        formset = PurchaseOrderItemFormSet(instance=obj)
    return render(request, "procurement/po_form.html", {"form": form, "formset": formset, "obj": obj})


@login_required
def po_receive(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST" and po.status != "received":
        with transaction.atomic():
            for item in po.items.select_related("raw_material"):
                mat = item.raw_material
                mat.stock = mat.stock + item.qty
                mat.cost_per_unit = item.unit_cost
                mat.save()
            po.status = "received"
            po.received_date = today()
            po.save()
        messages.success(request, "Stock received into inventory.")
    return redirect("procurement_list")


@login_required
def po_delete(request, pk):
    obj = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("procurement_list")
