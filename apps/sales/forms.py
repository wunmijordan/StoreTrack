from django import forms
from django.forms import inlineformset_factory
from .models import Sale, SaleItem

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E4536]/30 focus:border-[#1E4536]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class SaleForm(StyledModelForm):
    class Meta:
        model = Sale
        fields = ["date", "customer", "payment_method"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class SaleItemForm(StyledModelForm):
    class Meta:
        model = SaleItem
        fields = ["finished_good", "qty", "price"]


SaleItemFormSet = inlineformset_factory(Sale, SaleItem, form=SaleItemForm, extra=2, can_delete=True)
