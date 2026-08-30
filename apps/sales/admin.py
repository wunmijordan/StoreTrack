from django.contrib import admin
from .models import Sale, SaleItem

admin.site.register(Sale)
admin.site.register(SaleItem)
from .models import CustomerPayment
admin.site.register(CustomerPayment)
