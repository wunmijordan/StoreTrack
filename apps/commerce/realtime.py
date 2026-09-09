"""Small, transport-only helpers for tenant-safe commerce notification signals."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def business_notification_group(business_id):
    return f"commerce.notifications.business.{int(business_id)}"


def user_notification_group(business_id, user_id):
    return f"commerce.notifications.business.{int(business_id)}.user.{int(user_id)}"


def _publish(group, reason):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "notifications.changed", "reason": reason},
        )
    except Exception:
        # A real-time signal must never roll back the durable notification.
        logger.exception("Could not publish commerce notification signal")


def publish_business_notifications_changed(business_id, reason="created"):
    _publish(business_notification_group(business_id), reason)


def publish_user_notifications_changed(business_id, user_id, reason="read"):
    _publish(user_notification_group(business_id, user_id), reason)
