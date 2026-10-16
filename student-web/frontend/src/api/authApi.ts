/**
 * Auth API client
 * Implements the CSRF flow documented in docs/API.md:
 *  1. GET /api/auth/csrf → get token + session cookie
 *  2. POST /api/auth/login with CSRF header (form-encoded)
 *  3. GET /api/auth/csrf again to refresh token after login
 *  4. Include CSRF header on all mutating requests
 */
import type { CsrfToken, CurrentUser } from '../types/auth';
import { clearCsrfCache } from './client';

const BASE = '/api';

// ---------------------------------------------------------------------------
// Internal CSRF token cache (per page load, refreshed after login/logout)
// ---------------------------------------------------------------------------
let csrfCache: CsrfToken | null = null;

export async function fetchCsrf(): Promise<CsrfToken> {
  const res = await fetch(`${BASE}/auth/csrf`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error('Không thể lấy CSRF token');
  csrfCache = (await res.json()) as CsrfToken;
  return csrfCache;
}

async function getCsrf(): Promise<CsrfToken> {
  return csrfCache ?? fetchCsrf();
}

function csrfHeaders(csrf: CsrfToken): Record<string, string> {
  return { [csrf.headerName]: csrf.token };
}

// ---------------------------------------------------------------------------
// Auth endpoints
// ---------------------------------------------------------------------------

/** GET /api/auth/me — returns current user or null if unauthenticated */
export async function fetchMe(): Promise<CurrentUser | null> {
  try {
    const res = await fetch(`${BASE}/auth/me`, { credentials: 'same-origin' });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error('Không thể lấy thông tin người dùng');
    return (await res.json()) as CurrentUser;
  } catch {
    return null;
  }
}

/** Full login flow: get CSRF → POST login → refresh CSRF */
export async function login(username: string, password: string): Promise<void> {
  const csrf = await fetchCsrf();

  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      ...csrfHeaders(csrf),
    },
    body: new URLSearchParams({ username, password }),
  });

  if (!res.ok) {
    // 401 → wrong credentials or account not yet activated / locked
    throw new Error('Sai tên đăng nhập hoặc mật khẩu, hoặc tài khoản chưa được kích hoạt.');
  }

  // Refresh CSRF token after login (as documented)
  csrfCache = null;
  await fetchCsrf();
}

/** POST /api/auth/logout */
export async function logout(): Promise<void> {
  const csrf = await getCsrf();
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: csrfHeaders(csrf),
  });
  csrfCache = null;
  clearCsrfCache();
}

/**
 * POST /api/auth/activate
 * Activate account using one-time token (first-time setup).
 * Requires CSRF even though user is not yet logged in.
 */
export async function activateAccount(token: string, password: string): Promise<void> {
  const csrf = await fetchCsrf();

  const res = await fetch(`${BASE}/auth/activate`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(csrf),
    },
    body: JSON.stringify({ token, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { message?: string };
    throw new Error(
      body.message ??
      'Token không hợp lệ hoặc đã hết hạn (24 giờ). Yêu cầu cấp lại token từ quản trị viên.'
    );
  }
}

/** Fetch a fresh CSRF token because password changes invalidate old sessions. */
async function passwordRequest(path: string, payload: object): Promise<void> {
  const csrf = await fetchCsrf();
  const response = await fetch(`${BASE}/auth/${path}`, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrf) },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    if (response.status === 429) throw new Error('Bạn thao tác quá nhiều lần. Vui lòng chờ ít nhất 60 giây rồi thử lại.');
    if (response.status === 503) throw new Error('Chức năng gửi mã chưa sẵn sàng. Vui lòng liên hệ nhà trường hoặc thử lại sau.');
    if (response.status === 401) throw new Error('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    if (response.status === 403) throw new Error('Yêu cầu không được chấp nhận. Vui lòng tải lại trang hoặc đăng nhập lại.');
    const body = await response.json().catch(() => ({})) as { message?: string };
    throw new Error(body.message ?? 'Không thể thực hiện yêu cầu. Vui lòng thử lại.');
  }
}
export const requestPasswordReset = (studentCode: string) => passwordRequest('forgot-password', { studentCode });
export const resetPassword = (studentCode: string, code: string, newPassword: string) =>
  passwordRequest('reset-password', { studentCode, code, newPassword });
export const changePassword = (currentPassword: string, newPassword: string) =>
  passwordRequest('change-password', { currentPassword, newPassword });
export function clearAuthTokens() { csrfCache = null; clearCsrfCache(); }
