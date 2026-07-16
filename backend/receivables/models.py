from neomodel import (
    StructuredNode, StringProperty, BooleanProperty,
    FloatProperty, DateProperty, DateTimeProperty,
    UniqueIdProperty, RelationshipTo, RelationshipFrom, One, ZeroOrOne
)


class Customer(StructuredNode):
    customer_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    name = StringProperty(required=True)
    email = StringProperty(default='')
    phone = StringProperty(default='')
    address = StringProperty(default='')
    customer_type = StringProperty(
        choices=[('STUDENT', 'Student'), ('EXTERNAL', 'External')],
        default='EXTERNAL'
    )
    is_active = BooleanProperty(default=True)
    created_at = DateTimeProperty(default_now=True)

    invoices = RelationshipFrom('SalesInvoice', 'BILLED_TO')


class SalesInvoice(StructuredNode):
    invoice_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    invoice_number = StringProperty(required=True)
    date = DateProperty(required=True)
    due_date = DateProperty(required=True)
    description = StringProperty(default='')
    status = StringProperty(
        choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('PAID', 'Paid'), ('VOID', 'Void')],
        default='DRAFT'
    )
    total_amount = FloatProperty(default=0.0)
    amount_received = FloatProperty(default=0.0)
    created_by = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    customer = RelationshipTo('Customer', 'BILLED_TO', cardinality=One)
    ar_account = RelationshipTo('accounts.models.Account', 'RECEIVABLE_FROM', cardinality=One)
    lines = RelationshipTo('SalesInvoiceLine', 'HAS_LINE')
    journal_entry = RelationshipTo('journals.models.JournalEntry', 'HAS_JOURNAL_ENTRY', cardinality=ZeroOrOne)
    receipts = RelationshipFrom('ARReceipt', 'RECEIVES_PAYMENT_FOR')


class SalesInvoiceLine(StructuredNode):
    line_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    description = StringProperty(default='')
    quantity = FloatProperty(default=1.0)
    unit_price = FloatProperty(default=0.0)
    amount = FloatProperty(required=True)

    revenue_account = RelationshipTo('accounts.models.Account', 'EARNS_REVENUE', cardinality=One)


class ARReceipt(StructuredNode):
    receipt_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    receipt_date = DateProperty(required=True)
    amount = FloatProperty(required=True)
    reference = StringProperty(default='')
    created_by = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    invoice = RelationshipTo('SalesInvoice', 'RECEIVES_PAYMENT_FOR', cardinality=One)
    bank_account = RelationshipTo('banks.models.BankAccount', 'RECEIVED_INTO', cardinality=One)
    journal_entry = RelationshipTo('journals.models.JournalEntry', 'HAS_JOURNAL_ENTRY', cardinality=ZeroOrOne)
