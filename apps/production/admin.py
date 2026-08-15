from django.contrib import admin
from .models import ProductionRequest, ProductionOrder

admin.site.register(ProductionRequest)
admin.site.register(ProductionOrder)
