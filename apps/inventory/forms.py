from django import forms
from django.forms import inlineformset_factory
from .models import RawMaterial, FinishedGood, RecipeItem

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E4536]/30 focus:border-[#1E4536]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class RawMaterialForm(StyledModelForm):
    class Meta:
        model = RawMaterial
        fields = ["name", "unit", "stock", "reorder_level", "cost_per_unit"]


class FinishedGoodForm(StyledModelForm):
    class Meta:
        model = FinishedGood
        fields = ["name", "unit", "stock", "reorder_level", "selling_price"]


class RecipeItemForm(StyledModelForm):
    class Meta:
        model = RecipeItem
        fields = ["raw_material", "qty_per_unit"]


RecipeItemFormSet = inlineformset_factory(FinishedGood, RecipeItem, form=RecipeItemForm, extra=2, can_delete=True)
