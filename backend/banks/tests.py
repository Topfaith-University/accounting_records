import uuid
from datetime import date

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from users.models import Company
from accounts.models import Account


class GenerateReferenceTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co')

    def test_first_transaction_of_year(self):
        from banks.services import generate_bank_transaction_reference
        year = date.today().year
        ref = generate_bank_transaction_reference(str(self.company.id))
        self.assertEqual(ref, f'BT-{year}-0001')

    def test_increments_count(self):
        from banks.services import generate_bank_transaction_reference
        year = date.today().year
        for _ in range(5):
            generate_bank_transaction_reference(str(self.company.id))
        ref = generate_bank_transaction_reference(str(self.company.id))
        self.assertEqual(ref, f'BT-{year}-0006')


class GenerateInvoiceSettlementReferenceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co')

    def test_generates_sequence_per_invoice_and_family(self):
        from banks.services import generate_invoice_settlement_reference
        generate_invoice_settlement_reference('APPay', 'PI-2026-0002', str(self.company.id))
        reference = generate_invoice_settlement_reference('APPay', 'PI-2026-0002', str(self.company.id))
        self.assertEqual(reference, 'APPay-PI-2026-0002-0002')


class CreateBankTransactionTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co')
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        self.gl = Account.objects.create(
            company=self.company, code='1000', name='Bank GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        self.contra = Account.objects.create(
            company=self.company, code='4000', name='Tuition Revenue',
            account_type='Sales', normal_balance='CREDIT',
        )

    _NO_GL = object()

    def _make_bank(self, name='Main Bank', gl=_NO_GL):
        from banks.models import BankAccount
        return BankAccount.objects.create(
            company=self.company, name=name, bank_name='GTBank',
            account_number=str(uuid.uuid4()), opening_balance_date=date(2026, 1, 1),
            gl_account=self.gl if gl is self._NO_GL else gl,
        )

    def test_receipt_creates_posted_entry(self):
        from banks.services import create_bank_transaction
        source_bank = self._make_bank()
        txn = create_bank_transaction(
            company_id=str(self.company.id),
            transaction_type='RECEIPT',
            txn_date=date(2026, 1, 15),
            description='Tuition fee receipt',
            source_bank_id=str(source_bank.bank_account_id),
            destination_bank_id=None,
            splits=[{'account_id': str(self.contra.account_id), 'amount': 50000.0, 'description': 'Tuition'}],
            amount=None,
            created_by=self.user,
        )
        self.assertEqual(txn.journal_entry.status, 'POSTED')
        self.assertEqual(txn.journal_entry.entry_type, 'BANK_TRANSACTION')

    def test_transfer_uses_two_bank_gls(self):
        from banks.services import create_bank_transaction
        gl2 = Account.objects.create(
            company=self.company, code='1001', name='Petty Cash GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        source_bank = self._make_bank('Main Bank')
        dest_bank = self._make_bank('Petty Cash', gl=gl2)
        txn = create_bank_transaction(
            company_id=str(self.company.id),
            transaction_type='TRANSFER',
            txn_date=date(2026, 1, 20),
            description='Transfer to petty cash',
            source_bank_id=str(source_bank.bank_account_id),
            destination_bank_id=str(dest_bank.bank_account_id),
            splits=[],
            amount=10000.0,
            created_by=self.user,
        )
        sides = set(txn.journal_entry.lines.values_list('side', flat=True))
        self.assertEqual(sides, {'CREDIT', 'DEBIT'})

    def test_missing_gl_raises_validation_error(self):
        from banks.services import create_bank_transaction
        bank = self._make_bank(gl=None)
        with self.assertRaises(ValidationError):
            create_bank_transaction(
                company_id=str(self.company.id),
                transaction_type='PAYMENT',
                txn_date=date(2026, 1, 10),
                description='Test',
                source_bank_id=str(bank.bank_account_id),
                destination_bank_id=None,
                splits=[{'account_id': str(self.contra.account_id), 'amount': 100.0, 'description': ''}],
                amount=None,
                created_by=self.user,
            )

    def test_payment_bank_gl_is_credited(self):
        from banks.services import create_bank_transaction
        source_bank = self._make_bank()
        txn = create_bank_transaction(
            company_id=str(self.company.id),
            transaction_type='PAYMENT',
            txn_date=date(2026, 2, 1),
            description='Supplier payment',
            source_bank_id=str(source_bank.bank_account_id),
            destination_bank_id=None,
            splits=[{'account_id': str(self.contra.account_id), 'amount': 20000.0, 'description': ''}],
            amount=None,
            created_by=self.user,
        )
        bank_line = txn.journal_entry.lines.get(account=self.gl)
        contra_line = txn.journal_entry.lines.get(account=self.contra)
        self.assertEqual(bank_line.side, 'CREDIT')
        self.assertEqual(contra_line.side, 'DEBIT')

    def test_invalid_transaction_type_raises(self):
        from banks.services import create_bank_transaction
        source_bank = self._make_bank()
        with self.assertRaises(ValidationError):
            create_bank_transaction(
                company_id=str(self.company.id),
                transaction_type='REFUND',
                txn_date=date(2026, 1, 1),
                description='Test',
                source_bank_id=str(source_bank.bank_account_id),
                destination_bank_id=None,
                splits=[],
                amount=None,
                created_by=self.user,
            )


class BankOpeningBalanceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co')
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        from users.models import Membership
        Membership.objects.create(user=self.user, company=self.company, role='Manager')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.user.groups.add(manager_group)
        self.client = APIClient()

        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(self.user)
        token['company_id'] = str(self.company.id)
        token['company_name'] = self.company.name
        token['role'] = 'Manager'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _create_gl_account(self):
        resp = self.client.post('/api/accounts/', {
            'name': 'Test Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json')
        return resp.data['account_id']

    def test_bank_account_opening_balance_syncs_to_gl(self):
        from accounts.services import compute_account_balance
        gl_id = self._create_gl_account()
        resp = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank', 'bank_name': 'GTBank',
            'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 1000.0,
            'opening_balance_date': '2026-01-01', 'gl_account_id_input': gl_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(compute_account_balance(gl_id), 1000.0)

    def test_linking_gl_account_via_update_syncs_opening_balance(self):
        from accounts.services import compute_account_balance
        # Create the bank account with an opening balance but no GL account yet.
        resp = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank 2', 'bank_name': 'Zenith',
            'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 750.0,
            'opening_balance_date': '2026-01-01',
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        bank_account_id = resp.data['bank_account_id']
        self.assertIsNone(resp.data['gl_account_id'])

        # Now link a GL account via partial_update — this should post the
        # opening balance for the first time.
        gl_id = self._create_gl_account()
        resp = self.client.patch(f'/api/banks/accounts/{bank_account_id}/', {
            'gl_account_id_input': gl_id,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(compute_account_balance(gl_id), 750.0)

        # Saving again with the same GL account must not double-post.
        resp = self.client.patch(f'/api/banks/accounts/{bank_account_id}/', {
            'gl_account_id_input': gl_id,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(compute_account_balance(gl_id), 750.0)

    def test_editing_opening_balance_after_creation_is_ignored(self):
        from accounts.services import compute_account_balance
        gl_id = self._create_gl_account()
        resp = self.client.post('/api/banks/accounts/', {
            'name': 'Test Bank 3', 'bank_name': 'Access',
            'account_number': f'test-{uuid.uuid4()}',
            'opening_balance': 500.0,
            'opening_balance_date': '2026-01-01', 'gl_account_id_input': gl_id,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        bank_account_id = resp.data['bank_account_id']

        # Attempting to change the opening balance after creation must be a
        # no-op — otherwise the displayed value would desync from the GL
        # posting, which is only ever made once.
        resp = self.client.patch(f'/api/banks/accounts/{bank_account_id}/', {
            'opening_balance': 900.0,
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['opening_balance'], 500.0)
        self.assertEqual(compute_account_balance(gl_id), 500.0)


from payables.tests import CompanyScopedTestCase


class BankTransactionSearchTests(CompanyScopedTestCase):
    def setUp(self):
        super().setUp()
        from accounts.models import Account
        from banks.models import BankAccount
        from banks.services import create_bank_transaction
        from payables.models import Vendor
        from receivables.models import Customer

        self.gl = Account.objects.create(
            company=self.company, code='1000', name='Bank GL',
            account_type='Current Assets', normal_balance='DEBIT',
        )
        self.expense = Account.objects.create(
            company=self.company, code='6100', name='Office Supplies',
            account_type='Expenses', normal_balance='DEBIT',
        )
        self.bank = BankAccount.objects.create(
            company=self.company, name='Main Bank', bank_name='GTBank',
            account_number='0123456789', opening_balance_date=date(2026, 1, 1),
            gl_account=self.gl,
        )
        self.vendor = Vendor.objects.create(company=self.company, name='Acme Supplies')
        self.customer = Customer.objects.create(company=self.company, name='Jane Student')

        self.vendor_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='PAYMENT',
            txn_date=date(2026, 7, 1), description='Office chairs',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 200.0, 'description': 'Chairs'}],
            amount=None, created_by=self.user, vendor_id=str(self.vendor.vendor_id),
            reference='BT-0001',
        )
        self.customer_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='RECEIPT',
            txn_date=date(2026, 7, 2), description='Tuition payment',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 500.0, 'description': 'Tuition'}],
            amount=None, created_by=self.user, customer_id=str(self.customer.customer_id),
            reference='BT-0002',
        )
        self.plain_txn = create_bank_transaction(
            company_id=str(self.company.id), transaction_type='PAYMENT',
            txn_date=date(2026, 7, 3), description='Unrelated expense',
            source_bank_id=str(self.bank.bank_account_id), destination_bank_id=None,
            splits=[{'account_id': str(self.expense.account_id), 'amount': 50.0, 'description': 'Misc'}],
            amount=None, created_by=self.user, reference='BT-0003',
        )

    def test_search_matches_reference(self):
        resp = self.client.get('/api/banks/transactions/?search=BT-0003')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.plain_txn.transaction_id])

    def test_search_matches_description(self):
        resp = self.client.get('/api/banks/transactions/?search=tuition')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.customer_txn.transaction_id])

    def test_search_matches_vendor_name(self):
        resp = self.client.get('/api/banks/transactions/?search=Acme')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.vendor_txn.transaction_id])

    def test_search_matches_customer_name(self):
        resp = self.client.get('/api/banks/transactions/?search=Jane')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(ids, [self.customer_txn.transaction_id])

    def test_search_no_duplicate_rows(self):
        # Neither filter path joins a one-to-many relation, but assert
        # explicitly that a transaction with both vendor and customer unset
        # (or set) never appears twice in a single search response.
        resp = self.client.get('/api/banks/transactions/?search=BT-000')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [t['transaction_id'] for t in resp.data['results']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted([
            self.vendor_txn.transaction_id, self.customer_txn.transaction_id, self.plain_txn.transaction_id,
        ]))

    def test_search_case_insensitive_and_no_match(self):
        resp = self.client.get('/api/banks/transactions/?search=ACME')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(len(resp.data['results']), 1)

        resp = self.client.get('/api/banks/transactions/?search=nonexistent-xyz')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['results'], [])
