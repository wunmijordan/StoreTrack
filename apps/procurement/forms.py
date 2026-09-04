from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem
from inventory.models import FinishedGood, RawMaterial
from core.models import CashAccount

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class PurchaseOrderForm(StyledModelForm):
    amount_paid = forms.DecimalField(
        max_digits=16,
        decimal_places=2,
        required=False,
        min_value=0,
        label="Amount paid now",
        help_text="For Partially Paid orders only. The remaining balance stays payable in Finance.",
    )

    class Meta:
        model = PurchaseOrder
        fields = ["date", "supplier", "payment_status", "payment_method", "account"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = CashAccount.objects.filter(active=True).order_by("name")
        self.fields["account"].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("payment_status")
        amount_paid = cleaned.get("amount_paid") or 0

        if status in ("paid", "partial") and not cleaned.get("account"):
            self.add_error("account", "Select the cash/bank account used for this payment.")

        if status == "partial" and not self.instance.pk and amount_paid <= 0:
            self.add_error("amount_paid", "Enter the amount paid now for a partially paid order.")
        elif status == "unpaid" and amount_paid > 0:
            self.add_error("amount_paid", "An unpaid order cannot have an initial payment. Choose Partially Paid instead.")

        return cleaned


class PurchaseOrderItemForm(StyledModelForm):
    item = forms.ChoiceField(label="Inventory item")

    class Meta:
        model = PurchaseOrderItem
        fields = ["item", "qty", "unit_cost"]

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        raw_materials = RawMaterial.objects.filter(business=business).order_by("name")
        # Direct procurement is intentionally limited to products without a
        # recipe/BOM. Mixed produced-and-purchased stock would need lot-level
        # source allocation to keep COGS defensible.
        products = FinishedGood.objects.filter(
            business=business,
            stock__isnull=False,
        )
        if business and business.uses_production:
            products = products.filter(
                recipe_items__isnull=True,
                production_materials__isnull=True,
            )
        products = products.distinct().order_by("name")
        material_choices = []

        # Same category order as the Dashboard stock movement dropdown.
        for value, label in RawMaterial.CATEGORY_CHOICES:
            items = raw_materials.filter(category=value)
            if items.exists():
                material_choices.append(
                    (
                        label,
                        [
                            (f"raw:{item.pk}", item.name)
                            for item in items
                        ],
                    )
                )
        product_group = (
            "Products for resale",
            [(f"finished:{product.pk}", product.name) for product in products],
        )
        groups = [product_group, *material_choices]
        if business and business.uses_production:
            groups = [*material_choices, product_group]
        self.fields["item"].choices = [("", "Select an inventory item…"), *groups]
        self.fields["qty"].min_value = Decimal("0.01")
        self.fields["unit_cost"].min_value = Decimal("0")
        if self.instance and self.instance.pk:
            kind, pk = self.instance.item_identity
            self.fields["item"].initial = f"{kind}:{pk}"

    def clean(self):
        cleaned = super().clean()
        value = cleaned.get("item") or ""
        try:
            kind, raw_pk = value.split(":", 1)
            pk = int(raw_pk)
        except (TypeError, ValueError):
            self.add_error("item", "Select a valid inventory item.")
            return cleaned

        if kind == "raw":
            selected = RawMaterial.objects.filter(business=self.business, pk=pk).first()
            if selected:
                self.instance.raw_material = selected
                self.instance.finished_good = None
        elif kind == "finished":
            selected = FinishedGood.objects.filter(
                business=self.business,
                pk=pk,
                stock__isnull=False,
            )
            if self.business and self.business.uses_production:
                selected = selected.filter(
                    recipe_items__isnull=True,
                    production_materials__isnull=True,
                )
            selected = selected.distinct().first()
            if selected:
                self.instance.raw_material = None
                self.instance.finished_good = selected
        else:
            selected = None
        if not selected:
            self.add_error("item", "Select an item belonging to the active business.")
        return cleaned


PurchaseOrderItemFormSet = inlineformset_factory(PurchaseOrder, PurchaseOrderItem, form=PurchaseOrderItemForm, extra=1, can_delete=True)
