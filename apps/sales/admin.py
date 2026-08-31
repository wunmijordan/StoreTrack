from django.contrib import admin
from .models import Customer, Sale, SaleItem, CustomerProductPrice

admin.site.register(Customer)
admin.site.register(Sale)
admin.site.register(SaleItem)
from .models import CustomerPayment
admin.site.register(CustomerPayment)

admin.site.register(CustomerProductPrice)
