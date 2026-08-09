from datetime import date

from rest_framework import serializers

from config.auth import get_active_company_id
from .models import Account


class AccountSerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(
        source='parent', queryset=Account.objects.all(),
        required=False, allow_null=True, write_only=True,
    )
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'account_id', 'code', 'name', 'account_type', 'normal_balance', 'description',
            'opening_balance', 'is_active', 'is_system', 'parent_id', 'balance',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['account_id', 'is_system', 'created_at', 'updated_at']
        extra_kwargs = {'code': {'required': False}}

    def get_balance(self, obj):
        from .services import compute_account_balance
        return compute_account_balance(obj.account_id)

    def validate_code(self, value):
        # If code is provided, check if it's unique within the active company
        company_id = get_active_company_id(self.context['request'])
        qs = Account.objects.filter(code=value, company_id=company_id)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise serializers.ValidationError("An account with this code already exists.")
        return value

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])

        # Auto-generate code if not provided
        if not validated_data.get('code'):
            validated_data['code'] = self._generate_account_code(
                validated_data.get('account_type'), company_id
            )

        account = Account.objects.create(company_id=company_id, **validated_data)
        if account.opening_balance:
            from .services import post_opening_balance_entry
            post_opening_balance_entry(
                account, account.opening_balance, date.today(), self.context['request'].user,
            )
        return account

    def _generate_account_code(self, account_type, company_id):
        """Generate a sequential account code based on account type, unique within the company."""
        type_prefixes = {
            'Sales': '4000',
            'Cost of Sales': '5000',
            'Expenses': '6000',
            'Income Tax': '6000',
            'Non-Current Assets': '1000',
            'Current Assets': '1100',
            'Current Liabilities': '2000',
            'Non-Current Liabilities': '2100',
            "Owner's Equity": '3000',
            'Other Incomes': '4000',
        }
        prefix = type_prefixes.get(account_type, '9000')

        existing_codes = Account.objects.filter(
            code__startswith=prefix, company_id=company_id,
        ).values_list('code', flat=True)
        max_seq = 0
        for code in existing_codes:
            try:
                numeric_part = int(code[len(prefix):]) if len(code) > len(prefix) else 0
                max_seq = max(max_seq, numeric_part)
            except (ValueError, IndexError):
                continue
        return f"{prefix}{max_seq + 1:04d}"

    def update(self, instance, validated_data):
        # parent, code, and opening_balance are immutable after creation
        # (existing business rule — opening balance is a one-time posting).
        validated_data.pop('parent', None)
        validated_data.pop('code', None)
        validated_data.pop('opening_balance', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
