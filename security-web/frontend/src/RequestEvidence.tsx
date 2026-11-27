import { useEffect, useState } from "react";
import { lookupHybrid, type AiResult } from "./hybridLookup";

export function EvidenceFields({
  values,
}: {
  values: Record<string, string | number | null | undefined>;
}) {
  return (
    <dl className="detail-fields">
      {Object.entries(values).map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "Không có dữ liệu"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function JsonEvidence({
  title,
  text,
  initiallyOpen = false,
}: {
  title: string;
  text?: string | null;
  initiallyOpen?: boolean;
}) {
  const [feedback, setFeedback] = useState("");
  return (
    <details className="json-evidence" open={initiallyOpen}>
      <summary>{title}</summary>
      {text ? (
        <>
          <button
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(text);
                setFeedback("Đã sao chép bằng chứng.");
              } catch {
                setFeedback("Hãy chọn văn bản bên dưới để sao chép.");
              }
            }}
          >
            Sao chép toàn bộ JSON
          </button>
          <p role="status">{feedback}</p>
          <pre tabIndex={0} aria-label={title}>
            {text}
          </pre>
        </>
      ) : (
        <p className="muted">Không có bản ghi được lưu để hiển thị.</p>
      )}
    </details>
  );
}

export function RawEvidenceAvailability() {
  return (
    <details className="json-evidence">
      <summary>Bằng chứng gốc</summary>
      <p className="muted">
        Hệ thống không lưu bản ghi nguồn thô kèm sự kiện này.
      </p>
    </details>
  );
}

export function AnalysisEvidence({ result }: { result: AiResult }) {
  return (
    <>
      <JsonEvidence
        title="Bằng chứng tương quan đa nguồn (JSON)"
        text={result.correlation_json}
      />
      <JsonEvidence
        title="Biên nhận AI đã lưu (JSON)"
        text={result.receipt_json}
      />
      <JsonEvidence
        title="Quyết định Hybrid đã lưu (JSON)"
        text={result.hybrid_json}
      />
    </>
  );
}

export function AnalysisFields({ result }: { result: AiResult }) {
  return (
    <EvidenceFields
      values={{
        "Request ID": result.request_id,
        "Client IP từ NGINX": result.client_ip,
        "Phương thức": result.http_method,
        "Đường dẫn": result.uri_path,
        "Mã phản hồi": result.status_code,
        "Thời gian xử lý (ms)": result.latency_ms,
        "Flow ID": result.flow_id,
        "Transaction ID": result.tx_id,
        "Tương quan": result.correlation_status,
        "Nguồn liên kết": result.sources?.join(", "),
        ...(result.late != null && {
          "Thời điểm bằng chứng": result.late ? "Đến muộn" : "Đúng hạn",
        }),
        "Trạng thái AI": result.status,
        ...(result.anomalous != null && {
          "Tín hiệu AI": result.anomalous ? "Vượt ngưỡng" : "Không vượt ngưỡng",
        }),
        "Điểm AI": result.score?.toFixed(6),
        "Ngưỡng AI": result.threshold?.toFixed(6),
        "Quyết định Hybrid": result.hybrid,
        "Lý do Hybrid": result.hybrid_reason?.join(" · "),
      }}
    />
  );
}

export function RequestAnalysis({
  api,
  requestId,
}: {
  api: Parameters<typeof lookupHybrid>[0];
  requestId: string;
}) {
  const [result, setResult] = useState<AiResult | null>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    lookupHybrid(api, requestId, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setResult(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [api, requestId]);
  return (
    <>
      <h3>Phân tích request</h3>
      {result ? (
        <>
          <AnalysisFields result={result} />
          <AnalysisEvidence result={result} />
        </>
      ) : (
        <p role="status">
          {failed
            ? "Không tải được kết quả phân tích."
            : result === null
              ? "Chưa có kết quả phân tích."
              : "Đang tải kết quả phân tích…"}
        </p>
      )}
    </>
  );
}
