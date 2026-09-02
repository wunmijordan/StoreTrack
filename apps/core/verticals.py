"""Presentation and workflow vocabulary for supported business verticals.

Stored model keys remain stable across verticals. Only labels and small
workflow preferences vary, which keeps reports and existing data compatible.
"""

from .models import Business


VERTICAL_CONFIG = {
    Business.VERTICAL_BAKERY: {
        "platform_label": "Bakery operations",
        "orders": "Orders",
        "runs": "Shared Runs",
        "batches": "Production Batches",
        "customers": "Customers",
        "sales": "Sales",
        "stock_location": "Physical Store",
        "sale_intro": "Physical Store Stock only — immediate, from what's already on the Shelf.",
        "order_types": [
            ("distribution", "Distribution Order"),
            ("online", "Online Order"),
            ("physical_store", "Physical Store Order"),
        ],
    },
    Business.VERTICAL_RESTAURANT: {
        "platform_label": "Restaurant operations",
        "orders": "Kitchen Orders",
        "runs": "Prep Runs",
        "batches": "Prep Batches",
        "customers": "Guests & Customers",
        "sales": "POS Sales",
        "stock_location": "Kitchen / Counter",
        "sale_intro": "Record dine-in, takeaway, or delivery service from available prepared stock.",
        "order_types": [
            ("distribution", "Catering / Bulk Order"),
            ("online", "Delivery / Online Order"),
            ("physical_store", "Kitchen / Counter Replenishment"),
        ],
    },
    Business.VERTICAL_GENERAL: {
        "platform_label": "Production operations",
        "orders": "Production Orders",
        "runs": "Production Runs",
        "batches": "Production Batches",
        "customers": "Customers",
        "sales": "Sales",
        "stock_location": "Finished Goods Store",
        "sale_intro": "Record an immediate sale from available finished-goods stock.",
        "order_types": [
            ("distribution", "Wholesale / Customer Order"),
            ("online", "Online Order"),
            ("physical_store", "Stock Replenishment Order"),
        ],
    },
}


def vertical_config(business):
    key = getattr(business, "vertical", Business.VERTICAL_BAKERY)
    return VERTICAL_CONFIG.get(key, VERTICAL_CONFIG[Business.VERTICAL_GENERAL])
