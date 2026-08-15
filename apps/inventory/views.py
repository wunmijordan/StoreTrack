from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RawMaterialForm, FinishedGoodForm, RecipeItemFormSet
from .models import RawMaterial, FinishedGood


@login_required
def inventory(request):
    return render(request, "inventory/inventory.html", {
        "raw_materials": RawMaterial.objects.all(),
        "finished_goods": FinishedGood.objects.all(),
    })


@login_required
def raw_material_form(request, pk=None):
    obj = get_object_or_404(RawMaterial, pk=pk) if pk else None
    if request.method == "POST":
        form = RawMaterialForm(request.POST, instance=obj)
        if form.is_valid():
            m = form.save(commit=False)
            m.business = request.business
            m.save()
            messages.success(request, "Raw material saved.")
            return redirect("inventory")
    else:
        form = RawMaterialForm(instance=obj)
    return render(request, "inventory/rawmaterial_form.html", {"form": form, "obj": obj})


@login_required
def raw_material_delete(request, pk):
    obj = get_object_or_404(RawMaterial, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("inventory")


@login_required
def finished_good_form(request, pk=None):
    obj = get_object_or_404(FinishedGood, pk=pk) if pk else None
    if request.method == "POST":
        form = FinishedGoodForm(request.POST, instance=obj)
        if form.is_valid():
            good = form.save(commit=False)
            good.business = request.business
            good.save()
            formset = RecipeItemFormSet(request.POST, instance=good)
            if formset.is_valid():
                formset.save()
                messages.success(request, "Product saved.")
                return redirect("inventory")
        else:
            formset = RecipeItemFormSet(request.POST, instance=obj if obj else FinishedGood())
    else:
        form = FinishedGoodForm(instance=obj)
        formset = RecipeItemFormSet(instance=obj)
    return render(request, "inventory/finishedgood_form.html", {"form": form, "formset": formset, "obj": obj})


@login_required
def finished_good_delete(request, pk):
    obj = get_object_or_404(FinishedGood, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Removed.")
    return redirect("inventory")
