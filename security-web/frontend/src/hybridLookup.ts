export type AiResult = {
  request_id: string;
  status: string;
  score: number | null;
  threshold?: number | null;
  anomalous?: boolean | null;
  hybrid: string | null;
  hybrid_reason?: string[] | null;
  correlation_status?: string | null;
  sources?: string[] | null;
  late?: boolean | null;
  flow_id?: string | null;
  tx_id?: number | null;
  client_ip?: string | null;
  http_method?: string | null;
  uri_path?: string | null;
  status_code?: number | null;
  latency_ms?: number | null;
  receipt?: Record<string, unknown> | null;
  receipt_json?: string | null;
  correlation_json?: string | null;
  hybrid_json?: string | null;
};

export async function lookupHybrid(
  api: (path: string, options?: RequestInit) => Promise<unknown>,
  requestId: string,
  signal: AbortSignal,
): Promise<AiResult | null> {
  const response = (await api(
    `/api/ai?request_id=${encodeURIComponent(requestId)}`,
    { signal },
  )) as { result: AiResult | null };
  if (response.result && response.result.request_id !== requestId)
    throw new Error("Request ID không khớp.");
  return response.result;
}
