import jwt from 'jsonwebtoken';
import crypto from 'crypto';

const ACCESS_TTL_SECONDS = 8 * 60 * 60; // 8h, mirrors config.settings JWT lifetime
const REFRESH_TTL_SECONDS = 7 * 24 * 60 * 60; // 7d

export interface CompanyClaims {
  company_id: string;
  company_name: string;
  role: string;
}

export interface AccessTokenPayload extends Partial<CompanyClaims> {
  user_id: number;
  username: string;
  token_type: 'access';
}

export interface RefreshTokenPayload extends Partial<CompanyClaims> {
  user_id: number;
  username: string;
  token_type: 'refresh';
}

let secret = '';

export function configureJwtSecret(value: string) {
  secret = value;
}

function baseClaims(userId: number, username: string, company?: CompanyClaims | null) {
  return {
    user_id: userId,
    username,
    ...(company ?? {}),
  };
}

export function signTokenPair(userId: number, username: string, company?: CompanyClaims | null) {
  const jti = crypto.randomUUID();
  const access = jwt.sign(
    { ...baseClaims(userId, username, company), token_type: 'access', jti },
    secret,
    { expiresIn: ACCESS_TTL_SECONDS },
  );
  const refresh = jwt.sign(
    { ...baseClaims(userId, username, company), token_type: 'refresh', jti: crypto.randomUUID() },
    secret,
    { expiresIn: REFRESH_TTL_SECONDS },
  );
  return { access, refresh };
}

export function verifyAccessToken(token: string): AccessTokenPayload {
  const decoded = jwt.verify(token, secret) as AccessTokenPayload;
  if (decoded.token_type !== 'access') throw new Error('Not an access token.');
  return decoded;
}

export function verifyRefreshToken(token: string): RefreshTokenPayload {
  const decoded = jwt.verify(token, secret) as RefreshTokenPayload;
  if (decoded.token_type !== 'refresh') throw new Error('Not a refresh token.');
  return decoded;
}
