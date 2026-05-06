from django.contrib import admin
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog, WebPushSubscription

admin.site.register(MerchantPOSConfig)
admin.site.register(StorePOSConfig)
admin.site.register(PaymentMethod)
admin.site.register(WorkShift)
admin.site.register(ShiftLog)
admin.site.register(WebPushSubscription)
