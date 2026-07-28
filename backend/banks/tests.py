from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group



class GenerateReferenceTest(TestCase):

    @patch('banks.services.db')
    def test_first_transaction_of_year(self, mock_db):
        from datetime import date
        mock_db.cypher_query.return_value = ([[1]], None)
        from banks.services import generate_bank_transaction_reference
        year = date.today().year
        ref = generate_bank_transaction_reference()
        self.assertEqual(ref, f'BT-{year}-0001')

    @patch('banks.services.db')
    def test_increments_count(self, mock_db):
        from datetime import date
        mock_db.cypher_query.return_value = ([[6]], None)
        from banks.services import generate_bank_transaction_reference
        year = date.today().year
        ref = generate_bank_transaction_reference()
        self.assertEqual(ref, f'BT-{year}-0006')


class GenerateInvoiceSettlementReferenceTests(TestCase):

    @patch('banks.services.db')
    def test_generates_sequence_per_invoice_and_family(self, mock_db):
        mock_db.cypher_query.return_value = ([[2]], None)

        from banks.services import generate_invoice_settlement_reference

        reference = generate_invoice_settlement_reference('APPay', 'PI-2026-0002')

        self.assertEqual(reference, 'APPay-PI-2026-0002-0002')
        self.assertEqual(
            mock_db.cypher_query.call_args.args[1],
            {'prefix': 'APPay', 'invoice_number': 'PI-2026-0002'},
        )


class CreateBankTransactionTest(TestCase):

    def _make_mock_bank(self, bank_account_id, gl_account_id='gl-1'):
        bank = MagicMock()
        bank.bank_account_id = bank_account_id
        gl = MagicMock()
        gl.account_id = gl_account_id
        bank.gl_account.single.return_value = gl
        return bank, gl

    @patch('banks.services.generate_bank_transaction_reference', return_value='BT-2026-0001')
    @patch('banks.services.BankTransaction')
    @patch('banks.services.JournalLine')
    @patch('banks.services.JournalEntry')
    @patch('banks.services.BankAccount')
    def test_receipt_creates_posted_entry(self, MockBA, MockJE, MockJL, MockBT, mock_ref):
        source_bank, source_gl = self._make_mock_bank('bank-1')
        MockBA.nodes.get_or_none.return_value = source_bank
        mock_entry = MagicMock()
        MockJE.return_value = mock_entry
        mock_line = MagicMock()
        MockJL.return_value = mock_line

        with patch('banks.services.Account') as MockAcct:
            contra = MagicMock()
            MockAcct.nodes.get_or_none.return_value = contra
            mock_txn = MagicMock()
            MockBT.return_value = mock_txn

            from banks.services import create_bank_transaction
            from datetime import date
            result = create_bank_transaction(
                transaction_type='RECEIPT',
                txn_date=date(2026, 1, 15),
                description='Tuition fee receipt',
                source_bank_id='bank-1',
                destination_bank_id=None,
                splits=[{'account_id': 'acct-1', 'amount': 50000.0, 'description': 'Tuition'}],
                amount=None,
                created_by='admin',
            )

        self.assertEqual(MockJE.call_args.kwargs['status'], 'POSTED')
        self.assertEqual(MockJE.call_args.kwargs['entry_type'], 'BANK_TRANSACTION')
        self.assertEqual(result, mock_txn)

    @patch('banks.services.generate_bank_transaction_reference', return_value='BT-2026-0002')
    @patch('banks.services.BankTransaction')
    @patch('banks.services.JournalLine')
    @patch('banks.services.JournalEntry')
    @patch('banks.services.BankAccount')
    def test_transfer_uses_two_bank_gls(self, MockBA, MockJE, MockJL, MockBT, mock_ref):
        source_bank, source_gl = self._make_mock_bank('bank-1', 'gl-1')
        dest_bank, dest_gl = self._make_mock_bank('bank-2', 'gl-2')
        MockBA.nodes.get_or_none.side_effect = lambda bank_account_id: (
            source_bank if bank_account_id == 'bank-1' else dest_bank
        )
        mock_entry = MagicMock()
        MockJE.return_value = mock_entry
        mock_txn = MagicMock()
        MockBT.return_value = mock_txn

        line_calls = []
        def make_line(**kwargs):
            m = MagicMock()
            line_calls.append(kwargs)
            return m
        MockJL.side_effect = make_line

        from banks.services import create_bank_transaction
        from datetime import date
        create_bank_transaction(
            transaction_type='TRANSFER',
            txn_date=date(2026, 1, 20),
            description='Transfer to petty cash',
            source_bank_id='bank-1',
            destination_bank_id='bank-2',
            splits=[],
            amount=10000.0,
            created_by='admin',
        )

        sides = {c['side'] for c in line_calls}
        self.assertIn('CREDIT', sides)
        self.assertIn('DEBIT', sides)

    @patch('banks.services.BankAccount')
    def test_missing_gl_raises_validation_error(self, MockBA):
        bank = MagicMock()
        bank.gl_account.single.return_value = None
        MockBA.nodes.get_or_none.return_value = bank

        from banks.services import create_bank_transaction
        from datetime import date
        with self.assertRaises(ValidationError):
            create_bank_transaction(
                transaction_type='PAYMENT',
                txn_date=date(2026, 1, 10),
                description='Test',
                source_bank_id='bank-no-gl',
                destination_bank_id=None,
                splits=[{'account_id': 'acct-1', 'amount': 100.0, 'description': ''}],
                amount=None,
                created_by='admin',
            )

    @patch('banks.services.generate_bank_transaction_reference', return_value='BT-2026-0003')
    @patch('banks.services.BankTransaction')
    @patch('banks.services.JournalLine')
    @patch('banks.services.JournalEntry')
    @patch('banks.services.BankAccount')
    def test_payment_bank_gl_is_credited(self, MockBA, MockJE, MockJL, MockBT, mock_ref):
        source_bank, source_gl = self._make_mock_bank('bank-1')
        MockBA.nodes.get_or_none.return_value = source_bank
        mock_entry = MagicMock()
        MockJE.return_value = mock_entry
        mock_txn = MagicMock()
        MockBT.return_value = mock_txn

        line_sides = []
        def make_line(**kwargs):
            m = MagicMock()
            line_sides.append(kwargs.get('side'))
            return m
        MockJL.side_effect = make_line

        with patch('banks.services.Account') as MockAcct:
            MockAcct.nodes.get_or_none.return_value = MagicMock()
            from banks.services import create_bank_transaction
            from datetime import date
            create_bank_transaction(
                transaction_type='PAYMENT',
                txn_date=date(2026, 2, 1),
                description='Supplier payment',
                source_bank_id='bank-1',
                destination_bank_id=None,
                splits=[{'account_id': 'acct-1', 'amount': 20000.0, 'description': ''}],
                amount=None,
                created_by='admin',
            )

        # Bank GL must be CREDIT for PAYMENT
        self.assertEqual(line_sides[0], 'CREDIT')
        # Contra must be DEBIT
        self.assertEqual(line_sides[1], 'DEBIT')

    @patch('banks.services.BankAccount')
    def test_invalid_transaction_type_raises(self, MockBA):
        source_bank, _ = self._make_mock_bank('bank-1')
        MockBA.nodes.get_or_none.return_value = source_bank
        from banks.services import create_bank_transaction
        from datetime import date
        with self.assertRaises(ValidationError):
            create_bank_transaction(
                transaction_type='REFUND',
                txn_date=date(2026, 1, 1),
                description='Test',
                source_bank_id='bank-1',
                destination_bank_id=None,
                splits=[],
                amount=None,
                created_by='admin',
            )


class BankOpeningBalanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('tester', password='pw12345')
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.user.groups.add(manager_group)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_gl_account(self):
        resp = self.client.post('/api/accounts/', {
            'name': 'Test Bank GL', 'account_type': 'Current Assets', 'normal_balance': 'DEBIT',
        }, format='json')
        return resp.data['account_id']

    def test_bank_account_opening_balance_syncs_to_gl(self):
        import uuid
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
        import uuid
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
        import uuid
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
