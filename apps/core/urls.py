from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reports/", views.reports, name="reports"),
    path("reports/export/stock.csv", views.export_stock_csv, name="export_stock_csv"),
    path("reports/export/procurement.csv", views.export_procurement_csv, name="export_procurement_csv"),
    path("reports/export/production.csv", views.export_production_csv, name="export_production_csv"),
    path("reports/export/sales.csv", views.export_sales_csv, name="export_sales_csv"),
    path("reports/backup.json", views.backup_json, name="backup_json"),
]
