from datetime import date

from payables.tests import CompanyScopedTestCase


class TrialBalanceCarryForwardTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from journals.models import JournalEntry, JournalLine

        self.building = Account.objects.create(
            company=self.company, code='1200', name='Library Building',
            account_type='Non-Current Assets', normal_balance='DEBIT',
        )
        self.equity = Account.objects.create(
            company=self.company, code='3000', name='Owners Contribution',
            account_type="Owner's Equity", normal_balance='CREDIT',
        )
        self.expense = Account.objects.create(
            company=self.company, code='6000', name='Fuel & Diesel',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.bank = Account.objects.create(
            company=self.company, code='1000', name='Bank',
            account_type='Current Assets', normal_balance='DEBIT',
        )

        # Posted well before the trial balance's date_from — a prior-period
        # capitalization that should still show up as a carried-forward
        # balance-sheet balance.
        prior_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-PRIOR', date=date(2022, 3, 1),
            description='Building capitalization', status='POSTED', entry_type='MANUAL',
            total_debit=500.0, total_credit=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=prior_entry, account=self.building,
            side='DEBIT', amount=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=prior_entry, account=self.equity,
            side='CREDIT', amount=500.0,
        )

        # Posted inside the trial balance window — ordinary in-period expense.
        in_period_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-INPERIOD', date=date(2026, 3, 1),
            description='Fuel purchase', status='POSTED', entry_type='MANUAL',
            total_debit=100.0, total_credit=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=in_period_entry, account=self.expense,
            side='DEBIT', amount=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=in_period_entry, account=self.bank,
            side='CREDIT', amount=100.0,
        )

    def _row(self, resp, name):
        return next(r for r in resp.json()['rows'] if r['name'] == name)

    def test_balance_sheet_account_carries_forward_prior_period_balance(self):
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        building_row = self._row(resp, 'Library Building')
        self.assertEqual(building_row['balance'], 500.0)
        self.assertEqual(building_row['total_debits'], 500.0)

    def test_pl_account_still_scoped_to_period(self):
        # date_from is set AFTER the in-period entry's date, so if P&L
        # accounts were also switched to carry-forward semantics this would
        # incorrectly still show the expense.
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-06-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        expense_row = self._row(resp, 'Fuel & Diesel')
        self.assertEqual(expense_row['balance'], 0.0)

    def test_pl_account_shows_period_movement_when_in_range(self):
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        expense_row = self._row(resp, 'Fuel & Diesel')
        self.assertEqual(expense_row['balance'], 100.0)

    def test_balance_sheet_account_ignores_date_from_entirely(self):
        # date_from set AFTER the prior entry's date — balance-sheet accounts
        # should still show the full carried-forward balance as of date_to.
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-06-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        building_row = self._row(resp, 'Library Building')
        self.assertEqual(building_row['balance'], 500.0)


class TrialBalanceRetainedIncomeTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from journals.models import JournalEntry, JournalLine

        self.retained_income = Account.objects.create(
            company=self.company, code='3100', name='Retained Income',
            account_type="Owner's Equity", normal_balance='CREDIT',
        )
        self.expense = Account.objects.create(
            company=self.company, code='6000', name='Fuel & Diesel',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.revenue = Account.objects.create(
            company=self.company, code='4000', name='Sales',
            account_type='Sales', normal_balance='CREDIT',
        )
        self.bank = Account.objects.create(
            company=self.company, code='1000', name='Bank',
            account_type='Current Assets', normal_balance='DEBIT',
        )

        # Prior-period expense (net loss of 300 before the TB window opens).
        prior_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-PRIOR-EXP', date=date(2025, 1, 1),
            description='Prior year fuel', status='POSTED', entry_type='MANUAL',
            total_debit=300.0, total_credit=300.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=prior_entry, account=self.expense,
            side='DEBIT', amount=300.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=prior_entry, account=self.bank,
            side='CREDIT', amount=300.0,
        )

        # In-period revenue — should NOT be folded into Retained Income; it's
        # this period's own P&L movement.
        in_period_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-INPERIOD-REV', date=date(2026, 3, 1),
            description='In period sale', status='POSTED', entry_type='MANUAL',
            total_debit=500.0, total_credit=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=in_period_entry, account=self.bank,
            side='DEBIT', amount=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=in_period_entry, account=self.revenue,
            side='CREDIT', amount=500.0,
        )

    def _row(self, resp, name):
        return next(r for r in resp.json()['rows'] if r['name'] == name)

    def test_retained_income_reflects_only_prior_period_net_loss(self):
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        ri_row = self._row(resp, 'Retained Income')
        # A 300 prior-period expense with no offsetting revenue is a 300 net
        # loss, which nets to a 300 debit against the credit-normal account.
        self.assertEqual(ri_row['balance'], -300.0)
        self.assertEqual(ri_row['total_debits'], 300.0)

    def test_retained_income_excludes_in_period_activity(self):
        # The in-period 500 sale must not leak into Retained Income — it's
        # this period's own movement, shown on the Sales account instead.
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        sales_row = self._row(resp, 'Sales')
        self.assertEqual(sales_row['balance'], 500.0)
        ri_row = self._row(resp, 'Retained Income')
        self.assertEqual(ri_row['balance'], -300.0)

    def test_retained_income_zero_when_no_prior_activity(self):
        resp = self.client.get('/api/reports/trial-balance/', {
            'date_from': '2024-06-01', 'date_to': '2024-12-31',
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        ri_row = self._row(resp, 'Retained Income')
        self.assertEqual(ri_row['balance'], 0.0)


class BalanceSheetPLTests(CompanyScopedTestCase):
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


class DashboardAssetsTests(CompanyScopedTestCase):
    def test_dashboard_total_assets_matches_sum_of_asset_accounts(self):
        from accounts.services import compute_account_balance
        ids = []
        for name, opening in [('Cash', 300.0), ('Bank', 700.0)]:
            resp = self.client.post('/api/accounts/', {
                'name': name, 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
                'opening_balance': opening,
            }, format='json')
            self.assertEqual(resp.status_code, 201, resp.content)
            ids.append(resp.data['account_id'])

        expected_total = round(sum(compute_account_balance(i) for i in ids), 2)

        resp = self.client.get('/api/reports/dashboard/')
        self.assertEqual(resp.status_code, 200, resp.content)
        # dashboard total includes all active asset accounts in the DB, so assert
        # it's at least the sum of the ones we just created (other tests may add more).
        self.assertGreaterEqual(resp.json()['total_assets'], expected_total - 0.01)
