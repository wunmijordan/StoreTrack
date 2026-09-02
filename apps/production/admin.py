from django.contrib import admin
from .models import Order, OrderNumberSequence, OrderItem, ProductionBatch, ProductionQualityCheck, ProductionRun

admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(ProductionBatch)
admin.site.register(ProductionQualityCheck)

admin.site.register(ProductionRun)

admin.site.register(OrderNumberSequence)
