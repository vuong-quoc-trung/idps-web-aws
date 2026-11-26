import { sourceIpLabel } from "./sourceIp";
import {
  AlertTriage,
  type TriageAlert,
  type TriageHistory,
} from "./AlertTriage";
import { applicationEvidence } from "./applicationEvidence";
import { useEffect, useRef, useState } from "react";
export type Detail = {
  triage_history: TriageHistory[];
  alert: TriageAlert & {
    id: number;
    occurred_at: string;
    source: string;
    severity: number;
    src_ip: string | null;
    client_ip?: string | null;
    network_src_ip?: string | null;
    client_ip_verified?: boolean | null;
    suricata_post_proxy?: boolean | null;
    dest_ip: string | null;
    proto: string | null;
    rule_name: string;
    signature: string | null;
    category: string | null;
    action: string;
    evidence: string;
  };
  related: {
    id: number;
    occurred_at: string;
    rule_name: string;
    severity: number;
    source: string;
  }[];
  firewall: {
    id: number;
    action: string;
    status: string;
    actor: string;
    source: string;
    reason: string;
    details: string | null;
    created_at: string;
    completed_at: string | null;
  }[];
};
function evidenceInfo(raw: string) {
  try {
    const parsed = JSON.parse(raw);
    const http = parsed?.http;
    return {
      method: parsed?.http_method ?? http?.http_method,
      url:
        parsed?.uri_path ??
        (typeof http?.url === "string" ? http.url.split(/[?#]/, 1)[0] : null),
      status: parsed?.status_code ?? http?.status,
    };
  } catch {
    return {};
  }
}
export function AlertDetail({
  id,
  api,
  onClose,
  onSelect,
  onAudit,
  onBlock,
  admin,
  onChanged,
}: {
  id: number;
  api: (path: string, options?: RequestInit) => Promise<any>;
  admin: boolean;
  onChanged: () => void;
  onClose: () => void;
  onSelect: (id: number) => void;
  onAudit: (id: number) => void;
  onBlock?: (alert: Detail["alert"]) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [blocking, setBlocking] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    api(`/api/alerts/${id}`)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id, api]);
  const a = data?.alert;
  const evidence = a ? evidenceInfo(a.evidence) : null;
  const app = a ? applicationEvidence(a.evidence) : null;
  return (
    <dialog
      ref={dialog}
      className="alert-drawer"
      onClose={onClose}
      aria-labelledby="alert-detail-title"
    >
      <div className="drawer-heading">
        <h2 id="alert-detail-title">Chi tiết cảnh báo #{id}</h2>
        <button autoFocus onClick={() => dialog.current?.close()}>
          Đóng
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!a && !error && <p role="status">Đang tải chi tiết…</p>}
      {a && evidence && (
        <>
          <dl className="detail-fields">
            {Object.entries({
              "Thời gian": new Date(a.occurred_at).toLocaleString("vi-VN"),
              Nguồn: a.source,
              "Mức độ": `S${a.severity}`,
              "IP nguồn": sourceIpLabel(a),
              "Xác minh Client IP":
                a.source === "SURICATA"
                  ? a.client_ip_verified
                    ? "Đã xác minh từ proxy tin cậy"
                    : "Chưa xác minh"
                  : "Theo nguồn ứng dụng",
              "IP đích": a.dest_ip,
              "Giao thức": a.proto,
              "Luật phát hiện": a.rule_name,
              Nhóm: a.category,
              "Hành động": a.action,
            }).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? "Không có dữ liệu"}</dd>
              </div>
            ))}
          </dl>
          <AlertTriage
            key={a.id}
            initial={a}
            history={data.triage_history ?? []}
            admin={admin}
            api={api}
            onChanged={onChanged}
          />
          {app && (
            <section aria-label="Phát hiện hành vi ứng dụng">
              <h3>{app.code} · Tổng hợp hành vi</h3>
              <p>{app.reason}</p>
              <p>
                {app.count} sự kiện (đỉnh cửa sổ) · {app.endpoint}
              </p>
              <p>
                Lần đầu: {new Date(app.first).toLocaleString()} · Gần nhất:{" "}
                {new Date(app.last).toLocaleString()}
              </p>
              <p>{app.recommendation}</p>
            </section>
          )}
          {onBlock && a.src_ip && (
            <button
              disabled={blocking}
              onClick={async () => {
                setBlocking(true);
                try {
                  await onBlock(a);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBlocking(false);
                }
              }}
            >
              Yêu cầu chặn thủ công từ cảnh báo
            </button>
          )}
          <h3>Request HTTP</h3>
          <dl className="detail-fields">
            {Object.entries({
              "Phương thức": evidence.method,
              "Đường dẫn": evidence.url,
              "Mã phản hồi": evidence.status,
            }).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {value == null ? "Không có trong bằng chứng" : String(value)}
                </dd>
              </div>
            ))}
          </dl>
          <h3>Cảnh báo khác cùng IP nguồn</h3>
          {data.related.map((r) => (
            <button
              className="related-alert"
              key={r.id}
              onClick={() => onSelect(r.id)}
            >
              #{r.id} · {r.rule_name}
              <small>
                {new Date(r.occurred_at).toLocaleString()} · {r.source} ·
                Severity {r.severity}
              </small>
            </button>
          ))}
          {!data.related.length && (
            <p>
              {a.src_ip
                ? "Không có cảnh báo khác cùng IP."
                : "Không có IP nguồn để đối chiếu."}
            </p>
          )}
          <h3>Tác vụ firewall liên kết trực tiếp</h3>
          <button onClick={() => onAudit(id)}>
            Xem audit của cảnh báo #{id}
          </button>
          {data.firewall.map((f) => (
            <article className="panel" key={f.id}>
              <strong>
                #{f.id} · {f.action} ·{" "}
                {(
                  {
                    PENDING: "Đang chờ",
                    SUCCESS: "Thành công",
                    ERROR: "Thất bại",
                  } as Record<string, string>
                )[f.status] ?? f.status}
              </strong>
              <p>
                {f.actor} ·{" "}
                {f.source === "AUTO"
                  ? "Tự động"
                  : f.source === "RESTORE"
                    ? "Hệ thống khôi phục"
                    : f.source === "UI" || f.source === "API"
                      ? "Quản trị viên"
                      : f.source}{" "}
                · {f.reason}
              </p>
              <p>
                Tạo: {new Date(f.created_at).toLocaleString()}
                <br />
                Hoàn tất:{" "}
                {f.completed_at
                  ? new Date(f.completed_at).toLocaleString()
                  : "Chưa hoàn tất"}
              </p>
              {f.details && f.status === "ERROR" && <p>{f.details}</p>}
            </article>
          ))}
          {!data.firewall.length && <p>Chưa có tác vụ liên kết.</p>}
        </>
      )}
    </dialog>
  );
}
