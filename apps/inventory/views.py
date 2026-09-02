from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate

from .forms import RawMaterialForm, FinishedGoodForm, FinishedGoodChannelPriceFormSet, RecipeItemFormSet, ProductionMaterialFormSet
from .models import RawMaterial, FinishedGood, StockMovement, OperationalSupplyDispense, InventoryLocation
from core.services import audit
from .services import default_location, record_raw_material_movement



@login_required
def operational_supply_dispense(request):
    from django import forms
    class DispenseForm(forms.ModelForm):
        class Meta:
            model = OperationalSupplyDispense
            fields = ["date", "raw_material", "quantity", "reason", "description", "location"]
            widgets = {"date": forms.DateInput(attrs={"type": "date"})}
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for field in self.fields.values():
                field.widget.attrs["class"] = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"
            self.fields["raw_material"].queryset = RawMaterial.objects.filter(
                category=RawMaterial.CATEGORY_OPERATIONAL_SUPPLY
            ).order_by("name")
            self.fields["location"].queryset = InventoryLocation.objects.filter(active=True).order_by("name")
        def clean_quantity(self):
            q = self.cleaned_data["quantity"]
            if q <= 0: raise forms.ValidationError("Quantity must be greater than zero.")
            return q
        def clean_description(self):
            value = self.cleaned_data["description"].strip()
            if not value: raise forms.ValidationError("Describe how or why the supply was dispensed.")
            return value
        def clean_raw_material(self):
            m = self.cleaned_data["raw_material"]
            if m.category != RawMaterial.CATEGORY_OPERATIONAL_SUPPLY:
                raise forms.ValidationError("Only operational supplies can be dispensed here.")
            return m

    form = DispenseForm(request.POST or None, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.business = request.business
            obj.created_by = request.user
            if obj.location_id is None:
                obj.location = default_location(request.business)
            if obj.quantity > obj.raw_material.stock:
                form.add_error("quantity", f"Only {obj.raw_material.stock} {obj.raw_material.usage_unit} is available.")
            else:
                obj.save()
                record_raw_material_movement(
                    obj.raw_material, -obj.quantity, StockMovement.OPERATIONAL_DISPENSE,
                    note=obj.description, reference=f"DISP-{obj.pk}",
                    location=obj.location,
                )
                audit(request.business, request.user, "create", obj, f"Operational supply {obj.raw_material.name} dispensed", {"quantity": str(obj.quantity), "reason": obj.reason})
                messages.success(request, "Operational supply dispensed and stock updated.")
                return redirect("inventory")
    return render(request, "inventory/operational_supply_dispense.html", {"form": form, "raw_material_units": {str(m.pk): m.usage_unit for m in RawMaterial.objects.filter(category=RawMaterial.CATEGORY_OPERATIONAL_SUPPLY)}})


@login_required
def inventory(request):
    return render(request, "inventory/inventory.html", {
        "raw_materials": RawMaterial.objects.all(),
        "finished_goods": FinishedGood.objects.prefetch_related(
            "production_batches__reconciliation_out",
            "recipe_items", "production_materials",
        ),
    })


@login_required
def raw_material_inventory_pdf(request):
    """Shareable procurement snapshot of current raw-material stock.

    Status uses the same model properties as the Inventory screen:
    low = stock <= reorder level; warning = <= 1.5x reorder level;
    sufficient = above the warning band.
    """
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    materials = list(RawMaterial.objects.all().order_by("name"))
    business = request.business
    accent = colors.HexColor("#8f172d")
    paper = landscape(A4)
    buffer = BytesIO()
    response = HttpResponse(content_type="application/pdf")
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in business.name).strip("_") or "business"
    response["Content-Disposition"] = f'attachment; filename="{safe_name}_raw_material_stock.pdf"'

    doc = SimpleDocTemplate(
        buffer, pagesize=paper, rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=13 * mm, bottomMargin=13 * mm,
        title=f"{business.name} - Raw Material Stock",
        author=business.name,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("StockTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=colors.white, spaceAfter=2)
    subtitle_style = ParagraphStyle("StockSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#F7E8EC"))
    section_style = ParagraphStyle("StockSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=accent)
    small = ParagraphStyle("StockSmall", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#57534E"))
    small_right = ParagraphStyle("StockSmallRight", parent=small, alignment=TA_RIGHT)
    cell = ParagraphStyle("StockCell", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=colors.HexColor("#292524"))
    cell_bold = ParagraphStyle("StockCellBold", parent=cell, fontName="Helvetica-Bold")

    low_count = sum(1 for m in materials if m.is_low)
    warning_count = sum(1 for m in materials if (not m.is_low and m.is_warning))
    sufficient_count = len(materials) - low_count - warning_count

    header = Table([[Paragraph(escape(str(business.name)), title_style)], [Paragraph("Raw Material Inventory - Procurement Stock Snapshot", subtitle_style)]], colWidths=[paper[0] - 26 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ]))

    summary_data = [[
        Paragraph(f"<b>{len(materials)}</b><br/><font size=7>Total materials</font>", cell),
        Paragraph(f"<b>{sufficient_count}</b><br/><font size=7>Sufficient</font>", cell),
        Paragraph(f"<b>{warning_count}</b><br/><font size=7>Warning</font>", cell),
        Paragraph(f"<b>{low_count}</b><br/><font size=7>Low / reorder</font>", cell),
        Paragraph(f"Generated: {timezone.localtime().strftime('%d %b %Y, %H:%M')}", small_right),
    ]]
    summary = Table(summary_data, colWidths=[35*mm, 35*mm, 35*mm, 35*mm, paper[0]-26*mm-140*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FFFDF8")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#E7DFCC")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E7DFCC")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))

    table_data = [[
        Paragraph("Material", cell_bold), Paragraph("Category", cell_bold),
        Paragraph("Current stock", cell_bold), Paragraph("Reorder threshold", cell_bold),
        Paragraph("Status", cell_bold),
    ]]
    row_statuses = []
    for m in materials:
        factor = m.total_conversion_factor or Decimal("1")
        purchase_unit = m.purchase_unit or m.usage_unit
        purchase_stock = (m.stock / factor) if factor else m.stock
        reorder_purchase = (m.reorder_level / factor) if factor else m.reorder_level
        if m.is_low:
            status = "LOW"
            bg = colors.HexColor("#FEE2E2")
            fg = colors.HexColor("#B91C1C")
        elif m.is_warning:
            status = "WARNING"
            bg = colors.HexColor("#FEF3C7")
            fg = colors.HexColor("#92400E")
        else:
            status = "SUFFICIENT"
            bg = colors.HexColor("#DCFCE7")
            fg = colors.HexColor("#166534")
        safe_purchase_unit = escape(str(purchase_unit))
        safe_usage_unit = escape(str(m.usage_unit))
        current = f"{purchase_stock:.3f} {safe_purchase_unit}"
        if purchase_unit != m.usage_unit or factor != 1:
            current += f"<br/><font size=7 color='#78716C'>{m.stock:.3f} {safe_usage_unit} total</font>"
        threshold = f"{reorder_purchase:.3f} {safe_purchase_unit}"
        if purchase_unit != m.usage_unit or factor != 1:
            threshold += f"<br/><font size=7 color='#78716C'>{m.reorder_level:.2f} {safe_usage_unit} total</font>"
        table_data.append([
            Paragraph(escape(str(m.name)), cell_bold),
            Paragraph(escape(str(m.get_category_display())), cell),
            Paragraph(current, cell),
            Paragraph(threshold, cell),
            Paragraph(f"<b>{status}</b>", ParagraphStyle(f"status{len(table_data)}", parent=cell, textColor=fg)),
        ])
        row_statuses.append(bg)

    stock_table = Table(table_data, repeatRows=1, colWidths=[65*mm, 46*mm, 55*mm, 55*mm, 35*mm])
    ts = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F0EAD9")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#57534E")),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#DED6C5")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]
    for idx, bg in enumerate(row_statuses, start=1):
        ts.append(("BACKGROUND", (0,idx), (-1,idx), bg))
    stock_table.setStyle(TableStyle(ts))

    legend = Table([[
        Paragraph("<b>Green - Sufficient</b>: stock is above 1.5x reorder threshold", small),
        Paragraph("<b>Amber - Warning</b>: stock is above reorder threshold but at/below 1.5x", small),
        Paragraph("<b>Red - Low</b>: stock is at/below reorder threshold", small),
    ]], colWidths=[(paper[0]-26*mm)/3]*3)
    legend.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), colors.HexColor("#F0FDF4")),
        ("BACKGROUND", (1,0), (1,0), colors.HexColor("#FFFBEB")),
        ("BACKGROUND", (2,0), (2,0), colors.HexColor("#FEF2F2")),
        ("BOX", (0,0), (-1,-1), 0.4, colors.HexColor("#E7DFCC")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#E7DFCC")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    story = [header, Spacer(1, 6*mm), summary, Spacer(1, 5*mm), Paragraph("Current stock against reorder thresholds", section_style), Spacer(1, 2*mm)]
    if materials:
        story.append(stock_table)
    else:
        story.append(Paragraph("No raw materials are configured yet.", cell))
    story += [Spacer(1, 5*mm), legend]
    doc.build(story)
    response.write(buffer.getvalue())
    buffer.close()
    return response


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
            audit(request.business, request.user, "create" if obj is None else "update", m, f"Raw material {m.name} saved")
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
            audit(request.business, request.user, "create" if obj is None else "update", good, f"Finished good {good.name} saved")
            messages.success(request, "Product saved.")
            return redirect("inventory")
    else:
        form = FinishedGoodForm(instance=obj)
        formset = RecipeItemFormSet(instance=obj, prefix="recipe_items")
        production_formset = ProductionMaterialFormSet(instance=obj, prefix="production_materials")
        channel_price_formset = FinishedGoodChannelPriceFormSet(instance=obj, prefix="channel_prices")
    raw_material_units = {
        str(material.pk): material.usage_unit
        for material in RawMaterial.objects.all()
    }
    return render(request, "inventory/finishedgood_form.html", {
        "form": form,
        "formset": formset,
        "production_formset": production_formset,
        "channel_price_formset": channel_price_formset,
        "obj": obj,
        "raw_material_units": raw_material_units,
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

    materials = []
    if is_finished_good:
        for recipe in item.recipe_items.select_related("raw_material").order_by("raw_material__name"):
            materials.append({
                "name": recipe.raw_material.name,
                "category": "Recipe ingredient",
                "qty_per_batch": str(recipe.qty_per_batch),
                "usage_unit": recipe.raw_material.usage_unit,
                "flexible": recipe.flexible_usage,
            })
        for production_input in item.production_materials.select_related("raw_material").order_by("raw_material__name"):
            materials.append({
                "name": production_input.raw_material.name,
                "category": production_input.raw_material.get_category_display(),
                "qty_per_batch": str(production_input.qty_per_batch),
                "usage_unit": production_input.raw_material.usage_unit,
                "flexible": False,
            })

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
        "materials": materials,
        "data": data,
    }

    return JsonResponse(response)