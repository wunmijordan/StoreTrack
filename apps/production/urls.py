from django.urls import path
from . import views

urlpatterns = [
    path("orders/", views.orders_list, name="orders_list"),
    path("orders/add/", views.order_form, name="order_add"),
    path("orders/<int:pk>/edit/", views.order_form, name="order_edit"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/approve/", views.order_approve, name="order_approve"),
    path("orders/<int:pk>/reject/", views.order_reject, name="order_reject"),
    path("orders/<int:pk>/complete/", views.order_complete, name="order_complete"),
    path("orders/<int:pk>/delete/", views.order_delete, name="order_delete"),
]