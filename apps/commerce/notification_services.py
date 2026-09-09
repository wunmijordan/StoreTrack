import logging

from django.db import IntegrityError, transaction

from .models import CommerceNotification, CommerceSettings
from .realtime import publish_business_notifications_changed

logger = logging.getLogger(__name__)


def notify_commerce(*, business, event_type, title, message="", target_url="/commerce/", dedupe_key=""):
    """Record tenant activity without letting alerts interrupt commerce intake."""

    settings = CommerceSettings.raw_objects.filter(business=business).first()
    if settings and not settings.notifications_enabled:
        return None
    if settings and event_type in CommerceNotification.ORDER_EVENTS and not settings.notify_order_activity:
        return None
    if settings and event_type in CommerceNotification.PAYMENT_EVENTS and not settings.notify_payment_activity:
        return None

    values = {
        "business": business,
        "event_type": event_type,
        "title": str(title)[:160],
        "message": str(message)[:500],
        "target_url": str(target_url or "/commerce/")[:500],
        "dedupe_key": str(dedupe_key or "")[:180],
    }
    try:
        if values["dedupe_key"]:
            notice, created = CommerceNotification.raw_objects.get_or_create(
                business=business,
                dedupe_key=values["dedupe_key"],
                defaults={key: value for key, value in values.items() if key not in {"business", "dedupe_key"}},
            )
            if created:
                transaction.on_commit(
                    lambda: publish_business_notifications_changed(business.pk)
                )
            return notice
        notice = CommerceNotification.raw_objects.create(**values)
        transaction.on_commit(
            lambda: publish_business_notifications_changed(business.pk)
        )
        return notice
    except IntegrityError:
        # A concurrent callback may win the unique dedupe race.
        return CommerceNotification.raw_objects.filter(
            business=business, dedupe_key=values["dedupe_key"]
        ).first()


def queue_commerce_notification(**kwargs):
    """Create after the business transaction commits; notification failure is non-fatal."""

    def create_notice():
        try:
            notify_commerce(**kwargs)
        except Exception:
            logger.exception("Could not create commerce activity notification")

    transaction.on_commit(create_notice)
