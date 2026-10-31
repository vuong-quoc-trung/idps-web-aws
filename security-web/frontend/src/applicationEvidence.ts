export function applicationEvidence(raw: string) {
  try {
    const v = JSON.parse(raw);
    if (!v || typeof v.rule_code !== "string" || !/^APP-100[1-5]$/.test(v.rule_code)) return null;
    return {
      code: v.rule_code as string,
      count: typeof v.event_count === "number" ? v.event_count : 0,
      endpoint: typeof v.uri_path === "string" ? v.uri_path : "—",
      reason: typeof v.reason === "string" ? v.reason : "—",
      recommendation: v.recommended_action === "BLOCK" ? "BLOCK" : "ALERT_ONLY",
      first: typeof v.first_seen === "string" ? v.first_seen : "",
      last: typeof v.last_seen === "string" ? v.last_seen : "",
    };
  } catch { return null; }
}
