import { NextFunction, Request, Response } from 'express';
import { AccessTokenPayload, verifyAccessToken } from '../lib/jwt';

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      auth?: AccessTokenPayload;
    }
  }
}

/** Mirrors DRF's IsAuthenticated — every endpoint requires a valid access token
 * (CLAUDE.md: "All endpoints require IsAuthenticated"). Populates req.auth with
 * the decoded claims, read by config/auth.ts's get_active_company_id/get_active_role
 * equivalents. */
export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const header = req.headers.authorization || '';
  const [scheme, token] = header.split(' ');
  if (scheme !== 'Bearer' || !token) {
    res.status(401).json({ detail: 'Authentication credentials were not provided.' });
    return;
  }
  try {
    req.auth = verifyAccessToken(token);
    next();
  } catch {
    res.status(401).json({ detail: 'Given token not valid for any token type.' });
  }
}
