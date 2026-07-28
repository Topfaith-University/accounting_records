from rest_framework import serializers
from config.auth import get_active_company_id
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            acct = instance.account.single()
            data['account_id'] = acct.account_id if acct else None
        except Exception:
            data['account_id'] = None
        return data


class JournalEntrySerializer(serializers.Serializer):
    entry_id = serializers.CharField(read_only=True)
    reference = serializers.CharField(max_length=50, required=False, allow_blank=True)
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

    def validate_reference(self, value):
        # If reference is provided, check if it's unique within the active company
        company_id = get_active_company_id(self.context['request'])
        if value and JournalEntry.nodes.filter(reference=value, company_id=company_id).first_or_none() is not None:
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
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])

        # Auto-generate reference if not provided
        if 'reference' not in validated_data or not validated_data['reference']:
            validated_data['reference'] = self._generate_journal_entry_reference(company_id)

        entry = JournalEntry(company_id=company_id, **validated_data)
        entry.save()
        total_debit = 0.0
        total_credit = 0.0
        for line_data in lines_data:
            account_id = line_data.pop('account_id')
            line = JournalLine(company_id=company_id, **line_data)
            line.save()
            entry.lines.connect(line)
            account = Account.nodes.get_or_none(account_id=account_id, company_id=company_id)
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

    def update(self, instance, validated_data):
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])

        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if lines_data is not None:
            total_debit = 0.0
            total_credit = 0.0
            for existing_line in list(instance.lines.all()):
                instance.lines.disconnect(existing_line)
                existing_line.delete()
            for line_data in lines_data:
                account_id = line_data.pop('account_id')
                line = JournalLine(company_id=company_id, **line_data)
                line.save()
                instance.lines.connect(line)
                account = Account.nodes.get_or_none(account_id=account_id, company_id=company_id)
                if account:
                    line.account.connect(account)
                if line_data['side'] == 'DEBIT':
                    total_debit += line_data['amount']
                else:
                    total_credit += line_data['amount']
            instance.total_debit = total_debit
            instance.total_credit = total_credit

        instance.save()
        return instance

    def _generate_journal_entry_reference(self, company_id):
        """Generate a journal entry reference based on date and sequence, unique within the company."""
        from datetime import datetime
        # Format: JN-YYYYMMDD-XXXX (e.g., JN-20260526-0001)
        date_prefix = datetime.now().strftime('%Y%m%d')

        # Find the highest existing sequence for today (within this company) and increment
        today_entries = JournalEntry.nodes.filter(reference__startswith=f'JN-{date_prefix}-', company_id=company_id)
        if today_entries:
            # Extract sequence number and find max
            max_seq = 0
            for entry in today_entries:
                try:
                    # Assuming format like "JN-20260526-0001"
                    suffix = entry.reference.split('-')[-1]
                    seq_num = int(suffix)
                    max_seq = max(max_seq, seq_num)
                except (ValueError, IndexError):
                    # If parsing fails, skip this entry
                    continue
            next_seq = max_seq + 1
        else:
            next_seq = 1

        return f"JN-{date_prefix}-{next_seq:04d}"


class FiscalYearSerializer(serializers.Serializer):
    year_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=50)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def create(self, validated_data):
        from dateutil.relativedelta import relativedelta
        company_id = get_active_company_id(self.context['request'])
        year = FiscalYear(company_id=company_id, **validated_data)
        year.save()
        start = validated_data['start_date']
        for i in range(12):
            period_start = start + relativedelta(months=i)
            period_end = period_start + relativedelta(months=1) - relativedelta(days=1)
            period = AccountingPeriod(
                company_id=company_id,
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
