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
