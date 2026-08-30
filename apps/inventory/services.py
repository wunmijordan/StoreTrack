from decimal import Decimal
from django.db import transaction
from .models import StockMovement, InventoryLocation


def default_location(business):
    loc, _ = InventoryLocation.objects.get_or_create(business=business, name="Main Store", defaults={"location_type": "store", "created_by": None})
    return loc


@transaction.atomic
def record_raw_material_movement(material, quantity, movement_type, *, note="", reference="", unit_value=None, location=None):
    quantity = Decimal(quantity)
    material.stock = (material.stock + quantity).quantize(Decimal("0.01"))
    material.save(update_fields=["stock"])
    StockMovement.objects.create(
        business=material.business, raw_material=material, movement_type=movement_type,
        quantity=quantity, affects_stock=True, balance_after=material.stock, note=note,
        reference=reference, unit_value=Decimal(unit_value if unit_value is not None else material.cost_per_unit),
        location=location or default_location(material.business),
    )
    return material.stock


@transaction.atomic
def record_finished_good_movement(good, quantity, movement_type, *, note="", affects_stock=True, reference="", unit_value=None, location=None):
    quantity = Decimal(quantity)
    if affects_stock:
        if good.stock is None:
            raise ValueError(f"{good.name} is not configured for physical-store stock.")
        good.stock = (good.stock + quantity).quantize(Decimal("0.01"))
        good.save(update_fields=["stock"])
    StockMovement.objects.create(
        business=good.business, finished_good=good, movement_type=movement_type,
        quantity=quantity, affects_stock=affects_stock, balance_after=good.stock if affects_stock else None,
        note=note, reference=reference, unit_value=Decimal(unit_value if unit_value is not None else good.est_cost),
        location=location or default_location(good.business),
    )
    return good.stock
