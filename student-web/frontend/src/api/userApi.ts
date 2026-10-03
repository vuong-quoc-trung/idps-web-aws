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
import { apiGet, apiPost, apiPatch } from './client';
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
