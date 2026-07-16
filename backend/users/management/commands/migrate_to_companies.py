from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


ROLE_PRIORITY = ['Admin', 'Manager', 'Accountant', 'Staff']


class Command(BaseCommand):
    help = (
        "One-off migration: create a default company for existing (pre-multi-tenant) "
        "data, and give every existing Django user a Membership in it, with role "
        "derived from their current (global) group. Safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument('--company-name', default='Topfaith University')

    def handle(self, *args, **options):
        from users.models import Company, Membership

        company, created = Company.objects.get_or_create(name=options['company_name'])
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created company '{company.name}' ({company.id})."))
        else:
            self.stdout.write(f"Using existing company '{company.name}' ({company.id}).")

        migrated = 0
        for user in User.objects.all():
            if Membership.objects.filter(user=user, company=company).exists():
                continue

            group_names = set(user.groups.values_list('name', flat=True))
            role = 'Admin' if user.is_superuser else next(
                (r for r in ROLE_PRIORITY if r in group_names), 'Staff'
            )
            Membership.objects.create(user=user, company=company, role=role)
            migrated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {migrated} membership(s) in '{company.name}'."
        ))
        self.stdout.write(self.style.WARNING(
            f"Company id for the Neo4j data sweep: {company.id}"
        ))
