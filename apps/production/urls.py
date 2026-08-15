from django.urls import path
from . import views

urlpatterns = [
    path("requests/", views.requests_list, name="requests_list"),
    path("requests/add/", views.request_form, name="request_add"),
    path("requests/<int:pk>/edit/", views.request_form, name="request_edit"),
    path("requests/<int:pk>/cancel/", views.request_cancel, name="request_cancel"),
    path("requests/<int:pk>/delete/", views.request_delete, name="request_delete"),

    path("orders/", views.orders_list, name="orders_list"),
    path("orders/add/", views.order_form, name="order_add"),
    path("orders/<int:pk>/edit/", views.order_form, name="order_edit"),
    path("orders/<int:pk>/complete/", views.order_complete, name="order_complete"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/delete/", views.order_delete, name="order_delete"),
]
