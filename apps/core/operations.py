import logging
import secrets

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .jobs import run_all_jobs


logger = logging.getLogger(__name__)


@require_GET
def health(request):
    """Lightweight wake-up/readiness endpoint that intentionally avoids the DB."""
    return JsonResponse({"status": "ok", "service": "inprofic"})


@csrf_exempt
@require_POST
def run_jobs(request):
    """Run the shared scheduled-job registry using a bearer secret."""
    expected = settings.CRON_SECRET
    scheme, separator, supplied = request.headers.get("Authorization", "").partition(" ")
    authorized = (
        expected
        and separator
        and scheme.lower() == "bearer"
        and secrets.compare_digest(supplied.strip(), expected)
    )
    if not authorized:
        return JsonResponse({"detail": "Forbidden"}, status=403)

    try:
        completed = run_all_jobs()
    except Exception:
        logger.exception("Scheduled INPROFIC jobs failed")
        return JsonResponse({"status": "error"}, status=500)
    return JsonResponse({"status": "ok", "completed": completed})


@csrf_exempt
@require_POST
def dispatch_web_push(request):
    """Retry the durable Web Push outbox without running unrelated jobs."""
    expected = settings.CRON_SECRET
    scheme, separator, supplied = request.headers.get("Authorization", "").partition(" ")
    authorized = (
        expected and separator and scheme.lower() == "bearer"
        and secrets.compare_digest(supplied.strip(), expected)
    )
    if not authorized:
        return JsonResponse({"detail": "Forbidden"}, status=403)
    try:
        from commerce.webpush import dispatch_pending_pushes
        result = dispatch_pending_pushes(notice_limit=40, delivery_limit=20)
    except Exception:
        logger.exception("Commerce Web Push retry failed")
        return JsonResponse({"status": "error"}, status=500)
    return JsonResponse({"status": "ok", **result})
