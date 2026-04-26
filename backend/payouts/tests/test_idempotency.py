from django.test import TestCase, Client
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
from payouts.models import Merchant, LedgerEntry, PayoutRequest
import uuid
import json


def make_mock_redis():
    """Returns a mock Redis that always grants the lock and cleans up."""
    mock = MagicMock()
    mock.set.return_value = True   # always acquire lock
    mock.delete.return_value = 1
    return mock


class IdempotencyTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser2', password='testpass')
        self.merchant = Merchant.objects.create(
            user=self.user, name="Idempotency Test Merchant", email="idem@example.com"
        )
        LedgerEntry.objects.create(
            merchant=self.merchant, entry_type='credit',
            amount_paise=100000, description="Test credit"
        )
        self.client.login(username='testuser2', password='testpass')

    def _post_payout(self, key, amount=5000):
        return self.client.post(
            '/api/v1/payouts/',
            data=json.dumps({'amount_paise': amount, 'bank_account_id': 'ACC1'}),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    @patch('payouts.views.process_payout')
    @patch('payouts.views.redis_client', new_callable=make_mock_redis)
    def test_same_key_returns_same_payout_id(self, mock_redis, mock_task):
        key = str(uuid.uuid4())
        r1 = self._post_payout(key)
        r2 = self._post_payout(key)

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)  # idempotency replay returns same status
        self.assertEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_missing_idempotency_key_returns_400(self):
        r = self.client.post('/api/v1/payouts/',
            data=json.dumps({'amount_paise': 5000, 'bank_account_id': 'ACC1'}),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

    @patch('payouts.views.process_payout')
    @patch('payouts.views.redis_client', new_callable=make_mock_redis)
    def test_different_merchants_same_key_independent(self, mock_redis, mock_task):
        user2 = User.objects.create_user(username='testuser3', password='testpass')
        merchant2 = Merchant.objects.create(
            user=user2, name="Merchant 2", email="m2@example.com"
        )
        LedgerEntry.objects.create(
            merchant=merchant2, entry_type='credit',
            amount_paise=100000, description="Credit"
        )

        key = str(uuid.uuid4())  # same key for both merchants

        r1 = self._post_payout(key)

        client2 = Client()
        client2.login(username='testuser3', password='testpass')
        r2 = client2.post('/api/v1/payouts/',
            data=json.dumps({'amount_paise': 5000, 'bank_account_id': 'ACC1'}),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        # Both should succeed and create separate payouts
        self.assertEqual(PayoutRequest.objects.count(), 2)

    @patch('payouts.views.process_payout')
    @patch('payouts.views.redis_client', new_callable=make_mock_redis)
    def test_failed_payout_idempotency_caches_failure(self, mock_redis, mock_task):
        key = str(uuid.uuid4())
        # Overdraft attempt
        r1 = self._post_payout(key, amount=999999999)
        r2 = self._post_payout(key, amount=999999999)
        self.assertEqual(r1.status_code, 422)
        self.assertEqual(r2.status_code, 422)
        self.assertEqual(r1.json(), r2.json())
