import time
from decimal import Decimal

from django.test import TestCase
from django.test import override_settings
from django.db import connection
from django.core.management import call_command
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import Business
from .models import (
    BusinessFeatureAccess, BusinessModuleAccess, BusinessSubscription, CustomUser,
    RoleModulePermission, SubscriptionPayment, SubscriptionPaymentSettings,
    SubscriptionPlanModule, SubscriptionService, UserBusiness,
)
from .services import business_has_module, seed_business_roles
from .subscription_services import (
    apply_subscription_entitlements,
    create_payment_request,
    ensure_default_plans,
    grant_founder_lifetime,
    mark_payment_paid,
    payment_amount,
    payment_is_locked,
)


class TenantSignupTests(TestCase):
    def test_public_home_is_marketing_and_authenticated_home_remembers_workspace(self):
        response = self.client.get(reverse("marketing_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "From stock to sale, in one place", html=False)
        self.assertContains(response, "Sign in")

    def test_marketing_plan_prices_include_thousands_separators(self):
        plans = ensure_default_plans()
        plan = plans["starter"]
        plan.monthly_price = Decimal("12345.67")
        plan.save(update_fields=["monthly_price"])

        response = self.client.get(reverse("marketing_home"))

        self.assertContains(response, "₦12,345.67")

    def test_signup_provisions_business_admin_and_starter_trial(self):
        response = self.client.post(reverse("signup"), {
            "business_name": "Plate & Pantry",
            "vertical": Business.VERTICAL_RESTAURANT,
            "fullname": "Ada Admin",
            "username": "ada.admin",
            "email": "ada@example.com",
            "phone": "",
            "password1": "Zx!92-long-safe-passphrase",
            "password2": "Zx!92-long-safe-passphrase",
        })

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        business = Business.objects.get(name="Plate & Pantry")
        user = CustomUser.objects.get(username="ada.admin")
        membership = UserBusiness.objects.get(user=user, business=business)
        self.assertEqual(business.vertical, Business.VERTICAL_RESTAURANT)
        self.assertEqual(membership.role.key, CustomUser.ROLE_BUSINESS_ADMIN)
        self.assertEqual(business.module_access.filter(enabled=True).count(), 6)
        subscription = BusinessSubscription.objects.get(primary_business=business)
        self.assertEqual(subscription.plan.code, "starter")
        self.assertEqual(subscription.status, BusinessSubscription.STATUS_TRIAL)
        self.assertFalse(business.module_access.get(module="commerce").enabled)
        self.assertEqual(self.client.session["active_business_id"], business.pk)

    def test_signup_uses_a_unique_business_slug(self):
        Business.objects.create(name="Plate and Pantry", slug="plate-and-pantry")
        self.client.post(reverse("signup"), {
            "business_name": "Plate and Pantry",
            "vertical": Business.VERTICAL_GENERAL,
            "fullname": "Second Admin",
            "username": "second.admin",
            "email": "second@example.com",
            "password1": "Zx!92-long-safe-passphrase",
            "password2": "Zx!92-long-safe-passphrase",
        })
        self.assertTrue(Business.objects.filter(slug="plate-and-pantry-2").exists())


class TenantRoutingTests(TestCase):
    def setUp(self):
        self.alpha = Business.objects.create(name="Alpha", slug="alpha")
        self.beta = Business.objects.create(name="Beta", slug="beta")
        alpha_roles = seed_business_roles(self.alpha)
        beta_roles = seed_business_roles(self.beta)
        self.user = CustomUser.objects.create_user(
            username="tenant.user", password="safe-password-123", fullname="Tenant User"
        )
        UserBusiness.objects.create(
            user=self.user, business=self.alpha,
            role=alpha_roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        UserBusiness.objects.create(
            user=self.user, business=self.beta,
            role=beta_roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        self.client.force_login(self.user)

    def test_first_active_membership_is_selected_then_can_be_switched(self):
        response = self.client.get(reverse("business_settings"))
        self.assertEqual(response.context["biz"], self.alpha)

        response = self.client.post(reverse("switch_business"), {
            "business_id": self.beta.pk,
            "next": reverse("business_settings"),
        })
        self.assertRedirects(response, reverse("business_settings"), fetch_redirect_response=False)
        response = self.client.get(reverse("business_settings"))
        self.assertEqual(response.context["biz"], self.beta)

    def test_authenticated_root_continues_to_dashboard(self):
        response = self.client.get(reverse("marketing_home"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_authenticated_user_can_open_marketing_page_from_navigation(self):
        response = self.client.get(f'{reverse("marketing_home")}?view=marketing')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Go to your workspace")

    @override_settings(AUTHENTICATED_IDLE_TIMEOUT_SECONDS=60)
    def test_idle_authenticated_root_requires_sign_in_instead_of_showing_marketing(self):
        session = self.client.session
        session["storetrack_last_activity"] = int(time.time()) - 120
        session.save()
        response = self.client.get(reverse("marketing_home"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard')}",
            fetch_redirect_response=False,
        )

    def test_user_cannot_switch_to_business_without_membership(self):
        outsider = Business.objects.create(name="Outsider", slug="outsider")
        response = self.client.post(reverse("switch_business"), {"business_id": outsider.pk})
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(self.client.session.get("active_business_id"), outsider.pk)

    def test_business_admin_cannot_edit_another_tenants_user_by_id(self):
        outsider = Business.objects.create(name="Outsider", slug="outsider")
        outsider_roles = seed_business_roles(outsider)
        outsider_user = CustomUser.objects.create_user(
            username="outside.user", password="safe-password-123", fullname="Outside User"
        )
        UserBusiness.objects.create(
            user=outsider_user, business=outsider,
            role=outsider_roles[CustomUser.ROLE_MANAGER],
        )
        response = self.client.get(reverse("user_edit", args=[outsider_user.pk]))
        self.assertEqual(response.status_code, 404)

    def test_switch_rejects_external_next_url(self):
        response = self.client.post(reverse("switch_business"), {
            "business_id": self.beta.pk,
            "next": "https://example.invalid/phishing",
        })
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_recent_activity_does_not_rewrite_database_session(self):
        session = self.client.session
        session["active_business_id"] = self.alpha.pk
        session["storetrack_last_activity"] = int(time.time())
        session.save()

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        session_updates = [
            query["sql"] for query in queries
            if "UPDATE" in query["sql"].upper() and "DJANGO_SESSION" in query["sql"].upper()
        ]
        self.assertEqual(session_updates, [])

    def test_navigation_permissions_use_a_bounded_number_of_queries(self):
        session = self.client.session
        session["active_business_id"] = self.alpha.pk
        session["storetrack_last_activity"] = int(time.time())
        session.save()

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 14)

    def test_empty_dashboard_avoids_per_chart_point_queries(self):
        session = self.client.session
        session["active_business_id"] = self.alpha.pk
        session["storetrack_last_activity"] = int(time.time())
        session.save()

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 85)


class BusinessSettingsAccessTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Bakery", slug="bakery")
        roles = seed_business_roles(self.business)
        self.admin = CustomUser.objects.create_user(
            username="admin", password="safe-password-123", fullname="Business Admin"
        )
        self.manager = CustomUser.objects.create_user(
            username="manager", password="safe-password-123", fullname="Manager"
        )
        UserBusiness.objects.create(
            user=self.admin, business=self.business,
            role=roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        UserBusiness.objects.create(
            user=self.manager, business=self.business,
            role=roles[CustomUser.ROLE_MANAGER],
        )

    def test_business_admin_can_update_preferences_without_changing_slug(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("business_settings"), {
            "name": "New Name",
            "slug": "bakery",
            "vertical": Business.VERTICAL_RESTAURANT,
            "currency_symbol": "$",
            "background_color": "#173B45",
            "accent_color": "#126E82",
            "tagline": "Kitchen control",
            "restaurant_table_service": "on",
        })
        self.assertRedirects(response, reverse("business_settings"), fetch_redirect_response=False)
        self.business.refresh_from_db()
        self.assertEqual(self.business.name, "New Name")
        self.assertEqual(self.business.slug, "bakery")
        self.assertEqual(self.business.accent_color, "#126E82")
        self.assertEqual(self.business.background_color, "#173B45")
        self.assertEqual(self.business.vertical, Business.VERTICAL_RESTAURANT)

    def test_business_admin_can_choose_a_custom_public_slug(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("business_settings"), {
            "name": self.business.name,
            "slug": "theoven",
            "vertical": self.business.vertical,
            "currency_symbol": self.business.currency_symbol,
            "background_color": self.business.background_color,
            "accent_color": self.business.accent_color,
            "tagline": self.business.tagline,
            "restaurant_table_service": "on",
        })
        self.assertRedirects(response, reverse("business_settings"), fetch_redirect_response=False)
        self.business.refresh_from_db()
        self.assertEqual(self.business.slug, "theoven")

    def test_non_admin_cannot_open_business_preferences(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("business_settings")).status_code, 403)

    def test_business_module_entitlement_overrides_role_permission(self):
        BusinessModuleAccess.objects.create(
            business=self.business, module="dashboard", enabled=False,
            source=BusinessModuleAccess.SOURCE_PLAN,
        )
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("business_settings")).status_code, 200)

    def test_user_without_membership_cannot_reach_tenant_data(self):
        user = CustomUser.objects.create_user(
            username="orphan", password="safe-password-123", fullname="Orphan User"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "No active business access", status_code=403)


class SubscriptionEntitlementTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.timezone = timezone
        self.business = Business.objects.create(name="Plan Bakery", slug="plan-bakery")
        self.plans = ensure_default_plans()

    def _subscribe(self, code):
        plan = self.plans[code]
        subscription = BusinessSubscription.objects.create(
            primary_business=self.business, plan=plan, status=BusinessSubscription.STATUS_TRIAL,
            trial_ends_at=self.timezone.now() + self.timezone.timedelta(days=30),
        )
        SubscriptionService.objects.create(subscription=subscription, business=self.business, is_primary=True)
        apply_subscription_entitlements(subscription)
        return subscription

    def test_starter_matrix_keeps_commerce_production_and_finance_disabled(self):
        subscription = self._subscribe("starter")
        self.assertTrue(business_has_module(self.business, "inventory"))
        self.assertTrue(business_has_module(self.business, "sales"))
        self.assertFalse(business_has_module(self.business, "procurement"))
        self.assertFalse(business_has_module(self.business, "production"))
        self.assertFalse(business_has_module(self.business, "finance"))
        self.assertFalse(business_has_module(self.business, "commerce"))
        self.assertFalse(BusinessFeatureAccess.objects.get(business=self.business, feature="reports_full").enabled)
        self.assertEqual(subscription.plan.code, "starter")

    def test_business_pro_enables_commerce(self):
        self._subscribe("business_pro")
        self.assertTrue(business_has_module(self.business, "commerce"))

    def test_expired_subscription_keeps_only_dashboard_module_recovery(self):
        subscription = self._subscribe("production")
        subscription.trial_ends_at = self.timezone.now() - self.timezone.timedelta(seconds=1)
        subscription.save(update_fields=["trial_ends_at"])
        apply_subscription_entitlements(subscription)
        self.assertTrue(business_has_module(self.business, "dashboard"))
        self.assertFalse(business_has_module(self.business, "users"))
        self.assertFalse(business_has_module(self.business, "inventory"))

    def test_yearly_price_applies_founder_configured_discount_to_services(self):
        plan = self.plans["business_pro"]
        plan.monthly_price = 1000
        plan.yearly_discount_percent = 10
        plan.additional_service_discount_percent = 25
        plan.save()
        # Primary 1000 + additional service 750 = 1750/month; yearly at 10% off = 18,900.
        self.assertEqual(payment_amount(plan, 2, 12, billing_cycle=SubscriptionPayment.CYCLE_YEARLY), 18900)

    def test_trial_label_identifies_trial_and_date(self):
        subscription = self._subscribe("starter")
        self.assertIn("Trial", subscription.trial_status_label)
        self.assertIn(str(subscription.trial_ends_at.year), subscription.trial_status_label)

    def test_current_trial_plan_payment_stays_locked_until_final_seven_days(self):
        from django.core.exceptions import ValidationError

        subscription = self._subscribe("starter")
        self.plans["starter"].monthly_price = 1000
        self.plans["starter"].save(update_fields=["monthly_price"])
        self.assertTrue(payment_is_locked(subscription, self.plans["starter"]))
        with self.assertRaisesMessage(ValidationError, "opens within 7 days"):
            create_payment_request(subscription, self.plans["starter"], provider="paystack")

        subscription.trial_ends_at = self.timezone.now() + self.timezone.timedelta(days=6, hours=12)
        subscription.save(update_fields=["trial_ends_at"])
        self.assertFalse(payment_is_locked(subscription, self.plans["starter"]))

    def test_founder_plan_is_locked_but_other_plan_remains_open(self):
        founder = CustomUser.objects.create_superuser(username="grant-founder", password="safe-password-123")
        subscription = self._subscribe("starter")
        grant_founder_lifetime(subscription, self.plans["starter"], founder)
        subscription.refresh_from_db()
        self.assertTrue(payment_is_locked(subscription, self.plans["starter"]))
        self.assertFalse(payment_is_locked(subscription, self.plans["production"]))

    def test_subscription_sync_preserves_founder_lifetime_grant(self):
        founder = CustomUser.objects.create_superuser(
            username="sync-founder", password="safe-password-123"
        )
        subscription = self._subscribe("business_pro")
        grant_founder_lifetime(subscription, self.plans["business_pro"], founder)

        call_command("sync_subscriptions", verbosity=0)

        subscription.refresh_from_db()
        self.assertTrue(subscription.founder_lifetime)
        self.assertEqual(subscription.status, BusinessSubscription.STATUS_FOUNDER)
        self.assertTrue(
            BusinessModuleAccess.objects.get(
                business=self.business, module="commerce"
            ).enabled
        )

    def test_stale_payment_confirmation_cannot_revoke_newer_founder_grant(self):
        founder = CustomUser.objects.create_superuser(
            username="payment-founder", password="safe-password-123"
        )
        subscription = self._subscribe("starter")
        payment = SubscriptionPayment.objects.create(
            subscription=subscription,
            plan=self.plans["production"],
            amount=Decimal("1000.00"),
            months=1,
            billing_cycle=SubscriptionPayment.CYCLE_MONTHLY,
            provider="manual",
            reference="STALE-BEFORE-FOUNDER",
        )

        grant_founder_lifetime(subscription, self.plans["business_pro"], founder)
        mark_payment_paid(payment)

        payment.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.STATUS_PAID)
        self.assertTrue(subscription.founder_lifetime)
        self.assertEqual(subscription.status, BusinessSubscription.STATUS_FOUNDER)
        self.assertEqual(subscription.plan, self.plans["business_pro"])

    def test_payment_created_after_founder_grant_can_switch_plan(self):
        founder = CustomUser.objects.create_superuser(
            username="switch-founder", password="safe-password-123"
        )
        subscription = self._subscribe("starter")
        grant_founder_lifetime(subscription, self.plans["starter"], founder)
        subscription.refresh_from_db()
        payment = SubscriptionPayment.objects.create(
            subscription=subscription,
            plan=self.plans["production"],
            amount=Decimal("1000.00"),
            months=1,
            billing_cycle=SubscriptionPayment.CYCLE_MONTHLY,
            provider="manual",
            reference="POST-FOUNDER-SWITCH",
        )

        mark_payment_paid(payment)

        subscription.refresh_from_db()
        self.assertFalse(subscription.founder_lifetime)
        self.assertEqual(subscription.status, BusinessSubscription.STATUS_ACTIVE)
        self.assertEqual(subscription.plan, self.plans["production"])


class SeedQueryEfficiencyTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Seed Efficiency", slug="seed-efficiency")

    def test_role_seed_steady_state_is_bounded_and_repairs_missing_permissions(self):
        roles = seed_business_roles(self.business)

        with CaptureQueriesContext(connection) as queries:
            seeded = seed_business_roles(self.business)

        self.assertEqual(set(seeded), set(roles))
        self.assertLessEqual(len(queries), 3)

        manager = seeded[CustomUser.ROLE_MANAGER]
        RoleModulePermission.objects.filter(role=manager, module="sales").delete()
        with CaptureQueriesContext(connection) as repair_queries:
            seed_business_roles(self.business)

        self.assertTrue(RoleModulePermission.objects.filter(role=manager, module="sales").exists())
        self.assertLessEqual(len(repair_queries), 5)

    def test_plan_seed_steady_state_is_bounded_and_repairs_entitlement_drift(self):
        plans = ensure_default_plans()

        with CaptureQueriesContext(connection) as queries:
            seeded = ensure_default_plans()

        self.assertEqual(set(seeded), set(plans))
        self.assertLessEqual(len(queries), 3)

        starter = seeded["starter"]
        row = SubscriptionPlanModule.objects.get(plan=starter, module="inventory")
        row.enabled = False
        row.level = "none"
        row.save(update_fields=["enabled", "level"])
        SubscriptionPlanModule.objects.filter(plan=starter, module="sales").delete()

        with CaptureQueriesContext(connection) as repair_queries:
            ensure_default_plans()

        inventory = SubscriptionPlanModule.objects.get(plan=starter, module="inventory")
        sales = SubscriptionPlanModule.objects.get(plan=starter, module="sales")
        self.assertTrue(inventory.enabled)
        self.assertEqual(inventory.level, "full")
        self.assertTrue(sales.enabled)
        self.assertEqual(sales.level, "full")
        self.assertLessEqual(len(repair_queries), 6)


class FounderPaymentSettingsTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Platform Business", slug="platform-business")
        self.user = CustomUser.objects.create_superuser(
            username="founder", password="safe-password-123", fullname="Founder"
        )
        self.plans = ensure_default_plans()
        self.client.force_login(self.user)

    def test_founder_can_toggle_new_subscription_payment_channels(self):
        response = self.client.post(reverse("founder_subscriptions"), {
            "action": "save_payment_channels",
            "monnify_enabled": "on",
        })
        self.assertRedirects(response, reverse("founder_subscriptions"), fetch_redirect_response=False)
        payment_settings = SubscriptionPaymentSettings.load()
        self.assertFalse(payment_settings.paystack_enabled)
        self.assertTrue(payment_settings.monnify_enabled)
        self.assertEqual(payment_settings.updated_by, self.user)

    def test_active_plan_card_is_marked_and_current_trial_payment_is_disabled(self):
        from .subscription_services import start_trial_for_business

        start_trial_for_business(self.business, self.plans["starter"])
        response = self.client.get(reverse("subscription_plans"))
        self.assertContains(response, "Current · Free trial")
        self.assertContains(response, "Renewal opens in final 7 days")

    def test_active_plan_change_requires_explicit_acknowledgement(self):
        from .subscription_services import start_trial_for_business

        start_trial_for_business(self.business, self.plans["starter"])
        selected = self.plans["production"]
        selected.monthly_price = 1000
        selected.save(update_fields=["monthly_price"])
        url = reverse("subscription_payment_plan", args=[selected.code])
        response = self.client.post(url, {
            "provider": "paystack", "billing_cycle": "monthly", "months": "1",
        })
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertFalse(SubscriptionPayment.objects.exists())

    def test_disabled_provider_is_hidden_and_rejected_for_new_checkout(self):
        payment_settings = SubscriptionPaymentSettings.load()
        payment_settings.paystack_enabled = False
        payment_settings.monnify_enabled = True
        payment_settings.save()
        url = reverse("subscription_payment_plan", args=[self.plans["starter"].code])

        response = self.client.get(url)
        self.assertEqual(response.context["available_payment_providers"], [("monnify", "Monnify")])
        subscription = BusinessSubscription.objects.get(primary_business=self.business)
        from django.utils import timezone
        subscription.trial_ends_at = timezone.now() + timezone.timedelta(days=6)
        subscription.save(update_fields=["trial_ends_at"])
        response = self.client.post(url, {
            "provider": "paystack", "billing_cycle": "monthly", "months": "1",
        })
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.assertFalse(SubscriptionPayment.objects.exists())
