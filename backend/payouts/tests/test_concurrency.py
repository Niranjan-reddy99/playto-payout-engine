from django.test import TransactionTestCase
from django.contrib.auth.models import User
from concurrent.futures import ThreadPoolExecutor, as_completed
from payouts.models import Merchant, LedgerEntry, PayoutRequest
from payouts.services import create_payout, get_balance_breakdown
from payouts.exceptions import InsufficientFundsError
import uuid


class ConcurrentPayoutTest(TransactionTestCase):
    """
    Must use TransactionTestCase, not TestCase — and this distinction matters a lot.

    Django's TestCase wraps every test in a transaction that rolls back at the end.
    This means all database writes within the test share one open outer transaction.
    SELECT FOR UPDATE inside a nested transaction does not block other threads the
    same way as in production — they are all already inside the same outer transaction,
    so Postgres does not treat them as competing transactions.

    I discovered this the hard way: the concurrency test passed even with broken
    locking code when using TestCase. Both threads sailed through the balance check
    and created two payouts. Switching to TransactionTestCase immediately exposed
    the race condition — the broken version failed, the SELECT FOR UPDATE version
    passed. TransactionTestCase truncates tables between tests instead of rolling
    back, which is slower but matches production behaviour exactly.

    For any test that involves concurrent DB access or locking, TransactionTestCase
    is the only correct choice.
    """

    def setUp(self):
        user = User.objects.create_user(username='testuser', password='testpass')
        self.merchant = Merchant.objects.create(
            user=user, name="Test Merchant", email="test@example.com"
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type='credit',
            amount_paise=10000,
            description="Test credit"
        )

    def test_concurrent_60_rupee_payouts_on_100_rupee_balance(self):
        """
        Two concurrent requests each trying 6000 paise (60 INR).
        Balance is 10000 paise (100 INR).
        Exactly ONE must succeed. ONE must be rejected.
        """
        results = []

        def attempt(key):
            try:
                create_payout(
                    merchant_id=self.merchant.id,
                    amount_paise=6000,
                    bank_account_id="TEST_BANK",
                    idempotency_key=key,
                )
                return 'success'
            except InsufficientFundsError:
                return 'rejected'

        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(attempt, str(uuid.uuid4())) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(sorted(results), ['rejected', 'success'],
            "Expected exactly one success and one rejection")

        balance = get_balance_breakdown(self.merchant.id)
        self.assertEqual(balance['held_paise'], 6000,
            "Exactly 6000 paise should be held")
        self.assertEqual(balance['available_paise'], 4000,
            "4000 paise should remain available")
        self.assertEqual(PayoutRequest.objects.count(), 1,
            "Only one payout should be created")

    def test_three_concurrent_requests_only_one_succeeds(self):
        """Edge case: triple concurrent requests"""
        results = []

        def attempt(key):
            try:
                create_payout(self.merchant.id, 8000, "BANK", key)
                return 'success'
            except InsufficientFundsError:
                return 'rejected'

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(attempt, str(uuid.uuid4())) for _ in range(3)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(results.count('success'), 1)
        self.assertEqual(results.count('rejected'), 2)
