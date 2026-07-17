/** Raw-SQL schema migrations, applied in order inside a single transaction on
 * startup. Mirrors the live Django+Neo4j schema per docs/electron-desktop-port/PRD.md
 * §3/§3a/§3b — every domain table carries company_id (§3a), items carries
 * cost_price/selling_price instead of unit_price (§3b). */
export interface Migration {
  name: string;
  sql: string;
}

export const MIGRATIONS: Migration[] = [
  {
    name: '001_initial',
    sql: `
      -- Auth / RBAC (mirrors Django's users app, SQLite side per CLAUDE.md's dual-database pattern)
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        is_superuser INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
      );

      CREATE TABLE IF NOT EXISTS user_groups (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, group_id)
      );

      CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS memberships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'Staff',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (user_id, company_id)
      );

      CREATE TABLE IF NOT EXISTS invite_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        company_id TEXT REFERENCES companies(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT 'Staff',
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        used_at TEXT
      );

      -- Accounts
      CREATE TABLE IF NOT EXISTS accounts (
        account_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        account_type TEXT NOT NULL,
        normal_balance TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        opening_balance REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        is_system INTEGER NOT NULL DEFAULT 0,
        parent_id TEXT REFERENCES accounts(account_id),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_accounts_company ON accounts(company_id);

      -- Journals
      CREATE TABLE IF NOT EXISTS fiscal_years (
        year_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_fiscal_years_company ON fiscal_years(company_id);

      CREATE TABLE IF NOT EXISTS accounting_periods (
        period_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        fiscal_year_id TEXT NOT NULL REFERENCES fiscal_years(year_id),
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        period_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN'
      );
      CREATE INDEX IF NOT EXISTS idx_periods_company ON accounting_periods(company_id);

      CREATE TABLE IF NOT EXISTS journal_entries (
        entry_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        reference TEXT NOT NULL,
        date TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        entry_type TEXT NOT NULL DEFAULT 'MANUAL',
        total_debit REAL NOT NULL DEFAULT 0,
        total_credit REAL NOT NULL DEFAULT 0,
        period_id TEXT REFERENCES accounting_periods(period_id),
        created_by TEXT NOT NULL,
        approved_by TEXT NOT NULL DEFAULT '',
        approved_at TEXT,
        voided_by TEXT NOT NULL DEFAULT '',
        voided_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_entries_company ON journal_entries(company_id);

      CREATE TABLE IF NOT EXISTS journal_lines (
        line_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        entry_id TEXT NOT NULL REFERENCES journal_entries(entry_id),
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        side TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_lines_company ON journal_lines(company_id);
      CREATE INDEX IF NOT EXISTS idx_lines_entry ON journal_lines(entry_id);
      CREATE INDEX IF NOT EXISTS idx_lines_account ON journal_lines(account_id);

      -- Banks
      CREATE TABLE IF NOT EXISTS bank_accounts (
        bank_account_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        account_number TEXT,
        bank_name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'NGN',
        opening_balance REAL NOT NULL DEFAULT 0,
        opening_balance_date TEXT NOT NULL,
        gl_account_id TEXT REFERENCES accounts(account_id),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_bank_accounts_company ON bank_accounts(company_id);

      CREATE TABLE IF NOT EXISTS bank_reconciliations (
        reconciliation_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        bank_account_id TEXT NOT NULL REFERENCES bank_accounts(bank_account_id),
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        statement_balance REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by TEXT NOT NULL,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_recon_company ON bank_reconciliations(company_id);

      CREATE TABLE IF NOT EXISTS reconciliation_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reconciliation_id TEXT NOT NULL REFERENCES bank_reconciliations(reconciliation_id) ON DELETE CASCADE,
        journal_line_id TEXT NOT NULL REFERENCES journal_lines(line_id),
        UNIQUE (reconciliation_id, journal_line_id)
      );

      CREATE TABLE IF NOT EXISTS bank_transactions (
        transaction_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        reference TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        date TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        source_bank_id TEXT NOT NULL REFERENCES bank_accounts(bank_account_id),
        destination_bank_id TEXT REFERENCES bank_accounts(bank_account_id),
        journal_entry_id TEXT NOT NULL REFERENCES journal_entries(entry_id),
        vendor_id TEXT,
        customer_id TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_bank_txn_company ON bank_transactions(company_id);

      CREATE TABLE IF NOT EXISTS bank_txn_counters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id TEXT NOT NULL,
        year INTEGER NOT NULL,
        seq INTEGER NOT NULL DEFAULT 0,
        UNIQUE (company_id, year)
      );

      CREATE TABLE IF NOT EXISTS invoice_settlement_counters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id TEXT NOT NULL,
        prefix TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        seq INTEGER NOT NULL DEFAULT 0,
        UNIQUE (company_id, prefix, invoice_number)
      );

      -- Payables
      CREATE TABLE IF NOT EXISTS vendors (
        vendor_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_vendors_company ON vendors(company_id);

      CREATE TABLE IF NOT EXISTS purchase_invoices (
        invoice_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'DRAFT',
        total_amount REAL NOT NULL DEFAULT 0,
        amount_paid REAL NOT NULL DEFAULT 0,
        vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
        ap_account_id TEXT NOT NULL REFERENCES accounts(account_id),
        journal_entry_id TEXT REFERENCES journal_entries(entry_id),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_pinv_company ON purchase_invoices(company_id);
      CREATE INDEX IF NOT EXISTS idx_pinv_vendor ON purchase_invoices(vendor_id);

      CREATE TABLE IF NOT EXISTS purchase_invoice_lines (
        line_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_id TEXT NOT NULL REFERENCES purchase_invoices(invoice_id) ON DELETE CASCADE,
        description TEXT NOT NULL DEFAULT '',
        quantity REAL NOT NULL DEFAULT 1,
        unit_price REAL NOT NULL DEFAULT 0,
        amount REAL NOT NULL,
        expense_account_id TEXT NOT NULL REFERENCES accounts(account_id)
      );
      CREATE INDEX IF NOT EXISTS idx_pinvl_invoice ON purchase_invoice_lines(invoice_id);

      CREATE TABLE IF NOT EXISTS items (
        item_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        cost_price REAL NOT NULL DEFAULT 0,
        selling_price REAL NOT NULL DEFAULT 0,
        item_type TEXT NOT NULL DEFAULT 'SERVICE',
        vendor_id TEXT REFERENCES vendors(vendor_id),
        expense_account_id TEXT REFERENCES accounts(account_id),
        revenue_account_id TEXT REFERENCES accounts(account_id),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_items_company ON items(company_id);

      CREATE TABLE IF NOT EXISTS ap_payments (
        payment_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_id TEXT NOT NULL REFERENCES purchase_invoices(invoice_id),
        payment_date TEXT NOT NULL,
        amount REAL NOT NULL,
        reference TEXT NOT NULL DEFAULT '',
        bank_account_id TEXT NOT NULL REFERENCES bank_accounts(bank_account_id),
        journal_entry_id TEXT REFERENCES journal_entries(entry_id),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_appay_invoice ON ap_payments(invoice_id);

      -- Receivables
      CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        customer_type TEXT NOT NULL DEFAULT 'EXTERNAL',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_customers_company ON customers(company_id);

      CREATE TABLE IF NOT EXISTS sales_invoices (
        invoice_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_number TEXT NOT NULL,
        date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'DRAFT',
        total_amount REAL NOT NULL DEFAULT 0,
        amount_received REAL NOT NULL DEFAULT 0,
        customer_id TEXT NOT NULL REFERENCES customers(customer_id),
        ar_account_id TEXT NOT NULL REFERENCES accounts(account_id),
        journal_entry_id TEXT REFERENCES journal_entries(entry_id),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_sinv_company ON sales_invoices(company_id);
      CREATE INDEX IF NOT EXISTS idx_sinv_customer ON sales_invoices(customer_id);

      CREATE TABLE IF NOT EXISTS sales_invoice_lines (
        line_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_id TEXT NOT NULL REFERENCES sales_invoices(invoice_id) ON DELETE CASCADE,
        description TEXT NOT NULL DEFAULT '',
        quantity REAL NOT NULL DEFAULT 1,
        unit_price REAL NOT NULL DEFAULT 0,
        amount REAL NOT NULL,
        revenue_account_id TEXT NOT NULL REFERENCES accounts(account_id)
      );
      CREATE INDEX IF NOT EXISTS idx_sinvl_invoice ON sales_invoice_lines(invoice_id);

      CREATE TABLE IF NOT EXISTS ar_receipts (
        receipt_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        invoice_id TEXT NOT NULL REFERENCES sales_invoices(invoice_id),
        receipt_date TEXT NOT NULL,
        amount REAL NOT NULL,
        reference TEXT NOT NULL DEFAULT '',
        bank_account_id TEXT NOT NULL REFERENCES bank_accounts(bank_account_id),
        journal_entry_id TEXT REFERENCES journal_entries(entry_id),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_arrec_invoice ON ar_receipts(invoice_id);

      -- Budget
      CREATE TABLE IF NOT EXISTS budgets (
        budget_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        fiscal_year TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by TEXT NOT NULL,
        approved_by TEXT NOT NULL DEFAULT '',
        approved_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_budgets_company ON budgets(company_id);

      CREATE TABLE IF NOT EXISTS budget_lines (
        line_id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        budget_id TEXT NOT NULL REFERENCES budgets(budget_id) ON DELETE CASCADE,
        account_id TEXT NOT NULL REFERENCES accounts(account_id),
        budgeted_amount REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      );
      CREATE INDEX IF NOT EXISTS idx_budgetl_budget ON budget_lines(budget_id);
    `,
  },
];
