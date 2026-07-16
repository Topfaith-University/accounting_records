from rest_framework import serializers
from config.auth import get_active_company_id
from .models import Budget, BudgetLine


class BudgetLineSerializer(serializers.Serializer):
    line_id = serializers.CharField(read_only=True)
    account_id = serializers.CharField(write_only=True)
    account_code = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    account_type = serializers.SerializerMethodField()
    budgeted_amount = serializers.FloatField(min_value=0.01)

    def get_account_code(self, obj):
        try:
            return obj.account.single().code
        except Exception:
            return None

    def get_account_name(self, obj):
        try:
            return obj.account.single().name
        except Exception:
            return None

    def get_account_type(self, obj):
        try:
            return obj.account.single().account_type
        except Exception:
            return None


class BudgetSerializer(serializers.Serializer):
    budget_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200)
    fiscal_year = serializers.CharField(max_length=50)
    status = serializers.CharField(read_only=True)
    created_by = serializers.CharField(read_only=True)
    approved_by = serializers.CharField(read_only=True)
    approved_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    lines = BudgetLineSerializer(many=True, required=False)
    total_budgeted = serializers.SerializerMethodField()

    def get_total_budgeted(self, obj):
        try:
            return sum(l.budgeted_amount for l in obj.lines.all())
        except Exception:
            return 0.0

    def validate(self, data):
        lines = data.get('lines', [])
        if not lines:
            raise serializers.ValidationError({'lines': 'A budget requires at least one line.'})
        account_ids = [l['account_id'] for l in lines]
        if len(account_ids) != len(set(account_ids)):
            raise serializers.ValidationError({'lines': 'Each account can only appear once per budget.'})
        return data

    def create(self, validated_data):
        from accounts.models import Account
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])
        budget = Budget(company_id=company_id, **validated_data)
        budget.save()
        for line_data in lines_data:
            account_id = line_data.pop('account_id')
            line = BudgetLine(company_id=company_id, **line_data)
            line.save()
            budget.lines.connect(line)
            account = Account.nodes.get_or_none(account_id=account_id, company_id=company_id)
            if account:
                line.account.connect(account)
        return budget
