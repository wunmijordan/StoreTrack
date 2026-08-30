from django import forms
from django.forms import inlineformset_factory
from .models import Sale, SaleItem
from core.models import CashAccount

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class SaleForm(StyledModelForm):
    class Meta:
        model = Sale
        fields = ["date", "customer", "transaction_type", "unpaid_description", "payment_method", "account"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "unpaid_description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = CashAccount.objects.filter(active=True).order_by("name")
        self.fields["account"].required = False
        self.fields["transaction_type"].choices = [("paid", "Paid"), ("unpaid", "Unpaid")]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("transaction_type") == "unpaid" and not (cleaned.get("unpaid_description") or "").strip():
            self.add_error("unpaid_description", "Explain why this physical-store sale is unpaid.")
        if cleaned.get("transaction_type") == "paid" and not cleaned.get("account"):
            self.add_error("account", "Select the cash/bank account that received this payment.")
        return cleaned


class SaleItemForm(StyledModelForm):
    class Meta:
        model = SaleItem
        fields = ["finished_good", "batch_qty", "piece_qty", "discount"]


SaleItemFormSet = inlineformset_factory(Sale, SaleItem, form=SaleItemForm, extra=1, can_delete=True)