from rest_framework import serializers
from .models import Account
from .enums import AccountType


class AccountSerializer(serializers.Serializer):
    account_id = serializers.CharField(read_only=True)
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=200)
    account_type = serializers.ChoiceField(choices=[t.value for t in AccountType])
    normal_balance = serializers.ChoiceField(choices=['DEBIT', 'CREDIT'])
    description = serializers.CharField(default='', allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    is_system = serializers.BooleanField(default=False, read_only=True)
    parent_id = serializers.CharField(write_only=True, required=False, allow_null=True)
    balance = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_balance(self, obj):
        from .services import compute_account_balance
        return compute_account_balance(obj.account_id)

    def create(self, validated_data):
        parent_id = validated_data.pop('parent_id', None)
        account = Account(**validated_data)
        account.save()
        if parent_id:
            parent = Account.nodes.get_or_none(account_id=parent_id)
            if parent:
                account.parent.connect(parent)
        return account

    def update(self, instance, validated_data):
        validated_data.pop('parent_id', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
