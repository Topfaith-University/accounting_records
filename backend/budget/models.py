from neomodel import (
    StructuredNode, StringProperty, FloatProperty,
    DateTimeProperty, UniqueIdProperty,
    RelationshipTo, One,
)


class Budget(StructuredNode):
    budget_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    name = StringProperty(required=True)
    fiscal_year = StringProperty(required=True)
    status = StringProperty(
        choices=[('DRAFT', 'Draft'), ('APPROVED', 'Approved')], default='DRAFT'
    )
    created_by = StringProperty(required=True)
    approved_by = StringProperty(default='')
    approved_at = DateTimeProperty()
    created_at = DateTimeProperty(default_now=True)

    lines = RelationshipTo('BudgetLine', 'HAS_LINE')


class BudgetLine(StructuredNode):
    line_id = UniqueIdProperty()
    company_id = StringProperty(required=True, index=True)
    budgeted_amount = FloatProperty(required=True)
    created_at = DateTimeProperty(default_now=True)

    account = RelationshipTo('accounts.models.Account', 'FOR_ACCOUNT', cardinality=One)
