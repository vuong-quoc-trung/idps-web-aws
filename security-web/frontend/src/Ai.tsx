import { useCallback, useEffect, useState } from "react";
import { lookupHybrid, type AiResult } from "./hybridLookup";

type Api = (path: string, options?: RequestInit) => Promise<unknown>;
type Report = {
  sampled_at?: string;
  service?: { active?: string; watchdog_age_seconds?: number | null };
  summary: {
    window_minutes: number;
    scored: number;
    anomalous: number;
    recent: (AiResult & { received_at: string | null })[];
  };
};

const states: Record<string, string> = {
  SCORED: "Đã phân tích",
  ABSTAIN: "Không đủ dữ liệu",
  CONFLICT: "Bằng chứng xung đột",
  INFERENCE_ERROR: "Lỗi suy luận",
};

function useReport<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: string,
  delay: number,
) {
  const [sample, setSample] = useState<{
    key: string;
    value?: T;
    failed: boolean;
  }>();
  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await load(controller.signal);
        if (!controller.signal.aborted)
          setSample({ key, value, failed: false });
      } catch {
        if (!controller.signal.aborted)
          setSample((prev) => ({
            key,
            value: prev?.key === key ? prev.value : undefined,
            failed: true,
          }));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, delay);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, key, delay]);
  return sample?.key === key ? sample : undefined;
}

export function Ai({ api }: { api: Api }) {
  const [input, setInput] = useState("");
  const [requestId, setRequestId] = useState("");
  const loadReport = useCallback(
    (signal: AbortSignal) => api("/api/ai", { signal }) as Promise<Report>,
    [api],
  );
  const loadMatch = useCallback(
    (signal: AbortSignal) => lookupHybrid(api, requestId, signal),
    [api, requestId],
  );
  const report = useReport(loadReport, "summary", 5000);
  const match = useReport(loadMatch, requestId, 3000);
  const sample = report?.value;
  const summary = sample?.summary;
  const age = sample?.service?.watchdog_age_seconds;
  const fresh =
    sample?.sampled_at && Date.now() - Date.parse(sample.sampled_at) < 45_000;
  const ready =
    fresh && sample.service?.active === "active" && age != null && age <= 3;
  const rows = summary?.recent.filter((row) => row.received_at !== null) ?? [];
  const abnormal = summary?.anomalous ?? 0;
  const scored = summary?.scored ?? 0;

  return (
    <section className="panel ai-panel" aria-label="Kết quả AI">
      <div className="application-audit-heading">
        <h2>AI</h2>
        <span className={`badge ${ready ? "good" : "warn"}`}>
          {ready
            ? "Đang hoạt động"
            : fresh && sample.service?.active === "failed"
              ? "Dịch vụ gặp lỗi"
              : "Chưa xác minh hoạt động"}
        </span>
      </div>
      {report?.failed && <p role="status">Không cập nhật được kết quả AI.</p>}
      <div className="ai-analysis">
        <div className="ai-counts">
          <div>
            <span>Yêu cầu đã phân tích</span>
            <strong>{summary ? scored.toLocaleString("vi-VN") : "—"}</strong>
          </div>
          <div>
            <span>Yêu cầu bất thường</span>
            <strong>{summary ? abnormal.toLocaleString("vi-VN") : "—"}</strong>
          </div>
        </div>
        {summary && (
          <figure className="ai-figure">
            <figcaption>Kết quả trong {summary.window_minutes} phút</figcaption>
            <meter
              min={0}
              max={Math.max(1, scored)}
              value={abnormal}
              aria-label="Số yêu cầu bất thường trên tổng số đã phân tích"
            />
            <div className="ai-legend">
              <span>Bất thường · {abnormal}</span>
              <span>Dưới ngưỡng · {scored - abnormal}</span>
            </div>
          </figure>
        )}
      </div>
      <h3>Tra cứu Request ID</h3>
      <form
        className="filters ai-search"
        onSubmit={(event) => {
          event.preventDefault();
          setRequestId(input.trim().toLowerCase());
        }}
      >
        <label>
          Request ID
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            pattern="[a-fA-F0-9]{32}"
            maxLength={32}
            required
            autoComplete="off"
          />
        </label>
        <button type="submit">Tra cứu</button>
      </form>
      {requestId &&
        (match?.failed ? (
          <p role="status">Không tra cứu được kết quả.</p>
        ) : match?.value ? (
          <dl className="detail-fields">
            <div>
              <dt>Request ID</dt>
              <dd>{match.value.request_id}</dd>
            </div>
            <div>
              <dt>Trạng thái</dt>
              <dd>{states[match.value.status] ?? "Chưa có kết quả"}</dd>
            </div>
            <div>
              <dt>Điểm bất thường</dt>
              <dd>{match.value.score?.toFixed(6) ?? "—"}</dd>
            </div>
            <div>
              <dt>Hybrid</dt>
              <dd>{match.value.hybrid ?? "Chưa có quyết định"}</dd>
            </div>
          </dl>
        ) : (
          <p role="status">
            {match?.value === null
              ? "Chưa có kết quả cho Request ID này."
              : "Đang tra cứu…"}
          </p>
        ))}
      <h3>Kết quả gần đây</h3>
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Thời điểm</th>
                <th>Trạng thái</th>
                <th>Điểm bất thường</th>
                <th>Hybrid</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.request_id}>
                  <td>
                    <button
                      type="button"
                      onClick={() => {
                        setInput(row.request_id);
                        setRequestId(row.request_id);
                      }}
                    >
                      {row.request_id}
                    </button>
                  </td>
                  <td>{new Date(row.received_at!).toLocaleString("vi-VN")}</td>
                  <td>{states[row.status] ?? "Chưa có kết quả"}</td>
                  <td>{row.score?.toFixed(6) ?? "—"}</td>
                  <td>{row.hybrid ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">
          {summary ? "Chưa có kết quả gần đây." : "Đang chờ kết quả AI."}
        </p>
      )}
    </section>
  );
}
