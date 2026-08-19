from django import forms
from .models import ProductionRequest, ProductionOrder

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E4536]/30 focus:border-[#1E4536]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class ProductionRequestForm(StyledModelForm):
    class Meta:
        model = ProductionRequest
        fields = ["date", "requested_by", "linked_sale_item", "finished_good", "qty", "needed_by", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from sales.models import SaleItem
        linked_now = self.instance.linked_sale_item_id if self.instance and self.instance.pk else None
        eligible = SaleItem.objects.filter(
            sale__order_type="customer_order", sale__status="pending",
        ).exclude(production_requests__status__in=["pending", "in_production", "fulfilled"])
        if linked_now:
            # Keep the currently-linked item selectable when editing, even
            # though it now has this very request linked to it.
            eligible = eligible | SaleItem.objects.filter(pk=linked_now)
        self.fields["linked_sale_item"].queryset = eligible.select_related("sale", "finished_good")
        self.fields["linked_sale_item"].required = False
        self.fields["requested_by"].required = False
        # finished_good/qty are inherited from linked_sale_item when set —
        # enforced server-side in the view, not just hidden here.
        self.fields["finished_good"].required = False
        self.fields["qty"].required = False

    def clean(self):
        cleaned = super().clean()
        linked = cleaned.get("linked_sale_item")
        if linked:
            cleaned["finished_good"] = linked.finished_good
            cleaned["qty"] = linked.qty
        else:
            if not cleaned.get("finished_good"):
                self.add_error("finished_good", "Required unless linked to a customer order.")
            if not cleaned.get("qty"):
                self.add_error("qty", "Required unless linked to a customer order.")
        return cleaned


class ProductionOrderForm(StyledModelForm):
    class Meta:
        model = ProductionOrder
        fields = ["date", "order_type", "linked_request", "customer_name", "finished_good", "qty", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["linked_request"].queryset = ProductionRequest.objects.filter(status="pending")
        self.fields["linked_request"].required = False
        self.fields["customer_name"].required = False
        self.fields["finished_good"].required = False
        self.fields["qty"].required = False

    def clean(self):
        cleaned = super().clean()
        linked = cleaned.get("linked_request")
        if linked:
            cleaned["finished_good"] = linked.finished_good
            cleaned["qty"] = linked.qty
        else:
            if not cleaned.get("finished_good"):
                self.add_error("finished_good", "Required unless linked to a pending request.")
            if not cleaned.get("qty"):
                self.add_error("qty", "Required unless linked to a pending request.")
        return cleaned
