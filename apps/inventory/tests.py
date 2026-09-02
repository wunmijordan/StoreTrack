from decimal import Decimal

from django.test import SimpleTestCase

from .models import RawMaterial
from .views import _raw_material_stock_breakdown_markup


class RawMaterialPdfStockBreakdownTests(SimpleTestCase):
    def test_pdf_markup_matches_inventory_purchase_and_usage_breakdown(self):
        material = RawMaterial(
            purchase_unit="bag",
            package_qty=Decimal("50"),
            package_unit="kg",
            usage_unit="kg",
            usage_conversion_factor=Decimal("1"),
            stock=Decimal("130"),
        )

        self.assertEqual(
            _raw_material_stock_breakdown_markup(material),
            "<font name='Courier'>2</font> "
            "<font color='#A8A29E' size='7'><i>bags</i></font>, "
            "<font name='Courier'>30.00</font> "
            "<font color='#A8A29E' size='7'><i>kg</i></font>",
        )

    def test_pdf_markup_keeps_singular_purchase_unit_for_one(self):
        material = RawMaterial(
            purchase_unit="carton",
            package_qty=Decimal("12"),
            usage_unit="piece",
            usage_conversion_factor=Decimal("1"),
            stock=Decimal("17"),
        )

        markup = _raw_material_stock_breakdown_markup(material)

        self.assertIn("<i>carton</i>", markup)
        self.assertIn("<font name='Courier'>5.00</font>", markup)
