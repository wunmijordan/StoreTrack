from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import OrderForm, OrderItemFormSet
from .models import Order
from inventory.models import FinishedGood


def today():
    return timezone.localdate()


@login_required
def orders_list(request):
    orders = Order.objects.prefetch_related("items__finished_good")
    return render(request, "production/orders_list.html", {"orders": orders})


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
            order = form.save(commit=False)
            order.business = request.business
            if obj is None:
                order.created_by = request.user
            order.save()
            formset.instance = order
            items = formset.save(commit=False)
            for item in items:
                item.price = item.finished_good.selling_price
                item.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            messages.success(request, "Order updated." if obj else "Order created — approve it from the Orders page when ready.")
            return redirect("order_detail", pk=order.pk)
    else:
        form = OrderForm(instance=obj, initial=None if obj else {"date": today(), "order_type": "customer"})
        formset = OrderItemFormSet(instance=obj)
    prices = {str(g.pk): f"{g.selling_price}" for g in FinishedGood.objects.all()}
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
            mat.stock = mat.stock - needed
            mat.save()
        order.status = "approved"
        order.approved_date = today()
        order.save()
    messages.success(request, "Order approved — raw materials released for production.")
    return redirect("order_detail", pk=pk)


@login_required
def order_reject(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status == "pending":
        order.status = "rejected"
        order.save()
        messages.success(request, "Order rejected.")
    return redirect("orders_list")


@login_required
def order_complete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method != "POST" or order.status != "approved":
        return redirect("orders_list")
    with transaction.atomic():
        for item in order.items.select_related("finished_good"):
            good = item.finished_good
            good.total_produced = good.total_produced + item.total_units
            if order.order_type == "physical_store":
                good.stock = good.stock + item.total_units
            else:
                good.total_delivered_to_customers = good.total_delivered_to_customers + item.total_units
            good.save()
        order.status = "completed"
        order.completed_date = today()
        order.save()

        if order.order_type == "customer":
            from sales.models import Sale, SaleItem
            sale = Sale.objects.create(
                business=order.business, date=order.completed_date, customer=order.customer_name,
                payment_method=order.payment_method, source="customer_order", linked_order=order,
                created_by=request.user,
            )
            for item in order.items.all():
                SaleItem.objects.create(
                    sale=sale, finished_good=item.finished_good,
                    batch_qty=item.batch_qty, piece_qty=item.piece_qty,
                    discount=item.discount, price=item.price,
                )
    if order.order_type == "customer":
        messages.success(request, "Order completed — added to the Sales list as fulfilled.")
    else:
        messages.success(request, "Order completed — stock updated.")
    return redirect("orders_list")


@login_required
def order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == "POST" and order.status in ("pending", "rejected"):
        order.delete()
        messages.success(request, "Removed.")
    return redirect("orders_list")