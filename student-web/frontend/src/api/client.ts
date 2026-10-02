/**
 * Shared API client with CSRF support.
 * Keeps its own CSRF cache independent from authApi so it can be used
 * in any module without circular imports.
 */

const BASE = '/api';

interface CsrfToken { headerName: string; token: string; }
interface ApiErrorBody { status?: number; message?: string; }

let csrfCache: CsrfToken | null = null;

async function ensureCsrf(): Promise<CsrfToken> {
  if (csrfCache) return csrfCache;
  const res = await fetch(`${BASE}/auth/csrf`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error('Không thể lấy CSRF token');
  csrfCache = (await res.json()) as CsrfToken;
  return csrfCache;
}

/** Call this after logout to force CSRF refresh */
export function clearCsrfCache(): void { csrfCache = null; }

// ---- Custom error type ----
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function toError(res: Response): Promise<ApiError> {
  let message = `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as ApiErrorBody;
    if (body.message) message = body.message;
  } catch { /* ignore */ }
  return new ApiError(res.status, message);
}

// ---- HTTP helpers ----
export async function apiGet<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), { credentials: 'same-origin' });
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrf();
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204 || res.headers.get('content-length') === '0') return null as T;
  return res.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrf();
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  return res.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const csrf = await ensureCsrf();
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { [csrf.headerName]: csrf.token },
  });
  if (!res.ok) throw await toError(res);
}

// ---- Pagination wrapper ----
export interface Page<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}
