from django.contrib import admin
from .models import RawMaterial, FinishedGood, RecipeItem, ProductionMaterial

admin.site.register(RawMaterial)
admin.site.register(FinishedGood)
admin.site.register(RecipeItem)
admin.site.register(ProductionMaterial)
from .models import InventoryLocation, StockAdjustment, OperationalSupplyDispense
admin.site.register(InventoryLocation)
admin.site.register(StockAdjustment)

admin.site.register(OperationalSupplyDispense)
