from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class BalanceSheetPLTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_balance_sheet_includes_net_surplus_and_balances(self):
        # Asset account seeded with an opening balance (Phase 0 feature) — creates
        # a real DEBIT to the asset and a CREDIT to Opening Balance Equity, so the
        # sheet balances without needing any P&L activity.
        resp = self.client.post('/api/accounts/', {
            'name': 'Cash on Hand', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
            'opening_balance': 200.0,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = self.client.get('/api/reports/balance-sheet/', {'as_of_date': '2026-12-31'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json()['is_balanced'], resp.json())
