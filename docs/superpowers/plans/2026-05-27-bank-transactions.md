# Bank Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to record receipts, payments, and bank-to-bank transfers directly against a bank account; each transaction auto-creates and immediately posts a balanced journal entry.

**Architecture:** A new `BankTransaction` Neo4j node links to a source `BankAccount`, an optional destination `BankAccount` (for transfers), and a `JournalEntry` that is created and posted atomically by a service function. The frontend provides a dedicated list page and a form page, plus a new tab on the bank account detail page.

**Tech Stack:** Django + neomodel (backend), Angular 17 standalone components + axios (frontend), existing `viewsets.ViewSet` + plain `serializers.Serializer` patterns throughout.

---

## File Map

**Create:**
- `backend/banks/tests.py` — service-layer unit tests (mocked)
- `frontend/sage-frontend/src/app/services/bank-transactions.service.ts`
- `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.ts`
- `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.html`
- `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.ts`
- `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.html`

**Modify:**
- `backend/banks/models.py` — add `BankTransaction` node
- `backend/journals/models.py` — add `'BANK_TRANSACTION'` to `entry_type` choices
- `backend/banks/serializers.py` — add `BankTransactionSplitSerializer`, `BankTransactionSerializer`
- `backend/banks/services.py` — add `generate_bank_transaction_reference()`, `create_bank_transaction()`
- `backend/banks/views.py` — add `BankTransactionViewSet`
- `backend/banks/urls.py` — register `transactions` router prefix
- `frontend/sage-frontend/src/app/banks/bank-account-detail/bank-account-detail.component.ts` — add Transactions tab
- `frontend/sage-frontend/src/app/banks/bank-account-detail/bank-account-detail.component.html` — add Transactions tab UI
- `frontend/sage-frontend/src/app/app.routes.ts` — add two new routes
- `frontend/sage-frontend/src/app/shell/shell.component.html` — add Transactions nav child link

---

## Task B1: BankTransaction model + BANK_TRANSACTION entry type

**Files:**
- Modify: `backend/banks/models.py`
- Modify: `backend/journals/models.py`

- [ ] **Step 1: Add `BankTransaction` to `backend/banks/models.py`**

  Add these imports at the top (the file already imports `StructuredNode`, `StringProperty`, `FloatProperty`, `DateProperty`, `DateTimeProperty`, `UniqueIdProperty`, `RelationshipTo`, `One`; add `ZeroOrOne`):

  ```python
  from neomodel import (
      StructuredNode, StringProperty, BooleanProperty,
      FloatProperty, DateProperty, DateTimeProperty,
      UniqueIdProperty, RelationshipTo, One, ZeroOrOne
  )
  ```

  Append the `BankTransaction` class at the end of the file:

  ```python
  class BankTransaction(StructuredNode):
      transaction_id = UniqueIdProperty()
      reference = StringProperty(unique_index=True, required=True)
      transaction_type = StringProperty(
          choices=[('RECEIPT', 'Receipt'), ('PAYMENT', 'Payment'), ('TRANSFER', 'Transfer')],
          required=True
      )
      date = DateProperty(required=True)
      amount = FloatProperty(required=True)
      description = StringProperty(required=True)
      created_by = StringProperty(required=True)
      created_at = DateTimeProperty(default_now=True)

      source_bank = RelationshipTo('BankAccount', 'FROM_BANK', cardinality=One)
      destination_bank = RelationshipTo('BankAccount', 'TO_BANK', cardinality=ZeroOrOne)
      journal_entry = RelationshipTo('journals.models.JournalEntry', 'GENERATES_ENTRY', cardinality=One)
  ```

- [ ] **Step 2: Add `'BANK_TRANSACTION'` entry type to `backend/journals/models.py`**

  Find the `entry_type` field in `JournalEntry` (currently has `MANUAL`, `BANK_RECON`, `AP_PAYMENT`, `AR_RECEIPT`) and add the new choice:

  ```python
  entry_type = StringProperty(
      choices=[
          ('MANUAL', 'Manual'),
          ('BANK_RECON', 'Bank Reconciliation'),
          ('AP_PAYMENT', 'AP Payment'),
          ('AR_RECEIPT', 'AR Receipt'),
          ('BANK_TRANSACTION', 'Bank Transaction'),
      ],
      default='MANUAL'
  )
  ```

- [ ] **Step 3: Install Neo4j labels for the new node**

  ```bash
  docker exec django_backend python manage.py install_labels
  ```

  Expected: output mentions `BankTransaction` index/constraint creation with no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add backend/banks/models.py backend/journals/models.py
  git commit -m "feat: Add BankTransaction model and BANK_TRANSACTION entry type"
  ```

---

## Task B2: Reference generator + create_bank_transaction service

**Files:**
- Modify: `backend/banks/services.py`
- Modify: `backend/banks/tests.py`

- [ ] **Step 1: Write failing tests**

  Replace `backend/banks/tests.py` with:

  ```python
  from unittest.mock import patch, MagicMock, call
  from django.test import TestCase
  from rest_framework.exceptions import ValidationError


  class GenerateReferenceTest(TestCase):

      @patch('banks.services.db')
      def test_first_transaction_of_year(self, mock_db):
          from datetime import date
          mock_db.cypher_query.return_value = ([[0]], None)
          from banks.services import generate_bank_transaction_reference
          year = date.today().year
          ref = generate_bank_transaction_reference()
          self.assertEqual(ref, f'BT-{year}-0001')

      @patch('banks.services.db')
      def test_increments_count(self, mock_db):
          from datetime import date
          mock_db.cypher_query.return_value = ([[5]], None)
          from banks.services import generate_bank_transaction_reference
          year = date.today().year
          ref = generate_bank_transaction_reference()
          self.assertEqual(ref, f'BT-{year}-0006')


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
                  date=date(2026, 1, 15),
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
              date=date(2026, 1, 20),
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
                  date=date(2026, 1, 10),
                  description='Test',
                  source_bank_id='bank-no-gl',
                  destination_bank_id=None,
                  splits=[{'account_id': 'acct-1', 'amount': 100.0, 'description': ''}],
                  amount=None,
                  created_by='admin',
              )
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  docker exec django_backend python manage.py test banks.tests --verbosity=2 2>&1 | tail -20
  ```

  Expected: `ImportError` or `AttributeError` — `generate_bank_transaction_reference` and `create_bank_transaction` don't exist yet.

- [ ] **Step 3: Add service functions to `backend/banks/services.py`**

  Append to the end of `backend/banks/services.py`:

  ```python
  def generate_bank_transaction_reference() -> str:
      from datetime import date
      year = date.today().year
      results, _ = db.cypher_query(
          "MATCH (t:BankTransaction) WHERE t.reference STARTS WITH $prefix RETURN count(t)",
          {'prefix': f'BT-{year}-'}
      )
      count = int(results[0][0]) if results else 0
      return f'BT-{year}-{count + 1:04d}'


  def create_bank_transaction(
      transaction_type: str,
      date,
      description: str,
      source_bank_id: str,
      destination_bank_id,
      splits: list,
      amount,
      created_by: str,
  ):
      from rest_framework.exceptions import ValidationError
      from datetime import datetime
      from .models import BankAccount, BankTransaction
      from journals.models import JournalEntry, JournalLine

      source_bank = BankAccount.nodes.get_or_none(bank_account_id=source_bank_id)
      if not source_bank:
          raise ValidationError('Source bank account not found.')
      source_gl = source_bank.gl_account.single()
      if not source_gl:
          raise ValidationError('Source bank account has no linked GL account.')

      if transaction_type == 'TRANSFER':
          if not destination_bank_id:
              raise ValidationError('destination_bank_id is required for TRANSFER.')
          if destination_bank_id == source_bank_id:
              raise ValidationError('Source and destination bank accounts must differ.')
          dest_bank = BankAccount.nodes.get_or_none(bank_account_id=destination_bank_id)
          if not dest_bank:
              raise ValidationError('Destination bank account not found.')
          dest_gl = dest_bank.gl_account.single()
          if not dest_gl:
              raise ValidationError('Destination bank account has no linked GL account.')
          if not amount or float(amount) <= 0:
              raise ValidationError('Amount must be positive for TRANSFER.')
          total_amount = float(amount)
      else:
          if not splits:
              raise ValidationError('At least one split is required.')
          for split in splits:
              if float(split['amount']) <= 0:
                  raise ValidationError('Each split amount must be positive.')
          total_amount = sum(float(s['amount']) for s in splits)

      reference = generate_bank_transaction_reference()
      now = datetime.utcnow()

      entry = JournalEntry(
          reference=reference,
          date=date,
          description=description,
          status='POSTED',
          entry_type='BANK_TRANSACTION',
          total_debit=total_amount,
          total_credit=total_amount,
          created_by=created_by,
          approved_by=created_by,
          approved_at=now,
      )
      entry.save()

      if transaction_type == 'TRANSFER':
          credit_line = JournalLine(side='CREDIT', amount=total_amount, description=description)
          credit_line.save()
          credit_line.account.connect(source_gl)
          entry.lines.connect(credit_line)

          debit_line = JournalLine(side='DEBIT', amount=total_amount, description=description)
          debit_line.save()
          debit_line.account.connect(dest_gl)
          entry.lines.connect(debit_line)
      else:
          bank_side = 'DEBIT' if transaction_type == 'RECEIPT' else 'CREDIT'
          bank_line = JournalLine(side=bank_side, amount=total_amount, description=description)
          bank_line.save()
          bank_line.account.connect(source_gl)
          entry.lines.connect(bank_line)

          contra_side = 'CREDIT' if transaction_type == 'RECEIPT' else 'DEBIT'
          from accounts.models import Account
          for split in splits:
              contra_acct = Account.nodes.get_or_none(account_id=split['account_id'])
              if not contra_acct:
                  raise ValidationError(f"Account {split['account_id']} not found.")
              split_line = JournalLine(
                  side=contra_side,
                  amount=float(split['amount']),
                  description=split.get('description', ''),
              )
              split_line.save()
              split_line.account.connect(contra_acct)
              entry.lines.connect(split_line)

      txn = BankTransaction(
          reference=reference,
          transaction_type=transaction_type,
          date=date,
          amount=total_amount,
          description=description,
          created_by=created_by,
      )
      txn.save()
      txn.source_bank.connect(source_bank)
      if transaction_type == 'TRANSFER':
          txn.destination_bank.connect(dest_bank)
      txn.journal_entry.connect(entry)

      return txn
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  docker exec django_backend python manage.py test banks.tests --verbosity=2 2>&1 | tail -20
  ```

  Expected: `Ran 4 tests in ...s` — `OK`

- [ ] **Step 5: Commit**

  ```bash
  git add backend/banks/services.py backend/banks/tests.py
  git commit -m "feat: Add bank transaction reference generator and create_bank_transaction service"
  ```

---

## Task B3: BankTransaction serializers

**Files:**
- Modify: `backend/banks/serializers.py`

- [ ] **Step 1: Append serializers to `backend/banks/serializers.py`**

  Add after the existing `BankReconciliationSerializer` class:

  ```python
  class BankTransactionSplitSerializer(serializers.Serializer):
      account_id = serializers.CharField()
      amount = serializers.FloatField(min_value=0.01)
      description = serializers.CharField(default='', allow_blank=True)


  class BankTransactionSerializer(serializers.Serializer):
      transaction_id = serializers.CharField(read_only=True)
      reference = serializers.CharField(read_only=True)
      transaction_type = serializers.ChoiceField(choices=['RECEIPT', 'PAYMENT', 'TRANSFER'])
      date = serializers.DateField()
      amount = serializers.FloatField(read_only=True)
      description = serializers.CharField(max_length=500)
      created_by = serializers.CharField(read_only=True)
      created_at = serializers.DateTimeField(read_only=True)

      # Write-only inputs
      source_bank_id = serializers.CharField(write_only=True)
      destination_bank_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
      transfer_amount = serializers.FloatField(write_only=True, required=False, allow_null=True, min_value=0.01)
      splits = BankTransactionSplitSerializer(many=True, required=False, default=list)

      # Read-only derived fields
      source_bank_name = serializers.SerializerMethodField()
      destination_bank_name = serializers.SerializerMethodField()
      entry_id = serializers.SerializerMethodField()

      def get_source_bank_name(self, obj):
          try:
              ba = obj.source_bank.single()
              return ba.name if ba else None
          except Exception:
              return None

      def get_destination_bank_name(self, obj):
          try:
              ba = obj.destination_bank.single()
              return ba.name if ba else None
          except Exception:
              return None

      def get_entry_id(self, obj):
          try:
              entry = obj.journal_entry.single()
              return entry.entry_id if entry else None
          except Exception:
              return None

      def validate(self, data):
          txn_type = data.get('transaction_type')
          if txn_type == 'TRANSFER':
              if not data.get('destination_bank_id'):
                  raise serializers.ValidationError({'destination_bank_id': 'Required for TRANSFER.'})
              if not data.get('transfer_amount'):
                  raise serializers.ValidationError({'transfer_amount': 'Required for TRANSFER.'})
          else:
              if not data.get('splits'):
                  raise serializers.ValidationError({'splits': 'At least one split is required for RECEIPT/PAYMENT.'})
          return data
  ```

- [ ] **Step 2: Verify Django can import the new serializers**

  ```bash
  docker exec django_backend python -c "from banks.serializers import BankTransactionSerializer; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 3: Commit**

  ```bash
  git add backend/banks/serializers.py
  git commit -m "feat: Add BankTransactionSerializer and BankTransactionSplitSerializer"
  ```

---

## Task B4: BankTransactionViewSet + URL registration

**Files:**
- Modify: `backend/banks/views.py`
- Modify: `backend/banks/urls.py`

- [ ] **Step 1: Add import for `BankTransaction` at the top of `backend/banks/views.py`**

  Change the existing model import line from:
  ```python
  from .models import BankAccount
  ```
  to:
  ```python
  from .models import BankAccount, BankTransaction
  ```

  Change the serializer import line from:
  ```python
  from .serializers import BankAccountSerializer, BankReconciliationSerializer
  ```
  to:
  ```python
  from .serializers import BankAccountSerializer, BankReconciliationSerializer, BankTransactionSerializer
  ```

- [ ] **Step 2: Append `BankTransactionViewSet` at the end of `backend/banks/views.py`**

  ```python
  class BankTransactionViewSet(viewsets.ViewSet):
      permission_classes = [IsAuthenticated]

      def list(self, request):
          bank_account_id = request.query_params.get('bank_account_id')
          if bank_account_id:
              from neomodel import db
              results, _ = db.cypher_query(
                  "MATCH (t:BankTransaction)-[:FROM_BANK]->(ba:BankAccount {bank_account_id: $id}) "
                  "RETURN t.transaction_id ORDER BY t.created_at DESC",
                  {'id': bank_account_id}
              )
              txns = [BankTransaction.nodes.get_or_none(transaction_id=row[0]) for row in results]
          else:
              txns = list(BankTransaction.nodes.all())
              txns = sorted(txns, key=lambda t: str(t.created_at), reverse=True)
          return Response(BankTransactionSerializer([t for t in txns if t], many=True).data)

      def retrieve(self, request, pk=None):
          txn = BankTransaction.nodes.get_or_none(transaction_id=pk)
          if not txn:
              return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
          return Response(BankTransactionSerializer(txn).data)

      def create(self, request):
          serializer = BankTransactionSerializer(data=request.data)
          serializer.is_valid(raise_exception=True)
          data = serializer.validated_data
          from . import services
          try:
              txn = services.create_bank_transaction(
                  transaction_type=data['transaction_type'],
                  date=data['date'],
                  description=data['description'],
                  source_bank_id=data['source_bank_id'],
                  destination_bank_id=data.get('destination_bank_id'),
                  splits=data.get('splits', []),
                  amount=data.get('transfer_amount'),
                  created_by=request.user.username,
              )
          except Exception as e:
              return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
          return Response(BankTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
  ```

- [ ] **Step 3: Register the viewset in `backend/banks/urls.py`**

  Replace the entire file with:

  ```python
  from django.urls import path, include
  from rest_framework.routers import DefaultRouter
  from .views import BankAccountViewSet, BankReconciliationViewSet, BankTransactionViewSet

  router = DefaultRouter()
  router.register('accounts', BankAccountViewSet, basename='bank-account')
  router.register('reconciliations', BankReconciliationViewSet, basename='bank-reconciliation')
  router.register('transactions', BankTransactionViewSet, basename='bank-transaction')

  urlpatterns = [
      path('', include(router.urls)),
  ]
  ```

- [ ] **Step 4: Smoke-test the endpoint**

  ```bash
  docker exec django_backend python manage.py shell -c "
  from django.test import RequestFactory
  from banks.views import BankTransactionViewSet
  print('ViewSet imported OK')
  "
  ```

  Expected: `ViewSet imported OK`

- [ ] **Step 5: Commit**

  ```bash
  git add backend/banks/views.py backend/banks/urls.py
  git commit -m "feat: Add BankTransactionViewSet and register /api/banks/transactions/ endpoint"
  ```

---

## Task F1: BankTransactionsService (frontend)

**Files:**
- Create: `frontend/sage-frontend/src/app/services/bank-transactions.service.ts`

- [ ] **Step 1: Create the service file**

  ```typescript
  import { Injectable } from '@angular/core';
  import axios from 'axios';

  @Injectable({ providedIn: 'root' })
  export class BankTransactionsService {
    private baseUrl = 'http://localhost:8002/api/banks/transactions/';

    getAll(bankAccountId?: string) {
      const params = bankAccountId ? { bank_account_id: bankAccountId } : {};
      return axios.get(this.baseUrl, { params }).then(r => r.data);
    }

    getOne(id: string) {
      return axios.get(this.baseUrl + `${id}/`).then(r => r.data);
    }

    create(data: object) {
      return axios.post(this.baseUrl, data).then(r => r.data);
    }
  }
  ```

- [ ] **Step 2: Verify TypeScript compiles**

  ```bash
  cd "frontend/sage-frontend" && npx tsc --noEmit 2>&1 | head -20
  ```

  Expected: no output (zero errors).

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/sage-frontend/src/app/services/bank-transactions.service.ts
  git commit -m "feat: Add BankTransactionsService (frontend)"
  ```

---

## Task F2: BankTransactionListComponent

**Files:**
- Create: `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.ts`
- Create: `frontend/sage-frontend/src/app/banks/bank-transaction-list/bank-transaction-list.component.html`

- [ ] **Step 1: Create the component TypeScript file**

  ```typescript
  import { Component, OnInit } from '@angular/core';
  import { CommonModule } from '@angular/common';
  import { RouterModule } from '@angular/router';
  import { FormsModule } from '@angular/forms';
  import { BankTransactionsService } from '../../services/bank-transactions.service';
  import { BanksService } from '../../services/banks.service';

  @Component({
    selector: 'app-bank-transaction-list',
    standalone: true,
    imports: [CommonModule, RouterModule, FormsModule],
    templateUrl: './bank-transaction-list.component.html',
  })
  export class BankTransactionListComponent implements OnInit {
    transactions: any[] = [];
    banks: any[] = [];
    selectedBankId = '';
    loading = true;
    error = '';

    constructor(
      private txnService: BankTransactionsService,
      private banksService: BanksService,
    ) {}

    async ngOnInit() {
      try {
        const [txns, banks] = await Promise.all([
          this.txnService.getAll(),
          this.banksService.getAccounts(),
        ]);
        this.transactions = txns.results ?? txns;
        this.banks = banks.results ?? banks;
      } catch {
        this.error = 'Failed to load transactions.';
      } finally {
        this.loading = false;
      }
    }

    async filterByBank() {
      this.loading = true;
      this.error = '';
      try {
        const data = await this.txnService.getAll(this.selectedBankId || undefined);
        this.transactions = data.results ?? data;
      } catch {
        this.error = 'Failed to filter transactions.';
      } finally {
        this.loading = false;
      }
    }

    typeColor(type: string): string {
      const map: Record<string, string> = {
        RECEIPT: '#10b981',
        PAYMENT: '#ef4444',
        TRANSFER: '#3b82f6',
      };
      return map[type] ?? '#888';
    }
  }
  ```

- [ ] **Step 2: Create the template file**

  ```html
  <div class="page-header">
    <h1 class="page-title">Bank Transactions</h1>
    <a routerLink="/banks/transactions/new" class="btn-primary">+ New Transaction</a>
  </div>

  <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.25rem">
    <label style="font-size:.85rem;color:var(--text-secondary);font-weight:600">Filter by bank:</label>
    <select [(ngModel)]="selectedBankId" (ngModelChange)="filterByBank()"
      style="padding:.45rem .75rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;background:var(--white);color:var(--text-primary)">
      <option value="">All banks</option>
      @for (bank of banks; track bank.bank_account_id) {
        <option [value]="bank.bank_account_id">{{ bank.name }}</option>
      }
    </select>
  </div>

  @if (loading) { <p style="color:var(--text-muted)">Loading…</p> }
  @if (error) { <p style="color:var(--danger)">{{ error }}</p> }

  @if (!loading && !error) {
    <div class="card">
      <table class="data-table">
        <thead>
          <tr>
            <th>Reference</th>
            <th>Date</th>
            <th>Bank</th>
            <th>Type</th>
            <th>Description</th>
            <th style="text-align:right">Amount (₦)</th>
          </tr>
        </thead>
        <tbody>
          @for (txn of transactions; track txn.transaction_id) {
            <tr>
              <td class="mono">{{ txn.reference }}</td>
              <td>{{ txn.date }}</td>
              <td>{{ txn.source_bank_name }}</td>
              <td>
                <span [style.color]="typeColor(txn.transaction_type)"
                  style="font-weight:700;font-size:.8rem;text-transform:uppercase">
                  {{ txn.transaction_type }}
                </span>
              </td>
              <td style="color:var(--text-secondary)">{{ txn.description }}</td>
              <td class="mono" style="text-align:right">{{ txn.amount | number:'1.2-2' }}</td>
            </tr>
          }
          @empty {
            <tr>
              <td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem">
                No transactions found.
              </td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  }
  ```

- [ ] **Step 3: Verify build**

  ```bash
  cd "frontend/sage-frontend" && npx ng build --configuration development 2>&1 | tail -5
  ```

  Expected: `Application bundle generation complete.` with no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/sage-frontend/src/app/banks/bank-transaction-list/
  git commit -m "feat: Add BankTransactionListComponent"
  ```

---

## Task F3: BankTransactionFormComponent

**Files:**
- Create: `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.ts`
- Create: `frontend/sage-frontend/src/app/banks/bank-transaction-form/bank-transaction-form.component.html`

- [ ] **Step 1: Create the component TypeScript file**

  ```typescript
  import { Component, OnInit } from '@angular/core';
  import { CommonModule } from '@angular/common';
  import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
  import { ActivatedRoute, Router } from '@angular/router';
  import { BankTransactionsService } from '../../services/bank-transactions.service';
  import { BanksService } from '../../services/banks.service';
  import { AccountsService } from '../../services/accounts.service';

  @Component({
    selector: 'app-bank-transaction-form',
    standalone: true,
    imports: [CommonModule, ReactiveFormsModule],
    templateUrl: './bank-transaction-form.component.html',
  })
  export class BankTransactionFormComponent implements OnInit {
    form!: FormGroup;
    banks: any[] = [];
    accounts: any[] = [];
    saving = false;
    error = '';

    get splits(): FormArray { return this.form.get('splits') as FormArray; }
    get transactionType(): string { return this.form.get('transaction_type')?.value ?? ''; }
    get totalSplits(): number {
      return this.splits.controls.reduce((sum, c) => sum + (Number(c.value.amount) || 0), 0);
    }

    constructor(
      private fb: FormBuilder,
      private route: ActivatedRoute,
      private router: Router,
      private txnService: BankTransactionsService,
      private banksService: BanksService,
      private accountsService: AccountsService,
    ) {}

    async ngOnInit() {
      const preBankId = this.route.snapshot.queryParamMap.get('bank_id') ?? '';
      this.form = this.fb.group({
        transaction_type: ['RECEIPT', Validators.required],
        source_bank_id: [preBankId, Validators.required],
        destination_bank_id: [''],
        date: [new Date().toISOString().slice(0, 10), Validators.required],
        description: ['', Validators.required],
        transfer_amount: [null],
        splits: this.fb.array([]),
      });
      this.addSplit();
      try {
        const [banks, accounts] = await Promise.all([
          this.banksService.getAccounts(),
          this.accountsService.getAll(),
        ]);
        this.banks = banks.results ?? banks;
        this.accounts = accounts.results ?? accounts;
      } catch {
        this.error = 'Failed to load reference data.';
      }
    }

    addSplit() {
      this.splits.push(this.fb.group({
        account_id: ['', Validators.required],
        amount: [null, [Validators.required, Validators.min(0.01)]],
        description: [''],
      }));
    }

    removeSplit(i: number) {
      if (this.splits.length > 1) this.splits.removeAt(i);
    }

    async submit() {
      if (this.form.invalid) return;
      this.saving = true;
      this.error = '';
      const val = this.form.value;
      const payload: any = {
        transaction_type: val.transaction_type,
        date: val.date,
        description: val.description,
        source_bank_id: val.source_bank_id,
      };
      if (val.transaction_type === 'TRANSFER') {
        payload.destination_bank_id = val.destination_bank_id;
        payload.transfer_amount = Number(val.transfer_amount);
      } else {
        payload.splits = val.splits.map((s: any) => ({
          account_id: s.account_id,
          amount: Number(s.amount),
          description: s.description,
        }));
      }
      try {
        await this.txnService.create(payload);
        this.router.navigate(['/banks', val.source_bank_id]);
      } catch (e: any) {
        this.error = e.response?.data?.detail ?? JSON.stringify(e.response?.data) ?? 'Failed to save transaction.';
      } finally {
        this.saving = false;
      }
    }
  }
  ```

- [ ] **Step 2: Create the template file**

  ```html
  <div style="max-width:820px">
    <h1 class="page-title" style="margin-bottom:1.5rem">New Bank Transaction</h1>

    @if (error) {
      <p style="color:var(--danger);margin-bottom:1rem;font-size:.875rem">{{ error }}</p>
    }

    <form [formGroup]="form">
      <!-- Type selector -->
      <div class="card" style="padding:1.25rem;margin-bottom:1rem">
        <p style="font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-bottom:.75rem">Transaction Type</p>
        <div style="display:flex;gap:.5rem">
          @for (type of ['RECEIPT','PAYMENT','TRANSFER']; track type) {
            <button type="button" (click)="form.get('transaction_type')!.setValue(type)"
              [style.background]="transactionType === type ? 'var(--navy-primary)' : 'var(--white)'"
              [style.color]="transactionType === type ? '#fff' : 'var(--text-secondary)'"
              [style.borderColor]="transactionType === type ? 'var(--navy-primary)' : 'var(--border)'"
              style="padding:.5rem 1.25rem;border:1.5px solid;border-radius:var(--radius-sm);cursor:pointer;font-weight:700;font-size:.875rem;font-family:var(--font-body);transition:all 150ms">
              {{ type }}
            </button>
          }
        </div>
      </div>

      <!-- Header fields -->
      <div class="card" style="padding:1.25rem;margin-bottom:1rem">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem">
          <div>
            <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Source Bank Account *</label>
            <select formControlName="source_bank_id"
              style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box">
              <option value="">— select bank —</option>
              @for (bank of banks; track bank.bank_account_id) {
                <option [value]="bank.bank_account_id">{{ bank.name }}</option>
              }
            </select>
          </div>

          @if (transactionType === 'TRANSFER') {
            <div>
              <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Destination Bank Account *</label>
              <select formControlName="destination_bank_id"
                style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box">
                <option value="">— select bank —</option>
                @for (bank of banks; track bank.bank_account_id) {
                  <option [value]="bank.bank_account_id">{{ bank.name }}</option>
                }
              </select>
            </div>
          }
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
          <div>
            <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Date *</label>
            <input formControlName="date" type="date"
              style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
          </div>
          <div>
            <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Description *</label>
            <input formControlName="description" placeholder="e.g. Utility payment"
              style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-body);font-size:.875rem;box-sizing:border-box" />
          </div>
        </div>
      </div>

      <!-- Transfer amount (TRANSFER only) -->
      @if (transactionType === 'TRANSFER') {
        <div class="card" style="padding:1.25rem;margin-bottom:1rem">
          <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.3rem">Amount (₦) *</label>
          <input formControlName="transfer_amount" type="number" min="0.01" step="0.01" placeholder="0.00"
            style="width:240px;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
        </div>
      }

      <!-- Splits table (RECEIPT / PAYMENT only) -->
      @if (transactionType !== 'TRANSFER') {
        <div class="card" style="margin-bottom:1rem;overflow:hidden">
          <table style="width:100%;border-collapse:collapse">
            <thead style="background:var(--navy-subtle)">
              <tr>
                <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Contra Account</th>
                <th style="text-align:right;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep);width:160px">Amount (₦)</th>
                <th style="text-align:left;padding:.75rem 1rem;font-size:.8rem;font-weight:700;color:var(--navy-deep)">Memo</th>
                <th style="width:36px"></th>
              </tr>
            </thead>
            <tbody formArrayName="splits">
              @for (split of splits.controls; track $index) {
                <tr [formGroupName]="$index" style="border-top:1px solid var(--border)">
                  <td style="padding:.5rem 1rem">
                    <select formControlName="account_id"
                      style="width:100%;padding:.4rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-body);font-size:.84rem">
                      <option value="">— select account —</option>
                      @for (acct of accounts; track acct.account_id) {
                        <option [value]="acct.account_id">{{ acct.code }} — {{ acct.name }}</option>
                      }
                    </select>
                  </td>
                  <td style="padding:.5rem 1rem">
                    <input formControlName="amount" type="number" min="0.01" step="0.01" placeholder="0.00"
                      style="width:100%;padding:.4rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-mono);font-size:.875rem;text-align:right;box-sizing:border-box" />
                  </td>
                  <td style="padding:.5rem 1rem">
                    <input formControlName="description" placeholder="optional"
                      style="width:100%;padding:.4rem;border:1.5px solid var(--border);border-radius:var(--radius-xs);font-family:var(--font-body);font-size:.84rem;box-sizing:border-box" />
                  </td>
                  <td style="padding:.5rem;text-align:center">
                    <button type="button" (click)="removeSplit($index)"
                      style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:1rem;line-height:1">✕</button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;background:var(--navy-subtle);border-top:1px solid var(--border)">
            <button type="button" (click)="addSplit()"
              style="background:none;border:1.5px dashed var(--border-strong);padding:.375rem .875rem;border-radius:var(--radius-sm);cursor:pointer;color:var(--text-secondary);font-size:.875rem;font-family:var(--font-body)">
              + Add split
            </button>
            <span class="mono" style="font-size:.9rem;color:var(--text-secondary)">
              Total: <strong>₦{{ totalSplits | number:'1.2-2' }}</strong>
            </span>
          </div>
        </div>
      }

      <!-- Actions -->
      <div style="display:flex;gap:.75rem">
        <button type="button" (click)="submit()" [disabled]="form.invalid || saving"
          class="btn-primary">
          {{ saving ? 'Posting…' : 'Post Transaction' }}
        </button>
        <a routerLink="/banks/transactions" class="btn-secondary">Cancel</a>
      </div>
    </form>
  </div>
  ```

  Note: the `routerLink` on the Cancel anchor requires `RouterModule` in imports. Add it:

  In the component TS, `imports` already includes `ReactiveFormsModule` — add `RouterModule`:

  ```typescript
  imports: [CommonModule, ReactiveFormsModule, RouterModule],
  ```

  and add `RouterModule` to the import statement at the top:

  ```typescript
  import { ActivatedRoute, Router, RouterModule } from '@angular/router';
  ```

- [ ] **Step 3: Verify build**

  ```bash
  cd "frontend/sage-frontend" && npx ng build --configuration development 2>&1 | tail -5
  ```

  Expected: `Application bundle generation complete.` with no errors.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/sage-frontend/src/app/banks/bank-transaction-form/
  git commit -m "feat: Add BankTransactionFormComponent"
  ```

---

## Task F4: Wire up routes, nav, and bank account detail tab

**Files:**
- Modify: `frontend/sage-frontend/src/app/app.routes.ts`
- Modify: `frontend/sage-frontend/src/app/shell/shell.component.html`
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-detail/bank-account-detail.component.ts`
- Modify: `frontend/sage-frontend/src/app/banks/bank-account-detail/bank-account-detail.component.html`

- [ ] **Step 1: Add routes to `app.routes.ts`**

  The existing routes for `banks` are:
  ```typescript
  { path: 'banks', loadComponent: ... BankAccountListComponent },
  { path: 'banks/reconciliations/:id', loadComponent: ... BankReconciliationComponent },
  { path: 'banks/:id', loadComponent: ... BankAccountDetailComponent },
  ```

  Insert the two new routes BEFORE `banks/reconciliations/:id` (so they don't match as `:id`):

  ```typescript
  {
    path: 'banks/transactions/new',
    loadComponent: () => import('./banks/bank-transaction-form/bank-transaction-form.component').then(m => m.BankTransactionFormComponent)
  },
  {
    path: 'banks/transactions',
    loadComponent: () => import('./banks/bank-transaction-list/bank-transaction-list.component').then(m => m.BankTransactionListComponent)
  },
  ```

  After insertion the ordering must be:
  1. `banks` (list)
  2. `banks/transactions/new`
  3. `banks/transactions`
  4. `banks/reconciliations/:id`
  5. `banks/:id`

- [ ] **Step 2: Add Transactions nav link in `shell.component.html`**

  Inside the `@if (open['gl'])` block, after the `Banks Accounts` link, add:

  ```html
  <a routerLink="/banks/transactions" routerLinkActive="active-link" class="nav-child-link">Bank Transactions</a>
  ```

  The full GL section block should now read:

  ```html
  @if (open['gl']) {
    <a routerLink="/accounts" routerLinkActive="active-link" class="nav-child-link">Chart of Accounts</a>
    <a routerLink="/journals" routerLinkActive="active-link" class="nav-child-link">Journal Entries</a>
    <a routerLink="/banks" routerLinkActive="active-link" class="nav-child-link">Bank Accounts</a>
    <a routerLink="/banks/transactions" routerLinkActive="active-link" class="nav-child-link">Bank Transactions</a>
  }
  ```

- [ ] **Step 3: Update `bank-account-detail.component.ts`**

  Replace the entire file with the updated version that adds a Transactions tab:

  ```typescript
  import { Component, OnInit } from '@angular/core';
  import { CommonModule } from '@angular/common';
  import { RouterModule, ActivatedRoute, Router } from '@angular/router';
  import { FormsModule } from '@angular/forms';
  import { BanksService } from '../../services/banks.service';
  import { BankTransactionsService } from '../../services/bank-transactions.service';

  @Component({
    selector: 'app-bank-account-detail',
    standalone: true,
    imports: [CommonModule, RouterModule, FormsModule],
    templateUrl: './bank-account-detail.component.html',
  })
  export class BankAccountDetailComponent implements OnInit {
    account: any = null;
    reconciliations: any[] = [];
    transactions: any[] = [];
    loading = true;
    error = '';
    activeTab = 'reconciliations';
    txnLoading = false;

    showForm = false;
    formPeriodStart = '';
    formPeriodEnd = '';
    formStatementBalance = '';
    saving = false;
    formError = '';

    private id = '';

    constructor(
      private route: ActivatedRoute,
      private router: Router,
      private banksService: BanksService,
      private txnService: BankTransactionsService,
    ) {}

    async ngOnInit() {
      this.id = this.route.snapshot.paramMap.get('id') ?? '';
      try {
        const [account, reconciliations] = await Promise.all([
          this.banksService.getAccount(this.id),
          this.banksService.getAccountReconciliations(this.id),
        ]);
        this.account = account;
        this.reconciliations = reconciliations.results ?? reconciliations;
      } catch {
        this.error = 'Failed to load bank account details.';
      } finally {
        this.loading = false;
      }
    }

    async setTab(tab: string) {
      this.activeTab = tab;
      if (tab === 'transactions' && this.transactions.length === 0) {
        this.txnLoading = true;
        try {
          const data = await this.txnService.getAll(this.id);
          this.transactions = data.results ?? data;
        } catch {
          this.error = 'Failed to load transactions.';
        } finally {
          this.txnLoading = false;
        }
      }
    }

    toggleForm() {
      this.showForm = !this.showForm;
      this.formError = '';
      this.formPeriodStart = '';
      this.formPeriodEnd = '';
      this.formStatementBalance = '';
    }

    async submitCreate() {
      if (!this.formPeriodStart || !this.formPeriodEnd || !this.formStatementBalance) return;
      this.saving = true;
      this.formError = '';
      try {
        await this.banksService.createReconciliation({
          bank_account_id: this.id,
          period_start: this.formPeriodStart,
          period_end: this.formPeriodEnd,
          statement_balance: +this.formStatementBalance,
        });
        const data = await this.banksService.getAccountReconciliations(this.id);
        this.reconciliations = data.results ?? data;
        this.showForm = false;
        this.formPeriodStart = '';
        this.formPeriodEnd = '';
        this.formStatementBalance = '';
      } catch (e: any) {
        this.formError = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create reconciliation.');
      } finally {
        this.saving = false;
      }
    }

    statusColor(status: string): string {
      if (status === 'COMPLETED') return '#10b981';
      if (status === 'DRAFT') return '#f59e0b';
      return '#888';
    }

    typeColor(type: string): string {
      const map: Record<string, string> = {
        RECEIPT: '#10b981',
        PAYMENT: '#ef4444',
        TRANSFER: '#3b82f6',
      };
      return map[type] ?? '#888';
    }
  }
  ```

- [ ] **Step 4: Update `bank-account-detail.component.html`**

  Replace the entire file:

  ```html
  @if (loading) { <p style="color:var(--text-muted)">Loading…</p> }
  @if (error) { <p style="color:var(--danger)">{{ error }}</p> }

  @if (!loading && !error && account) {
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ account.name }}</h1>
        <p class="page-subtitle">{{ account.bank_name }}</p>
      </div>
      <a [routerLink]="['/banks/transactions/new']" [queryParams]="{bank_id: account.bank_account_id}"
        class="btn-primary">+ New Transaction</a>
    </div>

    <!-- Account info card -->
    <div class="card" style="padding:1.25rem;margin-bottom:1.5rem">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem">
        <div>
          <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em">Account Number</div>
          <div class="mono">{{ account.account_number }}</div>
        </div>
        <div>
          <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em">Currency</div>
          <div>{{ account.currency }}</div>
        </div>
        <div>
          <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em">Opening Balance</div>
          <div class="mono">₦{{ account.opening_balance | number:'1.2-2' }}</div>
        </div>
        <div>
          <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em">Opening Date</div>
          <div>{{ account.opening_balance_date }}</div>
        </div>
        <div>
          <div style="font-size:.75rem;color:var(--text-muted);margin-bottom:.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em">GL Account</div>
          <div class="mono" style="font-size:.875rem">{{ account.gl_account_id ?? '—' }}</div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-bar" style="margin-bottom:1.25rem">
      <button class="tab-btn" [class.active]="activeTab === 'reconciliations'" (click)="setTab('reconciliations')">Reconciliations</button>
      <button class="tab-btn" [class.active]="activeTab === 'transactions'" (click)="setTab('transactions')">Transactions</button>
    </div>

    <!-- Reconciliations tab -->
    @if (activeTab === 'reconciliations') {
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
        <span style="font-size:.875rem;color:var(--text-muted)">{{ reconciliations.length }} reconciliation(s)</span>
        <button (click)="toggleForm()" class="btn-secondary" style="font-size:.8rem;padding:.4rem .9rem">
          {{ showForm ? 'Cancel' : '+ New Reconciliation' }}
        </button>
      </div>

      @if (showForm) {
        <div class="card" style="padding:1.25rem;margin-bottom:1rem">
          <h3 style="margin:0 0 1rem;font-size:1rem;color:var(--navy-deep)">New Reconciliation</h3>
          @if (formError) {
            <p style="color:var(--danger);margin:0 0 .75rem;font-size:.875rem">{{ formError }}</p>
          }
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;margin-bottom:1rem">
            <div>
              <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.25rem">Period Start *</label>
              <input [(ngModel)]="formPeriodStart" type="date"
                style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);box-sizing:border-box" />
            </div>
            <div>
              <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.25rem">Period End *</label>
              <input [(ngModel)]="formPeriodEnd" type="date"
                style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);box-sizing:border-box" />
            </div>
            <div>
              <label style="display:block;font-size:.8rem;color:var(--text-muted);font-weight:700;margin-bottom:.25rem">Statement Balance (₦) *</label>
              <input [(ngModel)]="formStatementBalance" type="number" step="0.01"
                style="width:100%;padding:.5rem;border:1.5px solid var(--border);border-radius:var(--radius-sm);box-sizing:border-box" />
            </div>
          </div>
          <button (click)="submitCreate()" [disabled]="!formPeriodStart || !formPeriodEnd || !formStatementBalance || saving"
            class="btn-primary" style="font-size:.875rem">
            {{ saving ? 'Creating…' : 'Create Reconciliation' }}
          </button>
        </div>
      }

      <div class="card">
        <table class="data-table">
          <thead>
            <tr>
              <th>Period</th>
              <th style="text-align:right">Statement Balance</th>
              <th>Status</th>
              <th>Created By</th>
            </tr>
          </thead>
          <tbody>
            @for (recon of reconciliations; track recon.reconciliation_id) {
              <tr style="cursor:pointer" [routerLink]="['/banks/reconciliations', recon.reconciliation_id]">
                <td>{{ recon.period_start }} → {{ recon.period_end }}</td>
                <td class="mono" style="text-align:right">₦{{ recon.statement_balance | number:'1.2-2' }}</td>
                <td>
                  <span [style.color]="statusColor(recon.status)" style="font-weight:700;font-size:.8rem">
                    {{ recon.status }}
                  </span>
                </td>
                <td style="color:var(--text-muted)">{{ recon.created_by }}</td>
              </tr>
            }
            @empty {
              <tr>
                <td colspan="4" style="text-align:center;color:var(--text-muted);padding:2rem">No reconciliations yet.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }

    <!-- Transactions tab -->
    @if (activeTab === 'transactions') {
      <div style="display:flex;justify-content:flex-end;margin-bottom:.75rem">
        <a [routerLink]="['/banks/transactions/new']" [queryParams]="{bank_id: account.bank_account_id}"
          class="btn-primary" style="font-size:.875rem">+ New Transaction</a>
      </div>

      @if (txnLoading) { <p style="color:var(--text-muted)">Loading…</p> }

      @if (!txnLoading) {
        <div class="card">
          <table class="data-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Date</th>
                <th>Type</th>
                <th>Description</th>
                <th style="text-align:right">Amount (₦)</th>
              </tr>
            </thead>
            <tbody>
              @for (txn of transactions; track txn.transaction_id) {
                <tr>
                  <td class="mono">{{ txn.reference }}</td>
                  <td>{{ txn.date }}</td>
                  <td>
                    <span [style.color]="typeColor(txn.transaction_type)"
                      style="font-weight:700;font-size:.8rem;text-transform:uppercase">
                      {{ txn.transaction_type }}
                    </span>
                  </td>
                  <td style="color:var(--text-secondary)">{{ txn.description }}</td>
                  <td class="mono" style="text-align:right">{{ txn.amount | number:'1.2-2' }}</td>
                </tr>
              }
              @empty {
                <tr>
                  <td colspan="5" style="text-align:center;color:var(--text-muted);padding:2rem">No transactions yet.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    }
  }
  ```

- [ ] **Step 5: Verify build**

  ```bash
  cd "frontend/sage-frontend" && npx ng build --configuration development 2>&1 | tail -5
  ```

  Expected: `Application bundle generation complete.` with no errors.

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/sage-frontend/src/app/app.routes.ts \
          frontend/sage-frontend/src/app/shell/shell.component.html \
          frontend/sage-frontend/src/app/banks/bank-account-detail/
  git commit -m "feat: Wire bank transaction routes, nav link, and detail page Transactions tab"
  ```

---

## Verification Checklist

After all tasks complete, verify end-to-end:

1. `GET /api/banks/transactions/` → returns `[]` (200)
2. `POST /api/banks/transactions/` with `transaction_type=RECEIPT`, valid `source_bank_id`, one split → returns 201 with a `BT-YYYY-NNNN` reference
3. `POST /api/banks/transactions/` with no linked GL account on source bank → returns 400 with descriptive error
4. `POST /api/banks/transactions/` unbalanced (TRANSFER with same source/destination) → returns 400
5. `GET /api/journals/entries/?status=POSTED` → the auto-created journal entry appears with `entry_type=BANK_TRANSACTION`
6. Angular: `/banks/transactions` loads with empty state
7. Angular: `/banks/transactions/new?bank_id=X` pre-selects the bank, type selector switches between RECEIPT/PAYMENT (shows splits table) and TRANSFER (shows destination bank + amount field)
8. Angular: submit a RECEIPT → redirected to bank account detail, Transactions tab shows the new entry
9. Angular: sidebar "Bank Transactions" link is visible under General Ledger
