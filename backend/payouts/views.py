import uuid
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
import redis
from decouple import config

from .models import Merchant, LedgerEntry, PayoutRequest, IdempotencyRecord
from .serializers import (
    LedgerEntrySerializer, PayoutRequestSerializer,
    CreatePayoutSerializer, BalanceSerializer
)
from .services import create_payout, get_balance_breakdown
from .exceptions import InsufficientFundsError, InvalidTransitionError
from .tasks import process_payout

redis_client = redis.Redis.from_url(config('REDIS_URL', default='redis://localhost:6379/0'))


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        if not username or not password:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return Response({'username': user.username})

    def delete(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        merchant = request.user.merchant
        balance = get_balance_breakdown(merchant.id)
        serializer = BalanceSerializer(balance)
        return Response(serializer.data)


class PayoutListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        merchant = request.user.merchant
        payouts = PayoutRequest.objects.filter(merchant=merchant).order_by('-created_at')[:50]
        serializer = PayoutRequestSerializer(payouts, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        Two-layer idempotency:

        Layer 1 — PostgreSQL (durable, permanent replay store):
        IdempotencyRecord stores the exact response body and HTTP status code.
        Any repeat call after the first request completes returns the cached
        response instantly without touching any business logic. This is the
        authoritative record — it survives Redis restarts.

        Layer 2 — Redis (ephemeral, handles in-flight races):
        Handles the window where two requests arrive simultaneously before either
        has finished and written its IdempotencyRecord. The first request acquires
        the Redis lock with SET NX EX (atomic set-if-not-exists). The second sees
        the lock is taken and returns 409 Conflict immediately, preventing two
        payouts being created before the DB record exists.

        Keys are scoped per merchant via unique_together = [('merchant', 'key')].
        Merchant A and merchant B can both use the same UUID key without conflict.
        """
        merchant = request.user.merchant
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate the key is a valid UUID
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return Response(
                {'error': 'Idempotency-Key must be a valid UUID v4'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check DB for existing idempotency record (authoritative store)
        try:
            record = IdempotencyRecord.objects.get(merchant=merchant, key=idempotency_key)
            if record.expires_at > timezone.now():
                # Return the exact same response as the first call
                return Response(record.response_body, status=record.response_status)
            else:
                record.delete()
        except IdempotencyRecord.DoesNotExist:
            pass

        # Redis lock to handle concurrent requests with the same key
        lock_key = f"idem_lock:{merchant.id}:{idempotency_key}"
        # SET key value NX EX — only set if not exists, expire in 30s
        acquired = redis_client.set(lock_key, "1", nx=True, ex=30)

        if not acquired:
            return Response(
                {'error': 'A request with this Idempotency-Key is already in flight. Retry after a moment.'},
                status=status.HTTP_409_CONFLICT
            )

        try:
            serializer = CreatePayoutSerializer(data=request.data)
            if not serializer.is_valid():
                resp_data = serializer.errors
                resp_status = status.HTTP_400_BAD_REQUEST
                IdempotencyRecord.objects.create(
                    merchant=merchant,
                    key=idempotency_key,
                    response_body=resp_data,
                    response_status=resp_status,
                    expires_at=timezone.now() + timedelta(hours=24),
                )
                return Response(resp_data, status=resp_status)

            payout = create_payout(
                merchant_id=merchant.id,
                amount_paise=serializer.validated_data['amount_paise'],
                bank_account_id=serializer.validated_data['bank_account_id'],
                idempotency_key=idempotency_key,
            )

            resp_data = PayoutRequestSerializer(payout).data
            resp_status = status.HTTP_201_CREATED

            IdempotencyRecord.objects.create(
                merchant=merchant,
                key=idempotency_key,
                response_body=resp_data,
                response_status=resp_status,
                payout=payout,
                expires_at=timezone.now() + timedelta(hours=24),
            )

            # Queue the background job
            process_payout.delay(str(payout.id))

            return Response(resp_data, status=resp_status)

        except InsufficientFundsError as e:
            resp_data = {'error': str(e)}
            resp_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            IdempotencyRecord.objects.create(
                merchant=merchant,
                key=idempotency_key,
                response_body=resp_data,
                response_status=resp_status,
                expires_at=timezone.now() + timedelta(hours=24),
            )
            return Response(resp_data, status=resp_status)

        finally:
            redis_client.delete(lock_key)


class LedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        merchant = request.user.merchant
        entries = LedgerEntry.objects.filter(merchant=merchant).order_by('-created_at')[:100]
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response(serializer.data)


class PayoutDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payout_id):
        merchant = request.user.merchant
        try:
            payout = PayoutRequest.objects.get(id=payout_id, merchant=merchant)
            return Response(PayoutRequestSerializer(payout).data)
        except PayoutRequest.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
