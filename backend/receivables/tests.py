from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


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
