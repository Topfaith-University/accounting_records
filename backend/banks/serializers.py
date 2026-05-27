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
    current_balance = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_gl_account_id(self, obj):
        try:
            acct = obj.gl_account.single()
            return acct.account_id if acct else None
        except Exception:
            return None

    def get_current_balance(self, obj):
        try:
            acct = obj.gl_account.single()
            if not acct:
                return None
            from accounts.services import compute_account_balance
            return compute_account_balance(acct.account_id)
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
        gl_account_id = validated_data.pop('gl_account_id_input', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if 'gl_account_id_input' in self.initial_data:
            current_account = instance.gl_account.single()
            if current_account:
                instance.gl_account.disconnect(current_account)
            if gl_account_id:
                from accounts.models import Account
                new_account = Account.nodes.get_or_none(account_id=gl_account_id)
                if new_account:
                    instance.gl_account.connect(new_account)
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


class BankTransactionSplitSerializer(serializers.Serializer):
    account_id = serializers.CharField()
    amount = serializers.FloatField(min_value=0.01)
    description = serializers.CharField(default='', allow_blank=True)


class BankTransactionSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(read_only=True)
    reference = serializers.CharField(read_only=True)
    transaction_type = serializers.ChoiceField(choices=[('RECEIPT', 'Receipt'), ('PAYMENT', 'Payment'), ('TRANSFER', 'Transfer')])
    date = serializers.DateField()
    amount = serializers.FloatField(read_only=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    created_by = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    # Write-only inputs
    source_bank_id = serializers.CharField(write_only=True)
    destination_bank_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    transfer_amount = serializers.FloatField(write_only=True, required=False, allow_null=True, min_value=0.01)
    splits = BankTransactionSplitSerializer(many=True, write_only=True, required=False, default=list)

    # Read-only derived fields
    source_bank_name = serializers.SerializerMethodField()
    destination_bank_name = serializers.SerializerMethodField()
    entry_id = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()

    def get_source_bank_name(self, obj):
        try:
            ba = obj.source_bank.single()
            return ba.name if ba else None
        except Exception:
            return None

    def get_destination_bank_name(self, obj):
        try:
            ba = obj.destination_bank.single()
            return ba.name if ba else None
        except Exception:
            return None

    def get_entry_id(self, obj):
        try:
            entry = obj.journal_entry.single()
            return entry.entry_id if entry else None
        except Exception:
            return None

    def get_lines(self, obj):
        try:
            from journals.serializers import JournalLineSerializer
            entry = obj.journal_entry.single()
            if not entry:
                return []
            return JournalLineSerializer(list(entry.lines.all()), many=True).data
        except Exception:
            return []

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
