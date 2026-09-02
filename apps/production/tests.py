from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser, UserBusiness
from accounts.services import seed_business_roles
from core.models import Business
from inventory.models import FinishedGood, StockMovement
from sales.models import Sale
from .forms import OrderForm
from .models import Order, OrderItem, OrderNumberSequence


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


class MarketStockDistributionTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Bakery", slug="bakery")

    def test_market_stock_distribution_does_not_require_customer_or_payment(self):
        form = OrderForm(
            data={
                "date": "2026-09-02",
                "order_type": "distribution",
                "is_market_stock": "on",
                "notes": "Produce ahead of demand",
            },
            business=self.business,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        order = form.save(commit=False)
        self.assertTrue(order.is_market_stock_order)
        self.assertFalse(order.is_customer_order)
        self.assertIsNone(order.customer)
        self.assertEqual(order.customer_payment_status, "paid")
        self.assertIsNone(order.customer_payment_account)

    def test_assigned_distribution_still_requires_customer(self):
        form = OrderForm(
            data={
                "date": "2026-09-02",
                "order_type": "distribution",
                "customer_payment_status": "unpaid",
            },
            business=self.business,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("customer", form.errors)

    def test_completion_puts_market_output_in_stock_without_creating_sale(self):
        user = CustomUser.objects.create_superuser(
            username="admin", password="safe-password-123", fullname="Admin"
        )
        self.client.force_login(user)
        good = FinishedGood.raw_objects.create(
            business=self.business,
            name="Bread",
            unit="loaf",
            units_per_batch=Decimal("10"),
            stock=Decimal("5"),
            reorder_level=Decimal("1"),
            selling_price=Decimal("1000"),
        )
        order = Order.raw_objects.create(
            business=self.business,
            created_by=user,
            date=date(2026, 9, 2),
            order_type="distribution",
            is_market_stock=True,
            status="approved",
        )
        item = OrderItem.objects.create(
            order=order,
            finished_good=good,
            batch_qty=Decimal("1"),
            piece_qty=Decimal("0"),
            price=Decimal("1000"),
        )

        response = self.client.post(
            reverse("order_complete", args=[order.pk]),
            {
                f"item-{item.pk}-produced_units": "10",
                f"item-{item.pk}-wastage_units": "0",
                f"item-{item.pk}-batch_number": "D260902-MARKET-1",
                f"item-{item.pk}-expiry_date": "",
                f"item-{item.pk}-wastage_reason": "",
                f"item-{item.pk}-qc_status": "pending",
                f"item-{item.pk}-qc_notes": "",
                f"item-{item.pk}-shortage_reason": "",
                f"item-{item.pk}-excess_to_stock": "0",
                f"item-{item.pk}-excess_to_non_stock": "0",
                f"item-{item.pk}-excess_non_stock_purpose": "",
            },
        )

        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        order.refresh_from_db()
        good.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(good.stock, Decimal("15.00"))
        self.assertEqual(good.total_produced, Decimal("10.00"))
        self.assertEqual(good.total_delivered_to_customers, Decimal("0.00"))
        self.assertFalse(Sale.raw_objects.filter(linked_order=order).exists())
        movement = StockMovement.raw_objects.get(
            finished_good=good, movement_type=StockMovement.FG_PRODUCTION
        )
        self.assertTrue(movement.affects_stock)
        self.assertEqual(movement.quantity, Decimal("10"))
