import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# Each merchant maps 1-to-1 with a Django User account (for login).
class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class LedgerEntry(models.Model):
    # Every money movement is one of these four types.
    # Think of it like a bank statement — every line is either money in or money out.
    #
    #   credit  — customer paid the merchant (money arrives)
    #   debit   — payout completed successfully (money leaves)
    #   hold    — funds locked when a payout is requested (prevents double-spending)
    #   unhold  — hold released because the payout failed (money returns to available)
    #
    # The balance is always calculated by summing these entries — there is no
    # separate "balance" column anywhere. The ledger IS the balance.
    ENTRY_TYPES = [
        ('credit', 'Credit'),
        ('debit',  'Debit'),
        ('hold',   'Hold'),
        ('unhold', 'Unhold'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)

    # Always stored as a positive integer in paise (1 INR = 100 paise).
    # Using BigIntegerField (not FloatField or DecimalField) because integer
    # arithmetic is exact — there are no rounding errors possible.
    # Direction is encoded by entry_type, not by sign.
    amount_paise = models.BigIntegerField()

    # Optional link back to the payout that caused this entry.
    # SET_NULL so deleting a payout doesn't cascade-delete ledger history.
    payout = models.ForeignKey(
        'PayoutRequest', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ledger_entries'
    )
    description = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # This index makes the balance aggregation query fast — it only scans
        # rows for one merchant instead of the whole table.
        indexes = [models.Index(fields=['merchant', '-created_at'])]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise} paise for {self.merchant.name}"


class PayoutRequest(models.Model):
    # Defines which state transitions are legal.
    # Reading this dict: the key is the current state, the value is the list
    # of states it is allowed to move to.
    #
    #   pending     → can only go to processing (Celery picks it up)
    #   processing  → can go to completed (bank success) or failed (bank declined)
    #   completed   → terminal state, cannot move anywhere
    #   failed      → terminal state, cannot move anywhere
    #
    # An empty list [] means the state is terminal — no transitions allowed.
    # This is enforced in services.transition_state() — that is the only place
    # payout.status is ever changed.
    VALID_TRANSITIONS = {
        'pending':    ['processing'],
        'processing': ['completed', 'failed'],
        'completed':  [],
        'failed':     [],
    }

    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    amount_paise = models.BigIntegerField()
    bank_account_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    idempotency_key = models.CharField(max_length=255)
    attempts = models.IntegerField(default=0)       # how many times Celery has tried this payout
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # used by retry_stuck_payouts to find hangs

    class Meta:
        # Prevents two payouts from being created with the same idempotency key
        # for the same merchant at the database level (last line of defence).
        unique_together = [('merchant', 'idempotency_key')]
        indexes = [
            models.Index(fields=['status', 'updated_at']),   # for retry_stuck_payouts query
            models.Index(fields=['merchant', '-created_at']), # for listing payouts by merchant
        ]

    def __str__(self):
        return f"Payout {self.id} - {self.status}"


class IdempotencyRecord(models.Model):
    # Stores the exact HTTP response (body + status code) of the first request
    # for a given idempotency key. Subsequent requests with the same key get
    # this cached response returned — no business logic runs again.
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='idempotency_records')
    key = models.CharField(max_length=255)
    response_body = models.JSONField()      # exact JSON that was returned first time
    response_status = models.IntegerField() # exact HTTP status code (201, 422, etc.)
    payout = models.ForeignKey(PayoutRequest, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()     # keys expire after 24 hours, cleaned up by celery beat

    class Meta:
        # Two merchants can use the same UUID key without conflict — keys are per-merchant.
        unique_together = [('merchant', 'key')]
        indexes = [models.Index(fields=['merchant', 'key'])]

    def __str__(self):
        return f"IdempotencyRecord {self.key} for {self.merchant.name}"
