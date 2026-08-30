from django import forms
from core.models import CashAccount
from django.forms import inlineformset_factory
from .models import Order, OrderItem

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class OrderForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ["date", "order_type", "customer_name", "customer_region", "customer_group",
                  "customer_payment_status", "customer_payment_method", "customer_payment_account",
                  "transaction_type", "unpaid_description", "payment_method", "account", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_name"].required = False
        self.fields["payment_method"].required = False
        accounts = CashAccount.objects.filter(active=True).order_by("name")
        self.fields["account"].queryset = accounts
        self.fields["customer_payment_account"].queryset = accounts
        self.fields["customer_payment_account"].required = False
        self.fields["account"].required = False
        selected_type = (self.data.get("order_type") if self.data else None) or self.initial.get("order_type") or getattr(self.instance, "order_type", None)
        if selected_type in ("distribution", "online"):
            self.fields["transaction_type"].required = False
            self.fields["unpaid_description"].required = False
            self.fields["account"].required = False
            self.fields["customer_payment_status"].required = True
            self.fields["customer_payment_method"].required = True
        else:
            self.fields["customer_payment_status"].required = False
            self.fields["customer_payment_method"].required = False
            self.fields["customer_payment_account"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("order_type") in ("distribution", "online") and not cleaned.get("customer_name"):
            self.add_error("customer_name", "Required for distribution and online orders.")
        if cleaned.get("order_type") == "physical_store":
            if cleaned.get("transaction_type") == "unpaid" and not (cleaned.get("unpaid_description") or "").strip():
                self.add_error("unpaid_description", "Explain why this physical-store order is unpaid.")
            if cleaned.get("transaction_type") == "paid" and not cleaned.get("account"):
                self.add_error("account", "Select the cash/bank account that received this payment.")
        else:
            if cleaned.get("customer_payment_status") == "paid" and not cleaned.get("customer_payment_account"):
                self.add_error("customer_payment_account", "Select the account where the customer's payment was received.")
            cleaned["transaction_type"] = "paid" if cleaned.get("customer_payment_status") == "paid" else "unpaid"
            cleaned["unpaid_description"] = "" if cleaned.get("customer_payment_status") == "paid" else "Customer receivable — payment to be recorded through Finance."
            cleaned["account"] = cleaned.get("customer_payment_account") if cleaned.get("customer_payment_status") == "paid" else None
            cleaned["payment_method"] = cleaned.get("customer_payment_method") or "Transfer"
        return cleaned


class OrderItemForm(StyledModelForm):
    class Meta:
        model = OrderItem
        fields = ["finished_good", "batch_qty", "piece_qty", "discount"]


OrderItemFormSet = inlineformset_factory(Order, OrderItem, form=OrderItemForm, extra=1, can_delete=True)