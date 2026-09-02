from django.urls import path
from . import views

urlpatterns = [
    path("batches/", views.production_batches, name="production_batches"),
    path("batches/<int:pk>/", views.production_batch_detail, name="production_batch_detail"),
    path("batches/<int:pk>/quality-check/", views.production_batch_qc, name="production_batch_qc"),
    path("batches/<int:pk>/reconcile/", views.production_batch_reconcile, name="production_batch_reconcile"),
    path("orders/", views.orders_list, name="orders_list"),
    path("orders/add/", views.order_form, name="order_add"),
    path("orders/<int:pk>/edit/", views.order_form, name="order_edit"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/invoice/", views.order_invoice, name="order_invoice"),
    path("orders/<int:pk>/approve/", views.order_approve, name="order_approve"),
    path("orders/<int:pk>/reject/", views.order_reject, name="order_reject"),
    path("orders/<int:pk>/complete/", views.order_complete, name="order_complete"),
    path("orders/<int:pk>/reverse/", views.order_reverse, name="order_reverse"),
    path("orders/<int:pk>/delete/", views.order_delete, name="order_delete"),
]