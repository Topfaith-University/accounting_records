from django.conf import settings
from django.db import models

from config.ids import new_id
from users.models import Company
from accounts.models import Account


class Budget(models.Model):
    budget_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budgets')
    name = models.CharField(max_length=200)
    # Plain string, not a relation to journals.FiscalYear — pre-existing
    # inconsistency in the original schema, left as-is.
    fiscal_year = models.CharField(max_length=50)
    status = models.CharField(
        max_length=8, choices=[('DRAFT', 'Draft'), ('APPROVED', 'Approved')], default='DRAFT',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BudgetLine(models.Model):
    line_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_lines')
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='budget_lines')
    budgeted_amount = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
