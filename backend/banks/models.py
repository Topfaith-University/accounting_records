from neomodel import (
    StructuredNode, StringProperty, BooleanProperty,
    FloatProperty, DateProperty, DateTimeProperty,
    UniqueIdProperty, RelationshipTo, One
)


class BankAccount(StructuredNode):
    bank_account_id = UniqueIdProperty()
    name = StringProperty(required=True)
    account_number = StringProperty(unique_index=True)
    bank_name = StringProperty(required=True)
    currency = StringProperty(default='NGN')
    opening_balance = FloatProperty(default=0.0)
    opening_balance_date = DateProperty(required=True)
    is_active = BooleanProperty(default=True)
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)

    gl_account = RelationshipTo('accounts.models.Account', 'MAPS_TO_ACCOUNT', cardinality=One)
