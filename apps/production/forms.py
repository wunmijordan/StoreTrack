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
        fields = ["date", "requested_by", "finished_good", "qty", "needed_by", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


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
