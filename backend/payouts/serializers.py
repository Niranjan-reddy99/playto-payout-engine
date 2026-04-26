from rest_framework import serializers
from .models import Merchant, LedgerEntry, PayoutRequest


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ['id', 'entry_type', 'amount_paise', 'amount_inr', 'description', 'payout', 'created_at']

    def get_amount_inr(self, obj):
        return f"{obj.amount_paise / 100:.2f}"


class PayoutRequestSerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = PayoutRequest
        fields = ['id', 'amount_paise', 'amount_inr', 'bank_account_id', 'status', 'attempts', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'attempts', 'created_at', 'updated_at']

    def get_amount_inr(self, obj):
        return f"{obj.amount_paise / 100:.2f}"


class CreatePayoutSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.CharField(max_length=255)


class BalanceSerializer(serializers.Serializer):
    available_paise = serializers.IntegerField()
    held_paise = serializers.IntegerField()
    total_paise = serializers.IntegerField()
    available_inr = serializers.SerializerMethodField()
    held_inr = serializers.SerializerMethodField()
    total_inr = serializers.SerializerMethodField()

    def get_available_inr(self, obj):
        return f"{obj['available_paise'] / 100:.2f}"

    def get_held_inr(self, obj):
        return f"{obj['held_paise'] / 100:.2f}"

    def get_total_inr(self, obj):
        return f"{obj['total_paise'] / 100:.2f}"
