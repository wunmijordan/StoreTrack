import json
from uuid import UUID

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.services import user_has_permission

from .models import CommerceNotification, CommerceNotificationRead, CommerceSettings
from .realtime import publish_user_notifications_changed


def _authorized(request):
    return bool(
        request.user.is_authenticated
        and getattr(request, "business", None)
        and user_has_permission(request.user, request.business, "commerce", "view")
    )


def _unread(request):
    return CommerceNotification.raw_objects.filter(
        business=request.business
    ).exclude(reads__user=request.user)


@never_cache
@require_GET
def notification_feed(request):
    if not _authorized(request):
        return JsonResponse({"detail": "Commerce notification access is unavailable."}, status=403)
    settings = CommerceSettings.raw_objects.filter(business=request.business).first()
    enabled = settings.notifications_enabled if settings else True
    if not enabled:
        return JsonResponse({
            "enabled": False,
            "sound_enabled": False,
            "desktop_enabled": False,
            "poll_seconds": 8,
            "unread_count": 0,
            "notifications": [],
        })
    unread = _unread(request)
    rows = list(unread[:25])
    return JsonResponse({
        "enabled": True,
        "sound_enabled": settings.notification_sound_enabled if settings else True,
        "desktop_enabled": settings.notification_desktop_enabled if settings else True,
        "poll_seconds": 8,
        "unread_count": unread.count(),
        "notifications": [
            {
                "id": str(row.public_id),
                "event_type": row.event_type,
                "title": row.title,
                "message": row.message,
                "target_url": row.target_url,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    })


@never_cache
@require_POST
def notification_read(request):
    if not _authorized(request):
        return JsonResponse({"detail": "Commerce notification access is unavailable."}, status=403)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Submit valid JSON."}, status=400)

    unread = _unread(request)
    if payload.get("all") is True:
        notices = list(unread.only("pk"))
    else:
        try:
            public_ids = [UUID(str(value)) for value in payload.get("notification_ids", [])]
        except (TypeError, ValueError, AttributeError):
            return JsonResponse({"detail": "notification_ids must contain valid UUIDs."}, status=400)
        notices = list(unread.filter(public_id__in=public_ids).only("pk"))
    CommerceNotificationRead.objects.bulk_create(
        [CommerceNotificationRead(notification=notice, user=request.user) for notice in notices],
        ignore_conflicts=True,
    )
    publish_user_notifications_changed(request.business.pk, request.user.pk)
    return JsonResponse({"read": len(notices), "unread_count": _unread(request).count()})
