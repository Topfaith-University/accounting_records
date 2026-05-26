from rest_framework import serializers
from .models import BankAccount


class BankAccountSerializer(serializers.Serializer):
    bank_account_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    account_number = serializers.CharField(max_length=50)
    bank_name = serializers.CharField(max_length=200)
    currency = serializers.CharField(default='NGN')
    opening_balance = serializers.FloatField(default=0.0)
    opening_balance_date = serializers.DateField()
    is_active = serializers.BooleanField(default=True)
    gl_account_id_input = serializers.CharField(write_only=True, required=False, allow_null=True)
    gl_account_id = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_gl_account_id(self, obj):
        try:
            acct = obj.gl_account.single()
            return acct.account_id if acct else None
        except Exception:
            return None

    def create(self, validated_data):
        gl_account_id = validated_data.pop('gl_account_id_input', None)
        bank_account = BankAccount(**validated_data)
        bank_account.save()
        if gl_account_id:
            from accounts.models import Account
            acct = Account.nodes.get_or_none(account_id=gl_account_id)
            if acct:
                bank_account.gl_account.connect(acct)
        return bank_account

    def update(self, instance, validated_data):
        validated_data.pop('gl_account_id_input', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class BankReconciliationSerializer(serializers.Serializer):
    reconciliation_id = serializers.CharField(read_only=True)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    statement_balance = serializers.FloatField()
    status = serializers.CharField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    bank_account_id = serializers.SerializerMethodField()

    def get_bank_account_id(self, obj):
        try:
            ba = obj.bank_account.single()
            return ba.bank_account_id if ba else None
        except Exception:
            return None

    def create(self, validated_data):
        from .models import BankReconciliation
        bank_account = validated_data.pop('bank_account')
        recon = BankReconciliation(**validated_data)
        recon.save()
        recon.bank_account.connect(bank_account)
        return recon
