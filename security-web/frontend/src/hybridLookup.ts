type Research = {
  request_id: string;
  model_id: string | null;
  status: string;
  score: number | null;
  threshold: number | null;
};

type Incident = {
  request_id: string;
  https_research?: Research | null;
  policy_action: string;
  automatic_block: boolean;
  final_risk?: number;
  rule_sources?: string[];
  correlation_confidence?: string;
  evidence_ids?: string[];
};

export async function lookupHybrid(
  api: (path: string, options?: RequestInit) => Promise<unknown>,
  requestId: string,
  signal: AbortSignal,
) {
  const response = (await api(
    `/api/hybrid-incidents?request_id=${encodeURIComponent(requestId)}`,
    { signal },
  )) as { incidents: Incident[] };
  const incident = response.incidents.find(
    (row) => row.request_id === requestId,
  );
  if (!incident)
    return { message: "Chưa có quyết định Hybrid cho Request ID này." };
  const research = incident.https_research;
  if (research && research.request_id !== requestId)
    return { message: "Request ID của bằng chứng HTTPS không khớp." };
  return {
    fields: [
      ["Request ID", incident.request_id],
      ["Model", research?.model_id ?? "—"],
      ["Trạng thái", research?.status ?? "Chưa có bằng chứng HTTPS scorer"],
      [
        "AI Score",
        research?.status === "SCORED"
          ? (research.score?.toFixed(6) ?? "—")
          : "—",
      ],
      ["Threshold", research?.threshold?.toString() ?? "—"],
      ["Hybrid Policy", incident.policy_action],
      ["Điểm rủi ro", incident.final_risk?.toString() ?? "—"],
      ["Nguồn cảnh báo", incident.rule_sources?.join(", ") || "Chưa có"],
      ["Tương quan", incident.correlation_confidence ?? "—"],
      ["automatic_block", String(incident.automatic_block)],
    ],
    alertIds: [...new Set(incident.evidence_ids ?? [])]
      .filter((id) => /^alert:[1-9]\d*$/.test(id))
      .map((id) => Number(id.slice("alert:".length)))
      .filter(Number.isSafeInteger),
  };
}
