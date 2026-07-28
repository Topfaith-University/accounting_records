import crypto from 'crypto';
import { Kysely } from 'kysely';
import { Database } from '../db/types';

/** Mirrors accounts/services.py's get_or_create_opening_balance_equity_account:
 * a system account, code 3900, created lazily per company. */
export async function getOrCreateOpeningBalanceEquityAccount(
  db: Kysely<Database>,
  companyId: string,
): Promise<{ account_id: string; company_id: string; normal_balance: 'DEBIT' | 'CREDIT'; name: string }> {
  const existing = await db
    .selectFrom('accounts')
    .select(['account_id', 'company_id', 'normal_balance', 'name'])
    .where('company_id', '=', companyId)
    .where('code', '=', '3900')
    .executeTakeFirst();
  if (existing) return existing as any;

  const now = new Date().toISOString();
  const accountId = crypto.randomUUID();
  await db
    .insertInto('accounts')
    .values({
      account_id: accountId,
      company_id: companyId,
      code: '3900',
      name: 'Opening Balance Equity',
      account_type: "Owner's Equity",
      normal_balance: 'CREDIT',
      description: 'System account — contra side of opening balance postings.',
      opening_balance: 0,
      is_active: 1,
      is_system: 1,
      parent_id: null,
      updated_at: now,
    })
    .execute();
  return { account_id: accountId, company_id: companyId, normal_balance: 'CREDIT', name: 'Opening Balance Equity' };
}

/** Mirrors accounts/services.py's post_opening_balance_entry exactly — idempotent
 * (keyed by reference `OB-{key}`), see PRD §4.6 and the docstring there for why
 * reference_key matters when the caller isn't the GL account itself (bank
 * accounts sharing a GL account, PRD business-logic §4.7). */
export async function postOpeningBalanceEntry(
  db: Kysely<Database>,
  account: { account_id: string; company_id: string; normal_balance: 'DEBIT' | 'CREDIT'; name: string },
  openingBalance: number,
  asOfDate: string,
  username: string,
  referenceKey?: string,
): Promise<string | null> {
  if (!openingBalance) return null;

  const companyId = account.company_id;
  const key = referenceKey ? `${referenceKey}-${account.account_id}` : account.account_id;
  const reference = `OB-${key}`;

  const existingEntry = await db
    .selectFrom('journal_entries')
    .select('entry_id')
    .where('company_id', '=', companyId)
    .where('reference', '=', reference)
    .executeTakeFirst();
  if (existingEntry) return null;

  const equityAcct = await getOrCreateOpeningBalanceEquityAccount(db, companyId);

  const entryId = crypto.randomUUID();
  const now = new Date().toISOString();
  const amount = Math.abs(openingBalance);

  await db
    .insertInto('journal_entries')
    .values({
      entry_id: entryId,
      company_id: companyId,
      reference,
      date: asOfDate,
      description: `Opening balance — ${account.name}`,
      status: 'POSTED',
      entry_type: 'MANUAL',
      total_debit: amount,
      total_credit: amount,
      period_id: null,
      created_by: username,
      approved_by: username,
      approved_at: now,
      voided_by: '',
      voided_at: null,
      updated_at: now,
    })
    .execute();

  let accountSide: 'DEBIT' | 'CREDIT' = account.normal_balance === 'DEBIT' ? 'DEBIT' : 'CREDIT';
  let equitySide: 'DEBIT' | 'CREDIT' = accountSide === 'DEBIT' ? 'CREDIT' : 'DEBIT';
  if (openingBalance < 0) {
    [accountSide, equitySide] = [equitySide, accountSide];
  }

  await db
    .insertInto('journal_lines')
    .values({
      line_id: crypto.randomUUID(),
      company_id: companyId,
      entry_id: entryId,
      account_id: account.account_id,
      side: accountSide,
      amount,
      description: 'Opening balance',
    })
    .execute();

  await db
    .insertInto('journal_lines')
    .values({
      line_id: crypto.randomUUID(),
      company_id: companyId,
      entry_id: entryId,
      account_id: equityAcct.account_id,
      side: equitySide,
      amount,
      description: `Opening balance — ${account.name}`,
    })
    .execute();

  return entryId;
}
