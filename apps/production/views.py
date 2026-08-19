from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ProductionRequestForm, ProductionOrderForm
from .models import ProductionRequest, ProductionOrder


def today():
    return timezone.localdate()


@login_required
def requests_list(request):
    return render(request, "production/requests_list.html", {
        "requests": ProductionRequest.objects.select_related("finished_good")
    })


@login_required
def request_form(request, pk=None):
    obj = get_object_or_404(ProductionRequest, pk=pk) if pk else None
    if obj and obj.status != "pending":
        messages.error(request, "Only pending requests can be edited.")
        return redirect("requests_list")
    if request.method == "POST":
        form = ProductionRequestForm(request.POST, instance=obj)
        if form.is_valid():
            r = form.save(commit=False)
            r.business = request.business
            if obj is None:
                r.created_by = request.user
            r.save()
            messages.success(request, "Production request saved.")
            return redirect("requests_list")
    else:
        form = ProductionRequestForm(instance=obj, initial=None if obj else {"date": today()})
    return render(request, "production/request_form.html", {"form": form, "obj": obj})


@login_required
def request_cancel(request, pk):
    obj = get_object_or_404(ProductionRequest, pk=pk)
    if request.method == "POST" and obj.status == "pending":
        obj.status = "cancelled"
        obj.save()
        messages.success(request, "Request cancelled.")
    return redirect("requests_list")


@login_required
def request_delete(request, pk):
    obj = get_object_or_404(ProductionRequest, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("requests_list")


@login_required
def orders_list(request):
    orders = list(ProductionOrder.objects.select_related("finished_good", "linked_request"))
    for o in orders:
        o.shortage_list = o.shortages() if o.status == "planned" else []
    return render(request, "production/orders_list.html", {"orders": orders})


@login_required
def order_form(request, pk=None):
    obj = get_object_or_404(ProductionOrder, pk=pk) if pk else None
    if obj and obj.status != "planned":
        messages.error(request, "Only planned orders can be edited.")
        return redirect("orders_list")
    if request.method == "POST":
        form = ProductionOrderForm(request.POST, instance=obj)
        if form.is_valid():
            order = form.save(commit=False)
            order.business = request.business
            is_new = order.pk is None
            if is_new:
                order.created_by = request.user
            order.save()
            if is_new and order.order_type == "internal" and order.linked_request:
                order.linked_request.status = "in_production"
                order.linked_request.save()
            messages.success(request, "Production order saved.")
            return redirect("orders_list")
    else:
        form = ProductionOrderForm(instance=obj, initial=None if obj else {"date": today(), "order_type": "internal"})
    return render(request, "production/order_form.html", {"form": form, "obj": obj})


@login_required
def order_complete(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method != "POST" or order.status != "planned":
        return redirect("orders_list")
    force = request.POST.get("force") == "1"
    shortages = order.shortages()
    if shortages and not force:
        return render(request, "production/order_confirm.html", {"order": order, "shortages": shortages})
    with transaction.atomic():
        batches = order.batches_needed
        units_produced = order.units_to_produce
        for ri in order.finished_good.recipe_items.select_related("raw_material"):
            mat = ri.raw_material
            mat.stock = mat.stock - (ri.qty_per_batch * batches)
            mat.save()

        good = order.finished_good
        sale_item = order.linked_request.linked_sale_item if order.linked_request else None
        delivered_qty = sale_item.qty if sale_item else None
        # Production adds units_produced to stock. If this order exists to
        # fulfil a specific customer order line, that exact quantity is
        # immediately handed over — only the batch-rounding surplus (if
        # any) stays as shelf stock. Net effect: raw materials always drop
        # by the full batch; finished stock only rises by what's left over.
        net_stock_change = units_produced - delivered_qty if delivered_qty is not None else units_produced
        good.stock = good.stock + net_stock_change
        good.save()

        order.status = "completed"
        order.completed_date = today()
        order.save()

        if order.linked_request:
            order.linked_request.status = "fulfilled"
            order.linked_request.save()
            if sale_item:
                sale_item.sale.refresh_fulfillment_status()

    if sale_item:
        messages.success(
            request,
            f"Production completed — {units_produced} {good.unit} made, "
            f"{delivered_qty} delivered to {sale_item.sale.customer}'s order"
            + (f", {units_produced - delivered_qty} extra to shelf stock." if units_produced > delivered_qty else "."),
        )
    else:
        messages.success(request, "Production completed — stock updated.")
    return redirect("orders_list")


@login_required
def order_cancel(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == "POST" and order.status == "planned":
        order.status = "cancelled"
        order.save()
        if order.linked_request:
            order.linked_request.status = "pending"
            order.linked_request.save()
        messages.success(request, "Production order cancelled.")
    return redirect("orders_list")


@login_required
def order_delete(request, pk):
    obj = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("orders_list")
