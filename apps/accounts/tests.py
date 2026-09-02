from django.test import TestCase
from django.urls import reverse

from core.models import Business
from .models import BusinessModuleAccess, CustomUser, UserBusiness
from .services import seed_business_roles


class TenantSignupTests(TestCase):
    def test_signup_provisions_business_admin_and_full_modules(self):
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
        self.assertEqual(business.module_access.filter(enabled=True).count(), 9)
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
            "vertical": Business.VERTICAL_RESTAURANT,
            "currency_symbol": "$",
            "accent_color": "#126E82",
            "tagline": "Kitchen control",
            "restaurant_table_service": "on",
        })
        self.assertRedirects(response, reverse("business_settings"), fetch_redirect_response=False)
        self.business.refresh_from_db()
        self.assertEqual(self.business.name, "New Name")
        self.assertEqual(self.business.slug, "bakery")
        self.assertEqual(self.business.accent_color, "#126E82")
        self.assertEqual(self.business.vertical, Business.VERTICAL_RESTAURANT)

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
