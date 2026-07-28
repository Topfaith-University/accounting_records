import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { hashPassword, verifyPassword } from '../lib/password';
import { CompanyClaims, signTokenPair, verifyRefreshToken } from '../lib/jwt';
import { requireAuth } from '../middleware/auth';
import { syncLegacyGroupForRole } from '../lib/rbac';

const VALID_ROLES = new Set(['Admin', 'Manager', 'Accountant', 'Staff']);

/** Mirrors config/urls.py's _single_membership_or_none: if the user belongs to
 * exactly one company, that membership is embedded directly on login so the
 * common case is transparent; 0 or >1 memberships yields a pre-company token. */
async function singleMembershipOrNone(
  db: Kysely<Database>,
  userId: number,
): Promise<CompanyClaims | null> {
  const rows = await db
    .selectFrom('memberships')
    .innerJoin('companies', 'companies.id', 'memberships.company_id')
    .select(['memberships.company_id', 'companies.name as company_name', 'memberships.role'])
    .where('memberships.user_id', '=', userId)
    .execute();
  if (rows.length !== 1) return null;
  return { company_id: rows[0].company_id, company_name: rows[0].company_name, role: rows[0].role };
}

function validatePasswordFields(body: any): string | null {
  if (!body.username?.trim()) return 'Username is required.';
  if (!body.password) return 'Password is required.';
  if (body.password !== body.confirm_password) return 'Passwords do not match.';
  if (body.password.length < 8) return 'Password must be at least 8 characters.';
  return null;
}

export function authRouter(db: Kysely<Database>): Router {
  const router = Router();

  router.post('/token/', async (req, res) => {
    const { username, password } = req.body ?? {};
    const user = await db
      .selectFrom('users')
      .selectAll()
      .where('username', '=', username ?? '')
      .executeTakeFirst();
    if (!user || !verifyPassword(password ?? '', user.password_hash)) {
      res.status(401).json({ detail: 'No active account found with the given credentials' });
      return;
    }
    const company = await singleMembershipOrNone(db, user.id);
    const tokens = signTokenPair(user.id, user.username, company);
    res.json(tokens);
  });

  router.post('/token/refresh/', async (req, res) => {
    const { refresh } = req.body ?? {};
    try {
      const decoded = verifyRefreshToken(refresh ?? '');
      const company: CompanyClaims | null = decoded.company_id
        ? {
            company_id: decoded.company_id,
            company_name: decoded.company_name!,
            role: decoded.role!,
          }
        : null;
      const tokens = signTokenPair(decoded.user_id, decoded.username, company);
      res.json(tokens);
    } catch {
      res.status(401).json({ detail: 'Token is invalid or expired' });
    }
  });

  router.get('/me/', requireAuth, async (req, res) => {
    const userId = req.auth!.user_id;
    const user = await db.selectFrom('users').selectAll().where('id', '=', userId).executeTakeFirst();
    if (!user) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const memberships = await db
      .selectFrom('memberships')
      .innerJoin('companies', 'companies.id', 'memberships.company_id')
      .select(['memberships.company_id', 'companies.name as company_name', 'memberships.role'])
      .where('memberships.user_id', '=', userId)
      .execute();
    const groupRows = await db
      .selectFrom('user_groups')
      .innerJoin('groups', 'groups.id', 'user_groups.group_id')
      .select('groups.name')
      .where('user_groups.user_id', '=', userId)
      .execute();
    res.json({
      id: user.id,
      username: user.username,
      email: user.email,
      roles: groupRows.map((g) => g.name),
      active_company_id: req.auth!.company_id ?? null,
      memberships: memberships.map((m) => ({
        company_id: m.company_id,
        company_name: m.company_name,
        role: m.role,
      })),
    });
  });

  router.post('/switch-company/', requireAuth, async (req, res) => {
    const companyId = (req.body?.company_id ?? '').trim();
    if (!companyId) {
      res.status(400).json({ detail: 'company_id is required.' });
      return;
    }
    const membership = await db
      .selectFrom('memberships')
      .innerJoin('companies', 'companies.id', 'memberships.company_id')
      .select(['memberships.company_id', 'companies.name as company_name', 'memberships.role'])
      .where('memberships.user_id', '=', req.auth!.user_id)
      .where('memberships.company_id', '=', companyId)
      .executeTakeFirst();
    if (!membership) {
      res.status(403).json({ detail: 'You are not a member of that company.' });
      return;
    }
    const tokens = signTokenPair(req.auth!.user_id, req.auth!.username, {
      company_id: membership.company_id,
      company_name: membership.company_name,
      role: membership.role,
    });
    res.json(tokens);
  });

  router.post('/register/', async (req, res) => {
    const body = req.body ?? {};
    const inviteCode = await db
      .selectFrom('invite_codes')
      .selectAll()
      .where('code', '=', (body.invite_code ?? '').trim())
      .executeTakeFirst();
    const status = inviteCodeStatus(inviteCode);
    if (!inviteCode || status !== 'active') {
      res.status(400).json({ detail: 'Invalid or expired invite code.' });
      return;
    }
    if (!inviteCode.company_id) {
      res.status(400).json({ detail: 'This invite code is not linked to a company.' });
      return;
    }
    const validationError = validatePasswordFields(body);
    if (validationError) {
      res.status(400).json({ detail: validationError });
      return;
    }
    const existing = await db
      .selectFrom('users')
      .select('id')
      .where('username', '=', body.username.trim())
      .executeTakeFirst();
    if (existing) {
      res.status(400).json({ detail: 'Username already taken.' });
      return;
    }
    if (body.email) {
      const existingEmail = await db
        .selectFrom('users')
        .select('id')
        .where('email', '=', body.email.trim())
        .executeTakeFirst();
      if (existingEmail) {
        res.status(400).json({ detail: 'Email already registered.' });
        return;
      }
    }
    const inserted = await db
      .insertInto('users')
      .values({
        username: body.username.trim(),
        email: (body.email ?? '').trim(),
        password_hash: hashPassword(body.password),
        is_superuser: 0,
      })
      .returning('id')
      .executeTakeFirstOrThrow();
    await db
      .insertInto('memberships')
      .values({ user_id: inserted.id, company_id: inviteCode.company_id, role: inviteCode.role })
      .execute();
    await syncLegacyGroupForRole(db, inserted.id, inviteCode.role);
    await db
      .updateTable('invite_codes')
      .set({ used_by: inserted.id, used_at: new Date().toISOString() })
      .where('id', '=', inviteCode.id)
      .execute();
    res.status(201).json({ detail: 'Account created. You can now sign in.' });
  });

  router.post('/register-company/', async (req, res) => {
    const body = req.body ?? {};
    const companyName = (body.company_name ?? '').trim();
    if (!companyName) {
      res.status(400).json({ detail: 'Company name is required.' });
      return;
    }
    const validationError = validatePasswordFields(body);
    if (validationError) {
      res.status(400).json({ detail: validationError });
      return;
    }
    const existing = await db
      .selectFrom('users')
      .select('id')
      .where('username', '=', body.username.trim())
      .executeTakeFirst();
    if (existing) {
      res.status(400).json({ detail: 'Username already taken.' });
      return;
    }
    const userInsert = await db
      .insertInto('users')
      .values({
        username: body.username.trim(),
        email: (body.email ?? '').trim(),
        password_hash: hashPassword(body.password),
        is_superuser: 0,
      })
      .returning('id')
      .executeTakeFirstOrThrow();
    const companyId = crypto.randomUUID();
    await db.insertInto('companies').values({ id: companyId, name: companyName }).execute();
    await db
      .insertInto('memberships')
      .values({ user_id: userInsert.id, company_id: companyId, role: 'Admin' })
      .execute();
    await syncLegacyGroupForRole(db, userInsert.id, 'Admin');
    res.status(201).json({ detail: 'Company created. You can now sign in.' });
  });

  router.post('/join-company/', requireAuth, async (req, res) => {
    const body = req.body ?? {};
    const inviteCode = await db
      .selectFrom('invite_codes')
      .selectAll()
      .where('code', '=', (body.invite_code ?? '').trim())
      .executeTakeFirst();
    const status = inviteCodeStatus(inviteCode);
    if (!inviteCode || status !== 'active') {
      res.status(400).json({ detail: 'Invalid or expired invite code.' });
      return;
    }
    if (!inviteCode.company_id) {
      res.status(400).json({ detail: 'This invite code is not linked to a company.' });
      return;
    }
    const already = await db
      .selectFrom('memberships')
      .select('id')
      .where('user_id', '=', req.auth!.user_id)
      .where('company_id', '=', inviteCode.company_id)
      .executeTakeFirst();
    if (already) {
      res.status(400).json({ detail: 'You are already a member of this company.' });
      return;
    }
    await db
      .insertInto('memberships')
      .values({ user_id: req.auth!.user_id, company_id: inviteCode.company_id, role: inviteCode.role })
      .execute();
    await syncLegacyGroupForRole(db, req.auth!.user_id, inviteCode.role);
    await db
      .updateTable('invite_codes')
      .set({ used_by: req.auth!.user_id, used_at: new Date().toISOString() })
      .where('id', '=', inviteCode.id)
      .execute();
    const company = await db
      .selectFrom('companies')
      .select('name')
      .where('id', '=', inviteCode.company_id)
      .executeTakeFirstOrThrow();
    res.status(201).json({ detail: 'Joined company.', company_id: inviteCode.company_id, company_name: company.name });
  });

  router.post('/create-company/', requireAuth, async (req, res) => {
    const companyName = (req.body?.company_name ?? '').trim();
    if (!companyName) {
      res.status(400).json({ detail: 'Company name is required.' });
      return;
    }
    const companyId = crypto.randomUUID();
    await db.insertInto('companies').values({ id: companyId, name: companyName }).execute();
    await db
      .insertInto('memberships')
      .values({ user_id: req.auth!.user_id, company_id: companyId, role: 'Admin' })
      .execute();
    await syncLegacyGroupForRole(db, req.auth!.user_id, 'Admin');
    res.status(201).json({ detail: 'Company created.', company_id: companyId, company_name: companyName });
  });

  return router;
}

function inviteCodeStatus(code: { used_by: number | null; expires_at: string } | undefined): string {
  if (!code) return 'missing';
  if (code.used_by) return 'used';
  if (new Date() >= new Date(code.expires_at)) return 'expired';
  return 'active';
}
