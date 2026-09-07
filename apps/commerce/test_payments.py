import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounts.models import BusinessModuleAccess, CustomUser, UserBusiness
from accounts.services import seed_business_roles
from core.models import Business, FinancialTransaction
from inventory.models import FinishedGood, FinishedGoodChannelPrice

from .models import (
    CommerceGatewayEvent,
    CommerceIntegration,
    CommerceIntake,
    CommercePayment,
    CommercePaymentClaim,
    CommercePaymentConfiguration,
    CommercePaymentReceipt,
    CommerceSettings,
    StorefrontProduct,
)
from .payment_gateways import monnify_signature_valid, verify_monnify, verify_paystack
from .payment_services import record_verified_payment, reverse_payment_receipt
from .services import accept_intake, create_intake


class CommercePaymentTestBase(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Sample Store", slug="sample-store", vertical=Business.VERTICAL_RETAIL
        )
        BusinessModuleAccess.objects.update_or_create(
            business=self.business, module="commerce", defaults={"enabled": True}
        )
        CommerceSettings.raw_objects.create(business=self.business, enabled=True, api_enabled=True)
        self.integration = CommerceIntegration.raw_objects.create(
            business=self.business, name="Storefront", integration_type=CommerceIntegration.TYPE_API
        )
        self.config = CommercePaymentConfiguration.raw_objects.create(
            business=self.business,
            currency="NGN",
            paystack_enabled=True,
            paystack_secret_key="paystack-test-secret",
            monnify_enabled=True,
            monnify_api_key="monnify-api",
            monnify_secret_key="monnify-test-secret",
            monnify_contract_code="contract-1",
            bank_transfer_enabled=True,
            bank_name="Example Bank",
            bank_account_name="Sample Store",
            bank_account_number="0000000000",
            cash_enabled=True,
        )
        self.good = FinishedGood.raw_objects.create(
            business=self.business,
            name="Stock Product",
            unit="unit",
            units_per_batch=1,
            stock=20,
            reorder_level=2,
            selling_price=Decimal("2500.00"),
        )
        self.product = StorefrontProduct.raw_objects.create(
            business=self.business,
            finished_good=self.good,
            published=True,
            allow_stock_order=True,
            allow_preorder=False,
        )
        self.intake, _ = create_intake(
            business=self.business,
            source=CommerceIntake.SOURCE_API,
            ordering_mode=CommerceIntake.MODE_STOCK,
            customer={"name": "Sample Customer", "email": "customer@example.test"},
            items=[{"storefront_product": self.product, "quantity": "2"}],
            idempotency_key="order-key",
        )

    def api_post(self, path, payload, *, idem=None):
        headers = {"HTTP_X_STORETRACK_KEY": self.integration.api_key}
        if idem is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = idem
        return self.client.post(path, json.dumps(payload), content_type="application/json", **headers)

    def make_payment(self, method=CommercePayment.METHOD_CASH, **overrides):
        values = {
            "business": self.business,
            "intake": self.intake,
            "method": method,
            "status": CommercePayment.STATUS_PENDING,
            "amount": self.intake.total,
            "currency": "NGN",
            "reference": f"STP-{method.upper()}-{CommercePayment.raw_objects.count() + 1}",
            "gateway_reference": "",
            "idempotency_key": f"payment-{CommercePayment.raw_objects.count() + 1}",
        }
        values.update(overrides)
        return CommercePayment.raw_objects.create(**values)


class HeadlessPaymentApiTests(CommercePaymentTestBase):
    def test_storefront_amount_is_ignored_and_initialization_is_idempotent(self):
        path = f"/api/v1/storefronts/{self.business.slug}/orders/{self.intake.public_id}/payments/initiate"
        first = self.api_post(path, {"method": "cash", "amount": "0.01"}, idem="cash-selection")
        second = self.api_post(path, {"method": "cash", "amount": "900000"}, idem="cash-selection")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["amount"], "5000.00")
        self.assertEqual(first.json()["payment_id"], second.json()["payment_id"])
        self.assertEqual(CommercePayment.raw_objects.count(), 1)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 0)

    def test_distribution_minimum_returns_other_channel_suggestions(self):
        self.product.distribution_min_quantity = Decimal("10")
        self.product.save(update_fields=["distribution_min_quantity"])
        path = f"/api/v1/storefronts/{self.business.slug}/orders"
        response = self.api_post(
            path,
            {
                "order_mode": "distribution",
                "customer": {"name": "Sample Customer"},
                "items": [{"product_id": str(self.product.public_id), "quantity": "2"}],
            },
            idem="below-trade-minimum",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "minimum_not_met")
        self.assertEqual(
            [item["code"] for item in response.json()["suggested_order_modes"]],
            ["physical_store", "online"],
        )

    def test_non_production_channels_use_channel_price_without_creating_production(self):
        FinishedGoodChannelPrice.objects.create(
            finished_good=self.good, channel="online", price=Decimal("2250.00")
        )
        path = f"/api/v1/storefronts/{self.business.slug}/orders"
        response = self.api_post(
            path,
            {
                "order_mode": "online",
                "customer": {"name": "Sample Customer"},
                "items": [{"product_id": str(self.product.public_id), "quantity": "2"}],
            },
            idem="retail-online-channel",
        )
        self.assertEqual(response.status_code, 201)
        intake = CommerceIntake.raw_objects.get(public_id=response.json()["id"])
        self.assertEqual(intake.sales_channel, CommerceIntake.CHANNEL_ONLINE)
        self.assertEqual(intake.ordering_mode, CommerceIntake.MODE_STOCK)
        self.assertEqual(intake.total, Decimal("4500.00"))

    def test_payment_initialization_is_tenant_scoped(self):
        other = Business.objects.create(name="Other Store", slug="other-store", vertical=Business.VERTICAL_RETAIL)
        BusinessModuleAccess.objects.update_or_create(business=other, module="commerce", defaults={"enabled": True})
        CommerceSettings.raw_objects.create(business=other, enabled=True, api_enabled=True)
        other_integration = CommerceIntegration.raw_objects.create(
            business=other, name="Other API", integration_type=CommerceIntegration.TYPE_API
        )
        path = f"/api/v1/storefronts/{other.slug}/orders/{self.intake.public_id}/payments/initiate"
        response = self.client.post(
            path,
            json.dumps({"method": "cash"}),
            content_type="application/json",
            HTTP_X_STORETRACK_KEY=other_integration.api_key,
            HTTP_IDEMPOTENCY_KEY="cross-tenant",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CommercePayment.raw_objects.count(), 0)

    def test_current_payment_and_order_detail_remain_backward_compatible(self):
        detail_url = f"/api/v1/storefronts/{self.business.slug}/orders/{self.intake.public_id}"
        empty = self.client.get(detail_url, HTTP_X_STORETRACK_KEY=self.integration.api_key)
        self.assertEqual(empty.status_code, 200)
        self.assertIn("payment_state", empty.json())
        self.assertIsNone(empty.json()["payment"])

        payment = self.make_payment()
        current_url = f"{detail_url}/payments/current"
        current = self.client.get(current_url, HTTP_X_STORETRACK_KEY=self.integration.api_key)
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["payment_id"], str(payment.public_id))
        self.assertEqual(current.json()["balance"], "5000.00")
        enriched = self.client.get(detail_url, HTTP_X_STORETRACK_KEY=self.integration.api_key)
        self.assertEqual(enriched.json()["payment"]["method"], "cash")

    def test_bank_claim_is_evidence_only_and_deduplicated(self):
        payment = self.make_payment(method=CommercePayment.METHOD_BANK_TRANSFER)
        url = f"/api/v1/storefronts/{self.business.slug}/orders/{self.intake.public_id}/payments/current/claim"
        payload = {"payer_name": "Sample Customer", "transfer_reference": "BANK-SESSION-101"}
        first = self.api_post(url, payload)
        second = self.api_post(url, payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        payment.refresh_from_db()
        self.intake.refresh_from_db()
        self.assertEqual(payment.status, CommercePayment.STATUS_AWAITING_VERIFICATION)
        self.assertEqual(self.intake.payment_state, CommerceIntake.PAYMENT_PENDING)
        self.assertEqual(CommercePaymentClaim.raw_objects.count(), 1)
        self.assertEqual(CommercePaymentReceipt.raw_objects.count(), 0)

    @patch("commerce.payment_services.initialize_gateway")
    def test_browser_return_url_never_marks_gateway_payment_paid(self, initialize):
        initialize.return_value = {
            "authorization_url": "https://gateway.example.test/checkout/1",
            "gateway_reference": "provider-1",
            "metadata": {},
        }
        path = f"/api/v1/storefronts/{self.business.slug}/orders/{self.intake.public_id}/payments/initiate"
        response = self.api_post(
            path,
            {"method": "paystack", "return_url": "https://storefront.example.test/payment/return/"},
            idem="gateway-selection",
        )
        self.assertEqual(response.status_code, 200)
        payment = CommercePayment.raw_objects.get()
        self.assertEqual(payment.status, CommercePayment.STATUS_AWAITING_CUSTOMER)
        self.assertEqual(payment.amount_paid, Decimal("0"))
        self.assertEqual(FinancialTransaction.raw_objects.count(), 0)


class ManualVerificationTests(CommercePaymentTestBase):
    def _staff(self, role_key, username):
        roles = seed_business_roles(self.business)
        user = CustomUser.objects.create_user(username=username, password="test-password", fullname=username.title())
        UserBusiness.objects.create(user=user, business=self.business, role=roles[role_key])
        return user

    def test_only_authorized_staff_can_confirm_cash(self):
        payment = self.make_payment()
        user = self._staff(CustomUser.ROLE_STOCK_KEEPER, "stock-user")
        self.client.force_login(user)
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        response = self.client.post(
            f"/finance/commerce-payments/{payment.public_id}/confirm/",
            {"amount": "5000", "confirmation_token": "unauthorized-attempt"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CommercePaymentReceipt.raw_objects.count(), 0)

    def test_partial_manual_payment_records_actor_time_once_and_preserves_state_boundaries(self):
        payment = self.make_payment()
        user = self._staff(CustomUser.ROLE_ACCOUNTANT, "finance-user")
        self.client.force_login(user)
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()
        url = f"/finance/commerce-payments/{payment.public_id}/confirm/"
        data = {
            "amount": "1250.00",
            "location": "Main counter",
            "note": "Counted with cashier",
            "confirmation_token": "cash-confirmation-1",
        }
        first = self.client.post(url, data)
        second = self.client.post(url, data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        payment.refresh_from_db()
        self.intake.refresh_from_db()
        receipt = CommercePaymentReceipt.raw_objects.get()
        self.assertEqual(receipt.verified_by, user)
        self.assertIsNotNone(receipt.verified_at)
        self.assertEqual(receipt.location, "Main counter")
        self.assertEqual(payment.status, CommercePayment.STATUS_PARTIALLY_PAID)
        self.assertEqual(payment.amount_paid, Decimal("1250.00"))
        self.assertEqual(payment.balance, Decimal("3750.00"))
        self.assertEqual(self.intake.status, CommerceIntake.STATUS_PENDING)
        self.assertEqual(self.intake.fulfilment_state, CommerceIntake.FULFIL_PENDING)
        self.assertEqual(self.intake.payment_state, CommerceIntake.PAYMENT_PENDING)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 1)

    def test_bank_verification_requires_claim_and_reuses_receivable_semantics(self):
        payment = self.make_payment(method=CommercePayment.METHOD_BANK_TRANSFER)
        with self.assertRaisesMessage(Exception, "claim is required"):
            record_verified_payment(
                payment=payment,
                amount="1000",
                actor=None,
                idempotency_key="missing-claim",
            )
        claim = CommercePaymentClaim.raw_objects.create(
            business=self.business,
            payment=payment,
            payer_name="Sample Customer",
            transfer_reference="TRANSFER-200",
        )
        receipt, created = record_verified_payment(
            payment=payment,
            amount="1000",
            actor=None,
            idempotency_key="bank-confirm-1",
            claim=claim,
        )
        duplicate, created_again = record_verified_payment(
            payment=payment,
            amount="1000",
            actor=None,
            idempotency_key="bank-confirm-1",
            claim=claim,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(receipt.pk, duplicate.pk)
        payment.refresh_from_db()
        claim.refresh_from_db()
        self.assertEqual(payment.status, CommercePayment.STATUS_PARTIALLY_PAID)
        self.assertEqual(claim.status, CommercePaymentClaim.STATUS_ACCEPTED)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 1)

    def test_verified_intake_payment_allocates_to_sale_without_second_cash_entry(self):
        payment = self.make_payment()
        record_verified_payment(
            payment=payment,
            amount="5000",
            actor=None,
            idempotency_key="paid-before-acceptance",
        )
        accept_intake(self.intake, user=None)
        self.intake.refresh_from_db()
        sale = self.intake.accepted_sale
        self.assertEqual(sale.payments.count(), 1)
        self.assertEqual(sale.payments.get().amount, Decimal("5000.00"))
        self.assertEqual(sale.transaction_type, "paid")
        self.assertEqual(FinancialTransaction.raw_objects.count(), 1)

    def test_receipt_reversal_is_compensating_and_idempotent(self):
        payment = self.make_payment()
        receipt, _ = record_verified_payment(
            payment=payment,
            amount="5000",
            actor=None,
            idempotency_key="cash-to-reverse",
        )
        reversed_receipt, created = reverse_payment_receipt(
            receipt=receipt, actor=None, reason="Till recount correction"
        )
        duplicate, created_again = reverse_payment_receipt(
            receipt=receipt, actor=None, reason="Till recount correction"
        )
        payment.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(reversed_receipt.pk, duplicate.pk)
        self.assertEqual(payment.amount_paid, Decimal("0"))
        self.assertEqual(CommercePaymentReceipt.raw_objects.count(), 1)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 2)
        self.assertTrue(FinancialTransaction.raw_objects.get(pk=receipt.financial_transaction_id).reversed)


class GatewayWebhookTests(CommercePaymentTestBase):
    def _gateway_payment(self, method, reference, gateway_reference):
        return self.make_payment(
            method=method,
            reference=reference,
            gateway_reference=gateway_reference,
            status=CommercePayment.STATUS_AWAITING_CUSTOMER,
        )

    @patch("commerce.payment_services.verify_gateway")
    def test_paystack_signature_and_replay_safety(self, verify_gateway):
        payment = self._gateway_payment("paystack", "STP-PAYSTACK-WEBHOOK", "gateway-paystack-1")
        verify_gateway.return_value = (True, {"reference": payment.reference, "amount": "5000.00", "currency": "NGN"})
        payload = {"event": "charge.success", "data": {"reference": payment.reference, "id": 44}}
        raw = json.dumps(payload).encode()
        signature = hmac.new(self.config.paystack_secret_key.encode(), raw, hashlib.sha512).hexdigest()
        url = f"/api/v1/storefronts/{self.business.slug}/payments/paystack/webhook"
        invalid = self.client.post(url, raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE="bad")
        first = self.client.post(url, raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        replay = self.client.post(url, raw, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(invalid.status_code, 403)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, CommercePayment.STATUS_PAID)
        self.assertEqual(CommercePaymentReceipt.raw_objects.count(), 1)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 1)
        self.assertEqual(CommerceGatewayEvent.raw_objects.count(), 2)

    @patch("commerce.payment_services.verify_gateway")
    def test_monnify_signature_and_replay_safety(self, verify_gateway):
        payment = self._gateway_payment("monnify", "STP-MONNIFY-WEBHOOK", "gateway-monnify-1")
        verify_gateway.return_value = (True, {"reference": payment.reference, "amount": "5000.00", "currency": "NGN"})
        payload = {"eventType": "SUCCESSFUL_TRANSACTION", "eventData": {"paymentReference": payment.reference}}
        raw = json.dumps(payload).encode()
        signature = hmac.new(self.config.monnify_secret_key.encode(), raw, hashlib.sha512).hexdigest()
        url = f"/api/v1/storefronts/{self.business.slug}/payments/monnify/webhook"
        first = self.client.post(url, raw, content_type="application/json", HTTP_MONNIFY_SIGNATURE=signature)
        replay = self.client.post(url, raw, content_type="application/json", HTTP_MONNIFY_SIGNATURE=signature)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, CommercePayment.STATUS_PAID)
        self.assertEqual(CommercePaymentReceipt.raw_objects.count(), 1)
        self.assertEqual(FinancialTransaction.raw_objects.count(), 1)

    def test_monnify_allows_missing_signature_only_for_sandbox_verification(self):
        self.config.monnify_base_url = "https://sandbox.monnify.com"
        self.assertTrue(monnify_signature_valid(self.config, b"{}", ""))
        self.config.monnify_base_url = "https://api.monnify.com"
        self.assertFalse(monnify_signature_valid(self.config, b"{}", ""))

    @patch("commerce.payment_gateways._json_request")
    def test_paystack_verification_rejects_amount_reference_currency_or_owner_mismatch(self, request_json):
        payment = self._gateway_payment("paystack", "STP-PAYSTACK-VERIFY", "provider-verify-1")
        request_json.return_value = {
            "status": True,
            "data": {
                "status": "success",
                "reference": payment.reference,
                "amount": 499999,
                "currency": "NGN",
                "metadata": {
                    "storetrack_payment_id": str(payment.public_id),
                    "storetrack_order_id": str(self.intake.public_id),
                    "business_id": self.business.pk,
                },
            },
        }
        verified, _ = verify_paystack(payment, self.config)
        self.assertFalse(verified)

    @patch("commerce.payment_gateways._json_request")
    def test_monnify_verification_matches_reference_amount_currency_and_owner(self, request_json):
        payment = self._gateway_payment("monnify", "STP-MONNIFY-VERIFY", "provider-verify-2")
        request_json.side_effect = [
            {"requestSuccessful": True, "responseBody": {"accessToken": "short-lived-token"}},
            {
                "requestSuccessful": True,
                "responseBody": {
                    "paymentStatus": "PAID",
                    "paymentReference": payment.reference,
                    "transactionReference": payment.gateway_reference,
                    "amountPaid": "5000.00",
                    "currencyCode": "NGN",
                    "metaData": {
                        "storetrackPaymentId": str(payment.public_id),
                        "storetrackOrderId": str(self.intake.public_id),
                        "businessId": str(self.business.pk),
                    },
                },
            },
        ]
        verified, _ = verify_monnify(payment, self.config)
        self.assertTrue(verified)
