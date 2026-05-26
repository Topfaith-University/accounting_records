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
    gl_account_id = serializers.CharField(write_only=True, required=False, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        gl_account_id = validated_data.pop('gl_account_id', None)
        bank_account = BankAccount(**validated_data)
        bank_account.save()
        if gl_account_id:
            from accounts.models import Account
            acct = Account.nodes.get_or_none(account_id=gl_account_id)
            if acct:
                bank_account.gl_account.connect(acct)
        return bank_account

    def update(self, instance, validated_data):
        validated_data.pop('gl_account_id', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
