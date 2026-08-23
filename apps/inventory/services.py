from decimal import Decimal
from django.db import transaction

from .models import StockMovement


@transaction.atomic
def record_raw_material_movement(
    material,
    quantity,
    movement_type,
    *,
    note="",
):
    quantity = Decimal(quantity)

    material.stock = (
        material.stock + quantity
    ).quantize(Decimal("0.01"))

    material.save(update_fields=["stock"])

    StockMovement.objects.create(
        business=material.business,
        raw_material=material,
        movement_type=movement_type,
        quantity=quantity,
        affects_stock=True,
        balance_after=material.stock,
        note=note,
    )

    return material.stock


@transaction.atomic
def record_finished_good_movement(
    good,
    quantity,
    movement_type,
    *,
    note="",
    affects_stock=True,
):
    quantity = Decimal(quantity)

    if affects_stock:
        good.stock = (
            good.stock + quantity
        ).quantize(Decimal("0.01"))
        good.save(update_fields=["stock"])

    StockMovement.objects.create(
        business=good.business,
        finished_good=good,
        movement_type=movement_type,
        quantity=quantity,
        affects_stock=affects_stock,
        balance_after=good.stock,
        note=note,
    )

    return good.stock