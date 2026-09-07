from django.urls import path
from . import views
from . import payment_views

urlpatterns = [
    path("commerce/", views.commerce_dashboard, name="commerce_dashboard"),
    path("commerce/settings/", views.commerce_settings, name="commerce_settings"),
    path("commerce/products/<int:good_id>/", views.storefront_product_edit, name="storefront_product_edit"),
    path("commerce/integrations/add/", views.integration_add, name="commerce_integration_add"),
    path("commerce/payment-settings/", payment_views.payment_settings, name="commerce_payment_settings"),
    path("commerce/intakes/<uuid:public_id>/accept/", views.intake_accept, name="commerce_intake_accept"),
    path("finance/commerce-payments/", payment_views.payment_queue, name="commerce_payment_queue"),
    path("finance/commerce-payments/<uuid:public_id>/confirm/", payment_views.payment_confirm, name="commerce_payment_confirm"),
    path("finance/commerce-payments/<uuid:public_id>/reconcile/", payment_views.payment_reconcile, name="commerce_payment_reconcile"),
    path("finance/commerce-payment-claims/<int:claim_id>/reject/", payment_views.payment_claim_reject, name="commerce_payment_claim_reject"),
    path("finance/commerce-payment-receipts/<int:receipt_id>/reverse/", payment_views.payment_receipt_reverse, name="commerce_payment_receipt_reverse"),
    path("shop/<slug:business_slug>/", views.storefront, name="storefront"),
    path("shop/<slug:business_slug>/order-now/", views.order_now, name="storefront_order_now"),
    path("shop/<slug:business_slug>/order/", views.storefront_order, name="storefront_order"),
    path("shop/<slug:business_slug>/orders/<uuid:public_id>/", views.storefront_order_status, name="storefront_order_status"),
    path("shop/<slug:business_slug>/orders/<uuid:public_id>/preorder/", views.storefront_switch_preorder, name="storefront_switch_preorder"),
    path("api/v1/storefronts/<slug:business_slug>/products", views.api_products, name="commerce_api_products"),
    path("api/v1/storefronts/<slug:business_slug>/orders", views.api_orders, name="commerce_api_orders"),
    path("api/v1/storefronts/<slug:business_slug>/orders/<uuid:public_id>", views.api_order_detail, name="commerce_api_order_detail"),
    path("api/v1/storefronts/<slug:business_slug>/orders/<uuid:public_id>/payments/initiate", payment_views.api_payment_initiate, name="commerce_api_payment_initiate"),
    path("api/v1/storefronts/<slug:business_slug>/orders/<uuid:public_id>/payments/current", payment_views.api_payment_current, name="commerce_api_payment_current"),
    path("api/v1/storefronts/<slug:business_slug>/orders/<uuid:public_id>/payments/current/claim", payment_views.api_payment_claim, name="commerce_api_payment_claim"),
    path("api/v1/storefronts/<slug:business_slug>/payments/<str:provider>/webhook", payment_views.gateway_webhook, name="commerce_gateway_webhook"),
    path("api/v1/storefronts/<slug:business_slug>/orders/<uuid:public_id>/preorder", views.api_order_switch_preorder, name="commerce_api_order_switch_preorder"),
    path("api/v1/connectors/<slug:business_slug>/<int:integration_id>/orders", views.connector_orders, name="commerce_connector_orders"),
]
