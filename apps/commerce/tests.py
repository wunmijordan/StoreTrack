from decimal import Decimal
from django.test import TestCase
from core.models import Business
from inventory.models import FinishedGood, FinishedGoodChannelPrice
from .models import CommerceIntake, CommerceSettings, StorefrontProduct
from .services import accept_intake, create_intake


class CommerceIntakeTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Bakery", slug="bakery-commerce", vertical=Business.VERTICAL_BAKERY)
        self.good = FinishedGood.raw_objects.create(business=self.business, name="Mini Loaf", unit="loaf", units_per_batch=110, stock=20, reorder_level=5, selling_price=100)
        self.product = StorefrontProduct.raw_objects.create(business=self.business, finished_good=self.good, published=True, allow_stock_order=True, allow_preorder=True)

    def test_preorder_intake_does_not_mutate_stock_or_production_before_acceptance(self):
        intake, created = create_intake(
            business=self.business, source=CommerceIntake.SOURCE_API, ordering_mode=CommerceIntake.MODE_PREORDER,
            customer={"name":"Ada"}, items=[{"storefront_product":self.product,"quantity":"50"}], idempotency_key="abc",
        )
        self.assertTrue(created)
        self.good.refresh_from_db()
        self.assertEqual(self.good.stock, Decimal("20"))
        self.assertIsNone(intake.accepted_order_id)

    def test_idempotency_key_returns_same_intake(self):
        kwargs=dict(business=self.business, source=CommerceIntake.SOURCE_API, ordering_mode=CommerceIntake.MODE_STOCK, customer={"name":"Ada"}, items=[{"storefront_product":self.product,"quantity":"2"}], idempotency_key="same")
        first, created = create_intake(**kwargs)
        second, created_again = create_intake(**kwargs)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.sales_channel, CommerceIntake.CHANNEL_PHYSICAL_STORE)

    def test_public_order_numbers_increment_independently_per_business(self):
        other_business = Business.objects.create(name="Other Retailer", slug="other-retailer", vertical=Business.VERTICAL_RETAIL)
        first = CommerceIntake.raw_objects.create(
            business=self.business, ordering_mode=CommerceIntake.MODE_STOCK, customer_name="First Customer"
        )
        other_first = CommerceIntake.raw_objects.create(
            business=other_business, ordering_mode=CommerceIntake.MODE_STOCK, customer_name="Other Customer"
        )
        second = CommerceIntake.raw_objects.create(
            business=self.business, ordering_mode=CommerceIntake.MODE_STOCK, customer_name="Second Customer"
        )

        self.assertEqual(first.public_number, "WEB-000001")
        self.assertEqual(other_first.public_number, "WEB-000001")
        self.assertEqual(second.public_number, "WEB-000002")


class ProductionCommerceChannelTests(TestCase):
    def test_general_production_distribution_channel_uses_trade_price_and_pending_production(self):
        business = Business.objects.create(
            name="Sample Manufacturer", slug="sample-manufacturer", vertical=Business.VERTICAL_GENERAL
        )
        good = FinishedGood.raw_objects.create(
            business=business, name="Component Set", unit="set", units_per_batch=10,
            stock=0, reorder_level=0, selling_price=Decimal("100"),
        )
        FinishedGoodChannelPrice.objects.create(
            finished_good=good, channel="distribution", price=Decimal("80")
        )
        product = StorefrontProduct.raw_objects.create(
            business=business, finished_good=good, published=True,
            distribution_min_quantity=5, allow_preorder=True,
        )
        intake, _ = create_intake(
            business=business,
            source=CommerceIntake.SOURCE_API,
            sales_channel="distribution",
            customer={"name": "Trade Customer"},
            items=[{"storefront_product": product, "quantity": "5"}],
            idempotency_key="general-distribution",
        )
        self.assertEqual(intake.ordering_mode, CommerceIntake.MODE_PREORDER)
        self.assertEqual(intake.total, Decimal("400"))
        accept_intake(intake)
        intake.refresh_from_db()
        self.assertEqual(intake.accepted_order.order_type, "distribution")
        self.assertEqual(intake.accepted_order.items.get().price, Decimal("80"))


class CommerceApiProductTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Sample Restaurant", slug="sample-restaurant", vertical=Business.VERTICAL_RESTAURANT)
        CommerceSettings.raw_objects.create(business=self.business, enabled=True, api_enabled=True)
        self.good = FinishedGood.raw_objects.create(business=self.business, name="Moin Moin", unit="plate", units_per_batch=1, stock=12, reorder_level=2, selling_price=2500)
        self.product = StorefrontProduct.raw_objects.create(
            business=self.business, finished_good=self.good, published=True,
            image_url="https://cdn.example.test/moin-moin.jpg",
            min_quantity=1, preorder_min_quantity=5, allow_stock_order=True, allow_preorder=True,
        )

    def test_product_api_exposes_public_image_and_preorder_minimum(self):
        response = self.client.get(f"/api/v1/storefronts/{self.business.slug}/products")
        self.assertEqual(response.status_code, 200)
        row = response.json()["products"][0]
        self.assertEqual(row["image_url"], "https://cdn.example.test/moin-moin.jpg")
        self.assertEqual(row["preorder_min_quantity"], "5.00")
        self.assertEqual(
            [mode["code"] for mode in row["order_modes"]],
            ["physical_store", "online", "distribution"],
        )
        self.assertEqual(row["order_modes"][2]["label"], "Catering / Bulk Order")
