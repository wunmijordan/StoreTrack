from django.urls import path
from . import views

urlpatterns = [
    path("", views.sales_list, name="sales_list"),
    path("add/", views.sale_form, name="sale_add"),
    path("<int:pk>/delete/", views.sale_delete, name="sale_delete"),
]
