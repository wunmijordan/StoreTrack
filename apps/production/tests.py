from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser, UserBusiness
from accounts.services import seed_business_roles
from core.models import Business
from .models import Order, OrderNumberSequence


class BusinessOrderNumberingTests(TestCase):
    def setUp(self):
        self.a = Business.objects.create(name="Business A", slug="business-a")
        self.b = Business.objects.create(name="Business B", slug="business-b")

    def make_order(self, business):
        return Order.raw_objects.create(
            business=business,
            date=date(2026, 9, 2),
            order_type="physical_store",
            production_destination="store",
        )

    def test_numbering_is_independent_per_business(self):
        a1 = self.make_order(self.a)
        b1 = self.make_order(self.b)
        a2 = self.make_order(self.a)
        self.assertEqual(a1.order_number, 1)
        self.assertEqual(b1.order_number, 1)
        self.assertEqual(a2.order_number, 2)
        self.assertNotEqual(a1.pk, b1.pk)

    def test_resetting_one_empty_business_does_not_change_another(self):
        a1 = self.make_order(self.a)
        b1 = self.make_order(self.b)
        a1.delete()
        OrderNumberSequence.raw_objects.update_or_create(business=self.a, defaults={"next_number": 1})
        a_again = self.make_order(self.a)
        b2 = self.make_order(self.b)
        self.assertEqual(a_again.order_number, 1)
        self.assertEqual(b2.order_number, 2)
        self.assertEqual(b1.order_number, 1)


class VerticalProductionUiTests(TestCase):
    def test_restaurant_uses_restaurant_order_vocabulary(self):
        business = Business.objects.create(
            name="Kitchen", slug="kitchen", vertical=Business.VERTICAL_RESTAURANT
        )
        roles = seed_business_roles(business)
        user = CustomUser.objects.create_user(
            username="kitchen.admin", password="safe-password-123", fullname="Kitchen Admin"
        )
        UserBusiness.objects.create(
            user=user, business=business,
            role=roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        self.client.force_login(user)

        response = self.client.get(reverse("order_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catering / Bulk Order")
        self.assertContains(response, "Kitchen / Counter Replenishment")
        self.assertNotContains(response, ">Physical Store Order<")
