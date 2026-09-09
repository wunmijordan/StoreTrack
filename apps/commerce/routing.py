from django.urls import path

from .consumers import CommerceNotificationConsumer


websocket_urlpatterns = [
    path(
        "ws/commerce/notifications/",
        CommerceNotificationConsumer.as_asgi(),
        name="commerce_notification_socket",
    ),
]
