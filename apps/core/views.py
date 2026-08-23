import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum

from .models import Business
from .forms import BusinessForm
from inventory.models import RawMaterial, FinishedGood, RecipeItem, StockMovement
from procurement.models import PurchaseOrder, PurchaseOrderItem
from production.models import Order, OrderItem
from sales.models import Sale, SaleItem


def today():
    return timezone.localdate()


def _production_units(queryset):
    total = Decimal("0")
    for o in queryset.prefetch_related("items__finished_good"):
        total += o.total_units
    return total


def _sales_revenue(queryset):
    total = Decimal("0")
    for s in queryset.prefetch_related("items__finished_good"):
        total += s.total
    return total


def _quarter_start(d):
    q_month = (d.month - 1) // 3 * 3 + 1
    return d.replace(month=q_month, day=1)


def _stock_periods(item):
    """
    Build the dashboard stock overview from StockMovement.

    Stock changes come only from movements where affects_stock=True.
    Production is calculated separately from ALL FG_PRODUCTION movements,
    including customer-order production where affects_stock=False.
    """
    t = today()

    periods = [
        ("Today", t),
        ("This week", t - timedelta(days=t.weekday())),
        ("This month", t.replace(day=1)),
        ("This quarter", _quarter_start(t)),
        ("This year", t.replace(month=1, day=1)),
    ]

    if isinstance(item, RawMaterial):
        movements = item.stock_movements.all()
        is_finished_good = False
    else:
        movements = item.stock_movements.all()
        is_finished_good = True

    closing = item.stock
    rows = []

    for label, start in periods:
        period_movements = movements.filter(
            occurred_at__date__gte=start,
            occurred_at__date__lte=t,
        )

        # Only movements that actually alter physical stock.
        stock_movements = period_movements.filter(
            affects_stock=True,
        )

        net = stock_movements.aggregate(
            total=Sum("quantity")
        )["total"] or Decimal("0")

        opening = closing - net

        production = Decimal("0")

        if is_finished_good:
            production = period_movements.filter(
                movement_type=StockMovement.FG_PRODUCTION,
            ).aggregate(
                total=Sum("quantity")
            )["total"] or Decimal("0")

        rows.append({
            "label": label,
            "opening": opening,
            "closing": closing,
            "net": net,
            "production": production,
        })

    return rows


@login_required
def dashboard(request):
    raw_materials = RawMaterial.objects.all()
    finished_goods = FinishedGood.objects.all()
    warning_raw = [m for m in raw_materials if m.is_warning]
    warning_goods = [g for g in finished_goods if g.is_warning]
    low_raw = [m for m in raw_materials if m.is_low]
    low_goods = [g for g in finished_goods if g.is_low]
    total_low_count = len(low_raw) + len(low_goods)
    total_warning_count = len(warning_raw) + len(warning_goods)
    pending_orders = Order.objects.filter(status="pending")
    today_sales = Sale.objects.filter(date=today())
    today_revenue = _sales_revenue(today_sales)

    completed_today = Order.objects.filter(status="completed", completed_date=today())
    daily_units_made = _production_units(completed_today)

    month_start = today().replace(day=1)
    year_start = today().replace(month=1, day=1)
    monthly_units = _production_units(Order.objects.filter(status="completed", completed_date__gte=month_start))
    yearly_units = _production_units(Order.objects.filter(status="completed", completed_date__gte=year_start))
    monthly_revenue = _sales_revenue(Sale.objects.filter(date__gte=month_start))
    yearly_revenue = _sales_revenue(Sale.objects.filter(date__gte=year_start))

    selected_key = request.GET.get("stock_item", "")
    selected_kind, _, selected_pk = selected_key.partition(":")
    selected_item = None
    stock_periods = None
    stock_unit = ""
    if selected_kind == "raw":
        selected_item = raw_materials.filter(pk=selected_pk).first()

        if selected_item:
            stock_periods = _stock_periods(selected_item)
            stock_unit = selected_item.usage_unit

    elif selected_kind == "fg":
        selected_item = finished_goods.filter(pk=selected_pk).first()

        if selected_item:
            stock_periods = _stock_periods(selected_item)
            stock_unit = selected_item.unit

    return render(request, "core/dashboard.html", {
        "raw_count": raw_materials.count(),
        "goods_count": finished_goods.count(),
        "warning_raw": warning_raw,
        "warning_goods": warning_goods,
        "low_raw": low_raw,
        "low_goods": low_goods,
        "total_low_count": total_low_count,
        "total_warning_count": total_warning_count,
        "pending_orders_count": pending_orders.count(),
        "today_sales_count": today_sales.count(),
        "today_revenue": today_revenue,
        "daily_units_made": daily_units_made,
        "monthly_units": monthly_units,
        "yearly_units": yearly_units,
        "monthly_revenue": monthly_revenue,
        "yearly_revenue": yearly_revenue,
        "all_raw_materials": raw_materials,
        "all_finished_goods": finished_goods,
        "selected_kind": selected_kind,
        "selected_pk": selected_pk,
        "selected_item": selected_item,
        "stock_periods": stock_periods,
        "stock_unit": stock_unit,
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
        rows.append(["Raw material", m.name, m.usage_unit, m.stock, m.reorder_level, m.cost_per_unit,
                      m.purchase_unit, m.total_conversion_factor])
    for g in FinishedGood.objects.all():
        rows.append(["Finished good", g.name, g.unit, g.stock, g.reorder_level, g.selling_price, "", ""])
    return _csv_response("stock-report.csv",
                          ["Type", "Name", "Stock Unit", "Stock", "Reorder level", "Cost/Price per unit",
                           "Purchase Unit", "Usage Units per Purchase Unit"],
                          rows)


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
    for o in Order.objects.filter(status="completed").prefetch_related("items__finished_good"):
        for item in o.items.all():
            rows.append([o.completed_date, o.get_order_type_display(), item.finished_good.name, item.total_units])
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
        items = ", ".join(f"{i.finished_good.name} x{i.total_units}" for i in s.items.all())
        rows.append([s.date, s.customer, items, s.total, s.payment_method, s.get_source_display()])
    return _csv_response("sales-report.csv", ["Date", "Customer", "Items", "Total", "Payment", "Source"], rows)


@login_required
def backup_json(request):
    models_to_dump = [Business, RawMaterial, FinishedGood, RecipeItem, PurchaseOrder, PurchaseOrderItem,
                       Order, OrderItem, Sale, SaleItem]
    objects = []
    for model in models_to_dump:
        objects.extend(model.objects.all())
    data = serializers.serialize("json", objects, indent=2)
    response = HttpResponse(data, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="storetrack-backup-{today()}.json"'
    return response