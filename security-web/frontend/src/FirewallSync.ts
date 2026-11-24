import { createElement as h } from "react";

export type SyncReport = {
  status: "SYNCED" | "OUT_OF_SYNC" | "UNVERIFIED";
  reason: string;
  scope: string;
  differences: string[];
};

export function FirewallSync({ report, compact = false }: { report?: SyncReport; compact?: boolean }) {
  const mismatch = report?.status === "OUT_OF_SYNC" && report.differences?.length > 0;
  const matched = report?.status === "SYNCED";
  const label = matched ? "Đồng bộ" : mismatch ? "Chưa đồng bộ" : "Chưa xác minh";
  const message = matched ? "Đã đối chiếu PostgreSQL, journal và nftables."
    : mismatch ? report.differences.join(" · ")
    : report?.reason === "JOURNAL_UNAVAILABLE" || report?.reason === "DATABASE_BINDING_UNVERIFIED"
      ? "Database và nftables đều truy cập được, nhưng chưa đủ dữ liệu đối chiếu trạng thái thực thi. Chưa phát hiện bằng chứng sai lệch."
      : "Chưa đủ dữ liệu từ các nguồn để xác minh trạng thái thực thi.";
  return compact
    ? h("span", {className: "badge "+(matched ? "good" : mismatch ? "danger" : "warn"), title: message}, label)
    : h("p", {className: mismatch ? "error" : "notice"}, "DB / Firewall: ", label, ". ", message);
}
