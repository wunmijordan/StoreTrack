from django import forms
from .models import Business

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = [
            "name", "vertical", "currency_symbol", "background_color", "accent_color", "tagline",
            "restaurant_table_service",
        ]
        widgets = {
            "background_color": forms.TextInput(attrs={"type": "color"}),
            "accent_color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS
        self.fields["background_color"].label = "Navigation / background color"
        self.fields["accent_color"].label = "Button / action color"
        self.fields["restaurant_table_service"].widget.attrs["class"] = "h-4 w-4 accent-[#8f172d]"
