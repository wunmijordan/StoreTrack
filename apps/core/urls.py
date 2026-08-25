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
    path("reports/export/stock.xlsx", views.export_stock_xlsx, name="export_stock_xlsx"),
    path("reports/export/procurement.xlsx", views.export_procurement_xlsx, name="export_procurement_xlsx"),
    path("reports/export/production.xlsx", views.export_production_xlsx, name="export_production_xlsx"),
    path("reports/export/sales.xlsx", views.export_sales_xlsx, name="export_sales_xlsx"),
    path("reports/export/expenses.csv", views.export_expenses_csv, name="export_expenses_csv"),
    path("reports/export/expenses.xlsx", views.export_expenses_xlsx, name="export_expenses_xlsx"),
    path("reports/export/financial.csv", views.export_financial_csv, name="export_financial_csv"),
    path("reports/export/financial.xlsx", views.export_financial_xlsx, name="export_financial_xlsx"),
]
