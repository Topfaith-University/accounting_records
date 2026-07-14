from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class OpeningBalanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

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
        self.assertIsNone(JournalEntry.nodes.get_or_none(reference=f'OB-{account_id}'))


class AccountRBACTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('plain_user', password='pw12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_forbidden_for_non_admin_manager(self):
        resp = self.client.post('/api/accounts/', {
            'name': 'Should Not Be Created',
            'account_type': 'Expenses',
            'normal_balance': 'DEBIT',
        }, format='json')
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_partial_update_forbidden_for_non_admin_manager(self):
        from accounts.models import Account
        account = Account(
            code='9999', name='Existing Account',
            account_type='Expenses', normal_balance='DEBIT',
        )
        account.save()
        resp = self.client.patch(
            f'/api/accounts/{account.account_id}/', {'name': 'Renamed'}, format='json'
        )
        self.assertEqual(resp.status_code, 403, resp.content)
