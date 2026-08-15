from django.contrib import admin
from .models import PurchaseOrder, PurchaseOrderItem

admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
