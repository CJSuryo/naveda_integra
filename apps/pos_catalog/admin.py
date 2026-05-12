from django.contrib import admin
from .models import ModifierGroup, ModifierOption, ProductModifierGroup

admin.site.register(ModifierGroup)
admin.site.register(ModifierOption)
admin.site.register(ProductModifierGroup)
