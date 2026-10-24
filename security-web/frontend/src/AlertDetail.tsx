import { useEffect, useRef, useState } from "react";
export type Detail = {
  alert: {
    id: number;
    occurred_at: string;
    source: string;
    severity: number;
    src_ip: string | null;
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
      pretty: JSON.stringify(parsed, null, 2),
      method: http?.http_method,
      url: http?.url,
      agent: http?.http_user_agent,
      status: http?.status,
    };
  } catch {
    const match = raw.match(
      /"(\S+)\s+(.*?)\s+HTTP\/[\d.]+"\s+(\d{3})\s+\S+\s+"(?:[^"\\]|\\.)*"\s+"((?:[^"\\]|\\.)*)"/,
    );
    return {
      pretty: raw,
      method: match?.[1],
      url: match?.[2],
      status: match?.[3],
      agent: match?.[4],
    };
  }
}
export function AlertDetail({
  id,
  api,
  onClose,
  onSelect,
}: {
  id: number;
  api: (path: string) => Promise<any>;
  onClose: () => void;
  onSelect: (id: number) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    setCopied("");
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
              "Thời gian": `${new Date(a.occurred_at).toLocaleString()} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`,
              UTC: new Date(a.occurred_at).toISOString(),
              Nguồn: a.source,
              "Mức độ": `Severity ${a.severity}`,
              "IP nguồn": a.src_ip,
              "IP đích": a.dest_ip,
              "Giao thức": a.proto,
              Rule: a.rule_name,
              Signature: a.signature,
              Category: a.category,
              "Hành động": a.action,
            }).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? "Không có dữ liệu"}</dd>
              </div>
            ))}
          </dl>
          <h3>Request HTTP</h3>
          <dl className="detail-fields">
            {Object.entries({
              Method: evidence.method,
              URL: evidence.url,
              "User-Agent": evidence.agent,
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
          <h3>Bằng chứng gốc</h3>
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(a.evidence);
                setCopied("Đã sao chép bằng chứng gốc.");
              } catch {
                setCopied(
                  "Không thể sao chép tự động. Bạn có thể chọn văn bản bên dưới để sao chép.",
                );
              }
            }}
          >
            Sao chép
          </button>
          <p role="status">{copied}</p>
          <pre>{evidence.pretty}</pre>
          <h3>Cảnh báo khác cùng IP nguồn</h3>
          <p className="muted">
            Tối đa 10 cảnh báo gần nhất, toàn bộ thời gian.
          </p>
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
                {f.actor} · {f.reason}
              </p>
              <p>
                Tạo: {new Date(f.created_at).toLocaleString()}
                <br />
                Hoàn tất:{" "}
                {f.completed_at
                  ? new Date(f.completed_at).toLocaleString()
                  : "Chưa hoàn tất"}
              </p>
              {f.details && <pre>{f.details}</pre>}
            </article>
          ))}
          {!data.firewall.length && (
            <p>
              Không có tác vụ liên kết với cảnh báo này. Điều này không xác định
              IP hiện có bị chặn hay không.
            </p>
          )}
        </>
      )}
    </dialog>
  );
}
