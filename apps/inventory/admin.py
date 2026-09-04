from django.contrib import admin
from .models import (
    DistributionReturn,
    FinishedGood,
    MarketStockLot,
    MarketStockMovement,
    ProductionMaterial,
    RawMaterial,
    RecipeItem,
)

admin.site.register(RawMaterial)
admin.site.register(FinishedGood)
admin.site.register(RecipeItem)
admin.site.register(ProductionMaterial)
from .models import InventoryLocation, StockAdjustment, OperationalSupplyDispense
admin.site.register(InventoryLocation)
admin.site.register(StockAdjustment)

admin.site.register(OperationalSupplyDispense)
admin.site.register(MarketStockLot)
admin.site.register(MarketStockMovement)
admin.site.register(DistributionReturn)
