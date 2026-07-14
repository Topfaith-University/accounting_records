from neomodel import (
    StructuredNode, StringProperty, BooleanProperty,
    FloatProperty, DateProperty, DateTimeProperty,
    UniqueIdProperty, RelationshipTo, RelationshipFrom, One, ZeroOrOne
)


class Vendor(StructuredNode):
    vendor_id = UniqueIdProperty()
    name = StringProperty(required=True)
    email = StringProperty(default='')
    phone = StringProperty(default='')
    address = StringProperty(default='')
    is_active = BooleanProperty(default=True)
    created_at = DateTimeProperty(default_now=True)

    invoices = RelationshipFrom('PurchaseInvoice', 'FROM_VENDOR')


class PurchaseInvoice(StructuredNode):
    invoice_id = UniqueIdProperty()
    invoice_number = StringProperty(unique_index=True, required=True)
    date = DateProperty(required=True)
    due_date = DateProperty(required=True)
    description = StringProperty(default='')
    status = StringProperty(
        choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('PAID', 'Paid'), ('VOID', 'Void')],
        default='DRAFT'
    )
    total_amount = FloatProperty(default=0.0)
    amount_paid = FloatProperty(default=0.0)
    created_by = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    vendor = RelationshipTo('Vendor', 'FROM_VENDOR', cardinality=One)
    ap_account = RelationshipTo('accounts.models.Account', 'PAYABLE_TO', cardinality=One)
    lines = RelationshipTo('PurchaseInvoiceLine', 'HAS_LINE')
    journal_entry = RelationshipTo('journals.models.JournalEntry', 'HAS_JOURNAL_ENTRY', cardinality=ZeroOrOne)
    payments = RelationshipFrom('APPayment', 'PAYS_INVOICE')


class PurchaseInvoiceLine(StructuredNode):
    line_id = UniqueIdProperty()
    description = StringProperty(default='')
    quantity = FloatProperty(default=1.0)
    unit_price = FloatProperty(default=0.0)
    amount = FloatProperty(required=True)

    expense_account = RelationshipTo('accounts.models.Account', 'CHARGES_EXPENSE', cardinality=One)


class Item(StructuredNode):
    item_id = UniqueIdProperty()
    name = StringProperty(required=True)
    description = StringProperty(default='')
    unit_price = FloatProperty(default=0.0)
    item_type = StringProperty(
        choices=[('PRODUCT', 'Product'), ('SERVICE', 'Service')],
        default='SERVICE'
    )
    is_active = BooleanProperty(default=True)
    created_at = DateTimeProperty(default_now=True)

    vendor = RelationshipTo('Vendor', 'SUPPLIED_BY', cardinality=ZeroOrOne)
    expense_account = RelationshipTo('accounts.models.Account', 'DEFAULT_EXPENSE', cardinality=ZeroOrOne)
    revenue_account = RelationshipTo('accounts.models.Account', 'DEFAULT_REVENUE', cardinality=ZeroOrOne)


class APPayment(StructuredNode):
    payment_id = UniqueIdProperty()
    payment_date = DateProperty(required=True)
    amount = FloatProperty(required=True)
    reference = StringProperty(default='')
    created_by = StringProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    invoice = RelationshipTo('PurchaseInvoice', 'PAYS_INVOICE', cardinality=One)
    bank_account = RelationshipTo('banks.models.BankAccount', 'PAID_FROM', cardinality=One)
    journal_entry = RelationshipTo('journals.models.JournalEntry', 'HAS_JOURNAL_ENTRY', cardinality=ZeroOrOne)
