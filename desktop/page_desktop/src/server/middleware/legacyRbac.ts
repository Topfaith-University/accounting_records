import { NextFunction, Request, Response } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { userHasAnyGroup } from '../lib/rbac';

/** Legacy, global Django-Group RBAC gate (PRD §5.3/§10 quirk 12) — used by every
 * role-gated action except invite-codes/members management, which use the
 * company-role `isAdmin` check instead. Deliberately NOT unified with it. */
export function requireLegacyGroup(db: Kysely<Database>, groupNames: string[]) {
  return async (req: Request, res: Response, next: NextFunction) => {
    const ok = await userHasAnyGroup(db, req.auth!.user_id, groupNames);
    if (!ok) {
      res.status(403).json({ detail: 'Forbidden.' });
      return;
    }
    next();
  };
}

export function requireActiveCompany(req: Request, res: Response, next: NextFunction) {
  if (!req.auth?.company_id) {
    res.status(400).json({ detail: 'No active company.' });
    return;
  }
  next();
}
