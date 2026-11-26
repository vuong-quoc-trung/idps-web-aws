import { useEffect, useState } from "react";
import { lookupHybrid } from "./hybridLookup";

type Api = (path: string, options?: RequestInit) => Promise<unknown>;
type Observation = {
  request_id: string;
  received_at: string | null;
  status: string;
  score: number | null;
  hybrid: string | null;
};
type Report = {
  model: string;
  schema: string;
  threshold: number;
  sampled_at?: string;
  service?: { active?: string; watchdog_age_seconds?: number | null };
  summary: {
    window_minutes: number;
    eligible: number;
    scored: number;
    anomalous: number;
    pending: number;
    abstained: number;
    conflicts: number;
    inference_errors: number;
    latest_score_at: string | null;
    recent: Observation[];
  };
};

const states: Record<string, string> = {
  SCORED: "Đã phân tích",
  PENDING: "Chưa có kết quả",
  ABSTAIN: "Không đủ dữ liệu đúng hạn",
  CONFLICT: "Bằng chứng xung đột",
  INFERENCE_ERROR: "Lỗi suy luận",
};
const time = (value?: string | null) =>
  value ? new Date(value).toLocaleString("vi-VN") : "Chưa ghi nhận";

export function Ai({
  api,
  onAlert,
}: {
  api: Api;
  onAlert: (id: number) => void;
}) {
  const [report, setReport] = useState<Report>();
  const [error, setError] = useState(false);
  const [input, setInput] = useState("");
  const [requestId, setRequestId] = useState("");
  const [result, setResult] =
    useState<Awaited<ReturnType<typeof lookupHybrid>>>();
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = (await api("/api/ai", {
          signal: controller.signal,
        })) as Report;
        if (!controller.signal.aborted) {
          setReport(next);
          setError(false);
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [api]);
  useEffect(() => {
    if (!requestId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await lookupHybrid(api, requestId, controller.signal);
        if (!controller.signal.aborted) setResult(next);
      } catch {
        if (!controller.signal.aborted)
          setResult({ message: "Không tải được quyết định Hybrid." });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(refresh, 3000);
      }
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [api, requestId]);

  function choose(id: string) {
    if (id === requestId) return;
    setResult(undefined);
    setRequestId(id);
  }
  const summary = report?.summary;
  const age = report?.service?.watchdog_age_seconds;
  const sample = report?.sampled_at ? Date.parse(report.sampled_at) : NaN;
  const fresh = Number.isFinite(sample) && Date.now() - sample < 45_000;
  return (
    <article className="panel" aria-labelledby="ai-title">
      <h2 id="ai-title">AI</h2>
      <p>
        AI đưa ra điểm bất thường để Hybrid tham khảo. Tự động chặn bằng AI đang
        tắt.
      </p>
      {error && (
        <p role="status">
          Không cập nhật được dữ liệu AI. Số liệu đang hiển thị từ lần tải gần
          nhất.
        </p>
      )}
      <dl className="detail-fields">
        <div>
          <dt>Mô hình</dt>
          <dd>{report?.model ?? "—"}</dd>
        </div>
        <div>
          <dt>Lược đồ</dt>
          <dd>{report?.schema ?? "—"}</dd>
        </div>
        <div>
          <dt>Ngưỡng bất thường</dt>
          <dd>{report?.threshold ?? "—"}</dd>
        </div>
        <div>
          <dt>Dịch vụ suy luận</dt>
          <dd>
            {fresh
              ? report?.service?.active === "active"
                ? "Đang chạy"
                : (report?.service?.active ?? "Chưa xác minh")
              : "Chưa có mẫu trạng thái mới"}
          </dd>
        </div>
        <div>
          <dt>Heartbeat systemd tại lần đo</dt>
          <dd>
            {fresh && age != null
              ? `${age.toFixed(1)} giây trước`
              : "Chưa xác minh"}
          </dd>
        </div>
        <div>
          <dt>Kiểm tra trạng thái lúc</dt>
          <dd>{time(report?.sampled_at)}</dd>
        </div>
        <div>
          <dt>Nhận điểm gần nhất trong cửa sổ</dt>
          <dd>{time(summary?.latest_score_at)}</dd>
        </div>
      </dl>
      <h3>Yêu cầu quan sát trong {summary?.window_minutes ?? 15} phút</h3>
      <dl className="detail-fields">
        {[
          ["Đủ phạm vi", summary?.eligible],
          ["Đã phân tích", summary?.scored],
          ["Điểm vượt ngưỡng", summary?.anomalous],
          ["Chưa có kết quả", summary?.pending],
          ["Không đủ dữ liệu đúng hạn", summary?.abstained],
          ["Bằng chứng xung đột", summary?.conflicts],
          ["Lỗi suy luận", summary?.inference_errors],
        ].map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value ?? "—"}</dd>
          </div>
        ))}
      </dl>
      <h3>Tra cứu quyết định Hybrid</h3>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          choose(input.trim().toLowerCase());
        }}
      >
        <label htmlFor="ai-request-id">Request ID</label>{" "}
        <input
          id="ai-request-id"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          pattern="[a-fA-F0-9]{32}"
          maxLength={32}
          required
          autoComplete="off"
        />{" "}
        <button type="submit">Tra cứu</button>
      </form>
      {requestId &&
        (result?.fields ? (
          <>
            <dl className="detail-fields">
              {result.fields.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            {result.alertIds?.map((id) => (
              <button key={id} type="button" onClick={() => onAlert(id)}>
                Cảnh báo #{id}
              </button>
            ))}
          </>
        ) : (
          <p role="status">{result?.message ?? "Đang tra cứu…"}</p>
        ))}
      <h3>Quan sát gần đây</h3>
      {summary?.recent.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Nhận lúc</th>
                <th>Trạng thái</th>
                <th>Điểm bất thường</th>
                <th>Hybrid</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent.map((row) => (
                <tr key={row.request_id}>
                  <td>
                    <button
                      type="button"
                      onClick={() => {
                        setInput(row.request_id);
                        choose(row.request_id);
                      }}
                    >
                      {row.request_id}
                    </button>
                  </td>
                  <td>{time(row.received_at)}</td>
                  <td>{states[row.status] ?? row.status}</td>
                  <td>{row.score?.toFixed(6) ?? "—"}</td>
                  <td>{row.hybrid ?? "Chưa có"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">
          {summary
            ? "Chưa ghi nhận yêu cầu trong cửa sổ này."
            : "Đang chờ dữ liệu AI."}
        </p>
      )}
    </article>
  );
}
