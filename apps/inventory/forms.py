from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import inlineformset_factory
from .models import RawMaterial, FinishedGood, FinishedGoodChannelPrice, RecipeItem, ProductionMaterial

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class RawMaterialForm(StyledModelForm):
    """Stock and cost are entered here in the material's PURCHASE unit
    (e.g. '3 bags', 'cost 9000/bag') — the more natural way to count what's
    on hand and what it cost. Internally, RawMaterial.stock and
    .cost_per_unit are always stored in the fine USAGE unit (e.g. grams,
    spoons), because that's what recipes and every stock deduction are
    computed against. This form converts between the two on load and on
    save, via total_conversion_factor = package_qty x usage_conversion_factor."""

    package_qty = forms.DecimalField(
        max_digits=12, decimal_places=2, initial=1,
        label="Package quantity",
        help_text="How much is inside ONE purchase unit, e.g. 1 bag = 50 → 50.",
    )
    usage_conversion_factor = forms.DecimalField(
        max_digits=12, decimal_places=2, initial=1,
        label="Usage conversion",
        help_text="How many usage units in ONE package unit. Standard: kg→g is 1000. "
                   "Non-standard (spoon, cap…): count it yourself.",
    )
    reorder_level_purchase_units = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        initial=0,
        label="Reorder level (purchase units)",
        help_text="How many purchase units should trigger a reorder, e.g. 2 bags.",
    )
    stock_purchase_units = forms.DecimalField(
        label="Stock (in purchase units)", max_digits=14, decimal_places=2,
        required=False, initial=0,
        help_text="How many purchase units you currently have, e.g. 3 (bags).",
    )
    cost_per_purchase_unit = forms.DecimalField(
        label="Cost (per purchase unit)", max_digits=14, decimal_places=2,
        required=False, initial=0,
        help_text="What one purchase unit costs, e.g. price per bag.",
    )

    class Meta:
        model = RawMaterial
        # stock & cost_per_unit deliberately excluded — captured above in
        # purchase-unit terms and converted in save().
        fields = ["name", "category", "purchase_unit", "package_qty", "package_unit",
                  "usage_unit", "usage_conversion_factor", "reorder_level_purchase_units"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            factor = self.instance.total_conversion_factor or Decimal("1")
            # Quantize to exactly 2dp for display — plain division/multiplication
            # can produce long, ugly decimal expansions that don't match what
            # the 2dp fields will actually accept on resubmission. This does
            # NOT round to a whole purchase unit — fractional amounts like
            # 2.60 bags are shown and kept exactly, just cleaned to 2dp.
            self.fields["stock_purchase_units"].initial = (self.instance.stock / factor).quantize(Decimal("0.01"))
            self.fields["cost_per_purchase_unit"].initial = (self.instance.cost_per_unit * factor).quantize(Decimal("0.01"))
            self.fields["reorder_level_purchase_units"].initial = (self.instance.reorder_level / factor).quantize(Decimal("0.01"))

    def clean_package_qty(self):
        v = self.cleaned_data.get("package_qty")
        if v is not None and v <= 0:
            raise forms.ValidationError("Must be greater than zero.")
        return v

    def clean_usage_conversion_factor(self):
        v = self.cleaned_data.get("usage_conversion_factor")
        if v is not None and v <= 0:
            raise forms.ValidationError("Must be greater than zero.")
        return v

    def save(self, commit=True):
        instance = super().save(commit=False)
        package_qty = self.cleaned_data.get("package_qty") or Decimal("1")
        usage_conv = self.cleaned_data.get("usage_conversion_factor") or Decimal("1")
        factor = package_qty * usage_conv
        purchase_stock = self.cleaned_data.get("stock_purchase_units") or Decimal("0")
        purchase_cost = self.cleaned_data.get("cost_per_purchase_unit") or Decimal("0")
        purchase_reorder = (self.cleaned_data.get("reorder_level_purchase_units") or Decimal("0"))
        instance.stock = (purchase_stock * factor).quantize(Decimal("0.01"))
        instance.cost_per_unit = (purchase_cost / factor).quantize(Decimal("0.000001"))
        instance.reorder_level = (purchase_reorder * factor).quantize(Decimal("0.01"))
        if commit:
            instance.save()
        return instance


class FinishedGoodForm(StyledModelForm):
    class Meta:
        model = FinishedGood
        fields = ["name", "unit", "units_per_batch", "stock", "reorder_level", "selling_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].required = False
        self.fields["reorder_level"].required = False
        self.fields["selling_price"].required = False


class FinishedGoodChannelPriceForm(StyledModelForm):
    class Meta:
        model = FinishedGoodChannelPrice
        fields = ["channel", "price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price"].required = False


FinishedGoodChannelPriceFormSet = inlineformset_factory(
    FinishedGood, FinishedGoodChannelPrice, form=FinishedGoodChannelPriceForm, extra=3,
    can_delete=True, max_num=3, validate_max=True
)


class RecipeItemForm(StyledModelForm):
    class Meta:
        model = RecipeItem
        fields = ["raw_material", "qty_per_batch", "flexible_usage"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["raw_material"].queryset = RawMaterial.objects.filter(
            category=RawMaterial.CATEGORY_INGREDIENT
        )
        self.fields["flexible_usage"].widget.attrs["class"] = "h-4 w-4 rounded border-[#D9CFB4] text-[#8f172d]"


class ProductionMaterialForm(StyledModelForm):
    class Meta:
        model = ProductionMaterial
        fields = ["raw_material", "qty_per_batch"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Operational supplies (gloves, head nets, cleaning products, etc.)
        # are intentionally not attached to individual productions.
        self.fields["raw_material"].queryset = RawMaterial.objects.filter(
            category__in=[
                RawMaterial.CATEGORY_PACKAGING,
                RawMaterial.CATEGORY_PRODUCTION_SUPPLY,
            ]
        )


RecipeItemFormSet = inlineformset_factory(
    FinishedGood, RecipeItem, form=RecipeItemForm, extra=1, can_delete=True
)
ProductionMaterialFormSet = inlineformset_factory(
    FinishedGood, ProductionMaterial, form=ProductionMaterialForm, extra=1, can_delete=True
)
