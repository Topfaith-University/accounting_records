from neomodel import (
    StructuredNode, StringProperty, BooleanProperty,
    FloatProperty, DateProperty, DateTimeProperty,
    UniqueIdProperty, RelationshipTo, One, ZeroOrOne
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


class BankReconciliation(StructuredNode):
    reconciliation_id = UniqueIdProperty()
    period_start = DateProperty(required=True)
    period_end = DateProperty(required=True)
    statement_balance = FloatProperty(required=True)
    status = StringProperty(
        choices=[('DRAFT', 'Draft'), ('COMPLETED', 'Completed')], default='DRAFT'
    )
    created_by = StringProperty(required=True)
    completed_at = DateTimeProperty()
    created_at = DateTimeProperty(default_now=True)

    bank_account = RelationshipTo('BankAccount', 'FOR_ACCOUNT', cardinality=One)
    reconciled_lines = RelationshipTo('journals.models.JournalLine', 'RECONCILES')


class BankTransaction(StructuredNode):
    transaction_id = UniqueIdProperty()
    reference = StringProperty(unique_index=True, required=True)
    transaction_type = StringProperty(
        choices=[('RECEIPT', 'Receipt'), ('PAYMENT', 'Payment'), ('TRANSFER', 'Transfer')],
        required=True
    )
    date = DateProperty(required=True)
    amount = FloatProperty(required=True)
    description = StringProperty(default='')
    created_by = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)

    source_bank = RelationshipTo('BankAccount', 'FROM_BANK', cardinality=One)
    destination_bank = RelationshipTo('BankAccount', 'TO_BANK', cardinality=ZeroOrOne)
    journal_entry = RelationshipTo('journals.models.JournalEntry', 'GENERATES_ENTRY', cardinality=One)
