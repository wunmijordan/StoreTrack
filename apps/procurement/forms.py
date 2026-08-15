from django import forms
from django.forms import inlineformset_factory
from .models import PurchaseOrder, PurchaseOrderItem

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E4536]/30 focus:border-[#1E4536]"


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


PurchaseOrderItemFormSet = inlineformset_factory(PurchaseOrder, PurchaseOrderItem, form=PurchaseOrderItemForm, extra=2, can_delete=True)
