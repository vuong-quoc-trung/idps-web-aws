import { useEffect, useRef, useState, type FormEvent } from "react";
import { triageLabels } from "./operations";
export type TriageAlert = {
  id: number;
  triage_status: string;
  triage_version: number;
  triage_actor: string | null;
  triage_updated_at: string | null;
};
export type TriageHistory = {
  version: number;
  previous_status: string;
  status: string;
  actor: string;
  note: string;
  created_at: string;
};
export function AlertTriage({
  initial,
  history,
  admin,
  api,
  onChanged,
}: {
  initial: TriageAlert;
  history: TriageHistory[];
  admin: boolean;
  api: (path: string, options?: RequestInit) => Promise<any>;
  onChanged: () => void;
}) {
  const [record, setRecord] = useState(initial);
  const [entries, setEntries] = useState(history);
  const [status, setStatus] = useState(initial.triage_status);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function load(signal: AbortSignal) {
    const value = await api(`/api/alerts/${initial.id}`, { signal });
    if (signal.aborted) return;
    setRecord(value.alert);
    setStatus(value.alert.triage_status);
    setEntries(value.triage_history ?? []);
  }
  async function act(save: boolean, e?: FormEvent) {
    e?.preventDefault();
    if (busy) return;
    const current = new AbortController();
    controller.current = current;
    setBusy(true);
    setError("");
    setMessage("");
    let saved = false;
    try {
      if (save) {
        await api(`/api/alerts/${initial.id}/triage`, {
          method: "POST",
          signal: current.signal,
          body: JSON.stringify({
            status,
            version: record.triage_version,
            note,
          }),
        });
        saved = true;
        if (!current.signal.aborted) {
          setNote("");
          onChanged();
        }
      }
      await load(current.signal);
      if (!current.signal.aborted)
        setMessage(
          save
            ? "Đã lưu trạng thái và lịch sử xử lý."
            : "Đã tải trạng thái mới nhất; ghi chú nháp được giữ lại.",
        );
    } catch (e) {
      if (!current.signal.aborted)
        setError(
          (saved ? "Đã lưu nhưng chưa tải lại được chi tiết. " : "") +
            (e as Error).message,
        );
    } finally {
      if (!current.signal.aborted) setBusy(false);
    }
  }
  return (
    <section className="triage-panel" aria-label="Xử lý cảnh báo">
      <h3>Xử lý cảnh báo</h3>
      <p>
        <span className="badge">
          {triageLabels[record.triage_status] ?? record.triage_status}
        </span>
        {record.triage_actor && (
          <>
            {" "}
            · Cập nhật bởi {record.triage_actor} ·{" "}
            {record.triage_updated_at &&
              new Date(record.triage_updated_at).toLocaleString("vi-VN")}
          </>
        )}
      </p>
      <p className="muted">
        Trạng thái điều tra độc lập với hành động firewall. Đánh dấu đã xử lý
        không chặn hoặc bỏ chặn IP.
      </p>
      {admin ? (
        <form onSubmit={(e) => void act(true, e)}>
          <label>
            Trạng thái xử lý
            <select
              disabled={busy}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {Object.entries(triageLabels).map(([code, label]) => (
                <option value={code} key={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ghi chú xử lý (bắt buộc, tối đa 1.000 ký tự)
            <textarea
              required
              maxLength={1000}
              rows={3}
              disabled={busy}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Kết quả kiểm tra, lý do đóng hoặc mở lại; không nhập mật khẩu/token."
            />
          </label>
          <div className="triage-actions">
            <button disabled={busy || !note.trim()}>
              {busy ? "Đang xử lý…" : "Lưu xử lý"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(false)}
            >
              Tải lại trạng thái
            </button>
          </div>
        </form>
      ) : (
        <p className="muted">Tài khoản xem chỉ có quyền đọc lịch sử xử lý.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p role="status">{message}</p>
      <details>
        <summary>Lịch sử xử lý · {entries.length} bản ghi gần nhất</summary>
        {!entries.length && <p>Chưa có thao tác xử lý.</p>}
        <ol className="triage-history">
          {entries.map((h) => (
            <li key={h.version}>
              <strong>
                {triageLabels[h.previous_status]} → {triageLabels[h.status]}
              </strong>
              <small>
                {h.actor} · {new Date(h.created_at).toLocaleString("vi-VN")}
              </small>
              <p>{h.note}</p>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
