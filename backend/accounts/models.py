from neomodel import (
    StructuredNode, StringProperty, BooleanProperty, FloatProperty,
    DateTimeProperty, UniqueIdProperty, RelationshipTo, RelationshipFrom, ZeroOrOne
)
from .enums import AccountType


class Account(StructuredNode):
    account_id = UniqueIdProperty()
    code = StringProperty(unique_index=True, required=True)
    name = StringProperty(required=True)
    account_type = StringProperty(choices=AccountType.choices(), required=True)
    normal_balance = StringProperty(choices=[('DEBIT', 'Debit'), ('CREDIT', 'Credit')], required=True)
    description = StringProperty(default='')
    opening_balance = FloatProperty(default=0.0)
    is_active = BooleanProperty(default=True)
    is_system = BooleanProperty(default=False)
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)

    parent = RelationshipTo('Account', 'CHILD_OF', cardinality=ZeroOrOne)
    children = RelationshipFrom('Account', 'CHILD_OF')
