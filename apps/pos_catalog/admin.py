from django.contrib import admin
from .models import POSCategory, POSProduct, ProductStoreAvailability, ModifierGroup, ModifierOption, ProductModifierGroup

admin.site.register(POSCategory)
admin.site.register(POSProduct)
admin.site.register(ProductStoreAvailability)
admin.site.register(ModifierGroup)
admin.site.register(ModifierOption)
admin.site.register(ProductModifierGroup)
