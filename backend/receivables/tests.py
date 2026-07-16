from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpResponse
from unittest.mock import Mock, patch


class SalesInvoicePrintTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch('receivables.views.SalesInvoice.nodes', new_callable=Mock)
    @patch('receivables.views.pdf_response', create=True)
    def test_print_returns_sales_invoice_pdf(self, pdf_response, nodes):
        invoice = Mock(
            invoice_number='SI-0001', total_amount=1500.0, amount_received=200.0,
            date='2026-07-01', due_date='2026-07-31', description='', status='POSTED',
        )
        customer = Mock()
        line = Mock()
        invoice.customer.single.return_value = customer
        invoice.lines.all.return_value = [line]
        nodes.get_or_none.return_value = invoice
        pdf_response.return_value = HttpResponse(content_type='application/pdf')

        response = self.client.get('/api/receivables/invoices/invoice-1/print/')

        self.assertEqual(response.status_code, 200)
        pdf_response.assert_called_once()
        self.assertEqual(pdf_response.call_args.args[0], 'receivables/sales_invoice.html')
        self.assertEqual(pdf_response.call_args.args[2], 'sales-invoice-SI-0001')
        self.assertEqual(pdf_response.call_args.args[1]['outstanding_amount'], 1300.0)

    @patch('receivables.views.SalesInvoice.nodes', new_callable=Mock)
    def test_print_returns_not_found_for_missing_invoice(self, nodes):
        nodes.get_or_none.return_value = None

        response = self.client.get('/api/receivables/invoices/missing/print/')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {'detail': 'Not found.'})


class InvoiceLineQuantityUnitPriceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

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

        # Confirm it also comes back correctly on retrieve (exercises _serialize_invoice).
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


class CustomerRequiredFieldsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_customer_created_with_only_name(self):
        resp = self.client.post('/api/receivables/customers/', {'name': 'Jane Doe'}, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['email'], '')


class RecordReceiptBankTransactionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _setup_invoice_and_bank(self):
        import uuid
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
        txns = list(BankTransaction.nodes.filter(description=f"Receipt for {invoice['invoice_number']}"))
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].transaction_type, 'RECEIPT')
        self.assertEqual(txns[0].amount, 100.0)
        linked_customer = txns[0].customer.single()
        self.assertIsNotNone(linked_customer)
        self.assertEqual(linked_customer.customer_id, customer['customer_id'])


class RecordReceiptReferenceTests(TestCase):

    def test_partial_receipts_use_distinct_journal_references(self):
        from receivables.services import record_receipt

        invoice = Mock(
            invoice_number='SI-2026-0002', status='POSTED', total_amount=100.0, amount_received=0.0,
        )
        invoice.ar_account.single.return_value = Mock()
        invoice.customer.single.return_value = None
        bank = Mock()
        bank.gl_account.single.return_value = Mock()

        with patch('receivables.services.SalesInvoice.nodes', new_callable=Mock) as invoice_nodes, \
             patch('banks.models.BankAccount.nodes', new_callable=Mock) as bank_nodes, \
             patch('journals.models.JournalEntry') as journal_entry, \
             patch('journals.models.JournalLine'), \
             patch('receivables.services.ARReceipt'), \
             patch('banks.models.BankTransaction'), \
             patch('banks.services.generate_bank_transaction_reference', return_value='BT-2026-0001'), \
             patch('banks.services.generate_invoice_settlement_reference', side_effect=[
                 'ARRec-SI-2026-0002-0001', 'ARRec-SI-2026-0002-0002',
             ]):
            invoice_nodes.get_or_none.return_value = invoice
            bank_nodes.get_or_none.return_value = bank

            record_receipt('invoice-1', 'company-1', '2026-07-01', 40.0, '', 'bank-1', 'tester')
            record_receipt('invoice-1', 'company-1', '2026-07-02', 60.0, '', 'bank-1', 'tester')

        self.assertEqual(
            [call.kwargs['reference'] for call in journal_entry.call_args_list],
            ['ARRec-SI-2026-0002-0001', 'ARRec-SI-2026-0002-0002'],
        )
        self.assertEqual(invoice.status, 'PAID')


class CustomerStatementTests(TestCase):
    def setUp(self):
        from users.models import Company, Membership
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.groups.add(admin_group)

        # Create a company and membership for the test user
        self.company = Company.objects.create(name='Test Company')
        Membership.objects.create(user=self.user, company=self.company, role='Admin')

        # Create APIClient and set up authentication with company context
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        # Manually inject company_id into auth claims
        self.client.default_format = 'json'

        # Patch get_active_company_id to return test company (patch where it's imported/used)
        from unittest.mock import patch
        self.patchers = []
        # Patch in all modules that import get_active_company_id
        for module in ['payables.views', 'payables.serializers', 'accounts.views', 'accounts.serializers',
                       'banks.views', 'banks.serializers', 'journals.views', 'journals.serializers',
                       'receivables.views', 'receivables.serializers', 'budget.views', 'budget.serializers']:
            try:
                p = patch(f'{module}.get_active_company_id')
                mock = p.start()
                mock.return_value = str(self.company.id)
                self.patchers.append(p)
            except (ImportError, AttributeError):
                pass  # Module might not exist or might not import this

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()

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
        import uuid
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
