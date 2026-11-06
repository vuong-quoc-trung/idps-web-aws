export const triageLabels: Record<string, string> = {
  NEW: "Mới",
  INVESTIGATING: "Đang điều tra",
  RESOLVED: "Đã xử lý",
  FALSE_POSITIVE: "Báo động giả",
};
export function freshness(at: string | null | undefined, checkedAt?: string) {
  if (!at) return "Chưa ghi nhận dữ liệu";
  const elapsed =
    (Date.parse(checkedAt ?? new Date().toISOString()) - Date.parse(at)) / 1000;
  if (!Number.isFinite(elapsed)) return "Chưa xác định";
  if (elapsed < -5) return "Mốc thời gian phía trước — kiểm tra đồng hồ";
  if (elapsed <= 60) return "Có dữ liệu trong phút gần đây";
  return `Chưa thấy dữ liệu mới trong ${Math.floor(elapsed / 60)} phút`;
}
export type Verification = {
  deployment: string;
  deployed_file_matches_build: boolean | null;
  evidence_available: boolean;
  last_alert: {
    alert_id: number;
    occurred_at: string;
    ingested_at: string;
  } | null;
};
export function ruleDeployment(v?: Verification) {
  if (!v) return "Chưa có kết quả kiểm tra";
  if (v.deployment === "BUILT_IN") return "Logic có trong backend đang chạy";
  if (v.deployed_file_matches_build === true)
    return "File sensor khớp bản build; chưa xác minh đã nạp";
  if (v.deployed_file_matches_build === false)
    return "File sensor khác bản build; cần kiểm tra";
  return "Chưa xác minh file và rule đã nạp trên sensor";
}
