from django.urls import path
from . import views

urlpatterns = [
    path("", views.users_list, name="users_list"),
    path("add/", views.user_form, name="user_add"),
    path("<int:pk>/edit/", views.user_form, name="user_edit"),
    path("<int:pk>/permissions/", views.user_permissions, name="users_permissions"),
    path("roles/", views.roles_list, name="roles_list"),
    path("roles/add/", views.role_form, name="role_add"),
    path("roles/<int:pk>/edit/", views.role_form, name="role_edit"),
    path("roles/<int:pk>/permissions/", views.role_permissions, name="role_permissions"),
]
