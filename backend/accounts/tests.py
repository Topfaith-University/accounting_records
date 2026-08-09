from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class OpeningBalanceTests(TestCase):
    def setUp(self):
        from users.models import Company, Membership
        from rest_framework_simplejwt.tokens import AccessToken

        self.company = Company.objects.create(name='Test Co')
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        Membership.objects.create(user=self.user, company=self.company, role='Admin')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()

        token = AccessToken.for_user(self.user)
        token['company_id'] = str(self.company.id)
        token['company_name'] = self.company.name
        token['role'] = 'Admin'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_account_with_opening_balance_posts_journal_entry(self):
        from accounts.models import Account
        from accounts.services import compute_account_balance
        resp = self.client.post('/api/accounts/', {
            'name': 'Test Cash Account',
            'account_type': 'Current Assets',
            'normal_balance': 'DEBIT',
            'opening_balance': 500.0,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        account_id = resp.data['account_id']
        self.assertEqual(compute_account_balance(account_id), 500.0)

    def test_zero_opening_balance_posts_nothing(self):
        from journals.models import JournalEntry
        resp = self.client.post('/api/accounts/', {
            'name': 'Zero Balance Account',
            'account_type': 'Expenses',
            'normal_balance': 'DEBIT',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        account_id = resp.data['account_id']
        self.assertFalse(JournalEntry.objects.filter(reference=f'OB-{account_id}').exists())
