import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class LedgerEntry(models.Model):
    ENTRY_TYPES = [
        ('credit', 'Credit'),    # money IN from customer payment
        ('debit', 'Debit'),      # money OUT on payout success
        ('hold', 'Hold'),        # funds locked when payout created
        ('unhold', 'Unhold'),    # funds released when payout fails
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    amount_paise = models.BigIntegerField()  # ALWAYS positive. Direction encoded in entry_type.
    payout = models.ForeignKey('PayoutRequest', null=True, blank=True, on_delete=models.SET_NULL, related_name='ledger_entries')
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['merchant', '-created_at'])]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise} paise for {self.merchant.name}"


class PayoutRequest(models.Model):
    VALID_TRANSITIONS = {
        'pending':    ['processing'],
        'processing': ['completed', 'failed'],
        'completed':  [],
        'failed':     [],
    }

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    amount_paise = models.BigIntegerField()
    bank_account_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    idempotency_key = models.CharField(max_length=255)
    attempts = models.IntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('merchant', 'idempotency_key')]
        indexes = [
            models.Index(fields=['status', 'updated_at']),
            models.Index(fields=['merchant', '-created_at']),
        ]

    def __str__(self):
        return f"Payout {self.id} - {self.status}"


class IdempotencyRecord(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='idempotency_records')
    key = models.CharField(max_length=255)
    response_body = models.JSONField()
    response_status = models.IntegerField()
    payout = models.ForeignKey(PayoutRequest, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = [('merchant', 'key')]
        indexes = [models.Index(fields=['merchant', 'key'])]

    def __str__(self):
        return f"IdempotencyRecord {self.key} for {self.merchant.name}"
