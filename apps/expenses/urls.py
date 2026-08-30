from django.urls import path
from . import views

urlpatterns = [
    path("", views.expenses_list, name="expenses_list"),
    path("add/", views.expense_form, name="expense_add"),
    path("<int:pk>/edit/", views.expense_form, name="expense_edit"),
    path("<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("<int:pk>/invoice/", views.expense_invoice, name="expense_invoice"),
    path("payments/add/", views.expense_payment_form, name="expense_payment_add"),
]
