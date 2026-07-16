import { Injectable } from '@angular/core';
import axios from 'axios';
import { API_ROOT } from './api-base';

export interface Membership {
  company_id: string;
  company_name: string;
  role: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly ACCESS_KEY = 'page_access';
  private readonly REFRESH_KEY = 'page_refresh';
  private baseUrl = `${API_ROOT}auth/`;

  constructor() {
    this.setupInterceptors();
  }

  private setupInterceptors() {
    axios.interceptors.request.use((config) => {
      const token = this.getAccessToken();
      if (token) {
        config.headers['Authorization'] = `Bearer ${token}`;
      }
      return config;
    });

    axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const original = error.config;
        if (error.response?.status === 401 && !original._retry) {
          original._retry = true;
          try {
            await this.refreshToken();
            original.headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
            return axios(original);
          } catch {
            this.logout();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  async login(username: string, password: string): Promise<void> {
    const res = await axios.post(this.baseUrl + 'token/', { username, password });
    localStorage.setItem(this.ACCESS_KEY, res.data.access);
    localStorage.setItem(this.REFRESH_KEY, res.data.refresh);
  }

  /** Join an existing company via a single-use invite code. */
  async register(username: string, email: string, password: string, confirmPassword: string, inviteCode: string): Promise<void> {
    await axios.post(this.baseUrl + 'register/', {
      username,
      email,
      password,
      confirm_password: confirmPassword,
      invite_code: inviteCode,
    });
  }

  /** Create a brand-new company; the caller becomes that company's first Admin. */
  async registerCompany(companyName: string, username: string, email: string, password: string, confirmPassword: string): Promise<void> {
    await axios.post(this.baseUrl + 'register-company/', {
      company_name: companyName,
      username,
      email,
      password,
      confirm_password: confirmPassword,
    });
  }

  // Placeholder for future email-based password reset.
  // When SMTP is configured: POST /api/auth/password-reset/request/ with { email }
  // and POST /api/auth/password-reset/confirm/ with { token, new_password }.

  async refreshToken(): Promise<void> {
    const refresh = localStorage.getItem(this.REFRESH_KEY);
    if (!refresh) throw new Error('No refresh token');
    const res = await axios.post(this.baseUrl + 'token/refresh/', { refresh });
    localStorage.setItem(this.ACCESS_KEY, res.data.access);
  }

  logout(): void {
    localStorage.removeItem(this.ACCESS_KEY);
    localStorage.removeItem(this.REFRESH_KEY);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(this.ACCESS_KEY);
  }

  isLoggedIn(): boolean {
    return !!this.getAccessToken();
  }

  /** True once the current token is scoped to a specific company (the common case
   * for users with exactly one membership). False for a "pre-company" token, which
   * means the caller must fetch memberships and call switchCompany() first. */
  hasActiveCompany(): boolean {
    return !!this.getCurrentUser()?.companyId;
  }

  getCurrentUser(): { username: string; roles: string[]; companyId: string | null; companyName: string | null } | null {
    const token = this.getAccessToken();
    if (!token) return null;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return {
        username: payload.username ?? payload.user_id,
        roles: payload.role ? [payload.role] : [],
        companyId: payload.company_id ?? null,
        companyName: payload.company_name ?? null,
      };
    } catch {
      return null;
    }
  }

  /** Full list of companies this user belongs to, regardless of which one (if any)
   * the current token is scoped to. Used to decide whether a company picker is
   * needed, and to populate the "switch company" control. */
  async getMemberships(): Promise<Membership[]> {
    const res = await axios.get(this.baseUrl + 'me/');
    return res.data.memberships ?? [];
  }

  /** Mints a fresh token pair scoped to companyId (must be one of the user's
   * memberships) and stores it, replacing the current token. */
  async switchCompany(companyId: string): Promise<void> {
    const res = await axios.post(this.baseUrl + 'switch-company/', { company_id: companyId });
    localStorage.setItem(this.ACCESS_KEY, res.data.access);
    localStorage.setItem(this.REFRESH_KEY, res.data.refresh);
  }

  /** Adds a Membership to the CURRENT logged-in user via an invite code — does not
   * create a new account, unlike register(). */
  async joinCompany(inviteCode: string): Promise<void> {
    await axios.post(this.baseUrl + 'join-company/', { invite_code: inviteCode });
  }

  /** Creates a brand-new company and makes the CURRENT logged-in user its Admin —
   * does not create a new account, unlike registerCompany(). */
  async createCompanyForCurrentUser(companyName: string): Promise<void> {
    await axios.post(this.baseUrl + 'create-company/', { company_name: companyName });
  }
}
