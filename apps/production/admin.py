from django.contrib import admin
from .models import Order, OrderItem, ProductionBatch, ProductionQualityCheck

admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(ProductionBatch)
admin.site.register(ProductionQualityCheck)
