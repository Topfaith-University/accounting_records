import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from users.models import Company, Membership

COMPANY_SCOPED_MODULES = [
    'payables.views', 'payables.serializers', 'accounts.views', 'accounts.serializers',
    'banks.views', 'banks.serializers', 'journals.views', 'journals.serializers',
    'receivables.views', 'receivables.serializers', 'budget.views', 'budget.serializers',
    'reports.views',
]


class CompanyScopedTestCase(TestCase):
    """Base for tests that hit company-scoped endpoints: creates a company +
    membership for the test user and patches get_active_company_id everywhere
    it's imported, so `force_authenticate(user)` (which leaves request.auth
    None, since it bypasses JWT auth entirely) still resolves an active company.
    """

    def setUp(self):
        self.company = Company.objects.create(name='Test Company')
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        Membership.objects.create(user=self.user, company=self.company, role='Admin')

        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.patchers = []
        for module in COMPANY_SCOPED_MODULES:
            p = patch(f'{module}.get_active_company_id', return_value=str(self.company.id))
            p.start()
            self.patchers.append(p)

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()


class PurchaseInvoicePrintTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from payables.models import Vendor, PurchaseInvoice, PurchaseInvoiceLine

        self.vendor = Vendor.objects.create(company=self.company, name='Acme Supplies')
        ap_account = Account.objects.create(
            company=self.company, code='2000', name='AP Control',
            account_type='Current Liabilities', normal_balance='CREDIT',
        )
        expense_account = Account.objects.create(
            company=self.company, code='6000', name='Office Supplies',
            account_type='Expenses', normal_balance='DEBIT',
        )
        from datetime import date
        self.invoice = PurchaseInvoice.objects.create(
            company=self.company, invoice_number='PI-0001',
            date=date(2026, 7, 1), due_date=date(2026, 7, 31),
            status='POSTED', total_amount=1500.0, amount_paid=200.0,
            vendor=self.vendor, ap_account=ap_account,
        )
        PurchaseInvoiceLine.objects.create(
            company=self.company, invoice=self.invoice, description='Pens',
            amount=1500.0, expense_account=expense_account,
        )

    def test_print_returns_purchase_invoice_pdf(self):
        response = self.client.get(f'/api/payables/invoices/{self.invoice.invoice_id}/print/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_print_returns_not_found_for_missing_invoice(self):
        response = self.client.get('/api/payables/invoices/00000000-0000-0000-0000-000000000000/print/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'detail': 'Not found.'})


class InvoiceLineQuantityUnitPriceTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        resp = self.client.post('/api/accounts/', {
            'name': 'AP Control', 'account_type': 'Current Liabilities', 'normal_balance': 'CREDIT',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.ap_account_id = resp.data['account_id']

        resp = self.client.post('/api/accounts/', {
            'name': 'Office Supplies Expense', 'account_type': 'Expenses', 'normal_balance': 'DEBIT',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.expense_account_id = resp.data['account_id']

        resp = self.client.post('/api/payables/vendors/', {'name': 'Acme Supplies'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.vendor_id = resp.data['vendor_id']

    def test_quantity_and_unit_price_round_trip_through_api(self):
        resp = self.client.post('/api/payables/invoices/', {
            'date': '2026-07-01',
            'due_date': '2026-07-31',
            'vendor_id': self.vendor_id,
            'ap_account_id': self.ap_account_id,
            'lines': [{
                'expense_account_id': self.expense_account_id,
                'description': 'Printer paper',
                'quantity': 3,
                'unit_price': 500,
                'amount': 1500,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 3.0)
        self.assertEqual(line['unit_price'], 500.0)
        self.assertEqual(line['amount'], 1500.0)

        # Confirm it also comes back correctly on retrieve.
        resp = self.client.get(f"/api/payables/invoices/{resp.data['invoice_id']}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 3.0)
        self.assertEqual(line['unit_price'], 500.0)

    def test_quantity_and_unit_price_default_when_omitted(self):
        resp = self.client.post('/api/payables/invoices/', {
            'date': '2026-07-01',
            'due_date': '2026-07-31',
            'vendor_id': self.vendor_id,
            'ap_account_id': self.ap_account_id,
            'lines': [{
                'expense_account_id': self.expense_account_id,
                'description': 'Manual override line',
                'amount': 250,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 1.0)
        self.assertEqual(line['unit_price'], 0.0)
        self.assertEqual(line['amount'], 250.0)


class VendorRequiredFieldsTests(CompanyScopedTestCase):
    def test_vendor_created_with_only_name(self):
        resp = self.client.post('/api/payables/vendors/', {'name': 'Acme Supplies'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['email'], '')


class RecordPaymentBankTransactionTests(CompanyScopedTestCase):
    def _setup_invoice_and_bank(self):
        ap = self.client.post('/api/accounts/', {'name': 'AP Control', 'account_type': 'Current Liabilities', 'normal_balance': 'CREDIT'}, format='json').data
        expense = self.client.post('/api/accounts/', {'name': 'Office Supplies', 'account_type': 'Expenses', 'normal_balance': 'DEBIT'}, format='json').data
        bank_gl = self.client.post('/api/accounts/', {'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT'}, format='json').data
        vendor = self.client.post('/api/payables/vendors/', {'name': 'Test Vendor'}, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0,
            'opening_balance_date': '2026-01-01', 'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        invoice = self.client.post('/api/payables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'vendor_id': vendor['vendor_id'], 'ap_account_id': ap['account_id'],
            'lines': [{'description': 'Pens', 'amount': 100.0, 'expense_account_id': expense['account_id']}],
        }, format='json').data
        self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/post/")
        return invoice, bank, vendor

    def test_paying_invoice_creates_bank_transaction(self):
        from banks.models import BankTransaction
        invoice, bank, vendor = self._setup_invoice_and_bank()
        resp = self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/pay/", {
            'payment_date': '2026-01-15', 'amount': 100.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        txns = list(BankTransaction.objects.filter(description=f"Payment for {invoice['invoice_number']}"))
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].transaction_type, 'PAYMENT')
        self.assertEqual(txns[0].amount, 100.0)
        self.assertIsNotNone(txns[0].vendor)
        self.assertEqual(str(txns[0].vendor.vendor_id), vendor['vendor_id'])


class RecordPaymentReferenceTests(CompanyScopedTestCase):
    def test_partial_payments_use_distinct_journal_references(self):
        from accounts.models import Account
        from payables.models import Vendor, PurchaseInvoice, PurchaseInvoiceLine
        from banks.models import BankAccount
        from payables.services import record_payment
        from datetime import date

        ap_account = Account.objects.create(
            company=self.company, code='2000', name='AP Control',
            account_type='Current Liabilities', normal_balance='CREDIT',
        )
        expense_account = Account.objects.create(
            company=self.company, code='6000', name='Office Supplies',
            account_type='Expenses', normal_balance='DEBIT',
        )
        bank_gl = Account.objects.create(
            company=self.company, code='1000', name='Bank GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        vendor = Vendor.objects.create(company=self.company, name='Test Vendor')
        bank = BankAccount.objects.create(
            company=self.company, name='Test Bank', bank_name='GTBank',
            account_number=str(uuid.uuid4()), opening_balance_date=date(2026, 1, 1),
            gl_account=bank_gl,
        )
        invoice = PurchaseInvoice.objects.create(
            company=self.company, invoice_number='PI-2026-0002',
            date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            status='POSTED', total_amount=100.0, vendor=vendor, ap_account=ap_account,
        )
        PurchaseInvoiceLine.objects.create(
            company=self.company, invoice=invoice, description='Line',
            amount=100.0, expense_account=expense_account,
        )

        p1 = record_payment(str(invoice.invoice_id), str(self.company.id), '2026-07-01', 40.0, '', str(bank.bank_account_id), self.user)
        p2 = record_payment(str(invoice.invoice_id), str(self.company.id), '2026-07-02', 60.0, '', str(bank.bank_account_id), self.user)

        self.assertNotEqual(p1.journal_entry.reference, p2.journal_entry.reference)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'PAID')


class VendorStatementTests(CompanyScopedTestCase):
    def _post_invoice(self, vendor_id, amount, suffix=''):
        ap = self.client.post('/api/accounts/', {
            'name': f'AP Control{suffix}', 'account_type': 'Current Liabilities', 'normal_balance': 'CREDIT',
        }, format='json').data
        expense = self.client.post('/api/accounts/', {
            'name': f'Expense{suffix}', 'account_type': 'Expenses', 'normal_balance': 'DEBIT',
        }, format='json').data
        invoice = self.client.post('/api/payables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'vendor_id': vendor_id, 'ap_account_id': ap['account_id'],
            'lines': [{'description': 'Line item', 'amount': amount, 'expense_account_id': expense['account_id']}],
        }, format='json').data
        return invoice

    def test_statement_running_balance_after_partial_payment(self):
        vendor_resp = self.client.post('/api/payables/vendors/', {'name': 'Test Vendor'}, format='json')
        self.assertEqual(vendor_resp.status_code, 201, vendor_resp.content)
        vendor = vendor_resp.data
        invoice = self._post_invoice(vendor['vendor_id'], 1000.0)
        self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/post/")

        bank_gl = self.client.post('/api/accounts/', {
            'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0, 'opening_balance_date': '2026-01-01',
            'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        self.client.post(f"/api/payables/invoices/{invoice['invoice_id']}/pay/", {
            'payment_date': '2026-01-15', 'amount': 400.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')

        resp = self.client.get(f"/api/payables/vendors/{vendor['vendor_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        lines = resp.data['lines']
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['type'], 'INVOICE')
        self.assertEqual(lines[0]['credit'], 1000.0)
        self.assertEqual(lines[0]['debit'], 0.0)
        self.assertEqual(lines[0]['running_balance'], 1000.0)
        self.assertEqual(lines[1]['type'], 'PAYMENT')
        self.assertEqual(lines[1]['debit'], 400.0)
        self.assertEqual(lines[1]['running_balance'], 600.0)
        self.assertEqual(resp.data['closing_balance'], 600.0)

    def test_statement_excludes_draft_invoices(self):
        vendor = self.client.post('/api/payables/vendors/', {'name': 'Draft Vendor'}, format='json').data
        self._post_invoice(vendor['vendor_id'], 500.0, suffix=' Draft')  # left unposted (DRAFT)

        resp = self.client.get(f"/api/payables/vendors/{vendor['vendor_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['lines'], [])
        self.assertEqual(resp.data['closing_balance'], 0.0)

    def test_statement_returns_404_for_unknown_vendor(self):
        resp = self.client.get('/api/payables/vendors/does-not-exist/statement/')
        self.assertEqual(resp.status_code, 404)
