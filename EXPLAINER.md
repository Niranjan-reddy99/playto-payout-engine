# EXPLAINER.md — Playto Payout Engine

This document explains the five hardest design decisions in this codebase. Each section shows the actual code and the reasoning behind it.

---

## 1. The Ledger: Why No `balance` Column

The balance is never stored. It is always derived from ledger entries via a single aggregation query.

```python
# payouts/services.py — get_balance_breakdown()
entries = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    credits=Sum(Case(When(entry_type='credit', then=F('amount_paise')), default=0, output_field=BigIntegerField())),
    debits=Sum(Case(When(entry_type='debit', then=F('amount_paise')), default=0, output_field=BigIntegerField())),
    holds=Sum(Case(When(entry_type='hold', then=F('amount_paise')), default=0, output_field=BigIntegerField())),
    unholds=Sum(Case(When(entry_type='unhold', then=F('amount_paise')), default=0, output_field=BigIntegerField())),
)
total_paise    = credits - debits    # net money ever received minus paid out
held_paise     = holds - unholds     # currently locked for in-flight payouts
available_paise = total_paise - held_paise
```

**Why `BigIntegerField` instead of `DecimalField`?**
All amounts are stored in paise (the smallest INR unit, 1 INR = 100 paise). This means `BigIntegerField` is exact — no floating point. Converting to INR only happens at display time, never in business logic. `DecimalField` would work too, but integer arithmetic is faster and equally safe here.

**Why no stored `balance` column?**
A stored `balance` column creates a write-order dependency: you must update the balance in the same transaction as every ledger entry. Under concurrent load this is a hot-row contention bottleneck. The ledger-as-truth pattern (used by Stripe, Airbnb, etc.) means the source of truth is always the append-only ledger. You can reconstruct any balance at any point in time. The aggregation query is fast with the right index (`merchant, created_at`).

---

## 2. The Lock: `select_for_update()` and Why Python Locks Fail

```python
# payouts/services.py — create_payout()
@transaction.atomic
def create_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    # SELECT FOR UPDATE acquires a row-level exclusive lock on the merchant row.
    # Any concurrent call to this function for the same merchant will block here
    # until this transaction commits. This is database-level locking, NOT Python-level.
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    # Calculate balance INSIDE the transaction, AFTER acquiring the lock.
    # This ensures no other transaction can modify the balance between our check and our write.
    balance = get_balance_breakdown(merchant_id)
    available = balance['available_paise']

    if available < amount_paise:
        raise InsufficientFundsError(...)

    payout = PayoutRequest.objects.create(...)
    LedgerEntry.objects.create(entry_type='hold', ...)
    return payout
```

**What PostgreSQL primitive does this use?**
`SELECT ... FOR UPDATE` issues a row-level exclusive lock at the PostgreSQL level. The SQL generated is:
```sql
SELECT * FROM payouts_merchant WHERE id = %s FOR UPDATE
```
The database holds this lock until the enclosing transaction commits or rolls back. Any other transaction attempting a `SELECT FOR UPDATE` on the same merchant row will block (queue) at the database level, not the Python level.

**Why can't you use a Python threading lock (`threading.Lock`) here?**
A Python lock is per-process in-memory state. In production you run multiple Gunicorn workers (separate OS processes). Each worker has its own memory space. A `threading.Lock` in worker #1 is completely invisible to worker #2. Two concurrent HTTP requests hitting different workers would both pass the Python lock check and proceed to the overdraft simultaneously.

The database lock is shared across all processes — it lives in Postgres, not in any single worker's memory.

---

## 3. The Idempotency: Two-Layer Design

The POST `/api/v1/payouts/` endpoint uses a two-layer approach:

**Layer 1: Redis (for in-flight deduplication)**
```python
lock_key = f"idem_lock:{merchant.id}:{idempotency_key}"
acquired = redis_client.set(lock_key, "1", nx=True, ex=30)
if not acquired:
    return Response({'error': 'Request already in flight...'}, status=409)
```
`nx=True` means "only SET if Not eXists" — this is atomic at the Redis level. If two requests with the same key arrive simultaneously, exactly one gets `True`. The second gets `None` and immediately returns HTTP 409. The lock expires after 30 seconds to handle crashed workers.

**Layer 2: Database (authoritative replay store)**
```python
record = IdempotencyRecord.objects.get(merchant=merchant, key=idempotency_key)
if record.expires_at > timezone.now():
    return Response(record.response_body, status=record.response_status)
```
After the first request completes (success or failure), its full response body and status code are stored in `IdempotencyRecord`. All future replays of the same key return the exact same response — including failures. A failed-due-to-overdraft request will always return the same 422, preventing the client from retrying to drain the account.

**What happens if the second request arrives while the first is still inside the lock?**
The Redis `nx=True` check fires before acquiring the lock. The second request sees the key already set and immediately returns HTTP 409 Conflict. The client should retry after a moment. By the time it retries, the first request will have completed and written its `IdempotencyRecord` to the database, so the third attempt finds it and returns the cached response.

---

## 4. The State Machine: `VALID_TRANSITIONS`

```python
# payouts/models.py
class PayoutRequest(models.Model):
    VALID_TRANSITIONS = {
        'pending':    ['processing'],
        'processing': ['completed', 'failed'],
        'completed':  [],
        'failed':     [],
    }

# payouts/services.py
def transition_state(payout, new_status):
    valid_next = PayoutRequest.VALID_TRANSITIONS.get(payout.status, [])
    if new_status not in valid_next:
        raise InvalidTransitionError(
            f"Cannot transition {payout.status} -> {new_status} for payout {payout.id}"
        )
    payout.status = new_status
    payout.save(update_fields=['status', 'updated_at'])
```

**Why can't `failed -> completed` happen?**
Because `VALID_TRANSITIONS['failed'] = []`. When `transition_state(payout, 'completed')` is called on a failed payout, `valid_next` is an empty list. `'completed' not in []` is `True`, so `InvalidTransitionError` is raised. The only place state is ever changed is in `transition_state()`. There is no `payout.status = 'completed'` scattered anywhere else in the codebase.

This matters because a Celery task could retry after a payout already failed and was refunded. Without the state machine, a race condition could mark a refunded payout as completed and skip writing the refund ledger entry — debiting the merchant's balance without the held funds ever being released.

---

## 5. The AI Audit: What I Caught and Fixed

During development, the initial AI-generated `get_balance_breakdown` looked like this:

```python
# WRONG — vulnerable to race condition
def get_balance_breakdown_bad(merchant_id):
    entries = list(LedgerEntry.objects.filter(merchant_id=merchant_id))
    available = 0
    for entry in entries:
        if entry.entry_type == 'credit':
            available += entry.amount_paise
        elif entry.entry_type == 'debit':
            available -= entry.amount_paise
        # ... etc
    return available
```

**Why is this a race condition?**
This fetches all ledger rows into Python memory and sums them there. The fetch happens *before* `select_for_update()` has acquired the lock. Here's the exact failure sequence:

1. Request A: fetch ledger rows → sees balance = 10000
2. Request B: fetch ledger rows → sees balance = 10000 (same snapshot, no lock yet)
3. Request A: acquires `select_for_update()` lock, checks `available = 10000`, approves payout for 9000
4. Request B: acquires lock (A has committed), but its Python variable still holds `10000` — approves payout for 9000 too
5. Both payouts commit. Merchant is now 8000 paise in debt.

The stale read is outside the lock's protection window.

**The fix:** move the aggregation *inside* the `@transaction.atomic` block and run it as a single SQL query with `SUM(CASE WHEN ...)`. The query executes *after* the `SELECT FOR UPDATE` lock is acquired, so it reads the committed post-lock state. No Python-side summation, no stale reads.

```python
@transaction.atomic
def create_payout(merchant_id, ...):
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)  # lock first
    balance = get_balance_breakdown(merchant_id)  # query AFTER lock — correct
    ...
```

**A second thing I caught — TestCase vs TransactionTestCase:**

When I first wrote the concurrency test using Django's `TestCase`, it passed even with the broken Python-sum version of `get_balance_breakdown`. Both threads were approving 9000 paise payouts on a 10000 paise balance and the test still went green. I spent a while confused before I realised what was happening.

`TestCase` wraps every test in a transaction that rolls back at the end. All DB writes inside the test share one outer transaction. When two threads both run `SELECT FOR UPDATE` inside the same outer transaction, Postgres doesn't treat them as competing transactions — the lock doesn't actually block. The broken code looked correct because the test environment didn't match production at all.

Switching to `TransactionTestCase` made the test commit writes for real, exactly like production. The broken version immediately failed — both threads got through the balance check. The `select_for_update()` version passed. That's how I confirmed the locking actually worked and wasn't just getting lucky in test isolation.
