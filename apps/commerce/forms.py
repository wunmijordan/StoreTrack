from django import forms

from core.models import CashAccount
from inventory.models import FinishedGood
from .models import (
    CommerceIntegration,
    CommercePaymentConfiguration,
    CommerceSettings,
    StorefrontProduct,
)

CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class CommerceSettingsForm(forms.ModelForm):
    class Meta:
        model = CommerceSettings
        fields = ["enabled", "hosted_storefront_enabled", "order_now_link_enabled", "api_enabled", "connector_enabled", "insufficient_stock_policy", "public_note"]
        widgets = {"public_note": forms.Textarea(attrs={"rows": 2})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        labels = {
            "enabled": "Commerce master switch",
            "hosted_storefront_enabled": "Hosted storefront",
            "order_now_link_enabled": "Order Now link",
            "api_enabled": "Headless API",
            "connector_enabled": "Platform webhook / connector",
        }
        for name, f in self.fields.items():
            if name in labels: f.label = labels[name]
            if isinstance(f.widget, forms.CheckboxInput): f.widget.attrs["class"]="sr-only peer"
            else: f.widget.attrs["class"] = CLS


class StorefrontProductForm(forms.ModelForm):
    class Meta:
        model = StorefrontProduct
        fields = ["published", "public_name", "description", "image_url", "allow_stock_order", "allow_online_order", "allow_distribution_order", "allow_preorder", "min_quantity", "preorder_min_quantity", "distribution_min_quantity", "max_quantity", "preorder_lead_time"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
    def __init__(self,*args,business=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["allow_stock_order"].label = "Offer Physical Store / direct mode"
        self.fields["allow_online_order"].label = "Offer Online mode"
        self.fields["allow_distribution_order"].label = "Offer Distribution / bulk mode"
        self.fields["allow_preorder"].label = "Allow made-to-order production"
        self.fields["min_quantity"].label = "Physical Store / direct minimum"
        self.fields["preorder_min_quantity"].label = "Online minimum"
        self.fields["distribution_min_quantity"].label = "Distribution / bulk minimum"
        if business and not business.uses_production:
            self.fields.pop("allow_preorder")
            self.fields.pop("preorder_lead_time")
        for f in self.fields.values():
            if isinstance(f.widget, forms.CheckboxInput): f.widget.attrs["class"]="h-4 w-4 accent-[#8f172d]"
            else: f.widget.attrs["class"] = CLS


class CommerceIntegrationForm(forms.ModelForm):
    class Meta:
        model = CommerceIntegration
        fields = ["name", "integration_type", "allowed_origin", "active"]
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for f in self.fields.values():
            if isinstance(f.widget, forms.CheckboxInput): f.widget.attrs["class"]="h-4 w-4 accent-[#8f172d]"
            else: f.widget.attrs["class"] = CLS


class CommercePaymentConfigurationForm(forms.ModelForm):
    SECRET_FIELDS = ("paystack_secret_key", "monnify_api_key", "monnify_secret_key")

    class Meta:
        model = CommercePaymentConfiguration
        fields = [
            "currency",
            "paystack_enabled", "paystack_secret_key", "paystack_account",
            "monnify_enabled", "monnify_api_key", "monnify_secret_key",
            "monnify_contract_code", "monnify_base_url", "monnify_account",
            "bank_transfer_enabled", "bank_name", "bank_account_name",
            "bank_account_number", "bank_instructions", "bank_cash_account",
            "cash_enabled", "cash_instructions", "cash_account",
        ]
        widgets = {
            "paystack_secret_key": forms.PasswordInput(render_value=False),
            "monnify_api_key": forms.PasswordInput(render_value=False),
            "monnify_secret_key": forms.PasswordInput(render_value=False),
            "bank_instructions": forms.Textarea(attrs={"rows": 2}),
            "cash_instructions": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = CashAccount.raw_objects.filter(business=business, active=True).order_by("name")
        for name in ("paystack_account", "monnify_account", "bank_cash_account", "cash_account"):
            self.fields[name].queryset = accounts
            self.fields[name].required = False
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"
            else:
                field.widget.attrs["class"] = CLS
        for name in self.SECRET_FIELDS:
            self.fields[name].required = False
            if self.instance.pk and getattr(self.instance, name):
                self.fields[name].help_text = "A credential is saved. Leave blank to keep it unchanged."

    def clean_currency(self):
        value = (self.cleaned_data["currency"] or "").strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise forms.ValidationError("Use a three-letter currency code such as NGN.")
        return value

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            for name in self.SECRET_FIELDS:
                if not cleaned.get(name):
                    cleaned[name] = getattr(self.instance, name)
        if cleaned.get("paystack_enabled") and not cleaned.get("paystack_secret_key"):
            self.add_error("paystack_secret_key", "Add the Paystack secret key before enabling Paystack.")
        monnify_required = ("monnify_api_key", "monnify_secret_key", "monnify_contract_code")
        if cleaned.get("monnify_enabled"):
            for name in monnify_required:
                if not cleaned.get(name):
                    self.add_error(name, "This credential is required when Monnify is enabled.")
        if cleaned.get("bank_transfer_enabled"):
            for name in ("bank_name", "bank_account_name", "bank_account_number"):
                if not cleaned.get(name):
                    self.add_error(name, "This bank detail is required when bank transfer is enabled.")
        return cleaned
