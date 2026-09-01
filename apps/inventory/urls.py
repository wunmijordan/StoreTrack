from django.urls import path
from . import views

urlpatterns = [
    path("", views.inventory, name="inventory"),
    path("raw-material/add/", views.raw_material_form, name="raw_material_add"),
    path("raw-material/export/pdf/", views.raw_material_inventory_pdf, name="raw_material_inventory_pdf"),
    path("raw-material/<int:pk>/edit/", views.raw_material_form, name="raw_material_edit"),
    path("raw-material/<int:pk>/delete/", views.raw_material_delete, name="raw_material_delete"),
    path("product/add/", views.finished_good_form, name="finished_good_add"),
    path("product/<int:pk>/edit/", views.finished_good_form, name="finished_good_edit"),
    path("product/<int:pk>/delete/", views.finished_good_delete, name="finished_good_delete"),
    path("stock-history/<str:kind>/<int:pk>/", views.stock_history, name="stock_history"),
    path("operational-supply/dispense/", views.operational_supply_dispense, name="operational_supply_dispense"),
]
