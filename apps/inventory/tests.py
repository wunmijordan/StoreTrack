from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from core.models import Business
from core.pdf_fonts import PDF_MONO_MEDIUM_FONT
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
            f"<font name='{PDF_MONO_MEDIUM_FONT}'>2</font> "
            "<font color='#78716C' size='9'><b><i>bags</i></b></font>, "
            f"<font name='{PDF_MONO_MEDIUM_FONT}'>30.00</font> "
            "<font color='#78716C' size='9'><b><i>kg</i></b></font>",
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
        self.assertIn(f"<font name='{PDF_MONO_MEDIUM_FONT}'>5.00</font>", markup)


class RawMaterialPdfThemeTests(TestCase):
    def test_tenant_themed_pdf_renders_successfully(self):
        business = Business.objects.create(
            name="Blue Kitchen",
            slug="blue-kitchen",
            background_color="#173B45",
            accent_color="#D6A84B",
        )
        RawMaterial.raw_objects.create(
            business=business,
            name="Flour",
            purchase_unit="bag",
            package_qty=Decimal("50"),
            package_unit="kg",
            usage_unit="kg",
            usage_conversion_factor=Decimal("1"),
            stock=Decimal("130"),
            reorder_level=Decimal("50"),
        )
        user = CustomUser.objects.create_superuser(
            username="pdf-admin",
            password="safe-password-123",
            fullname="PDF Admin",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("raw_material_inventory_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 1000)
