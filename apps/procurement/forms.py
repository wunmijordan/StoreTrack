from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem
from inventory.models import RawMaterial

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class PurchaseOrderForm(StyledModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["date", "supplier"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


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
