import csv
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from openpyxl import Workbook

from .models import Business
from .forms import BusinessForm
from inventory.models import RawMaterial, FinishedGood, RecipeItem, ProductionMaterial, StockMovement
from procurement.models import PurchaseOrder, PurchaseOrderItem
from production.models import Order, OrderItem
from sales.models import Sale, SaleItem
from expenses.models import Expense


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


def _procurement_spend(start, end):
    """Cash/spend ledger for received purchase orders only.

    A PO becomes business spend when it is received into inventory. Draft and
    ordered-but-not-received POs remain commitments, not realised spend.
    """
    total = Decimal("0")
    qs = PurchaseOrder.objects.filter(status="received").filter(
        Q(received_date__range=(start, end)) |
        Q(received_date__isnull=True, date__range=(start, end))
    )
    for po in qs.prefetch_related("items"):
        total += po.total
    return total


def _expense_spend(start, end):
    return Expense.objects.filter(date__range=(start, end)).aggregate(total=Sum("amount"))["total"] or Decimal("0")


def _spend(start, end):
    return _procurement_spend(start, end) + _expense_spend(start, end)


def _quarter_start(d):
    q_month = (d.month - 1) // 3 * 3 + 1
    return d.replace(month=q_month, day=1)


def _financial_periods():
    t = today()
    quarter = _quarter_start(t)
    return [
        ("Weekly", t - timedelta(days=t.weekday()), t),
        ("Monthly", t.replace(day=1), t),
        ("Quarterly", quarter, t),
        ("Yearly", t.replace(month=1, day=1), t),
    ]


def _financial_snapshot():
    rows = []
    for label, start, end in _financial_periods():
        sales = _sales_revenue(Sale.objects.filter(date__range=(start, end)))
        procurement = _procurement_spend(start, end)
        misc = _expense_spend(start, end)
        spend = procurement + misc
        rows.append({
            "label": label,
            "sales": sales,
            "procurement": procurement,
            "misc": misc,
            "spend": spend,
            "revenue": sales - spend,
        })
    return rows


def _financial_chart_series():
    """Return dashboard chart data at useful resolutions for each period tab.

    Week/month use daily points; quarter uses weekly points; year uses monthly
    points. Spend is realised procurement plus miscellaneous expense, matching
    the financial cards and revenue calculation already shown on the dashboard.
    """
    t = today()
    week_start = t - timedelta(days=6)
    month_start = t.replace(day=1)
    quarter_start = _quarter_start(t)
    year_start = t.replace(month=1, day=1)

    def bucket(start, end, label):
        sales = _sales_revenue(
            Sale.objects.filter(date__gte=start, date__lte=end)
        )

        procurement = _procurement_spend(start, end)
        misc = _expense_spend(start, end)

        spend = procurement + misc
        revenue = sales - spend

        return {
            "label": str(label),
            "sales": float(sales or 0),
            "spend": float(spend or 0),
            "revenue": float(revenue or 0),
        }

    daily = []
    d = week_start
    while d <= t:
        daily.append(bucket(d, d, d.strftime("%a %d")))
        d += timedelta(days=1)

    month_daily = []
    d = month_start
    while d <= t:
        month_daily.append(bucket(d, d, d.strftime("%d %b")))
        d += timedelta(days=1)

    quarterly = []
    d = quarter_start
    while d <= t:
        end = min(d + timedelta(days=6), t)
        quarterly.append(bucket(d, end, f"{d.strftime('%d %b')}–{end.strftime('%d %b')}"))
        d = end + timedelta(days=1)

    yearly = []
    for month in range(1, t.month + 1):
        start = year_start.replace(month=month, day=1)
        if month == 12:
            next_start = year_start.replace(year=t.year + 1, month=1, day=1)
        else:
            next_start = year_start.replace(month=month + 1, day=1)
        end = min(next_start - timedelta(days=1), t)
        yearly.append(bucket(start, end, start.strftime("%b")))

    return {"week": daily, "month": month_daily, "quarter": quarterly, "year": yearly}

def _financial_chart_json():
    return _financial_chart_series()


def _sales_by_channel(start=None, end=None):
    qs = Sale.objects.all()
    if start and end:
        qs = qs.filter(date__range=(start, end))
    result = {"walkin": Decimal("0"), "distribution_order": Decimal("0"), "online_order": Decimal("0")}
    for sale in qs.prefetch_related("items__finished_good"):
        result[sale.source] = result.get(sale.source, Decimal("0")) + sale.total
    return result

def _channel_breakdown(channel, start, end):
    """Sales breakdown for a customer channel by region and customer group."""
    source = {"distribution": "distribution_order", "online": "online_order"}.get(channel)
    if not source:
        return []
    sales = Sale.objects.filter(source=source, date__range=(start, end)).select_related("linked_order").prefetch_related("items__finished_good")
    buckets = {}
    for sale in sales:
        order = sale.linked_order
        region = (order.customer_region if order and order.customer_region else "Unassigned region").strip()
        group = (order.customer_group if order and order.customer_group else "Unassigned group").strip()
        key = (region, group)
        buckets[key] = buckets.get(key, Decimal("0")) + sale.total
    return [{"region": k[0], "group": k[1], "sales": v} for k, v in sorted(buckets.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))]


def _stock_periods(item):
    """Build stock, procurement spend and purchase-price movement overview.

    For raw materials, each period's price comparison is:
        latest procurement occurring inside that period
        vs.
        the immediately preceding procurement overall.

    The preceding procurement may therefore be before the period.
    """
    t = today()
    periods = [
        ("Today", t),
        ("This week", t - timedelta(days=t.weekday())),
        ("This month", t.replace(day=1)),
        ("This quarter", _quarter_start(t)),
        ("This year", t.replace(month=1, day=1)),
    ]

    movements = item.stock_movements.all()
    is_finished_good = isinstance(item, FinishedGood)

    closing = item.stock
    rows = []

    if not is_finished_good:
        purchase_lines = list(
            PurchaseOrderItem.objects.filter(
                raw_material=item,
                purchase_order__status="received",
            ).select_related("purchase_order")
        )

        def procurement_date(line):
            po = line.purchase_order
            return po.received_date or po.date

        # Chronological procurement ledger.
        # pk is used as a deterministic tie-breaker when two lines have
        # the same procurement date.
        purchase_lines.sort(
            key=lambda line: (
                procurement_date(line),
                line.pk,
            )
        )

    else:
        purchase_lines = []

    for label, start in periods:
        period_movements = movements.filter(
            occurred_at__date__gte=start,
            occurred_at__date__lte=t,
        )

        stock_movements = period_movements.filter(affects_stock=True)

        net = (
            stock_movements.aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )

        opening = closing - net

        production = Decimal("0")

        if is_finished_good:
            production = (
                period_movements.filter(
                    movement_type=StockMovement.FG_PRODUCTION,
                ).aggregate(total=Sum("quantity"))["total"]
                or Decimal("0")
            )

        net_spend = Decimal("0")
        price_difference = None
        price_difference_pct = None
        latest_purchase_cost = None
        previous_purchase_cost = None
        latest_procurement = None
        previous_procurement = None

        if not is_finished_good:
            # All procurement lines occurring inside this period.
            period_lines = [
                line
                for line in purchase_lines
                if start <= procurement_date(line) <= t
            ]

            if period_lines:
                # Because purchase_lines is already chronological, the
                # last line is the latest procurement in this period.
                latest_line = period_lines[-1]
                latest_index = purchase_lines.index(latest_line)

                latest_procurement = latest_line
                latest_purchase_cost = (
                    latest_line.unit_cost or Decimal("0")
                )

                # The immediately preceding procurement overall.
                if latest_index > 0:
                    previous_line = purchase_lines[latest_index - 1]
                    previous_procurement = previous_line
                    previous_purchase_cost = (
                        previous_line.unit_cost or Decimal("0")
                    )

                    price_difference = (
                        latest_purchase_cost - previous_purchase_cost
                    )

                    if previous_purchase_cost != 0:
                        price_difference_pct = (
                            price_difference
                            / previous_purchase_cost
                            * Decimal("100")
                        )

            # Spend remains the total spend occurring inside this period.
            for line in period_lines:
                net_spend += line.line_total or Decimal("0")

        rows.append({
            "label": label,
            "opening": opening,
            "closing": closing,
            "net": net,
            "production": production,
            "net_spend": net_spend,

            # Latest procurement vs immediately previous procurement.
            "price_difference": price_difference,
            "price_difference_pct": price_difference_pct,

            # Useful if you later want to show the actual two costs.
            "latest_purchase_cost": latest_purchase_cost,
            "previous_purchase_cost": previous_purchase_cost,
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

    financial = _financial_snapshot()
    financial_json = _financial_chart_series()
    channel = _sales_by_channel(month_start, today())
    channel_breakdowns = {
        "distribution": _channel_breakdown(
            "distribution",
            month_start,
            today(),
        ),
        "online": _channel_breakdown(
            "online",
            month_start,
            today(),
        ),
    }

    raw_material_categories = []
    for value, label in RawMaterial.CATEGORY_CHOICES:
        items = raw_materials.filter(category=value)
        raw_material_categories.append({"value": value, "label": label, "items": items})

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
        "financial": financial,
        "financial_json": financial_json,
        "channel_sales": channel,
        "channel_breakdowns": channel_breakdowns,
        "all_raw_materials": raw_materials,
        "raw_material_categories": raw_material_categories,
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


def _xlsx_response(filename, sheet_name, header, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append(header)
    for row in rows:
        ws.append(list(row))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for column in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(max_len + 2, 10), 42)
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


def _stock_rows():
    rows = []
    for m in RawMaterial.objects.all():
        rows.append(["Raw material", m.name, m.get_category_display(), m.usage_unit, m.stock, m.reorder_level, m.cost_per_unit, m.purchase_unit, m.total_conversion_factor])
    for g in FinishedGood.objects.all():
        rows.append(["Finished good", g.name, "Finished good", g.unit, g.stock, g.reorder_level, g.selling_price, "", ""])
    return rows


def _procurement_rows():
    rows = []
    for p in PurchaseOrder.objects.prefetch_related("items__raw_material"):
        for i in p.items.all():
            rows.append([p.date, p.received_date, p.supplier, p.status, i.raw_material.name, i.raw_material.get_category_display(), i.qty, i.raw_material.purchase_unit, i.unit_cost, i.line_total])
    return rows


def _production_rows():
    rows = []
    for o in Order.objects.filter(status="completed").prefetch_related("items__finished_good"):
        for item in o.items.all():
            rows.append([o.completed_date, o.get_order_type_display(), o.customer_name, item.finished_good.name, item.total_units, item.line_total])
    return rows


def _sales_rows(qs=None):
    qs = qs or Sale.objects.all()
    rows = []
    for s in qs.prefetch_related("items__finished_good"):
        items = ", ".join(f"{i.finished_good.name} x{i.total_units}" for i in s.items.all())
        rows.append([s.date, s.customer, items, s.total, s.payment_method, s.get_source_display()])
    return rows


def _expense_rows():
    rows = []
    for e in Expense.objects.select_related("raw_material"):
        rows.append([e.date, e.get_category_display(), e.description, e.vendor, e.amount, e.notes])
    return rows


@login_required
def export_stock_csv(request):
    return _csv_response("stock-report.csv", ["Type", "Name", "Category", "Stock Unit", "Stock", "Reorder level", "Cost/Price per unit", "Purchase Unit", "Usage Units per Purchase Unit"], _stock_rows())


@login_required
def export_stock_xlsx(request):
    return _xlsx_response("stock-report.xlsx", "Stock", ["Type", "Name", "Category", "Stock Unit", "Stock", "Reorder level", "Cost/Price per unit", "Purchase Unit", "Usage Units per Purchase Unit"], _stock_rows())


@login_required
def export_procurement_csv(request):
    return _csv_response("procurement-report.csv", ["Date", "Received Date", "Supplier", "Status", "Item", "Category", "Qty", "Purchase Unit", "Unit Cost", "Line Total"], _procurement_rows())


@login_required
def export_procurement_xlsx(request):
    return _xlsx_response("procurement-report.xlsx", "Procurement", ["Date", "Received Date", "Supplier", "Status", "Item", "Category", "Qty", "Purchase Unit", "Unit Cost", "Line Total"], _procurement_rows())


@login_required
def export_production_csv(request):
    return _csv_response("production-report.csv", ["Date", "Type", "Customer", "Product", "Qty produced", "Order Value"], _production_rows())


@login_required
def export_production_xlsx(request):
    return _xlsx_response("production-report.xlsx", "Production", ["Date", "Type", "Customer", "Product", "Qty produced", "Order Value"], _production_rows())


@login_required
def export_sales_csv(request):
    qs = Sale.objects.all()
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return _csv_response("sales-report.csv", ["Date", "Customer", "Items", "Total", "Payment", "Source"], _sales_rows(qs))


@login_required
def export_sales_xlsx(request):
    qs = Sale.objects.all()
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return _xlsx_response("sales-report.xlsx", "Sales", ["Date", "Customer", "Items", "Total", "Payment", "Source"], _sales_rows(qs))


@login_required
def export_expenses_csv(request):
    return _csv_response("expenses-report.csv", ["Date", "Category", "Description", "Vendor", "Amount", "Notes"], _expense_rows())


@login_required
def export_expenses_xlsx(request):
    return _xlsx_response("expenses-report.xlsx", "Expenses", ["Date", "Category", "Description", "Vendor", "Amount", "Notes"], _expense_rows())


@login_required
def export_financial_csv(request):
    rows = [[r["label"], r["sales"], r["procurement"], r["misc"], r["spend"], r["revenue"]] for r in _financial_snapshot()]
    return _csv_response("financial-summary.csv", ["Period", "Sales", "Procurement Spend", "Misc Spend", "Total Spend", "Revenue"], rows)


@login_required
def export_financial_xlsx(request):
    rows = [[r["label"], r["sales"], r["procurement"], r["misc"], r["spend"], r["revenue"]] for r in _financial_snapshot()]
    return _xlsx_response("financial-summary.xlsx", "Financial Summary", ["Period", "Sales", "Procurement Spend", "Misc Spend", "Total Spend", "Revenue"], rows)


@login_required
def backup_json(request):
    models_to_dump = [Business, RawMaterial, FinishedGood, RecipeItem, ProductionMaterial, StockMovement,
                      PurchaseOrder, PurchaseOrderItem, Order, OrderItem, Sale, SaleItem, Expense]
    objects = []
    for model in models_to_dump:
        objects.extend(model.objects.all())
    data = serializers.serialize("json", objects, indent=2)
    response = HttpResponse(data, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="storetrack-backup-{today()}.json"'
    return response
