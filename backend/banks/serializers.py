from rest_framework import serializers
from config.auth import get_active_company_id
from accounts.models import Account
from .models import BankAccount, BankReconciliation, BankTransaction


class BankAccountSerializer(serializers.ModelSerializer):
    gl_account_id_input = serializers.PrimaryKeyRelatedField(
        source='gl_account', queryset=Account.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    gl_account_id = serializers.PrimaryKeyRelatedField(source='gl_account', read_only=True)
    current_balance = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = [
            'bank_account_id', 'name', 'account_number', 'bank_name', 'currency',
            'opening_balance', 'opening_balance_date', 'is_active',
            'gl_account_id_input', 'gl_account_id', 'current_balance', 'created_at', 'updated_at',
        ]
        read_only_fields = ['bank_account_id', 'created_at', 'updated_at']

    def get_current_balance(self, obj):
        try:
            from .services import compute_bank_current_balance
            return compute_bank_current_balance(obj.bank_account_id, obj.company_id)
        except Exception:
            return None

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        gl_account = validated_data.pop('gl_account', None)
        bank_account = BankAccount.objects.create(company_id=company_id, gl_account=gl_account, **validated_data)
        if gl_account and bank_account.opening_balance:
            from accounts.services import post_opening_balance_entry
            post_opening_balance_entry(
                gl_account, bank_account.opening_balance, bank_account.opening_balance_date,
                self.context['request'].user,
                reference_key=bank_account.bank_account_id,
            )
        return bank_account

    def update(self, instance, validated_data):
        # Immutable after creation, like AccountSerializer.update()'s `code`/`opening_balance`
        # handling — editing it here would desync the bank's displayed opening_balance from
        # the GL posting already made (post_opening_balance_entry only ever posts once).
        validated_data.pop('opening_balance', None)
        new_gl_account = validated_data.pop('gl_account', 'UNCHANGED')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if new_gl_account != 'UNCHANGED' and new_gl_account and new_gl_account.account_id != instance.gl_account_id:
            instance.gl_account = new_gl_account
            instance.save(update_fields=['gl_account'])
            if instance.opening_balance:
                from accounts.services import post_opening_balance_entry
                post_opening_balance_entry(
                    new_gl_account, instance.opening_balance, instance.opening_balance_date,
                    self.context['request'].user,
                    reference_key=instance.bank_account_id,
                )
        return instance


class BankReconciliationSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    bank_account_id = serializers.PrimaryKeyRelatedField(source='bank_account', read_only=True)

    class Meta:
        model = BankReconciliation
        fields = [
            'reconciliation_id', 'period_start', 'period_end', 'statement_balance',
            'status', 'created_by', 'completed_at', 'created_at', 'bank_account_id',
        ]
        read_only_fields = ['reconciliation_id', 'status', 'completed_at', 'created_at']


class BankTransactionSplitSerializer(serializers.Serializer):
    account_id = serializers.CharField()
    amount = serializers.FloatField(min_value=0.01)
    description = serializers.CharField(default='', allow_blank=True)


class BankTransactionSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)

    # Write-only inputs
    source_bank_id = serializers.CharField(write_only=True)
    destination_bank_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    transfer_amount = serializers.FloatField(write_only=True, required=False, allow_null=True, min_value=0.01)
    splits = BankTransactionSplitSerializer(many=True, write_only=True, required=False, default=list)
    vendor_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    customer_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    # Read-only derived fields
    source_bank_name = serializers.CharField(source='source_bank.name', read_only=True, default=None)
    destination_bank_name = serializers.CharField(source='destination_bank.name', read_only=True, default=None)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    entry_id = serializers.PrimaryKeyRelatedField(source='journal_entry', read_only=True)
    lines = serializers.SerializerMethodField()

    class Meta:
        model = BankTransaction
        fields = [
            'transaction_id', 'reference', 'transaction_type', 'date', 'amount', 'description',
            'created_by', 'created_at',
            'source_bank_id', 'destination_bank_id', 'transfer_amount', 'splits', 'vendor_id', 'customer_id',
            'source_bank_name', 'destination_bank_name', 'vendor_name', 'customer_name', 'entry_id', 'lines',
        ]
        read_only_fields = ['transaction_id', 'reference', 'amount', 'created_at']

    def get_lines(self, obj):
        from journals.serializers import JournalLineSerializer
        if not obj.journal_entry_id:
            return []
        return JournalLineSerializer(obj.journal_entry.lines.select_related('account').all(), many=True).data

    def validate(self, data):
        txn_type = data.get('transaction_type')
        if txn_type == 'TRANSFER':
            if not data.get('destination_bank_id'):
                raise serializers.ValidationError({'destination_bank_id': 'Required for TRANSFER.'})
            if not data.get('transfer_amount'):
                raise serializers.ValidationError({'transfer_amount': 'Required for TRANSFER.'})
        else:
            if not data.get('splits'):
                raise serializers.ValidationError({'splits': 'At least one split is required for RECEIPT/PAYMENT.'})
        return data
