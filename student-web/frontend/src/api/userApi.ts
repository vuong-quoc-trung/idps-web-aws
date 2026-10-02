/**
 * userApi — ADMIN-only account management endpoints
 * Based on docs/API.md §Quản trị tài khoản
 *
 * Endpoints:
 *   GET  /users                          → paginated list
 *   GET  /users/{id}                     → single user
 *   POST /users                          → create ADMIN/STAFF, returns activationToken
 *   PATCH /users/{id}/enabled            → enable/disable
 *   POST /users/{id}/activation-token    → re-issue token (pending accounts only)
 */
import { apiGet, apiPost } from './client';
import type { Page } from './client';

export type UserRole = 'ADMIN' | 'STAFF' | 'STUDENT';

export interface UserSummary {
  id: number;
  username: string;
  role: UserRole;
  enabled: boolean;
  passwordSetupRequired: boolean;
  fullName?: string;
  studentCode?: string;
  createdAt?: string;
}

export interface UserDetail extends UserSummary {
  lastLoginAt?: string;
  activationTokenExpiry?: string;
}

export interface CreateUserPayload {
  username: string;
  role: 'ADMIN' | 'STAFF';
}

export interface CreateUserResponse {
  user: UserDetail;
  activationToken: string;
}

export interface ReissueTokenResponse {
  activationToken: string;
}

export interface UserListParams {
  page?: number;
  size?: number;
}

// ---- PATCH helper ----
async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const csrfRes = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
  const csrf = await csrfRes.json() as { headerName: string; token: string };
  const res = await fetch(`/api${path}`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const b = await res.json() as { message?: string }; if (b.message) msg = b.message; } catch { /* ignore */ }
    throw new Error(msg);
  }
  if (res.status === 204 || res.headers.get('content-length') === '0') return null as T;
  return res.json() as Promise<T>;
}

export const userApi = {
  /** GET /users — paginated list */
  list(params?: UserListParams): Promise<Page<UserSummary>> {
    const p: Record<string, string | number> = {};
    if (params?.page !== undefined) p.page = params.page;
    if (params?.size !== undefined) p.size = params.size;
    return apiGet<Page<UserSummary>>('/users', p);
  },

  /** GET /users/{id} */
  get(id: number): Promise<UserDetail> {
    return apiGet<UserDetail>(`/users/${id}`);
  },

  /** POST /users — create ADMIN or STAFF account, returns one-time activation token */
  create(payload: CreateUserPayload): Promise<CreateUserResponse> {
    return apiPost<CreateUserResponse>('/users', payload);
  },

  /** PATCH /users/{id}/enabled — enable or disable account */
  setEnabled(id: number, enabled: boolean): Promise<UserDetail> {
    return apiPatch<UserDetail>(`/users/${id}/enabled`, { enabled });
  },

  /** POST /users/{id}/activation-token — re-issue token for pending accounts */
  reissueToken(id: number): Promise<ReissueTokenResponse> {
    return apiPost<ReissueTokenResponse>(`/users/${id}/activation-token`, {});
  },
};
