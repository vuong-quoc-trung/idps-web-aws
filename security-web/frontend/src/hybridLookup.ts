export type AiResult = {
  request_id: string;
  status: string;
  score: number | null;
  threshold?: number | null;
  anomalous?: boolean | null;
  hybrid: string | null;
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
