import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

/** Persists a random JWT signing secret alongside the SQLite file so tokens
 * survive app restarts but are unique per install (no shared/hardcoded key). */
export function getOrCreateJwtSecret(dataDir: string): string {
  const secretPath = path.join(dataDir, '.jwt-secret');
  if (fs.existsSync(secretPath)) {
    return fs.readFileSync(secretPath, 'utf8').trim();
  }
  const secret = crypto.randomBytes(48).toString('hex');
  fs.writeFileSync(secretPath, secret, { mode: 0o600 });
  return secret;
}
