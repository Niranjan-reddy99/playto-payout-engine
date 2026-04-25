from django.db import transaction
from django.db.models import Sum, Case, When, BigIntegerField, F
from django.utils import timezone
import redis
from decouple import config
from .models import Merchant, LedgerEntry, PayoutRequest, IdempotencyRecord
from .exceptions import InsufficientFundsError, InvalidTransitionError

redis_client = redis.Redis.from_url(config('REDIS_URL', default='redis://localhost:6379/0'))


def get_balance_breakdown(merchant_id):
    """
    Balance is NEVER stored as a column. It is always derived from ledger entries.

    Why no balance column: storing one creates a second source of truth. Any bug
    that credits or debits the column without writing a ledger entry causes silent
    corruption that is impossible to audit. With this approach, the ledger IS the
    balance. The sum of entries is always authoritative and fully reconstructable.

    Why db aggregation and not Python sum(): if we fetch rows and sum in Python,
    we see a snapshot from before any concurrent transaction commits. Another request
    could be writing a hold entry right now and we would not see it. Running the
    aggregation as a single SQL query inside the same transaction means we always
    read the committed state as of the lock acquisition — no stale reads possible.
    """
    entries = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        credits=Sum(
            Case(
                When(entry_type='credit', then=F('amount_paise')),
                default=0,
                output_field=BigIntegerField()
            )
        ),
        debits=Sum(
            Case(
                When(entry_type='debit', then=F('amount_paise')),
                default=0,
                output_field=BigIntegerField()
            )
        ),
        holds=Sum(
            Case(
                When(entry_type='hold', then=F('amount_paise')),
                default=0,
                output_field=BigIntegerField()
            )
        ),
        unholds=Sum(
            Case(
                When(entry_type='unhold', then=F('amount_paise')),
                default=0,
                output_field=BigIntegerField()
            )
        ),
    )
    credits = entries['credits'] or 0
    debits = entries['debits'] or 0
    holds = entries['holds'] or 0
    unholds = entries['unholds'] or 0

    total_paise = credits - debits  # net money ever received minus money paid out
    held_paise = holds - unholds    # currently locked
    available_paise = total_paise - held_paise

    return {
        'available_paise': available_paise,
        'held_paise': held_paise,
        'total_paise': total_paise,
    }


def transition_state(payout, new_status):
    """
    Single place where state changes happen. This is intentional.

    VALID_TRANSITIONS acts as an allowlist. Any transition not explicitly listed
    raises before touching the database. failed → completed is blocked because
    valid_next for 'failed' is []. completed → pending is blocked for the same reason.

    Without this guard, a retry loop on a completed payout could accidentally
    re-debit a merchant. That bug would be invisible until someone noticed their
    balance was wrong — classic "works fine until it doesn't" financial bug.
    """
    valid_next = PayoutRequest.VALID_TRANSITIONS.get(payout.status, [])
    if new_status not in valid_next:
        raise InvalidTransitionError(
            f"Cannot transition {payout.status} -> {new_status} for payout {payout.id}"
        )
    payout.status = new_status
    payout.updated_at = timezone.now()
    payout.save(update_fields=['status', 'updated_at'])


@transaction.atomic
def create_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    """
    Two properties this function must guarantee simultaneously:

    1. ATOMICITY: the payout row and the hold ledger entry are created together
       or not at all. A crash between the two writes must leave no partial state.

    2. NO OVERDRAFT: we cannot check balance then deduct as two separate operations.
       Another request could pass the check in the gap before our deduct — classic
       TOCTOU (time-of-check to time-of-use) race condition.

    Solution: SELECT FOR UPDATE on the merchant row. PostgreSQL holds a row-level
    exclusive lock until this transaction commits. Any other call to create_payout
    for the same merchant blocks at the .get() line. When it unblocks it re-reads
    the balance and correctly sees the updated ledger.

    Why not threading.Lock()? It is per-process in-memory state. Gunicorn runs
    multiple worker processes with separate memory spaces. A lock in worker 1 is
    completely invisible to worker 2. Only the database can coordinate across all
    processes — which is why this lock must live in Postgres, not Python.
    """
    if amount_paise <= 0:
        raise ValueError("amount_paise must be positive")

    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    # Balance query runs AFTER the lock is acquired so it reads committed post-lock state.
    balance = get_balance_breakdown(merchant_id)
    available = balance['available_paise']

    if available < amount_paise:
        raise InsufficientFundsError(
            f"Insufficient funds. Available: {available} paise, Requested: {amount_paise} paise"
        )

    payout = PayoutRequest.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        bank_account_id=bank_account_id,
        status='pending',
        idempotency_key=idempotency_key,
    )

    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type='hold',
        amount_paise=amount_paise,
        payout=payout,
        description=f"Hold for payout {payout.id}",
    )

    return payout
