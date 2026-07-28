import { Kysely, sql } from 'kysely';
import { Database } from '../db/types';
import { codePrefixForType } from '../lib/accountTypes';

/** Mirrors accounts/services.py's compute_account_balance — always derived from
 * posted journal lines, never a stored running total (PRD §4.5). */
export async function computeAccountBalance(
  db: Kysely<Database>,
  accountId: string,
  asOfDate?: string,
): Promise<number> {
  let query = db
    .selectFrom('journal_lines')
    .innerJoin('journal_entries', 'journal_entries.entry_id', 'journal_lines.entry_id')
    .innerJoin('accounts', 'accounts.account_id', 'journal_lines.account_id')
    .where('journal_lines.account_id', '=', accountId)
    .where('journal_entries.status', '=', 'POSTED');
  if (asOfDate) {
    query = query.where('journal_entries.date', '<=', asOfDate);
  }
  const row = await query
    .select([
      'accounts.normal_balance as normal_balance',
      sql<number>`coalesce(sum(case when journal_lines.side = 'DEBIT' then journal_lines.amount else 0 end), 0)`.as(
        'total_debits',
      ),
      sql<number>`coalesce(sum(case when journal_lines.side = 'CREDIT' then journal_lines.amount else 0 end), 0)`.as(
        'total_credits',
      ),
    ])
    .executeTakeFirst();

  if (!row) {
    const acct = await db.selectFrom('accounts').select('normal_balance').where('account_id', '=', accountId).executeTakeFirst();
    return acct ? 0 : 0;
  }
  const debits = row.total_debits ?? 0;
  const credits = row.total_credits ?? 0;
  const balance = row.normal_balance === 'DEBIT' ? debits - credits : credits - debits;
  return Math.round(balance * 100) / 100;
}

/** Mirrors AccountSerializer._generate_account_code exactly (PRD §4.1):
 * non-atomic scan-then-insert — find the max existing sequence for this
 * type's prefix within the company, increment, zero-pad to 4 digits. */
export async function generateAccountCode(
  db: Kysely<Database>,
  accountType: string,
  companyId: string,
): Promise<string> {
  const prefix = codePrefixForType(accountType);
  const existing = await db
    .selectFrom('accounts')
    .select('code')
    .where('company_id', '=', companyId)
    .where('code', 'like', `${prefix}%`)
    .execute();

  let maxSeq = 0;
  for (const { code } of existing) {
    const numericPart = code.length > prefix.length ? parseInt(code.slice(prefix.length), 10) : 0;
    if (!Number.isNaN(numericPart)) maxSeq = Math.max(maxSeq, numericPart);
  }
  const nextSeq = maxSeq + 1;
  return `${prefix}${String(nextSeq).padStart(4, '0')}`;
}
