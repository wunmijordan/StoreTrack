from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ExpenseForm
from .models import Expense


def today():
    return timezone.localdate()


@login_required
def expenses_list(request):
    expenses = Expense.objects.select_related("created_by")
    total = sum((e.amount for e in expenses), Decimal("0"))
    return render(request, "expenses/expenses_list.html", {"expenses": expenses, "total_expenses": total})


@login_required
def expense_form(request, pk=None):
    obj = get_object_or_404(Expense, pk=pk) if pk else None
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=obj)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.business = request.business
            if obj is None:
                expense.created_by = request.user
            expense.save()
            messages.success(request, "Expense saved.")
            return redirect("expenses_list")
    else:
        form = ExpenseForm(instance=obj, initial=None if obj else {"date": today()})
    return render(request, "expenses/expense_form.html", {"form": form, "obj": obj})


@login_required
def expense_delete(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Expense removed.")
    return redirect("expenses_list")
