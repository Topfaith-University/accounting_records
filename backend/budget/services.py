from datetime import datetime
from django.utils import timezone

from django.db.models import Sum, Case, When, F, Value, FloatField
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from .models import Budget, BudgetLine


def approve_budget(budget: Budget, approver) -> Budget:
    if budget.status == 'APPROVED':
        raise ValidationError('Already approved.')
    budget.status = 'APPROVED'
    budget.approved_by = approver
    budget.approved_at = timezone.now()
    budget.save()
    return budget


def compute_variance(budget_id: str, company_id: str) -> list:
    """Budgeted vs. actual per line. Deliberately one query per line (not a
    single 2-hop conditional-sum join) — obviously correct over a small
    per-budget line count, avoiding the double-join-inflates-the-sum risk of
    two Sum(Case(...)) annotations sharing one reverse-FK join.
    """
    lines = (
        BudgetLine.objects
        .filter(budget_id=budget_id, budget__company_id=company_id)
        .select_related('account')
        .order_by('account__code')
    )
    result = []
    for line in lines:
        account = line.account
        agg = account.journal_lines.filter(
            entry__status='POSTED', entry__company_id=company_id,
        ).aggregate(
            debits=Coalesce(Sum(Case(
                When(side='DEBIT', then=F('amount')), default=Value(0.0), output_field=FloatField(),
            )), 0.0),
            credits=Coalesce(Sum(Case(
                When(side='CREDIT', then=F('amount')), default=Value(0.0), output_field=FloatField(),
            )), 0.0),
        )
        debits = agg['debits'] or 0.0
        credits = agg['credits'] or 0.0
        if account.normal_balance == 'DEBIT':
            actual = round(debits - credits, 2)
        else:
            actual = round(credits - debits, 2)
        budgeted = line.budgeted_amount or 0.0
        variance = round(budgeted - actual, 2)
        result.append({
            'account_id': account.account_id,
            'code': account.code,
            'name': account.name,
            'account_type': account.account_type,
            'budgeted': budgeted,
            'actual': actual,
            'variance': variance,
            'variance_pct': round(variance / budgeted * 100, 1) if budgeted else None,
        })
    return result
