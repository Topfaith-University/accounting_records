import { ColumnType, Generated } from 'kysely';

type Num = ColumnType<number, number, number>;
type Bool01 = ColumnType<number, number, number>;

export interface UsersTable {
  id: Generated<number>;
  username: string;
  email: string;
  password_hash: string;
  is_superuser: Bool01;
  created_at: Generated<string>;
}

export interface GroupsTable {
  id: Generated<number>;
  name: string;
}

export interface UserGroupsTable {
  user_id: number;
  group_id: number;
}

export interface CompaniesTable {
  id: string;
  name: string;
  created_at: Generated<string>;
}

export interface MembershipsTable {
  id: Generated<number>;
  user_id: number;
  company_id: string;
  role: string;
  created_at: Generated<string>;
}

export interface InviteCodesTable {
  id: Generated<number>;
  code: string;
  company_id: string | null;
  role: string;
  created_by: number | null;
  created_at: Generated<string>;
  expires_at: string;
  used_by: number | null;
  used_at: string | null;
}

export interface AccountsTable {
  account_id: string;
  company_id: string;
  code: string;
  name: string;
  account_type: string;
  normal_balance: 'DEBIT' | 'CREDIT';
  description: string;
  opening_balance: Num;
  is_active: Bool01;
  is_system: Bool01;
  parent_id: string | null;
  created_at: Generated<string>;
  updated_at: string;
}

export interface FiscalYearsTable {
  year_id: string;
  company_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: 'OPEN' | 'CLOSED';
  created_at: Generated<string>;
}

export interface AccountingPeriodsTable {
  period_id: string;
  company_id: string;
  fiscal_year_id: string;
  name: string;
  start_date: string;
  end_date: string;
  period_number: number;
  status: 'OPEN' | 'CLOSED';
}

export interface JournalEntriesTable {
  entry_id: string;
  company_id: string;
  reference: string;
  date: string;
  description: string;
  status: 'DRAFT' | 'POSTED' | 'VOID';
  entry_type: 'MANUAL' | 'BANK_RECON' | 'AP_PAYMENT' | 'AR_RECEIPT' | 'BANK_TRANSACTION';
  total_debit: Num;
  total_credit: Num;
  period_id: string | null;
  created_by: string;
  approved_by: string;
  approved_at: string | null;
  voided_by: string;
  voided_at: string | null;
  created_at: Generated<string>;
  updated_at: string;
}

export interface JournalLinesTable {
  line_id: string;
  company_id: string;
  entry_id: string;
  account_id: string;
  side: 'DEBIT' | 'CREDIT';
  amount: Num;
  description: string;
  created_at: Generated<string>;
}

export interface BankAccountsTable {
  bank_account_id: string;
  company_id: string;
  name: string;
  account_number: string | null;
  bank_name: string;
  currency: string;
  opening_balance: Num;
  opening_balance_date: string;
  gl_account_id: string | null;
  is_active: Bool01;
  created_at: Generated<string>;
  updated_at: string;
}

export interface BankReconciliationsTable {
  reconciliation_id: string;
  company_id: string;
  bank_account_id: string;
  period_start: string;
  period_end: string;
  statement_balance: Num;
  status: 'DRAFT' | 'COMPLETED';
  created_by: string;
  completed_at: string | null;
  created_at: Generated<string>;
}

export interface ReconciliationLinesTable {
  id: Generated<number>;
  reconciliation_id: string;
  journal_line_id: string;
}

export interface BankTransactionsTable {
  transaction_id: string;
  company_id: string;
  reference: string;
  transaction_type: 'RECEIPT' | 'PAYMENT' | 'TRANSFER';
  date: string;
  amount: Num;
  description: string;
  source_bank_id: string;
  destination_bank_id: string | null;
  journal_entry_id: string;
  vendor_id: string | null;
  customer_id: string | null;
  created_by: string;
  created_at: Generated<string>;
  updated_at: string;
}

export interface BankTxnCountersTable {
  id: Generated<number>;
  company_id: string;
  year: number;
  seq: number;
}

export interface InvoiceSettlementCountersTable {
  id: Generated<number>;
  company_id: string;
  prefix: string;
  invoice_number: string;
  seq: number;
}

export interface VendorsTable {
  vendor_id: string;
  company_id: string;
  name: string;
  email: string;
  phone: string;
  address: string;
  is_active: Bool01;
  created_at: Generated<string>;
}

export interface PurchaseInvoicesTable {
  invoice_id: string;
  company_id: string;
  invoice_number: string;
  date: string;
  due_date: string;
  description: string;
  status: 'DRAFT' | 'POSTED' | 'PAID' | 'VOID';
  total_amount: Num;
  amount_paid: Num;
  vendor_id: string;
  ap_account_id: string;
  journal_entry_id: string | null;
  created_by: string;
  created_at: Generated<string>;
}

export interface PurchaseInvoiceLinesTable {
  line_id: string;
  company_id: string;
  invoice_id: string;
  description: string;
  quantity: Num;
  unit_price: Num;
  amount: Num;
  expense_account_id: string;
}

export interface ItemsTable {
  item_id: string;
  company_id: string;
  name: string;
  description: string;
  cost_price: Num;
  selling_price: Num;
  item_type: 'PRODUCT' | 'SERVICE';
  vendor_id: string | null;
  expense_account_id: string | null;
  revenue_account_id: string | null;
  is_active: Bool01;
  created_at: Generated<string>;
}

export interface ApPaymentsTable {
  payment_id: string;
  company_id: string;
  invoice_id: string;
  payment_date: string;
  amount: Num;
  reference: string;
  bank_account_id: string;
  journal_entry_id: string | null;
  created_by: string;
  created_at: Generated<string>;
}

export interface CustomersTable {
  customer_id: string;
  company_id: string;
  name: string;
  email: string;
  phone: string;
  address: string;
  customer_type: 'STUDENT' | 'EXTERNAL';
  is_active: Bool01;
  created_at: Generated<string>;
}

export interface SalesInvoicesTable {
  invoice_id: string;
  company_id: string;
  invoice_number: string;
  date: string;
  due_date: string;
  description: string;
  status: 'DRAFT' | 'POSTED' | 'PAID' | 'VOID';
  total_amount: Num;
  amount_received: Num;
  customer_id: string;
  ar_account_id: string;
  journal_entry_id: string | null;
  created_by: string;
  created_at: Generated<string>;
}

export interface SalesInvoiceLinesTable {
  line_id: string;
  company_id: string;
  invoice_id: string;
  description: string;
  quantity: Num;
  unit_price: Num;
  amount: Num;
  revenue_account_id: string;
}

export interface ArReceiptsTable {
  receipt_id: string;
  company_id: string;
  invoice_id: string;
  receipt_date: string;
  amount: Num;
  reference: string;
  bank_account_id: string;
  journal_entry_id: string | null;
  created_by: string;
  created_at: Generated<string>;
}

export interface BudgetsTable {
  budget_id: string;
  company_id: string;
  name: string;
  fiscal_year: string;
  status: 'DRAFT' | 'APPROVED';
  created_by: string;
  approved_by: string;
  approved_at: string | null;
  created_at: Generated<string>;
}

export interface BudgetLinesTable {
  line_id: string;
  company_id: string;
  budget_id: string;
  account_id: string;
  budgeted_amount: Num;
  created_at: Generated<string>;
}

export interface Database {
  users: UsersTable;
  groups: GroupsTable;
  user_groups: UserGroupsTable;
  companies: CompaniesTable;
  memberships: MembershipsTable;
  invite_codes: InviteCodesTable;
  accounts: AccountsTable;
  fiscal_years: FiscalYearsTable;
  accounting_periods: AccountingPeriodsTable;
  journal_entries: JournalEntriesTable;
  journal_lines: JournalLinesTable;
  bank_accounts: BankAccountsTable;
  bank_reconciliations: BankReconciliationsTable;
  reconciliation_lines: ReconciliationLinesTable;
  bank_transactions: BankTransactionsTable;
  bank_txn_counters: BankTxnCountersTable;
  invoice_settlement_counters: InvoiceSettlementCountersTable;
  vendors: VendorsTable;
  purchase_invoices: PurchaseInvoicesTable;
  purchase_invoice_lines: PurchaseInvoiceLinesTable;
  items: ItemsTable;
  ap_payments: ApPaymentsTable;
  customers: CustomersTable;
  sales_invoices: SalesInvoicesTable;
  sales_invoice_lines: SalesInvoiceLinesTable;
  ar_receipts: ArReceiptsTable;
  budgets: BudgetsTable;
  budget_lines: BudgetLinesTable;
}
