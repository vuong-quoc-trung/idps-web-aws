/**
 * Auth API client
 * Implements the CSRF flow documented in docs/API.md:
 *  1. GET /api/auth/csrf → get token + session cookie
 *  2. POST /api/auth/login with CSRF header (form-encoded)
 *  3. GET /api/auth/csrf again to refresh token after login
 *  4. Include CSRF header on all mutating requests
 */
import type { CsrfToken, CurrentUser } from '../types/auth';

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
