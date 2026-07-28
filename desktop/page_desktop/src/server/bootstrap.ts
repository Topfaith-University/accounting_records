import { Kysely } from 'kysely';
import { Database } from './db/types';
import { syncAllLegacyGroups } from './lib/rbac';

/** Mirrors backend/entrypoint.sh's group seeding — idempotent, safe to run on
 * every startup. Note this is the legacy Django Group system (PRD §10 quirk 12),
 * separate from company Membership.role. */
export async function seedGroups(db: Kysely<Database>): Promise<void> {
  for (const name of ['Admin', 'Manager', 'Accountant']) {
    const existing = await db.selectFrom('groups').select('id').where('name', '=', name).executeTakeFirst();
    if (!existing) {
      await db.insertInto('groups').values({ name }).execute();
    }
  }
  // Retroactive fix: keep every existing membership's legacy-group access in
  // sync on every startup, so installs created before this existed (or a role
  // change made via /members/) never get stuck locked out.
  await syncAllLegacyGroups(db);
}
