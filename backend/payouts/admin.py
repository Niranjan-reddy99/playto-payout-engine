from django.contrib import admin
from .models import Merchant, LedgerEntry, PayoutRequest, IdempotencyRecord

admin.site.register(Merchant)
admin.site.register(LedgerEntry)
admin.site.register(PayoutRequest)
admin.site.register(IdempotencyRecord)
