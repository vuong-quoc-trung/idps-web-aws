import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "./Icon";
import {
  auditQuery,
  auditPageSize as pageSize,
  defaultAuditFilters as defaults,
  type AuditFilters as Filters,
} from "./auditQuery";

type Api = (path: string, options?: RequestInit) => Promise<any>;
type Observation = {
  id: number;
  occurred_at: string;
  observed_at: string;
  source: string;
  client_ip: string | null;
  http_method: string | null;
  uri_path: string | null;
  status_code: number | null;
  latency_ms: number | null;
  request_id: string | null;
  event_type: string;
  outcome: string;
  role: string | null;
};
type Watcher = {
  state: string;
  last_data_at: string | null;
  error_present: boolean;
};
type Page = {
  items: Observation[];
  total: number;
  collection: {
    enabled: boolean;
    retention_days: number;
    max_events: number;
    watchers: Record<string, Watcher>;
  };
};
const sources = ["STUDENT_AUDIT", "NGINX", "SURICATA"];
const sourceName = (source: string) =>
  ({ STUDENT_AUDIT: "Student audit", NGINX: "Nginx", SURICATA: "Suricata" })[
    source
  ] ?? source;
const time = (value: string) => new Date(value).toLocaleString("vi-VN");

export function ApplicationAudit({
  api,
  refreshSignal,
}: {
  api: Api;
  refreshSignal: number;
}) {
  const [draft, setDraft] = useState<Filters>(defaults);
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Page | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [loadedAt, setLoadedAt] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const lastTrigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const params = auditQuery(filters, offset);
    setLoading(true);
    setError("");
    setData(null);
    api(`/api/application-audit?${params}`, { signal: controller.signal })
      .then((page: Page) => {
        if (!controller.signal.aborted) {
          setData(page);
          setLoadedAt(time(new Date().toISOString()));
        }
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, filters, offset, revision, refreshSignal]);
  function apply(event: FormEvent) {
    event.preventDefault();
    try {
      auditQuery(draft, 0);
    } catch (e) {
      setFilterError((e as Error).message);
      return;
    }
    setFilterError("");
    setFilters({ ...draft });
    setOffset(0);
  }
  function reset() {
    const next = defaults();
    setDraft(next);
    setFilters(next);
    setFilterError("");
    setOffset(0);
  }
  function correlate(requestId: string) {
    const next = { ...defaults(), from: "", source: "", request_id: requestId };
    setDraft(next);
    setFilters(next);
    setFilterError("");
    setOffset(0);
    setSelected(null);
  }
  function open(id: number, trigger?: HTMLButtonElement) {
    if (trigger) lastTrigger.current = trigger;
    setSelected(id);
  }
  const collection = data?.collection;
  return (
    <section className="panel application-audit" aria-labelledby="audit-title">
      <div className="application-audit-heading">
        <div>
          <h2 id="audit-title">Sự kiện ứng dụng & traffic</h2>
          <p className="muted">
            Mỗi dòng là một lần quan sát theo Schema v1. Mặc định hiển thị
            Student audit trong 24 giờ qua. Thời gian theo múi giờ trình duyệt (
            {Intl.DateTimeFormat().resolvedOptions().timeZone}). Bấm Tải lại
            audit hoặc Làm mới phía trên để cập nhật bản ghi mới.
          </p>
        </div>
        <button onClick={() => setRevision((n) => n + 1)} disabled={loading}>
          <Icon name="refresh" className={loading ? "is-spinning" : ""} />
          Tải lại audit
        </button>
      </div>
      {collection && (
        <div
          className="audit-collection"
          aria-label="Trạng thái thu thập audit"
        >
          <p>
            <span className={`badge ${collection.enabled ? "good" : "warn"}`}>
              {collection.enabled ? "Thu thập đang bật" : "Thu thập đang tắt"}
            </span>{" "}
            Lưu tối đa {collection.retention_days} ngày /{" "}
            {collection.max_events.toLocaleString("vi-VN")} sự kiện.
          </p>
          {!collection.enabled && (
            <p className="notice">
              Các bản ghi cũ vẫn xem được. Chế độ thu thập dataset đang tắt nên
              bảng này không nhận thêm quan sát mới.
            </p>
          )}
          <ul className="audit-watchers">
            {sources.map((source) => {
              const watcher = collection.watchers[source];
              return (
                <li key={source}>
                  <strong>{sourceName(source)}</strong>:{" "}
                  {watcher?.state ?? "chưa cấu hình"}
                  {watcher?.error_present && " · đang có lỗi đọc log"}
                  {watcher?.last_data_at && (
                    <span className="muted">
                      {" "}
                      · dữ liệu gần nhất {time(watcher.last_data_at)}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <form className="filters audit-filters" onSubmit={apply}>
        {(
          [
            ["from", "Từ thời điểm (bao gồm)"],
            ["to", "Đến thời điểm (không gồm)"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type="datetime-local"
              value={draft[key]}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          </label>
        ))}
        <label>
          Nguồn
          <select
            value={draft.source}
            onChange={(e) => setDraft({ ...draft, source: e.target.value })}
          >
            <option value="">Tất cả nguồn</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {sourceName(s)}
              </option>
            ))}
          </select>
        </label>
        <label>
          IP client (chính xác)
          <input
            value={draft.client_ip}
            maxLength={45}
            placeholder="192.168.10.10 hoặc IPv6"
            onChange={(e) => setDraft({ ...draft, client_ip: e.target.value })}
          />
        </label>
        <label>
          Endpoint có chứa
          <input
            value={draft.uri_path}
            maxLength={512}
            placeholder="/api/students"
            onChange={(e) => setDraft({ ...draft, uri_path: e.target.value })}
          />
        </label>
        <label>
          Mã HTTP (chính xác)
          <input
            type="number"
            min="100"
            max="599"
            step="1"
            value={draft.status_code}
            placeholder="200, 401…"
            onChange={(e) =>
              setDraft({ ...draft, status_code: e.target.value })
            }
          />
        </label>
        <label>
          Method
          <select
            value={draft.http_method}
            onChange={(e) =>
              setDraft({ ...draft, http_method: e.target.value })
            }
          >
            <option value="">Tất cả method</option>
            {[
              "GET",
              "HEAD",
              "OPTIONS",
              "POST",
              "PUT",
              "PATCH",
              "DELETE",
              "CONNECT",
              "TRACE",
              "OTHER",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Request ID (chính xác)
          <input
            value={draft.request_id}
            maxLength={128}
            placeholder="X-Request-Id"
            onChange={(e) => setDraft({ ...draft, request_id: e.target.value })}
          />
        </label>
        <div className="audit-filter-actions">
          <button type="submit">Áp dụng bộ lọc</button>
          <button type="button" onClick={reset}>
            Đặt lại
          </button>
        </div>
      </form>
      {filterError && (
        <p className="error" role="alert">
          {filterError}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          Không tải được audit: {error}. Hãy thử tải lại.
        </p>
      )}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="muted audit-result-count"
      >
        {loading
          ? "Đang tải sự kiện…"
          : data
            ? `${data.total.toLocaleString("vi-VN")} sự kiện khớp bộ lọc · tải lúc ${loadedAt}`
            : "Chưa tải được dữ liệu."}
      </div>
      {data && data.items.length === 0 && (
        <p className="notice">
          Không có sự kiện khớp bộ lọc. Hãy kiểm tra khoảng thời gian, nguồn và
          trạng thái thu thập ở trên.
        </p>
      )}
      {data && data.items.length > 0 && (
        <div
          className="table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Bảng audit, có thể cuộn ngang"
        >
          <table className="audit-events-table">
            <caption className="sr-only">
              Các quan sát ứng dụng, mới nhất trước
            </caption>
            <thead>
              <tr>
                {[
                  "Thời gian",
                  "Nguồn / Loại",
                  "IP client",
                  "Request",
                  "HTTP",
                  "Độ trễ",
                  "Request ID",
                  "Chi tiết",
                ].map((h) => (
                  <th scope="col" key={h}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <time dateTime={e.occurred_at}>{time(e.occurred_at)}</time>
                  </td>
                  <td>
                    {sourceName(e.source)}
                    <small>{e.event_type}</small>
                  </td>
                  <td className="mono">{e.client_ip ?? "—"}</td>
                  <td className="audit-endpoint">
                    <span className="chip">{e.http_method ?? "—"}</span>
                    <span className="mono">{e.uri_path ?? "—"}</span>
                  </td>
                  <td>{e.status_code ?? "—"}</td>
                  <td>
                    {e.latency_ms == null
                      ? "—"
                      : `${e.latency_ms.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} ms`}
                  </td>
                  <td className="audit-request-id mono">
                    {e.request_id ?? "—"}
                  </td>
                  <td>
                    <button
                      onClick={(event) => open(e.id, event.currentTarget)}
                      aria-label={`Xem sự kiện #${e.id}`}
                    >
                      Xem
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination" aria-label="Phân trang audit">
        <button
          disabled={loading || !data || offset === 0}
          onClick={() => setOffset((n) => Math.max(0, n - pageSize))}
        >
          Trang trước
        </button>
        <span>
          Trang {offset / pageSize + 1}
          {data ? ` / ${Math.max(1, Math.ceil(data.total / pageSize))}` : ""}
        </span>
        <button
          disabled={
            loading ||
            !data ||
            offset + pageSize >= data.total ||
            offset + pageSize > 1_000_000
          }
          onClick={() => setOffset((n) => n + pageSize)}
        >
          Trang sau
        </button>
      </div>
      <p className="muted">
        Mã HTTP và outcome mô tả kết quả request. Việc xác định tấn công xem tại
        tab Cảnh báo. Một request có thể có nhiều quan sát từ các nguồn khác
        nhau.
      </p>
      {selected !== null && (
        <AuditDetail
          id={selected}
          api={api}
          onSelect={open}
          onCorrelate={correlate}
          onClose={() => {
            setSelected(null);
            lastTrigger.current?.focus();
          }}
        />
      )}
    </section>
  );
}

type Detail = {
  id: number;
  occurred_at: string;
  observed_at: string;
  canonical: Record<string, unknown> & { request_id: string | null };
  related: Observation[];
};
function AuditDetail({
  id,
  api,
  onClose,
  onSelect,
  onCorrelate,
}: {
  id: number;
  api: Api;
  onClose: () => void;
  onSelect: (id: number) => void;
  onCorrelate: (requestId: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    api(`/api/application-audit/${id}`, { signal: controller.signal })
      .then((value: Detail) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [api, id]);
  const canonical = data?.canonical;
  return (
    <dialog
      ref={dialog}
      className="alert-drawer"
      onClose={onClose}
      aria-labelledby="audit-detail-title"
    >
      <div className="drawer-heading">
        <h2 id="audit-detail-title">Sự kiện audit #{id}</h2>
        <button autoFocus onClick={() => dialog.current?.close()}>
          Đóng
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Đang tải chi tiết…</p>}
      {data && canonical && (
        <>
          <p className="muted">
            Bản ghi Schema v1 đã che query, định danh và dữ liệu nhạy cảm.
          </p>
          <dl className="detail-fields">
            {Object.entries({
              "Thời điểm (UTC)": data.occurred_at,
              "Thu thập (UTC)": data.observed_at,
              Nguồn: canonical.source,
              Instance: canonical.source_instance,
              "Request ID": canonical.request_id,
              "IP client": canonical.client_ip,
              "User HMAC": canonical.user_id,
              "Username HMAC": canonical.username,
              Role: canonical.role,
              "User-Agent": canonical.user_agent,
              "Outcome HTTP": canonical.outcome,
            }).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value == null ? "Không có dữ liệu" : String(value)}</dd>
              </div>
            ))}
          </dl>
          <h3>Canonical JSON</h3>
          <pre tabIndex={0} aria-label="Canonical JSON đã che dữ liệu">
            {JSON.stringify(canonical, null, 2)}
          </pre>
          <h3>Quan sát cùng Request ID</h3>
          {canonical.request_id ? (
            <>
              <button onClick={() => onCorrelate(canonical.request_id!)}>
                Lọc tất cả nguồn theo Request ID này
              </button>
              <p className="muted">
                Tối đa 10 quan sát khác gần nhất có cùng Request ID; mỗi nguồn
                có thể ghi riêng một sự kiện.
              </p>
              {data.related.length === 0 && (
                <p>Chưa có quan sát khác cùng Request ID.</p>
              )}
              {data.related.map((r) => (
                <button
                  className="related-alert"
                  key={r.id}
                  onClick={() => onSelect(r.id)}
                >
                  #{r.id} · {sourceName(r.source)} ·{" "}
                  {r.http_method ?? r.event_type} {r.uri_path ?? ""}
                  <small>
                    {time(r.occurred_at)} · HTTP {r.status_code ?? "—"}
                  </small>
                </button>
              ))}
            </>
          ) : (
            <p className="muted">
              Sự kiện này không có Request ID để liên kết.
            </p>
          )}
        </>
      )}
    </dialog>
  );
}
