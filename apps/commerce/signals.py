from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from .models import CommercePushSubscription


@receiver(user_logged_out)
def deactivate_push_subscriptions_on_logout(sender, request, user, **kwargs):
    """Stop background tenant alerts once a user explicitly signs out."""
    if user and getattr(user, "pk", None):
        CommercePushSubscription.objects.filter(user=user, active=True).update(active=False)
