import {
  AlertTriage,
  type TriageAlert,
  type TriageHistory,
} from "./AlertTriage";
import { applicationEvidence } from "./applicationEvidence";
import {
  EvidenceFields,
  RequestAnalysis,
  SavedEvidence,
} from "./RequestEvidence";
import { useEffect, useRef, useState } from "react";
export type Detail = {
  triage_history: TriageHistory[];
  rule_id?: string | null;
  link?: {
    basis: string;
    request_id: string | null;
    flow_id: string | null;
    tx_id: number | null;
  } | null;
  suricata_http?: {
    basis: "FLOW_CONTEXT" | "SENSOR_TRANSACTION";
    request_id: string;
    flow_id: string;
    tx_id: number;
    client_ip: string;
    http_method: string | null;
    uri_path: string | null;
    status_code: number | null;
    latency_ms: number | null;
    correlation_status: string;
    sources: string[];
  }[];
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
      latency: parsed?.latency_ms,
      flowId: parsed?.flow_id,
      srcPort: parsed?.src_port,
      destPort: parsed?.dest_port,
      requestId: parsed?.request_id,
      txId: parsed?.suricata_origin?.tx_id,
      interface: parsed?.suricata_origin?.interface,
      peerIp: parsed?.peer_ip,
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
  manualPeer,
  onOpenManualBlock,
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
  manualPeer?: string;
  onOpenManualBlock?: (source: string | null | undefined) => void;
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
  const suricataHttp = data?.suricata_http ?? [];
  const directHttp = suricataHttp.find(
    (http) => http.basis === "SENSOR_TRANSACTION",
  );
  const flowHttp = suricataHttp.filter((http) => http.basis === "FLOW_CONTEXT");
  const evidence = a ? evidenceInfo(a.evidence) : null;
  const app = a ? applicationEvidence(a.evidence) : null;
  const source =
    a?.source === "SURICATA"
      ? a.client_ip_verified
        ? a.client_ip
        : null
      : a?.src_ip;
  const hasHttp =
    evidence?.method != null ||
    evidence?.url != null ||
    evidence?.status != null;
  const requestId =
    directHttp?.request_id ??
    (a?.source !== "SURICATA" && data?.link?.basis === "REQUEST_ID"
      ? data.link.request_id
      : null);
  const networkOnly =
    a?.source === "SURICATA" &&
    !hasHttp &&
    data?.link?.basis === "FLOW_CONTEXT";
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
              "Client IP":
                a.source === "SURICATA"
                  ? (directHttp?.client_ip ??
                    (a.client_ip_verified ? a.client_ip : null) ??
                    (networkOnly
                      ? "Không áp dụng cho sự kiện TCP"
                      : "Chưa xác minh"))
                  : a.src_ip,
              "Bằng chứng Client IP":
                a.source === "SURICATA"
                  ? directHttp
                    ? "Khớp giao dịch với NGINX tin cậy"
                    : a.client_ip_verified
                      ? "Đã xác minh từ proxy tin cậy"
                      : networkOnly
                        ? "Không áp dụng"
                        : "Chưa xác minh"
                  : a.src_ip
                    ? `Theo bản ghi ${a.source}`
                    : "Chưa xác minh",
              ...(flowHttp.length === 1 && {
                "Client IP của HTTP cùng flow": flowHttp[0].client_ip,
              }),
              "IP nguồn mạng":
                a.network_src_ip ??
                evidence.peerIp ??
                (a.source === "NGINX" ||
                (a.source === "SURICATA" && !a.suricata_post_proxy)
                  ? a.src_ip
                  : null),
              "Cổng nguồn": evidence.srcPort,
              "IP đích quan sát": a.dest_ip,
              "Cổng đích": evidence.destPort,
              "Giao thức": a.proto,
              "Giao diện mạng": evidence.interface,
              "Luật phát hiện": a.rule_name,
              "Rule ID / SID": data.rule_id ?? app?.code,
              Nhóm: a.category,
              "Hành động": a.action,
            }).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? "Không có dữ liệu"}</dd>
              </div>
            ))}
          </dl>
          {manualPeer && onOpenManualBlock && (
            <>
              <button onClick={() => onOpenManualBlock(source)}>
                Mở form chặn thủ công
              </button>
              {!source && (
                <p className="muted">
                  Chưa xác minh IP client. Hãy nhập IP cần chặn đã được bạn xác
                  minh.
                </p>
              )}
            </>
          )}
          {manualPeer && !onOpenManualBlock && admin && (
            <p className="muted">Chặn thủ công tạm thời chưa sẵn sàng.</p>
          )}
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
          <h3>Bằng chứng của cảnh báo</h3>
          <EvidenceFields
            values={{
              "Request ID": requestId ?? evidence.requestId,
              "Flow ID": data.link?.flow_id ?? evidence.flowId,
              "Transaction ID": data.link?.tx_id ?? evidence.txId,
              ...(!networkOnly && {
                "Phương thức": directHttp?.http_method ?? evidence.method,
                "Đường dẫn": directHttp?.uri_path ?? evidence.url,
                "Mã phản hồi": directHttp?.status_code ?? evidence.status,
                "Thời gian xử lý (ms)":
                  directHttp?.latency_ms ?? evidence.latency,
              }),
            }}
          />
          {networkOnly && (
            <p className="muted">
              Phân tích HTTP không áp dụng cho cảnh báo TCP này.
            </p>
          )}
          {flowHttp.length > 0 && (
            <>
              <h3>HTTP cùng flow</h3>
              <p className="muted">
                IP bên dưới thuộc giao dịch HTTP cùng flow. Danh tính nguồn của
                cảnh báo TCP được xác minh riêng.
              </p>
              {flowHttp.map((http) => (
                <EvidenceFields
                  key={http.request_id}
                  values={{
                    "Client IP từ NGINX": http.client_ip,
                    "Phương thức": http.http_method,
                    "Đường dẫn": http.uri_path,
                    "Mã phản hồi": http.status_code,
                    "Thời gian xử lý (ms)": http.latency_ms,
                    "Request ID": http.request_id,
                    "Flow ID": http.flow_id,
                    "Transaction ID": http.tx_id,
                    "Tương quan request": http.correlation_status,
                    "Nguồn liên kết": http.sources?.join(", "),
                  }}
                />
              ))}
            </>
          )}
          {requestId && /^[a-f0-9]{32}$/.test(requestId) && (
            <RequestAnalysis key={requestId} api={api} requestId={requestId} />
          )}
          <SavedEvidence key={a.id} text={a.evidence} />
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
