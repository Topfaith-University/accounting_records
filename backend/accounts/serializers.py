from rest_framework import serializers
from .models import Account
from .enums import AccountType


class AccountSerializer(serializers.Serializer):
    account_id = serializers.CharField(read_only=True)
    code = serializers.CharField(max_length=20, required=False)
    name = serializers.CharField(max_length=200)
    account_type = serializers.ChoiceField(choices=[t.value for t in AccountType])
    normal_balance = serializers.ChoiceField(choices=['DEBIT', 'CREDIT'])
    description = serializers.CharField(default='', allow_blank=True)
    opening_balance = serializers.FloatField(default=0.0)
    is_active = serializers.BooleanField(default=True)
    is_system = serializers.BooleanField(default=False, read_only=True)
    parent_id = serializers.CharField(write_only=True, required=False, allow_null=True)
    balance = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_balance(self, obj):
        from .services import compute_account_balance
        return compute_account_balance(obj.account_id)

    def validate_code(self, value):
        # If code is provided, check if it's unique
        if value and Account.nodes.filter(code=value).exists():
            raise serializers.ValidationError("An account with this code already exists.")
        return value

    def create(self, validated_data):
        parent_id = validated_data.pop('parent_id', None)

        # Auto-generate code if not provided
        if 'code' not in validated_data or not validated_data['code']:
            validated_data['code'] = self._generate_account_code(
                validated_data.get('account_type')
            )

        account = Account(**validated_data)
        account.save()
        if validated_data.get('opening_balance'):
            from .services import post_opening_balance_entry
            from datetime import date
            post_opening_balance_entry(account, account.opening_balance, date.today(), self.context['request'].user.username)
        if parent_id:
            parent = Account.nodes.get_or_none(account_id=parent_id)
            if parent:
                account.parent.connect(parent)
        return account

    def _generate_account_code(self, account_type):
        """Generate a sequential account code based on account type."""
        # Define account type to code prefix mapping
        type_prefixes = {
            'Sales': '4000',           # Revenue
            'Cost of Sales': '5000',   # Cost of Goods Sold
            'Expenses': '6000',        # Expenses
            'Income Tax': '6000',      # Expenses (tax)
            'Non-Current Assets': '1000', # Fixed Assets
            'Current Assets': '1100',  # Current Assets
            'Current Liabilities': '2000', # Current Liabilities
            'Non-Current Liabilities': '2100', # Long-term Liabilities
            'Owner\'s Equity': '3000', # Equity
            'Other Incomes': '4000',   # Other Revenue
        }

        prefix = type_prefixes.get(account_type, '9000')  # Default to 9000 for others

        # Find the highest existing code for this prefix and increment
        existing_accounts = Account.nodes.filter(code__startswith=prefix)
        if existing_accounts:
            # Extract numeric part and find max
            max_seq = 0
            for account in existing_accounts:
                try:
                    # Assuming format like "1001", "1002", etc.
                    numeric_part = int(account.code[len(prefix):]) if len(account.code) > len(prefix) else 0
                    max_seq = max(max_seq, numeric_part)
                except (ValueError, IndexError):
                    # If parsing fails, skip this account
                    continue
            next_seq = max_seq + 1
        else:
            next_seq = 1

        # Format code with proper padding (e.g., 1001, 1002)
        return f"{prefix}{next_seq:04d}"

    def update(self, instance, validated_data):
        validated_data.pop('parent_id', None)
        # Don't allow changing the code once set (optional business rule)
        validated_data.pop('code', None)
        validated_data.pop('opening_balance', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
