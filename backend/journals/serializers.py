from rest_framework import serializers
from .models import JournalEntry, JournalLine, FiscalYear, AccountingPeriod


class JournalLineSerializer(serializers.Serializer):
    line_id = serializers.CharField(read_only=True)
    account_id = serializers.CharField(write_only=True)
    account_code = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    side = serializers.ChoiceField(choices=['DEBIT', 'CREDIT'])
    amount = serializers.FloatField(min_value=0.01)
    description = serializers.CharField(default='', allow_blank=True)

    def get_account_code(self, obj):
        try:
            acct = obj.account.single()
            return acct.code if acct else None
        except Exception:
            return None

    def get_account_name(self, obj):
        try:
            acct = obj.account.single()
            return acct.name if acct else None
        except Exception:
            return None


class JournalEntrySerializer(serializers.Serializer):
    entry_id = serializers.CharField(read_only=True)
    reference = serializers.CharField(max_length=50)
    date = serializers.DateField()
    description = serializers.CharField(max_length=500)
    status = serializers.CharField(read_only=True)
    entry_type = serializers.ChoiceField(
        choices=['MANUAL', 'BANK_RECON', 'AP_PAYMENT', 'AR_RECEIPT'],
        default='MANUAL'
    )
    total_debit = serializers.FloatField(read_only=True)
    total_credit = serializers.FloatField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    approved_by = serializers.CharField(read_only=True)
    approved_at = serializers.DateTimeField(read_only=True)
    voided_by = serializers.CharField(read_only=True)
    voided_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    lines = JournalLineSerializer(many=True, required=False)

    def validate(self, data):
        lines = data.get('lines', [])
        if len(lines) < 2:
            raise serializers.ValidationError({'lines': 'A journal entry requires at least 2 lines.'})
        total_debit = sum(l['amount'] for l in lines if l['side'] == 'DEBIT')
        total_credit = sum(l['amount'] for l in lines if l['side'] == 'CREDIT')
        if round(total_debit, 2) != round(total_credit, 2):
            raise serializers.ValidationError({
                'lines': f'Debits ({total_debit:.2f}) must equal credits ({total_credit:.2f}).'
            })
        return data

    def create(self, validated_data):
        from accounts.models import Account
        lines_data = validated_data.pop('lines', [])
        entry = JournalEntry(**validated_data)
        entry.save()
        total_debit = 0.0
        total_credit = 0.0
        for line_data in lines_data:
            account_id = line_data.pop('account_id')
            line = JournalLine(**line_data)
            line.save()
            entry.lines.connect(line)
            account = Account.nodes.get_or_none(account_id=account_id)
            if account:
                line.account.connect(account)
            if line_data['side'] == 'DEBIT':
                total_debit += line_data['amount']
            else:
                total_credit += line_data['amount']
        entry.total_debit = total_debit
        entry.total_credit = total_credit
        entry.save()
        return entry


class FiscalYearSerializer(serializers.Serializer):
    year_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=50)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        from datetime import date
        from dateutil.relativedelta import relativedelta
        year = FiscalYear(**validated_data)
        year.save()
        start = validated_data['start_date']
        for i in range(12):
            period_start = start + relativedelta(months=i)
            period_end = period_start + relativedelta(months=1) - relativedelta(days=1)
            period = AccountingPeriod(
                name=period_start.strftime('%B %Y'),
                start_date=period_start,
                end_date=period_end,
                period_number=i + 1,
            )
            period.save()
            period.fiscal_year.connect(year)
        return year


class AccountingPeriodSerializer(serializers.Serializer):
    period_id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    start_date = serializers.DateField(read_only=True)
    end_date = serializers.DateField(read_only=True)
    period_number = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    fiscal_year_id = serializers.SerializerMethodField()

    def get_fiscal_year_id(self, obj):
        try:
            fy = obj.fiscal_year.single()
            return fy.year_id if fy else None
        except Exception:
            return None
