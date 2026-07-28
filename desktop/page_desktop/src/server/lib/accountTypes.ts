/** Mirrors backend/accounts/enums.py's AccountType exactly (PRD §4.11). */
export const ACCOUNT_TYPES = [
  'Sales',
  'Cost of Sales',
  'Expenses',
  'Income Tax',
  'Non-Current Assets',
  'Current Assets',
  'Current Liabilities',
  'Non-Current Liabilities',
  "Owner's Equity",
  'Other Incomes',
] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number];

const DEBIT_NORMAL = new Set<AccountType>([
  'Non-Current Assets',
  'Current Assets',
  'Cost of Sales',
  'Expenses',
  'Income Tax',
]);

export function normalBalanceForType(accountType: string): 'DEBIT' | 'CREDIT' {
  return DEBIT_NORMAL.has(accountType as AccountType) ? 'DEBIT' : 'CREDIT';
}

/** Mirrors AccountSerializer._generate_account_code's type_prefixes map exactly,
 * including the intentional collisions (Expenses/Income Tax both '6000',
 * Sales/Other Incomes both '4000'). */
const CODE_PREFIXES: Record<string, string> = {
  Sales: '4000',
  'Cost of Sales': '5000',
  Expenses: '6000',
  'Income Tax': '6000',
  'Non-Current Assets': '1000',
  'Current Assets': '1100',
  'Current Liabilities': '2000',
  'Non-Current Liabilities': '2100',
  "Owner's Equity": '3000',
  'Other Incomes': '4000',
};

export function codePrefixForType(accountType: string): string {
  return CODE_PREFIXES[accountType] ?? '9000';
}
