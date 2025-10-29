from django.db import models
from neomodel import StructuredNode, StringProperty, RelationshipTo, FloatProperty, DateTimeProperty, UniqueIdProperty
# Create your models here.


class BankAccount(StructuredNode):
    bank_account_id = UniqueIdProperty()
    name = StringProperty(required=True)
    account_number = StringProperty(unique_index=True)
    # category =
    bank_name = StringProperty(required=True)
    opening_balance = FloatProperty(default=0.0)
    opening_balance_date = DateTimeProperty(default_now=True)
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
