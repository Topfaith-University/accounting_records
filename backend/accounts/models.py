from django.db import models

from config.ids import new_id
from users.models import Company
from .enums import AccountType


class Account(models.Model):
    account_id = models.CharField(max_length=32, primary_key=True, default=new_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='accounts')
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=30, choices=AccountType.choices())
    normal_balance = models.CharField(max_length=6, choices=[('DEBIT', 'Debit'), ('CREDIT', 'Credit')])
    description = models.TextField(default='', blank=True)
    opening_balance = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
    )

    class Meta:
        unique_together = [('company', 'code')]

    def __str__(self):
        return f'{self.code} - {self.name}'
