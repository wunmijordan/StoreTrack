from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem
from inventory.models import RawMaterial
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
    class Meta:
        model = PurchaseOrderItem
        fields = ["raw_material", "qty", "unit_cost"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        raw_material_field = self.fields["raw_material"]

        # Keep the existing ModelChoiceField so validation and
        # instance handling continue to work normally.
        raw_materials = RawMaterial.objects.all().order_by("name")

        grouped_choices = []

        # Same category order as the Dashboard stock movement dropdown.
        for value, label in RawMaterial.CATEGORY_CHOICES:
            items = raw_materials.filter(category=value)

            if items.exists():
                grouped_choices.append(
                    (
                        label,
                        [
                            (str(item.pk), item.name)
                            for item in items
                        ],
                    )
                )

        # Preserve the normal empty option.
        raw_material_field.choices = [
            ("", "Select a Raw Material…"),
            *grouped_choices,
        ]


PurchaseOrderItemFormSet = inlineformset_factory(PurchaseOrder, PurchaseOrderItem, form=PurchaseOrderItemForm, extra=1, can_delete=True)
