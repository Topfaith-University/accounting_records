from neomodel import (
    StructuredNode, StringProperty, FloatProperty, BooleanProperty,
    DateProperty, DateTimeProperty, IntegerProperty, UniqueIdProperty,
    RelationshipTo, RelationshipFrom, ZeroOrOne, One, ZeroOrMore
)


class FiscalYear(StructuredNode):
    year_id = UniqueIdProperty()
    name = StringProperty(required=True)
    start_date = DateProperty(required=True)
    end_date = DateProperty(required=True)
    status = StringProperty(
        choices=[('OPEN', 'Open'), ('CLOSED', 'Closed')], default='OPEN'
    )
    created_at = DateTimeProperty(default_now=True)

    periods = RelationshipFrom('AccountingPeriod', 'BELONGS_TO_YEAR')


class AccountingPeriod(StructuredNode):
    period_id = UniqueIdProperty()
    name = StringProperty(required=True)
    start_date = DateProperty(required=True)
    end_date = DateProperty(required=True)
    period_number = IntegerProperty(required=True)
    status = StringProperty(
        choices=[('OPEN', 'Open'), ('CLOSED', 'Closed')], default='OPEN'
    )

    fiscal_year = RelationshipTo('FiscalYear', 'BELONGS_TO_YEAR', cardinality=One)


class JournalEntry(StructuredNode):
    entry_id = UniqueIdProperty()
    reference = StringProperty(unique_index=True, required=True)
    date = DateProperty(required=True)
    description = StringProperty(required=True)
    status = StringProperty(
        choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('VOID', 'Void')],
        default='DRAFT'
    )
    entry_type = StringProperty(
        choices=[
            ('MANUAL', 'Manual'),
            ('BANK_RECON', 'Bank Reconciliation'),
            ('AP_PAYMENT', 'AP Payment'),
            ('AR_RECEIPT', 'AR Receipt'),
        ],
        default='MANUAL'
    )
    total_debit = FloatProperty(default=0.0)
    total_credit = FloatProperty(default=0.0)
    created_by = StringProperty(required=True)
    approved_by = StringProperty(default='')
    approved_at = DateTimeProperty()
    voided_by = StringProperty(default='')
    voided_at = DateTimeProperty()
    created_at = DateTimeProperty(default_now=True)
    updated_at = DateTimeProperty(default_now=True)

    lines = RelationshipTo('JournalLine', 'HAS_LINE')
    period = RelationshipTo('AccountingPeriod', 'IN_PERIOD', cardinality=ZeroOrOne)


class JournalLine(StructuredNode):
    line_id = UniqueIdProperty()
    side = StringProperty(
        choices=[('DEBIT', 'Debit'), ('CREDIT', 'Credit')], required=True
    )
    amount = FloatProperty(required=True)
    description = StringProperty(default='')
    created_at = DateTimeProperty(default_now=True)

    account = RelationshipTo('accounts.models.Account', 'AFFECTS_ACCOUNT', cardinality=One)
