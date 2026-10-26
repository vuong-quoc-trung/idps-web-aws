export type AuditFilters = {
  from: string;
  to: string;
  source: string;
  client_ip: string;
  uri_path: string;
  status_code: string;
  request_id: string;
  http_method: string;
};
export const auditPageSize = 25;

export function defaultAuditFilters(now = Date.now()): AuditFilters {
  const date = new Date(now - 24 * 60 * 60 * 1000);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return {
    from: local.toISOString().slice(0, 16),
    to: "",
    source: "STUDENT_AUDIT",
    client_ip: "",
    uri_path: "",
    status_code: "",
    request_id: "",
    http_method: "",
  };
}

/** datetime-local uses the browser timezone; only UTC instants go over the API. */
export function auditQuery(filters: AuditFilters, offset: number): string {
  const params = new URLSearchParams({
    limit: String(auditPageSize),
    offset: String(offset),
  });
  const instants: Record<string, Date> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (!value.trim()) continue;
    if (key === "from" || key === "to") {
      const date = new Date(value);
      if (!Number.isFinite(date.getTime()))
        throw new Error("Thời gian lọc không hợp lệ.");
      instants[key] = date;
      params.set(key, date.toISOString());
    } else {
      params.set(key, value.trim());
    }
  }
  if (instants.from && instants.to && instants.from >= instants.to)
    throw new Error("Thời gian bắt đầu phải trước thời gian kết thúc.");
  return params.toString();
}
