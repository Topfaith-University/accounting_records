import uuid

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from users.models import Company, Membership
from payables.tests import COMPANY_SCOPED_MODULES, CompanyScopedTestCase


class SalesInvoicePrintTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from receivables.models import Customer, SalesInvoice, SalesInvoiceLine

        self.customer = Customer.objects.create(company=self.company, name='Jane Student')
        ar_account = Account.objects.create(
            company=self.company, code='1100', name='AR Control',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        revenue_account = Account.objects.create(
            company=self.company, code='4000', name='Tuition Revenue',
            account_type='Sales', normal_balance='CREDIT',
        )
        from datetime import date
        self.invoice = SalesInvoice.objects.create(
            company=self.company, invoice_number='SI-0001',
            date=date(2026, 7, 1), due_date=date(2026, 7, 31),
            status='POSTED', total_amount=1500.0, amount_received=200.0,
            customer=self.customer, ar_account=ar_account,
        )
        SalesInvoiceLine.objects.create(
            company=self.company, invoice=self.invoice, description='Tuition fee',
            amount=1500.0, revenue_account=revenue_account,
        )

    def test_print_returns_sales_invoice_pdf(self):
        response = self.client.get(f'/api/receivables/invoices/{self.invoice.invoice_id}/print/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_print_returns_not_found_for_missing_invoice(self):
        response = self.client.get('/api/receivables/invoices/00000000-0000-0000-0000-000000000000/print/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'detail': 'Not found.'})


class InvoiceLineQuantityUnitPriceTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        resp = self.client.post('/api/accounts/', {
            'name': 'AR Control', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.ar_account_id = resp.data['account_id']

        resp = self.client.post('/api/accounts/', {
            'name': 'Tuition Revenue', 'account_type': 'Sales', 'normal_balance': 'CREDIT',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.revenue_account_id = resp.data['account_id']

        resp = self.client.post('/api/receivables/customers/', {'name': 'Jane Student'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.customer_id = resp.data['customer_id']

    def test_quantity_and_unit_price_round_trip_through_api(self):
        resp = self.client.post('/api/receivables/invoices/', {
            'date': '2026-07-01',
            'due_date': '2026-07-31',
            'customer_id': self.customer_id,
            'ar_account_id': self.ar_account_id,
            'lines': [{
                'revenue_account_id': self.revenue_account_id,
                'description': 'Tuition fee',
                'quantity': 2,
                'unit_price': 750,
                'amount': 1500,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 2.0)
        self.assertEqual(line['unit_price'], 750.0)
        self.assertEqual(line['amount'], 1500.0)

        resp = self.client.get(f"/api/receivables/invoices/{resp.data['invoice_id']}/")
        self.assertEqual(resp.status_code, 200, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 2.0)
        self.assertEqual(line['unit_price'], 750.0)

    def test_quantity_and_unit_price_default_when_omitted(self):
        resp = self.client.post('/api/receivables/invoices/', {
            'date': '2026-07-01',
            'due_date': '2026-07-31',
            'customer_id': self.customer_id,
            'ar_account_id': self.ar_account_id,
            'lines': [{
                'revenue_account_id': self.revenue_account_id,
                'description': 'Manual override line',
                'amount': 300,
            }],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.data['lines'][0]
        self.assertEqual(line['quantity'], 1.0)
        self.assertEqual(line['unit_price'], 0.0)
        self.assertEqual(line['amount'], 300.0)


class CustomerRequiredFieldsTests(CompanyScopedTestCase):
    def test_customer_created_with_only_name(self):
        resp = self.client.post('/api/receivables/customers/', {'name': 'Jane Doe'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['email'], '')


class RecordReceiptBankTransactionTests(CompanyScopedTestCase):
    def _setup_invoice_and_bank(self):
        ar = self.client.post('/api/accounts/', {'name': 'AR Control', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT'}, format='json').data
        revenue = self.client.post('/api/accounts/', {'name': 'Tuition Revenue', 'account_type': 'Sales', 'normal_balance': 'CREDIT'}, format='json').data
        bank_gl = self.client.post('/api/accounts/', {'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT'}, format='json').data
        customer = self.client.post('/api/receivables/customers/', {'name': 'Jane Student'}, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0,
            'opening_balance_date': '2026-01-01', 'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        invoice = self.client.post('/api/receivables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'customer_id': customer['customer_id'], 'ar_account_id': ar['account_id'],
            'lines': [{'description': 'Tuition', 'amount': 100.0, 'revenue_account_id': revenue['account_id']}],
        }, format='json').data
        self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/post/")
        return invoice, bank, customer

    def test_receiving_invoice_creates_bank_transaction(self):
        from banks.models import BankTransaction
        invoice, bank, customer = self._setup_invoice_and_bank()
        resp = self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/receive/", {
            'receipt_date': '2026-01-15', 'amount': 100.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        txns = list(BankTransaction.objects.filter(description=f"Receipt for {invoice['invoice_number']}"))
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].transaction_type, 'RECEIPT')
        self.assertEqual(txns[0].amount, 100.0)
        self.assertIsNotNone(txns[0].customer)
        self.assertEqual(str(txns[0].customer.customer_id), customer['customer_id'])


class RecordReceiptReferenceTests(CompanyScopedTestCase):
    def test_partial_receipts_use_distinct_journal_references(self):
        from accounts.models import Account
        from receivables.models import Customer, SalesInvoice, SalesInvoiceLine
        from banks.models import BankAccount
        from receivables.services import record_receipt
        from datetime import date

        ar_account = Account.objects.create(
            company=self.company, code='1100', name='AR Control',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        revenue_account = Account.objects.create(
            company=self.company, code='4000', name='Tuition Revenue',
            account_type='Sales', normal_balance='CREDIT',
        )
        bank_gl = Account.objects.create(
            company=self.company, code='1000', name='Bank GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        customer = Customer.objects.create(company=self.company, name='Jane Student')
        bank = BankAccount.objects.create(
            company=self.company, name='Test Bank', bank_name='GTBank',
            account_number=str(uuid.uuid4()), opening_balance_date=date(2026, 1, 1),
            gl_account=bank_gl,
        )
        invoice = SalesInvoice.objects.create(
            company=self.company, invoice_number='SI-2026-0002',
            date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            status='POSTED', total_amount=100.0, customer=customer, ar_account=ar_account,
        )
        SalesInvoiceLine.objects.create(
            company=self.company, invoice=invoice, description='Line',
            amount=100.0, revenue_account=revenue_account,
        )

        r1 = record_receipt(str(invoice.invoice_id), str(self.company.id), '2026-07-01', 40.0, '', str(bank.bank_account_id), self.user)
        r2 = record_receipt(str(invoice.invoice_id), str(self.company.id), '2026-07-02', 60.0, '', str(bank.bank_account_id), self.user)

        self.assertNotEqual(r1.journal_entry.reference, r2.journal_entry.reference)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'PAID')


class CustomerStatementTests(CompanyScopedTestCase):
    def _post_invoice(self, customer_id, amount, suffix=''):
        ar = self.client.post('/api/accounts/', {
            'name': f'AR Control{suffix}', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        revenue = self.client.post('/api/accounts/', {
            'name': f'Revenue{suffix}', 'account_type': 'Sales', 'normal_balance': 'CREDIT',
        }, format='json').data
        invoice = self.client.post('/api/receivables/invoices/', {
            'date': '2026-01-01', 'due_date': '2026-02-01',
            'customer_id': customer_id, 'ar_account_id': ar['account_id'],
            'lines': [{'description': 'Line item', 'amount': amount, 'revenue_account_id': revenue['account_id']}],
        }, format='json').data
        return invoice

    def test_statement_running_balance_after_partial_receipt(self):
        customer = self.client.post('/api/receivables/customers/', {'name': 'Test Customer'}, format='json').data
        invoice = self._post_invoice(customer['customer_id'], 1000.0)
        self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/post/")

        bank_gl = self.client.post('/api/accounts/', {
            'name': 'Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json').data
        bank = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank', 'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 5000.0, 'opening_balance_date': '2026-01-01',
            'gl_account_id_input': bank_gl['account_id'],
        }, format='json').data
        self.client.post(f"/api/receivables/invoices/{invoice['invoice_id']}/receive/", {
            'receipt_date': '2026-01-15', 'amount': 400.0, 'bank_account_id': bank['bank_account_id'],
        }, format='json')

        resp = self.client.get(f"/api/receivables/customers/{customer['customer_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        lines = resp.data['lines']
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['type'], 'INVOICE')
        self.assertEqual(lines[0]['debit'], 1000.0)
        self.assertEqual(lines[0]['credit'], 0.0)
        self.assertEqual(lines[0]['running_balance'], 1000.0)
        self.assertEqual(lines[1]['type'], 'RECEIPT')
        self.assertEqual(lines[1]['credit'], 400.0)
        self.assertEqual(lines[1]['running_balance'], 600.0)
        self.assertEqual(resp.data['closing_balance'], 600.0)

    def test_statement_excludes_draft_invoices(self):
        customer = self.client.post('/api/receivables/customers/', {'name': 'Draft Customer'}, format='json').data
        self._post_invoice(customer['customer_id'], 500.0, suffix=' Draft')  # left unposted (DRAFT)

        resp = self.client.get(f"/api/receivables/customers/{customer['customer_id']}/statement/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['lines'], [])
        self.assertEqual(resp.data['closing_balance'], 0.0)

    def test_statement_returns_404_for_unknown_customer(self):
        resp = self.client.get('/api/receivables/customers/does-not-exist/statement/')
        self.assertEqual(resp.status_code, 404)
