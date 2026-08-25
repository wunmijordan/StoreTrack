from django.urls import path
from . import views

urlpatterns = [
    path("", views.expenses_list, name="expenses_list"),
    path("add/", views.expense_form, name="expense_add"),
    path("<int:pk>/edit/", views.expense_form, name="expense_edit"),
    path("<int:pk>/delete/", views.expense_delete, name="expense_delete"),
]
