from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from payouts.models import Merchant, LedgerEntry, PayoutRequest
from payouts.tasks import process_payout, retry_pending_payouts


class PayoutTaskTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='taskuser', password='testpass')
        self.merchant = Merchant.objects.create(
            user=user, name="Task Merchant", email="task@example.com"
        )

    def create_pending_payout(self, amount_paise=5000, attempts=0, updated_at=None):
        payout = PayoutRequest.objects.create(
            merchant=self.merchant,
            amount_paise=amount_paise,
            bank_account_id='ACC1',
            status='pending',
            idempotency_key=f'key-{timezone.now().timestamp()}-{attempts}',
            attempts=attempts,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type='hold',
            amount_paise=amount_paise,
            payout=payout,
            description=f"Hold for payout {payout.id}",
        )
        if updated_at is not None:
            PayoutRequest.objects.filter(id=payout.id).update(updated_at=updated_at)
            payout.refresh_from_db()
        return payout

    @patch('payouts.tasks.simulate_bank_settlement', return_value='hang')
    def test_third_hang_marks_payout_failed_and_returns_funds(self, _mock_bank):
        payout = self.create_pending_payout(attempts=2)

        process_payout.run(str(payout.id))

        payout.refresh_from_db()
        self.assertEqual(payout.status, 'failed')
        self.assertEqual(payout.attempts, 3)
        self.assertTrue(
            LedgerEntry.objects.filter(
                payout=payout,
                entry_type='unhold',
                amount_paise=payout.amount_paise,
            ).exists()
        )

    @patch('payouts.tasks.process_payout.delay')
    def test_old_pending_payout_is_redispatched(self, mock_delay):
        payout = self.create_pending_payout(
            updated_at=timezone.now() - timedelta(seconds=31)
        )

        retry_pending_payouts()

        mock_delay.assert_called_once_with(str(payout.id))
