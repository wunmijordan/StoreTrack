from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BusinessSubscription
from accounts.subscription_services import apply_subscription_entitlements


class Command(BaseCommand):
    help = "Expire elapsed trials/paid subscriptions and refresh BusinessModuleAccess entitlements."

    def handle(self, *args, **options):
        changed = 0
        for subscription in BusinessSubscription.objects.select_related("plan").all():
            if not subscription.founder_lifetime and not subscription.is_effectively_active and subscription.status != BusinessSubscription.STATUS_EXPIRED:
                subscription.status = BusinessSubscription.STATUS_EXPIRED
                subscription.save(update_fields=["status"])
                changed += 1
            apply_subscription_entitlements(subscription)
        self.stdout.write(self.style.SUCCESS(f"Subscription entitlements synced; {changed} subscription(s) marked expired."))
