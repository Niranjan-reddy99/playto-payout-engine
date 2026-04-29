from django.core.management.base import BaseCommand
from django.db.models import Sum

from payouts.models import PayoutRequest, LedgerEntry


class Command(BaseCommand):
    help = "Repairs completed payouts that still have an unreleased hold"

    def handle(self, *args, **kwargs):
        repaired = 0

        completed_payouts = PayoutRequest.objects.filter(status='completed')
        for payout in completed_payouts:
            held = LedgerEntry.objects.filter(
                payout=payout,
                entry_type='hold',
            ).aggregate(total=Sum('amount_paise'))['total'] or 0

            released = LedgerEntry.objects.filter(
                payout=payout,
                entry_type='unhold',
            ).aggregate(total=Sum('amount_paise'))['total'] or 0

            missing_release = held - released
            if missing_release <= 0:
                continue

            LedgerEntry.objects.create(
                merchant=payout.merchant,
                entry_type='unhold',
                amount_paise=missing_release,
                payout=payout,
                description=f"Repair: release hold for completed payout {payout.id}",
            )
            repaired += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Repaired completed payout {payout.id} by releasing {missing_release} paise"
                )
            )

        if repaired == 0:
            self.stdout.write("No completed payouts needed repair")
        else:
            self.stdout.write(self.style.SUCCESS(f"Repaired {repaired} completed payouts"))
