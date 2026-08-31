from decimal import Decimal

from django.test import TestCase

from core.models import Business
from inventory.models import FinishedGood, FinishedGoodChannelPrice
from .models import Customer, CustomerProductPrice


class CustomerProductPriceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Test Business", slug="test-business")
        self.customer = Customer.objects.create(business=self.business, name="Customer A")
        self.good = FinishedGood.objects.create(
            business=self.business, name="Product A", unit="piece", selling_price=Decimal("100.00")
        )
        FinishedGoodChannelPrice.objects.create(
            finished_good=self.good, channel="distribution", price=Decimal("90.00")
        )
        FinishedGoodChannelPrice.objects.create(
            finished_good=self.good, channel="online", price=Decimal("95.00")
        )

    def test_customer_price_overrides_channel_price(self):
        CustomerProductPrice.objects.create(
            business=self.business, customer=self.customer, finished_good=self.good,
            channel="distribution", price=Decimal("120.00")
        )
        self.assertEqual(self.good.selling_price_for("distribution", self.customer), Decimal("120.00"))
        self.assertEqual(self.good.selling_price_for("online", self.customer), Decimal("95.00"))

    def test_without_customer_override_channel_price_is_unchanged(self):
        self.assertEqual(self.good.selling_price_for("distribution", self.customer), Decimal("90.00"))

    def test_customer_price_is_channel_specific(self):
        CustomerProductPrice.objects.create(
            business=self.business, customer=self.customer, finished_good=self.good,
            channel="online", price=Decimal("125.00")
        )
        self.assertEqual(self.good.selling_price_for("online", self.customer), Decimal("125.00"))
        self.assertEqual(self.good.selling_price_for("distribution", self.customer), Decimal("90.00"))
