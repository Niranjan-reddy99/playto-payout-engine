import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from payouts.models import Merchant, LedgerEntry, PayoutRequest


class Command(BaseCommand):
    help = 'Seeds database with test merchants and credit history'

    def handle(self, *args, **kwargs):
        merchants_data = [
            {
                'username': 'acme_merchant',
                'password': 'testpass123',
                'name': 'Acme Design Studio',
                'email': 'acme@example.com',
                'credits': [150000, 200000, 75000, 50000],
            },
            {
                'username': 'byte_merchant',
                'password': 'testpass123',
                'name': 'ByteCraft Agency',
                'email': 'byte@example.com',
                'credits': [300000, 125000, 80000],
            },
            {
                'username': 'nova_merchant',
                'password': 'testpass123',
                'name': 'Nova Freelancer',
                'email': 'nova@example.com',
                'credits': [45000, 90000, 60000, 120000],
            },
        ]

        for m_data in merchants_data:
            user, created = User.objects.get_or_create(username=m_data['username'])
            if created:
                user.set_password(m_data['password'])
                user.save()

            merchant, _ = Merchant.objects.get_or_create(
                email=m_data['email'],
                defaults={'user': user, 'name': m_data['name']}
            )

            if LedgerEntry.objects.filter(merchant=merchant).exists():
                self.stdout.write(f"Skipping {merchant.name} - already seeded")
                continue

            for i, amount in enumerate(m_data['credits']):
                LedgerEntry.objects.create(
                    merchant=merchant,
                    entry_type='credit',
                    amount_paise=amount,
                    description=f"Customer payment #{i+1} via Stripe",
                )

            # One completed historical payout
            payout = PayoutRequest.objects.create(
                merchant=merchant,
                amount_paise=50000,
                bank_account_id="HDFC_SAVINGS_001",
                status='completed',
                idempotency_key=str(uuid.uuid4()),
                attempts=1,
            )
            LedgerEntry.objects.create(
                merchant=merchant, entry_type='hold',
                amount_paise=50000, payout=payout,
                description="Hold for historical payout"
            )
            LedgerEntry.objects.create(
                merchant=merchant, entry_type='debit',
                amount_paise=50000, payout=payout,
                description="Historical payout completed"
            )

            # One failed payout (funds should be back)
            failed_payout = PayoutRequest.objects.create(
                merchant=merchant,
                amount_paise=20000,
                bank_account_id="ICICI_001",
                status='failed',
                idempotency_key=str(uuid.uuid4()),
                attempts=3,
            )
            LedgerEntry.objects.create(
                merchant=merchant, entry_type='hold',
                amount_paise=20000, payout=failed_payout,
                description="Hold for failed payout"
            )
            LedgerEntry.objects.create(
                merchant=merchant, entry_type='unhold',
                amount_paise=20000, payout=failed_payout,
                description="Funds returned for failed payout"
            )

            self.stdout.write(self.style.SUCCESS(f"Seeded {merchant.name}"))

        self.stdout.write(self.style.SUCCESS("Seeding complete!"))
        self.stdout.write("Credentials:")
        for m in merchants_data:
            self.stdout.write(f"  username: {m['username']}  password: {m['password']}")
