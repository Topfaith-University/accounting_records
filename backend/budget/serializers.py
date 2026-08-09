from rest_framework import serializers
from config.auth import get_active_company_id
from accounts.models import Account
from .models import Budget, BudgetLine


class BudgetLineSerializer(serializers.ModelSerializer):
    account_id = serializers.PrimaryKeyRelatedField(source='account', queryset=Account.objects.all())
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    account_type = serializers.CharField(source='account.account_type', read_only=True)

    class Meta:
        model = BudgetLine
        fields = ['line_id', 'account_id', 'account_code', 'account_name', 'account_type', 'budgeted_amount']
        read_only_fields = ['line_id']
        extra_kwargs = {'budgeted_amount': {'min_value': 0.01}}


class BudgetSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)
    approved_by = serializers.CharField(source='approved_by.username', read_only=True, default=None)
    lines = BudgetLineSerializer(many=True, required=False)
    total_budgeted = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            'budget_id', 'name', 'fiscal_year', 'status', 'created_by', 'approved_by',
            'approved_at', 'created_at', 'lines', 'total_budgeted',
        ]
        read_only_fields = ['budget_id', 'status', 'approved_at', 'created_at']

    def get_total_budgeted(self, obj):
        return sum(l.budgeted_amount for l in obj.lines.all())

    def validate(self, data):
        lines = data.get('lines', [])
        if not lines:
            raise serializers.ValidationError({'lines': 'A budget requires at least one line.'})
        account_ids = [l['account'].account_id for l in lines]
        if len(account_ids) != len(set(account_ids)):
            raise serializers.ValidationError({'lines': 'Each account can only appear once per budget.'})
        return data

    def create(self, validated_data):
        company_id = get_active_company_id(self.context['request'])
        lines_data = validated_data.pop('lines', [])
        budget = Budget.objects.create(company_id=company_id, **validated_data)
        for line_data in lines_data:
            BudgetLine.objects.create(company_id=company_id, budget=budget, **line_data)
        return budget
