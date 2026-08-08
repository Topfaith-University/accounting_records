from datetime import date

from django.test import TestCase

from payables.tests import CompanyScopedTestCase

# Create your tests here.


class JournalEntrySearchTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from journals.models import JournalEntry, JournalLine

        self.rent_account = Account.objects.create(
            company=self.company, code='6100', name='Rent Expense',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.bank_account = Account.objects.create(
            company=self.company, code='1000', name='Main Bank',
            account_type='Current Assets', normal_balance='DEBIT',
        )

        self.rent_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-000001', date=date(2026, 7, 1),
            description='July office rent', status='POSTED',
            total_debit=500.0, total_credit=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.rent_entry, account=self.rent_account,
            side='DEBIT', amount=500.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.rent_entry, account=self.bank_account,
            side='CREDIT', amount=500.0,
        )

        self.other_entry = JournalEntry.objects.create(
            company=self.company, reference='JE-000002', date=date(2026, 7, 2),
            description='Unrelated payment', status='POSTED',
            total_debit=100.0, total_credit=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.other_entry, account=self.bank_account,
            side='CREDIT', amount=100.0,
        )
        JournalLine.objects.create(
            company=self.company, entry=self.other_entry, account=self.bank_account,
            side='DEBIT', amount=100.0,
        )

    def test_search_matches_reference(self):
        resp = self.client.get('/api/journals/entries/?search=JE-000002')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(ids, [self.other_entry.entry_id])

    def test_search_matches_description(self):
        resp = self.client.get('/api/journals/entries/?search=office rent')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(ids, [self.rent_entry.entry_id])

    def test_search_matches_account_name_without_duplicates(self):
        # rent_entry has two lines on bank_account-adjacent accounts; searching
        # by an account name that appears on multiple lines of the same entry
        # must still return that entry exactly once.
        resp = self.client.get('/api/journals/entries/?search=Main Bank')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [e['entry_id'] for e in resp.data['results']]
        self.assertEqual(sorted(ids), sorted([self.rent_entry.entry_id, self.other_entry.entry_id]))
        self.assertEqual(len(ids), len(set(ids)))

    def test_search_case_insensitive_and_no_match(self):
        resp = self.client.get('/api/journals/entries/?search=RENT')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data['results']), 1)

        resp = self.client.get('/api/journals/entries/?search=nonexistent-xyz')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['results'], [])
