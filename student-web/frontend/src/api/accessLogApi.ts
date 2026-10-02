/**
 * accessLogApi — ADMIN-only audit access log endpoints
 * Based on backend AccessLogController (/api/access-logs)
 *
 * Endpoints:
 *   GET /api/access-logs        -> paginated list of AccessLogSummary
 *   GET /api/access-logs/{id}   -> detail of single log entry
 */
import { apiGet, type Page } from './client';

export interface AccessLogSummary {
  id: number;
  userId?: number | null;
  clientIp?: string | null;
  method: string;
  path: string;
  statusCode: number;
  action?: string | null;
  requestTimeMs?: number | null;
  createdAt: string;
}

export interface AccessLogListParams {
  page?: number;
  size?: number;
}

export const accessLogApi = {
  /** GET /api/access-logs — paginated list */
  list(params?: AccessLogListParams): Promise<Page<AccessLogSummary>> {
    const p: Record<string, string | number> = {};
    if (params?.page !== undefined) p.page = params.page;
    if (params?.size !== undefined) p.size = params.size;
    return apiGet<Page<AccessLogSummary>>('/access-logs', p);
  },

  /** GET /api/access-logs/{id} — single log entry */
  get(id: number): Promise<AccessLogSummary> {
    return apiGet<AccessLogSummary>(`/access-logs/${id}`);
  },
};
