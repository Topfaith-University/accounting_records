from django.db import models
from neomodel import StructuredNode, StringProperty, RelationshipTo, FloatProperty, DateTimeProperty, UniqueIdProperty
from .enums import AccountType

# Create your models here.


class Account(StructuredNode):
    account_id = UniqueIdProperty()
    name = StringProperty(required=True)
    account_type = StringProperty(choices=AccountType.choices(), required=True)
    balance = FloatProperty(default=0.0)
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)
