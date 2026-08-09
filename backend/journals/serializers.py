from datetime import datetime

from rest_framework import serializers

from config.auth import get_active_company_id
from accounts.models import Account
from .models import JournalEntry, JournalLine, FiscalYear, AccountingPeriod, Counter


class JournalLineSerializer(serializers.ModelSerializer):
    account_id = serializers.PrimaryKeyRelatedField(source='account', queryset=Account.objects.all())
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = JournalLine
        fields = ['line_id', 'account_id', 'account_code', 'account_name', 'side', 'amount', 'description']
        read_only_fields = ['line_id']

    def validate_amount(self, value):
        if value < 0.01:
            raise serializers.ValidationError('Ensure this value is greater than or equal to 0.01.')
        return value


class JournalEntrySerializer(serializers.ModelSerializer):
    reference = serializers.CharField(max_length=50, required=False, allow_blank=True)
    entry_type = serializers.ChoiceField(
        choices=['MANUAL', 'BANK_RECON', 'AP_PAYMENT', 'AR_RECEIPT'], default='MANUAL',
    )
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    approved_by = serializers.CharField(source='approved_by.username', read_only=True, default=None)
    voided_by = serializers.CharField(source='voided_by.username', read_only=True, default=None)
    lines = JournalLineSerializer(many=True, required=False)

    class Meta:
        model = JournalEntry
        fields = [
            'entry_id', 'reference', 'date', 'description', 'status', 'entry_type',
            'total_debit', 'total_credit', 'created_by', 'approved_by', 'approved_at',
            'voided_by', 'voided_at', 'created_at', 'lines',
        ]
        read_only_fields = [
            'entry_id', 'status', 'total_debit', 'total_credit',
            'approved_at', 'voided_at', 'created_at',
        ]

    def validate_reference(self, value):
        # If reference is provided, check if it's unique within the active company
        company_id = get_active_company_id(self.context['request'])
        qs = JournalEntry.objects.filter(reference=value, company_id=company_id)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise serializers.ValidationError("A journal entry with this reference already exists.")
        return value

    def validate(self, data):
        if self.instance and 'lines' not in data:
            return data
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
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])

        # Auto-generate reference if not provided
        if not validated_data.get('reference'):
            validated_data['reference'] = self._generate_journal_entry_reference(company_id)

        entry = JournalEntry.objects.create(company_id=company_id, **validated_data)
        total_debit = 0.0
        total_credit = 0.0
        for line_data in lines_data:
            JournalLine.objects.create(company_id=company_id, entry=entry, **line_data)
            if line_data['side'] == 'DEBIT':
                total_debit += line_data['amount']
            else:
                total_credit += line_data['amount']
        entry.total_debit = total_debit
        entry.total_credit = total_credit
        entry.save()
        return entry

    def update(self, instance, validated_data):
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if lines_data is not None:
            total_debit = 0.0
            total_credit = 0.0
            instance.lines.all().delete()
            for line_data in lines_data:
                JournalLine.objects.create(company_id=company_id, entry=instance, **line_data)
                if line_data['side'] == 'DEBIT':
                    total_debit += line_data['amount']
                else:
                    total_credit += line_data['amount']
            instance.total_debit = total_debit
            instance.total_credit = total_credit

        instance.save()
        return instance

    def _generate_journal_entry_reference(self, company_id):
        """JN-YYYYMMDD-XXXX, sequence unique per company per day, via the
        shared race-safe Counter (see journals/models.py)."""
        date_prefix = datetime.now().strftime('%Y%m%d')
        seq = Counter.next(f'JN-{date_prefix}-{company_id}')
        return f"JN-{date_prefix}-{seq:04d}"


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = ['year_id', 'name', 'start_date', 'end_date', 'status', 'created_at']
        read_only_fields = ['year_id', 'status', 'created_at']

    def create(self, validated_data):
        from dateutil.relativedelta import relativedelta
        company_id = get_active_company_id(self.context['request'])
        year = FiscalYear.objects.create(company_id=company_id, **validated_data)
        start = validated_data['start_date']
        for i in range(12):
            period_start = start + relativedelta(months=i)
            period_end = period_start + relativedelta(months=1) - relativedelta(days=1)
            AccountingPeriod.objects.create(
                company_id=company_id,
                fiscal_year=year,
                name=period_start.strftime('%B %Y'),
                start_date=period_start,
                end_date=period_end,
                period_number=i + 1,
            )
        return year


class AccountingPeriodSerializer(serializers.ModelSerializer):
    fiscal_year_id = serializers.PrimaryKeyRelatedField(source='fiscal_year', read_only=True)

    class Meta:
        model = AccountingPeriod
        fields = ['period_id', 'name', 'start_date', 'end_date', 'period_number', 'status', 'fiscal_year_id']
        read_only_fields = ['period_id', 'name', 'start_date', 'end_date', 'period_number', 'status']
