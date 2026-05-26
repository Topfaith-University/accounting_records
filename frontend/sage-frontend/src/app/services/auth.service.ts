import { Injectable } from '@angular/core';
import axios from 'axios';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly ACCESS_KEY = 'sage_access';
  private readonly REFRESH_KEY = 'sage_refresh';
  private baseUrl = 'http://localhost:8002/api/auth/';

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

  getCurrentUser(): { username: string; roles: string[] } | null {
    const token = this.getAccessToken();
    if (!token) return null;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return { username: payload.username ?? payload.user_id, roles: payload.groups ?? [] };
    } catch {
      return null;
    }
  }
}
