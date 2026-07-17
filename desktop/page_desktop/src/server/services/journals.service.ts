import { Kysely } from 'kysely';
import { Database } from '../db/types';

/** Mirrors JournalEntrySerializer._generate_journal_entry_reference exactly
 * (PRD §4.2): JN-YYYYMMDD-XXXX, non-atomic scan-then-increment per company. */
export async function generateJournalEntryReference(db: Kysely<Database>, companyId: string): Promise<string> {
  const now = new Date();
  const datePrefix = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const prefix = `JN-${datePrefix}-`;
  const existing = await db
    .selectFrom('journal_entries')
    .select('reference')
    .where('company_id', '=', companyId)
    .where('reference', 'like', `${prefix}%`)
    .execute();
  let maxSeq = 0;
  for (const { reference } of existing) {
    const suffix = reference.split('-').pop() ?? '';
    const seqNum = parseInt(suffix, 10);
    if (!Number.isNaN(seqNum)) maxSeq = Math.max(maxSeq, seqNum);
  }
  return `${prefix}${String(maxSeq + 1).padStart(4, '0')}`;
}

class ServiceError extends Error {}

/** Mirrors journals/services.py's post_entry exactly (PRD §4.4): DRAFT-only,
 * >=2 lines, balance check, every line's account must be active. */
export async function postJournalEntry(
  db: Kysely<Database>,
  entryId: string,
  companyId: string,
  approverUsername: string,
): Promise<void> {
  const entry = await db
    .selectFrom('journal_entries')
    .selectAll()
    .where('entry_id', '=', entryId)
    .where('company_id', '=', companyId)
    .executeTakeFirst();
  if (!entry) throw new ServiceError('Journal entry not found.');
  if (entry.status !== 'DRAFT') throw new ServiceError(`Cannot post entry with status ${entry.status}.`);

  const lines = await db.selectFrom('journal_lines').selectAll().where('entry_id', '=', entryId).execute();
  if (lines.length < 2) throw new ServiceError('Entry must have at least 2 lines.');

  const totalDebit = lines.filter((l) => l.side === 'DEBIT').reduce((s, l) => s + l.amount, 0);
  const totalCredit = lines.filter((l) => l.side === 'CREDIT').reduce((s, l) => s + l.amount, 0);
  if (Math.round(totalDebit * 100) !== Math.round(totalCredit * 100)) {
    throw new ServiceError(`Debits (${totalDebit.toFixed(2)}) ≠ Credits (${totalCredit.toFixed(2)}).`);
  }

  for (const line of lines) {
    const acct = await db.selectFrom('accounts').select(['is_active']).where('account_id', '=', line.account_id).executeTakeFirst();
    if (!acct || !acct.is_active) throw new ServiceError('Line references an inactive or missing account.');
  }

  await db
    .updateTable('journal_entries')
    .set({ status: 'POSTED', approved_by: approverUsername, approved_at: new Date().toISOString() })
    .where('entry_id', '=', entryId)
    .execute();
}

/** Mirrors journals/services.py's void_entry exactly (PRD §4.4/§10 quirk 6):
 * POSTED-only; never reverses amounts, just flips status. */
export async function voidJournalEntry(
  db: Kysely<Database>,
  entryId: string,
  companyId: string,
  voiderUsername: string,
): Promise<void> {
  const entry = await db
    .selectFrom('journal_entries')
    .selectAll()
    .where('entry_id', '=', entryId)
    .where('company_id', '=', companyId)
    .executeTakeFirst();
  if (!entry) throw new ServiceError('Journal entry not found.');
  if (entry.status !== 'POSTED') {
    throw new ServiceError(`Only POSTED entries can be voided. Current status: ${entry.status}.`);
  }
  await db
    .updateTable('journal_entries')
    .set({ status: 'VOID', voided_by: voiderUsername, voided_at: new Date().toISOString() })
    .where('entry_id', '=', entryId)
    .execute();
}

export { ServiceError };
