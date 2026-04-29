import random
import time
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import PayoutRequest, LedgerEntry
from .services import transition_state
from .exceptions import InvalidTransitionError

logger = get_task_logger(__name__)
MAX_PAYOUT_ATTEMPTS = 3


def retry_countdown_for_attempt(attempt_number):
    # attempt 1 -> 10s, attempt 2 -> 30s, attempt 3 -> terminal failure
    return 10 * (3 ** (attempt_number - 1))


def finalize_failed_payout(payout_id, reason):
    with transaction.atomic():
        payout = PayoutRequest.objects.select_for_update().get(id=payout_id)
        if payout.status != 'processing':
            return False

        # Returning held funds and marking the payout failed must be atomic.
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            entry_type='unhold',
            amount_paise=payout.amount_paise,
            payout=payout,
            description=f"Funds returned for failed payout {payout.id}: {reason}",
        )
        transition_state(payout, 'failed')
        logger.warning(f"Payout {payout_id} failed permanently: {reason}")
        return True


def requeue_processing_payout(payout_id):
    with transaction.atomic():
        payout = PayoutRequest.objects.select_for_update().get(id=payout_id)
        if payout.status == 'processing':
            payout.status = 'pending'
            payout.updated_at = timezone.now()
            payout.save(update_fields=['status', 'updated_at'])
            return True
    return False


def schedule_retry_or_fail(payout_id, attempt_number, reason):
    if attempt_number >= MAX_PAYOUT_ATTEMPTS:
        finalize_failed_payout(payout_id, f"{reason} after {attempt_number} attempts")
        return

    requeued = requeue_processing_payout(payout_id)
    if not requeued:
        logger.warning(
            f"Payout {payout_id} could not be requeued for retry because status changed"
        )
        return

    countdown = retry_countdown_for_attempt(attempt_number)
    logger.warning(f"Payout {payout_id} {reason}. Retrying in {countdown}s")
    process_payout.apply_async(args=[str(payout_id)], countdown=countdown)


def simulate_bank_settlement():
    """70% success, 20% fail, 10% hang (simulates timeout)"""
    time.sleep(0.25)  # simulate bank latency without making the demo feel sluggish
    r = random.random()
    if r < 0.70:
        return 'success'
    elif r < 0.90:
        return 'failed'
    else:
        return 'hang'


@shared_task(bind=True, max_retries=3, name='payouts.tasks.process_payout')
def process_payout(self, payout_id):
    """
    Two separate transactions here are intentional, not an oversight.

    Transaction 1 (pending → processing): short and fast. Just flips the state
    and increments attempts. We want this lock held for the minimum possible time
    so other Celery workers processing different payouts are not serialised behind it.

    Bank call happens OUTSIDE any transaction. Bank settlement can take seconds.
    Holding a DB transaction open during a network call is dangerous — it holds
    row locks and exhausts the connection pool under load. The payout sits in
    'processing' state during this window, which is exactly what the state machine
    is designed to represent.

    Transaction 2 (processing → completed/failed + ledger entry): the fund release
    (unhold) and the state transition happen in the same atomic block. It is
    impossible for a payout to reach 'failed' without the funds being returned.
    These two writes are inseparable by design.
    """
    attempt_number = None
    try:
        with transaction.atomic():
            payout = PayoutRequest.objects.select_for_update().get(id=payout_id)
            if payout.status != 'pending':
                logger.info(f"Payout {payout_id} is {payout.status}, skipping")
                return

            payout.attempts += 1
            payout.last_attempted_at = timezone.now()
            payout.save(update_fields=['attempts', 'last_attempted_at'])
            attempt_number = payout.attempts
            transition_state(payout, 'processing')

        result = simulate_bank_settlement()
        logger.info(f"Bank result for {payout_id}: {result}")

        if result == 'hang':
            schedule_retry_or_fail(payout_id, attempt_number, "hung in processing")
            return

        with transaction.atomic():
            payout = PayoutRequest.objects.select_for_update().get(id=payout_id)
            if payout.status != 'processing':
                logger.warning(f"Payout {payout_id} no longer processing, aborting")
                return

            if result == 'success':
                LedgerEntry.objects.create(
                    merchant=payout.merchant,
                    entry_type='debit',
                    amount_paise=payout.amount_paise,
                    payout=payout,
                    description=f"Payout {payout.id} completed",
                )
                transition_state(payout, 'completed')
                logger.info(f"Payout {payout_id} completed successfully")

            elif result == 'failed':
                # unhold and state transition in one atomic block — these must never be split.
                LedgerEntry.objects.create(
                    merchant=payout.merchant,
                    entry_type='unhold',
                    amount_paise=payout.amount_paise,
                    payout=payout,
                    description=f"Funds returned for failed payout {payout.id}",
                )
                transition_state(payout, 'failed')
                logger.info(f"Payout {payout_id} failed, funds returned")

    except Exception as exc:
        logger.exception(f"Error processing payout {payout_id}: {exc}")
        if attempt_number is None:
            payout = PayoutRequest.objects.filter(id=payout_id).only('attempts').first()
            attempt_number = payout.attempts if payout else 1
        schedule_retry_or_fail(payout_id, attempt_number, "raised an exception")


@shared_task(name='payouts.tasks.retry_stuck_payouts')
def retry_stuck_payouts():
    """
    Celery Beat task. Runs every 60 seconds.
    Finds payouts stuck in 'processing' for >30 seconds.
    """
    threshold = timezone.now() - timedelta(seconds=30)
    stuck = PayoutRequest.objects.filter(
        status='processing',
        updated_at__lt=threshold,
    )
    count = stuck.count()
    if count:
        logger.info(f"Found {count} stuck payouts, requeueing")
    for payout in stuck:
        schedule_retry_or_fail(payout.id, payout.attempts, "stuck in processing")


@shared_task(name='payouts.tasks.retry_pending_payouts')
def retry_pending_payouts():
    """
    Safety net for accepted payouts that were committed but not dispatched.
    Re-enqueue pending payouts older than 30 seconds.
    """
    threshold = timezone.now() - timedelta(seconds=30)
    orphaned = PayoutRequest.objects.filter(
        status='pending',
        updated_at__lt=threshold,
    )
    count = orphaned.count()
    if count:
        logger.info(f"Found {count} pending payouts to re-dispatch")
    for payout in orphaned:
        process_payout.delay(str(payout.id))


@shared_task(name='payouts.tasks.expire_idempotency_keys')
def expire_idempotency_keys():
    """Runs every hour. Cleans up expired idempotency records."""
    from .models import IdempotencyRecord
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=timezone.now()).delete()
    logger.info(f"Expired {deleted} idempotency records")
