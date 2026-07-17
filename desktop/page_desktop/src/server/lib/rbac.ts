import { Request } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';

/** Reads the active-company claims off the validated JWT — mirrors
 * backend/config/auth.py's get_active_company_id/get_active_role/is_admin
 * (PRD §5.1a). A pre-company token (0 or >1 memberships, not yet switched)
 * carries no company_id claim. */
export function getActiveCompanyId(req: Request): string | null {
  return req.auth?.company_id ?? null;
}

export function getActiveRole(req: Request): string | null {
  return req.auth?.role ?? null;
}

export function isAdmin(req: Request): boolean {
  return getActiveRole(req) === 'Admin';
}

/** Legacy, global Django-Group-style RBAC check (PRD §5.3/§10 quirk 12) —
 * deliberately independent of the company Membership.role above. Every
 * role gate except invite-codes/members management uses this. */
export async function userHasAnyGroup(
  db: Kysely<Database>,
  userId: number,
  groupNames: string[],
): Promise<boolean> {
  const row = await db
    .selectFrom('user_groups')
    .innerJoin('groups', 'groups.id', 'user_groups.group_id')
    .select('groups.id')
    .where('user_groups.user_id', '=', userId)
    .where('groups.name', 'in', groupNames)
    .executeTakeFirst();
  return !!row;
}

/** The live web app never gives regular users a path into the legacy Django
 * groups above — only `entrypoint.sh`'s one-time superuser bootstrap does,
 * via a step this desktop port has no equivalent of. Left as pure quirk-12
 * fidelity, that means NO desktop user could ever pass the legacy-group
 * checks gating Account/BankAccount CRUD, journal posting, reconciliation,
 * budgets, or fiscal years — a hard blocker, not a quirk worth preserving.
 * Fix: keep company Membership.role in sync with the matching legacy group
 * (Admin->Admin, Manager->Manager, Accountant->Accountant; Staff has no
 * legacy-group equivalent, matching the live app). Only ever adds — never
 * removes on downgrade, mirroring the add-only nature of the original
 * superuser bootstrap this replaces. */
const ROLE_TO_LEGACY_GROUP: Record<string, string | undefined> = {
  Admin: 'Admin',
  Manager: 'Manager',
  Accountant: 'Accountant',
  Staff: undefined,
};

export async function syncLegacyGroupForRole(db: Kysely<Database>, userId: number, role: string): Promise<void> {
  const groupName = ROLE_TO_LEGACY_GROUP[role];
  if (!groupName) return;
  const group = await db.selectFrom('groups').select('id').where('name', '=', groupName).executeTakeFirst();
  if (!group) return;
  const already = await db
    .selectFrom('user_groups')
    .select('user_id')
    .where('user_id', '=', userId)
    .where('group_id', '=', group.id)
    .executeTakeFirst();
  if (already) return;
  await db.insertInto('user_groups').values({ user_id: userId, group_id: group.id }).execute();
}

/** Retroactively applies syncLegacyGroupForRole to every existing membership —
 * run at startup so installs created before this fix (including mid-testing
 * ones) get unblocked without needing to recreate their company/account. */
export async function syncAllLegacyGroups(db: Kysely<Database>): Promise<void> {
  const memberships = await db.selectFrom('memberships').select(['user_id', 'role']).execute();
  for (const m of memberships) {
    await syncLegacyGroupForRole(db, m.user_id, m.role);
  }
}
