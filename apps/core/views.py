import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Business
from .forms import BusinessForm
from inventory.models import RawMaterial, FinishedGood, RecipeItem
from procurement.models import PurchaseOrder, PurchaseOrderItem
from production.models import ProductionRequest, ProductionOrder
from sales.models import Sale, SaleItem


def today():
    return timezone.localdate()


@login_required
def dashboard(request):
    raw_materials = RawMaterial.objects.all()
    finished_goods = FinishedGood.objects.all()
    low_raw = [m for m in raw_materials if m.is_low]
    low_goods = [g for g in finished_goods if g.is_low]
    pending_requests = ProductionRequest.objects.filter(status="pending")
    planned_orders = ProductionOrder.objects.filter(status="planned")
    today_sales = Sale.objects.filter(date=today())
    today_revenue = sum((s.total for s in today_sales), Decimal("0"))
    return render(request, "core/dashboard.html", {
        "raw_count": raw_materials.count(),
        "goods_count": finished_goods.count(),
        "low_raw": low_raw,
        "low_goods": low_goods,
        "pending_requests": pending_requests,
        "planned_orders": planned_orders,
        "today_sales_count": today_sales.count(),
        "today_revenue": today_revenue,
    })


@login_required
def reports(request):
    biz = request.business
    if request.method == "POST":
        form = BusinessForm(request.POST, instance=biz)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated.")
    else:
        form = BusinessForm(instance=biz)
    return render(request, "core/reports.html", {"settings_form": form})


def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


@login_required
def export_stock_csv(request):
    rows = []
    for m in RawMaterial.objects.all():
        rows.append(["Raw material", m.name, m.unit, m.stock, m.reorder_level, m.cost_per_unit])
    for g in FinishedGood.objects.all():
        rows.append(["Finished good", g.name, g.unit, g.stock, g.reorder_level, g.selling_price])
    return _csv_response("stock-report.csv", ["Type", "Name", "Unit", "Stock", "Reorder level", "Cost/Price per unit"], rows)


@login_required
def export_procurement_csv(request):
    rows = []
    for p in PurchaseOrder.objects.prefetch_related("items__raw_material"):
        items = ", ".join(f"{i.raw_material.name} x{i.qty}" for i in p.items.all())
        rows.append([p.date, p.supplier, p.status, items, p.total])
    return _csv_response("procurement-report.csv", ["Date", "Supplier", "Status", "Items", "Total"], rows)


@login_required
def export_production_csv(request):
    rows = []
    for o in ProductionOrder.objects.filter(status="completed").select_related("finished_good"):
        rows.append([o.completed_date, o.order_type, o.finished_good.name, o.qty])
    return _csv_response("production-report.csv", ["Date", "Type", "Product", "Qty produced"], rows)


@login_required
def export_sales_csv(request):
    qs = Sale.objects.prefetch_related("items__finished_good")
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    rows = []
    for s in qs:
        items = ", ".join(f"{i.finished_good.name} x{i.qty}" for i in s.items.all())
        rows.append([s.date, s.customer, items, s.total, s.payment_method])
    return _csv_response("sales-report.csv", ["Date", "Customer", "Items", "Total", "Payment"], rows)


@login_required
def backup_json(request):
    models_to_dump = [Business, RawMaterial, FinishedGood, RecipeItem, PurchaseOrder, PurchaseOrderItem,
                       ProductionRequest, ProductionOrder, Sale, SaleItem]
    objects = []
    for model in models_to_dump:
        objects.extend(model.objects.all())
    data = serializers.serialize("json", objects, indent=2)
    response = HttpResponse(data, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="storetrack-backup-{today()}.json"'
    return response
