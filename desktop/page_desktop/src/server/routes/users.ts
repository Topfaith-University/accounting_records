import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { getActiveCompanyId, isAdmin, syncLegacyGroupForRole } from '../lib/rbac';

const VALID_ROLES = new Set(['Admin', 'Manager', 'Accountant', 'Staff']);

function serializeInviteCode(code: any, createdByUsername: string | null, usedByUsername: string | null) {
  const status = !code.used_by ? (new Date() >= new Date(code.expires_at) ? 'expired' : 'active') : 'used';
  return {
    id: code.id,
    code: code.code,
    role: code.role,
    status,
    created_by: createdByUsername,
    created_at: code.created_at,
    expires_at: code.expires_at,
    used_by: usedByUsername,
    used_at: code.used_at,
  };
}

/** /api/users/ — invite-codes and members, both Admin-only per the company-role
 * check (PRD §5.1a/§5.3), NOT the legacy Django-group check used everywhere else. */
export function usersRouter(db: Kysely<Database>): Router {
  const router = Router();
  router.use(requireAuth);

  router.get('/invite-codes/', async (req, res) => {
    if (!isAdmin(req)) {
      res.status(403).json({ detail: 'Permission denied.' });
      return;
    }
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company. Switch to a company first.' });
      return;
    }
    const codes = await db
      .selectFrom('invite_codes')
      .selectAll()
      .where('company_id', '=', companyId)
      .orderBy('created_at', 'desc')
      .execute();
    const users = await db.selectFrom('users').select(['id', 'username']).execute();
    const usernameById = new Map(users.map((u) => [u.id, u.username]));
    res.json(
      codes.map((c) =>
        serializeInviteCode(
          c,
          c.created_by ? usernameById.get(c.created_by) ?? null : null,
          c.used_by ? usernameById.get(c.used_by) ?? null : null,
        ),
      ),
    );
  });

  router.post('/invite-codes/', async (req, res) => {
    if (!isAdmin(req)) {
      res.status(403).json({ detail: 'Permission denied.' });
      return;
    }
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company. Switch to a company first.' });
      return;
    }
    const role = (req.body?.role || 'Staff').trim();
    if (!VALID_ROLES.has(role)) {
      res.status(400).json({ detail: `role must be one of ${[...VALID_ROLES].sort()}.` });
      return;
    }
    const code = generateInviteCode();
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    const inserted = await db
      .insertInto('invite_codes')
      .values({ code, company_id: companyId, role, created_by: req.auth!.user_id, expires_at: expiresAt })
      .returning('id')
      .executeTakeFirstOrThrow();
    const full = await db.selectFrom('invite_codes').selectAll().where('id', '=', inserted.id).executeTakeFirstOrThrow();
    res.status(201).json(serializeInviteCode(full, req.auth!.username, null));
  });

  router.delete('/invite-codes/:id/', async (req, res) => {
    if (!isAdmin(req)) {
      res.status(403).json({ detail: 'Permission denied.' });
      return;
    }
    const companyId = getActiveCompanyId(req);
    const code = await db
      .selectFrom('invite_codes')
      .selectAll()
      .where('id', '=', Number(req.params.id))
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!code) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (code.used_by) {
      res.status(400).json({ detail: 'Cannot revoke a used code.' });
      return;
    }
    await db.deleteFrom('invite_codes').where('id', '=', code.id).execute();
    res.status(204).send();
  });

  router.get('/members/', async (req, res) => {
    if (!isAdmin(req)) {
      res.status(403).json({ detail: 'Permission denied.' });
      return;
    }
    const companyId = getActiveCompanyId(req);
    if (!companyId) {
      res.status(400).json({ detail: 'No active company. Switch to a company first.' });
      return;
    }
    const members = await db
      .selectFrom('memberships')
      .innerJoin('users', 'users.id', 'memberships.user_id')
      .select(['memberships.id as membership_id', 'users.id as user_id', 'users.username', 'users.email', 'memberships.role', 'memberships.created_at'])
      .where('memberships.company_id', '=', companyId)
      .orderBy('users.username')
      .execute();
    res.json(members);
  });

  router.patch('/members/:id/', async (req, res) => {
    if (!isAdmin(req)) {
      res.status(403).json({ detail: 'Permission denied.' });
      return;
    }
    const companyId = getActiveCompanyId(req);
    const membership = await db
      .selectFrom('memberships')
      .selectAll()
      .where('id', '=', Number(req.params.id))
      .where('company_id', '=', companyId ?? '')
      .executeTakeFirst();
    if (!membership) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const role = (req.body?.role ?? '').trim();
    if (!VALID_ROLES.has(role)) {
      res.status(400).json({ detail: `role must be one of ${[...VALID_ROLES].sort()}.` });
      return;
    }
    if (membership.role === 'Admin' && role !== 'Admin') {
      const otherAdmins = await db
        .selectFrom('memberships')
        .select('id')
        .where('company_id', '=', companyId!)
        .where('role', '=', 'Admin')
        .where('id', '!=', membership.id)
        .execute();
      if (otherAdmins.length === 0) {
        res.status(400).json({ detail: 'Cannot change role: this is the only Admin in the company.' });
        return;
      }
    }
    await db.updateTable('memberships').set({ role }).where('id', '=', membership.id).execute();
    await syncLegacyGroupForRole(db, membership.user_id, role);
    const user = await db.selectFrom('users').select(['id', 'username', 'email']).where('id', '=', membership.user_id).executeTakeFirstOrThrow();
    res.json({
      membership_id: membership.id,
      user_id: user.id,
      username: user.username,
      email: user.email,
      role,
      created_at: membership.created_at,
    });
  });

  return router;
}

function generateInviteCode(): string {
  const raw = crypto.randomUUID().replace(/-/g, '').toUpperCase();
  return `TFU-${raw.slice(0, 4)}-${raw.slice(4, 8)}-${raw.slice(8, 12)}`;
}
