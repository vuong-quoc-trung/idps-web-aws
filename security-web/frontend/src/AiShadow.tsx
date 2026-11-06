import { useEffect, useState } from "react";

type Score = {
  event_id: string;
  request_id: string;
  observed_at: string;
  model_version: string;
  score: number | null;
  threshold: number;
  above_threshold: boolean | null;
  status: string;
  latency_ms: number | null;
  feature_availability: {
    headers_complete: boolean;
    body_observed: boolean;
    numeric_dropped_query_fields: number;
  } | null;
  correlated_sources: string[];
};
type Report = {
  items: Score[];
  three_source?: {items: {
    request_id: string; status: string; sources: string[];
    flow_id: string | null; tx_id: number | null; late_event: boolean;
    flow_context_alerts: number;
    glu: {model_version: string; score: number; threshold: number; latency_ms: number;
      flow_observed: boolean; context_incomplete: boolean} | null;
  }[]};
  delivery: {
    collection_enabled: boolean;
    nginx_observed_requests: number;
    scored: number;
    inference_errors: number;
    unresolved_after_grace: number;
    grace_seconds: number;
  };
  worker: {
    status: string;
    stale: boolean;
    received_at: string;
    metrics: {
      processed: number;
      rejected: number;
      queue_dropped: number;
      inference_errors: number;
      cpu_temperature_c: number | null;
    };
  } | null;
};

export function AiShadow({
  api,
}: {
  api: (path: string, options?: RequestInit) => Promise<unknown>;
}) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState("");
  const [filter, setFilter] = useState("");
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = (await api(
          `/api/ai-shadow?limit=50${filter ? `&request_id=${encodeURIComponent(filter)}` : ""}`,
        )) as Report;
        if (!disposed) {
          setReport(result);
          setError("");
        }
      } catch {
        if (!disposed)
          setError(
            "Không tải được kết quả AI. Dữ liệu đang hiển thị có thể đã cũ.",
          );
      } finally {
        if (!disposed) timer = setTimeout(() => void load(), 3000);
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [api, filter]);
  const worker = report?.worker;
  return (
    <section className="panel" aria-labelledby="ai-title">
      <div className="panel-heading">
        <h2 id="ai-title">AI shadow · Request Intelligence v2</h2>
        <span className="badge">Enforcement: DISABLED</span>
      </div>
      <p className="muted">
        Score nghiên cứu, không phải xác suất tấn công hoặc Ground Truth. Cảnh
        báo AI mang nguồn AI_SHADOW; Suricata là nguồn phát hiện riêng.
      </p>
      <p role="status">
        Worker:{" "}
        <strong>
          {!worker
            ? "Chưa nhận heartbeat"
            : worker.stale
              ? "STALE / mất heartbeat"
              : worker.status}
        </strong>
        {worker &&
          ` · Nhận lúc ${new Date(worker.received_at).toLocaleTimeString()} · CPU ${worker.metrics.cpu_temperature_c ?? "?"}°C`}
      </p>
      {worker && (
        <p className="muted">
          Phiên hiện tại: {worker.metrics.processed} đã chấm ·{" "}
          {worker.metrics.rejected} input bị từ chối ·{" "}
          {worker.metrics.queue_dropped} bỏ do hàng đợi đầy ·{" "}
          {worker.metrics.inference_errors} lỗi inference
        </p>
      )}
      <p className="muted">
        Input: URI thật và 3 header được chọn (User-Agent, Accept,
        Content-Type). Cookie/Authorization không thu thập; body chưa quan sát.
        GLU207 được kiểm điều kiện riêng trên từng request bên dưới; không ghép score.
      </p>
      {report?.delivery && (
        <p className="muted" role="status">
          Telemetry 5 phút (bỏ {report.delivery.grace_seconds}s đang xử lý):{" "}
          {report.delivery.nginx_observed_requests} request Nginx đã quan sát ·{" "}
          {report.delivery.scored} có score · {report.delivery.inference_errors}{" "}
          lỗi inference · {report.delivery.unresolved_after_grace} chưa có kết
          quả.
          {report.delivery.collection_enabled
            ? " Chưa có kết quả có thể do mất datagram, từ chối input, worker dừng hoặc chậm xử lý/ingestion; không phải tỷ lệ mất gói chính xác."
            : " Collection đang tắt; các số này không phản ánh toàn bộ traffic hiện tại."}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form
        className="filters"
        onSubmit={(event) => {
          event.preventDefault();
          setFilter(requestId.trim());
        }}
      >
        <label>
          Request ID (32 ký tự hex)
          <input
            value={requestId}
            onChange={(event) => setRequestId(event.target.value)}
            pattern="[a-f0-9]{32}"
            placeholder="X-Request-Id từ Nginx"
          />
        </label>
        <button type="submit">Tra cứu</button>
        <button
          type="button"
          onClick={() => {
            setRequestId("");
            setFilter("");
          }}
        >
          Xem mới nhất
        </button>
      </form>
      {report?.three_source && (
        <>
          <h3>Correlation ba nguồn / GLU207 shadow</h3>
          <p className="muted">Chỉ quan sát gateway IDS opt-in. Thiếu EVE không có nghĩa benign.
            Flow alert là context, không phải bằng chứng tấn công của từng request.
            GLU207 dùng ngưỡng nghiên cứu benign-only, không phải xác suất tấn công.</p>
          <div className="table-wrap"><table>
            <caption>Kết quả correlation và model riêng biệt</caption>
            <thead><tr><th>Request / nguồn</th><th>Correlation / transaction</th><th>GLU207</th></tr></thead>
            <tbody>{report.three_source.items.map(r => <tr key={r.request_id}>
              <td><code>{r.request_id}</code><div>{r.sources.join(", ")}</div></td>
              <td>{r.status}{r.late_event ? " · LATE_EVENT" : ""}<div>Flow {r.flow_id ?? "?"} / tx {r.tx_id ?? "?"}</div>
                <div>Flow context alerts: {r.flow_context_alerts}</div></td>
              <td>{r.glu ? <><strong>{r.glu.score.toFixed(6)}</strong> / {r.glu.threshold.toFixed(6)} (≥)
                <div>{r.glu.model_version} · {r.glu.latency_ms.toFixed(1)}ms</div>
                <div>Prior flow: {r.glu.flow_observed ? "observed" : "missing"} · History: {r.glu.context_incomplete ? "incomplete" : "available"}</div></> : "NOT_READY / chưa có score hợp lệ"}</td>
            </tr>)}</tbody>
          </table></div>
        </>
      )}
      <div className="table-wrap">
        <table>
          <caption className="muted">
            50 kết quả mới nhất · chỉ metadata, không lưu HTTP payload
          </caption>
          <thead>
            <tr>
              <th>Request / thời gian</th>
              <th>Model / nguồn tương quan</th>
              <th>Score / ngưỡng</th>
              <th>Trạng thái</th>
              <th>Features / độ trễ</th>
            </tr>
          </thead>
          <tbody>
            {report?.items.map((row) => (
              <tr key={row.event_id}>
                <td>
                  <code>{row.request_id}</code>
                  <br />
                  <small>{new Date(row.observed_at).toLocaleString()}</small>
                </td>
                <td>
                  {row.model_version}
                  <br />
                  <small>
                    NGINX_UNIX_SYSLOG ·{" "}
                    {row.correlated_sources.join(", ") ||
                      "Đang chờ canonical telemetry"}
                  </small>
                </td>
                <td>
                  {row.score?.toFixed(6) ?? "—"} / {row.threshold.toFixed(6)}
                  <br />
                  <small>score &gt; threshold</small>
                </td>
                <td>
                  <span className="badge">
                    {row.status !== "SCORED"
                      ? row.status
                      : row.above_threshold
                        ? "ALERT · shadow"
                        : "Dưới ngưỡng"}
                  </span>
                </td>
                <td>
                  Headers một phần · Body: thiếu
                  <br />
                  <small>
                    {row.latency_ms?.toFixed(2) ?? "—"} ms · query fields bỏ:{" "}
                    {row.feature_availability?.numeric_dropped_query_fields ??
                      "—"}
                  </small>
                </td>
              </tr>
            ))}
            {report && report.items.length === 0 && (
              <tr>
                <td colSpan={5}>
                  Chưa có kết quả cho bộ lọc này. Kiểm tra worker và nguồn
                  Nginx.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
