from django.core.management.base import BaseCommand, CommandError
from neomodel import db


# Every domain label across every app that now carries a company_id property.
DOMAIN_LABELS = [
    'Account',
    'BankAccount', 'BankReconciliation', 'BankTransaction',
    'FiscalYear', 'AccountingPeriod', 'JournalEntry', 'JournalLine',
    'Vendor', 'PurchaseInvoice', 'PurchaseInvoiceLine', 'Item', 'APPayment',
    'Customer', 'SalesInvoice', 'SalesInvoiceLine', 'ARReceipt',
    'Budget', 'BudgetLine',
]


class Command(BaseCommand):
    help = (
        "One-off migration: stamp company_id onto every existing Neo4j domain node "
        "that predates multi-tenancy. Safe to run multiple times (only touches nodes "
        "where company_id IS NULL)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--company-name', default='Topfaith University')

    def handle(self, *args, **options):
        from users.models import Company

        company = Company.objects.filter(name=options['company_name']).first()
        if not company:
            raise CommandError(
                f"No company named '{options['company_name']}' found. "
                "Run migrate_to_companies first."
            )

        for label in DOMAIN_LABELS:
            results, _ = db.cypher_query(
                f"""
                MATCH (n:{label})
                WHERE n.company_id IS NULL
                SET n.company_id = $company_id
                RETURN count(n) AS updated
                """,
                {'company_id': str(company.id)},
            )
            updated = results[0][0] if results else 0
            self.stdout.write(f"{label}: stamped {updated} node(s).")

        self.stdout.write(self.style.SUCCESS(
            f"Done. All existing domain data now belongs to '{company.name}' ({company.id})."
        ))
