from django.contrib import admin
from .models import PurchaseOrder, PurchaseOrderItem

admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
from .models import SupplierPayment
admin.site.register(SupplierPayment)
