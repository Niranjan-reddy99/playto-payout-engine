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


def simulate_bank_settlement():
    """70% success, 20% fail, 10% hang (simulates timeout)"""
    time.sleep(1)  # simulate network latency
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
    try:
        with transaction.atomic():
            payout = PayoutRequest.objects.select_for_update().get(id=payout_id)
            if payout.status != 'pending':
                logger.info(f"Payout {payout_id} is {payout.status}, skipping")
                return

            payout.attempts += 1
            payout.last_attempted_at = timezone.now()
            payout.save(update_fields=['attempts', 'last_attempted_at'])
            transition_state(payout, 'processing')

        result = simulate_bank_settlement()
        logger.info(f"Bank result for {payout_id}: {result}")

        if result == 'hang':
            # Leave state as 'processing' — retry_stuck_payouts beat task will requeue after 30s.
            logger.warning(f"Payout {payout_id} hung in processing")
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
        # Exponential backoff: 10s, 30s, 90s (10 * 3^retry_count)
        countdown = 10 * (3 ** self.request.retries)
        logger.error(f"Error processing payout {payout_id}: {exc}. Retrying in {countdown}s")
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(name='payouts.tasks.retry_stuck_payouts')
def retry_stuck_payouts():
    """
    Celery Beat task. Runs every 60 seconds.
    Finds payouts stuck in 'processing' for >30 seconds with <3 attempts.
    """
    threshold = timezone.now() - timedelta(seconds=30)
    stuck = PayoutRequest.objects.filter(
        status='processing',
        updated_at__lt=threshold,
        attempts__lt=3,
    )
    count = stuck.count()
    if count:
        logger.info(f"Found {count} stuck payouts, requeueing")
    for payout in stuck:
        # Reset to pending so process_payout can pick it up
        with transaction.atomic():
            p = PayoutRequest.objects.select_for_update().get(id=payout.id)
            if p.status == 'processing':
                p.status = 'pending'
                p.save(update_fields=['status'])
        process_payout.delay(str(payout.id))


@shared_task(name='payouts.tasks.expire_idempotency_keys')
def expire_idempotency_keys():
    """Runs every hour. Cleans up expired idempotency records."""
    from .models import IdempotencyRecord
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=timezone.now()).delete()
    logger.info(f"Expired {deleted} idempotency records")
