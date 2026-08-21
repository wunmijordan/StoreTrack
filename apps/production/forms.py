from django import forms
from django.forms import inlineformset_factory
from .models import Order, OrderItem

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E4536]/30 focus:border-[#1E4536]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class OrderForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ["date", "order_type", "customer_name", "payment_method", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_name"].required = False
        self.fields["payment_method"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("order_type") == "customer" and not cleaned.get("customer_name"):
            self.add_error("customer_name", "Required for a customer order.")
        return cleaned


class OrderItemForm(StyledModelForm):
    class Meta:
        model = OrderItem
        fields = ["finished_good", "batch_qty", "piece_qty", "discount"]


OrderItemFormSet = inlineformset_factory(Order, OrderItem, form=OrderItemForm, extra=2, can_delete=True)