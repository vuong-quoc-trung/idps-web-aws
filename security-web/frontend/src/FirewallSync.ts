import { createElement as h } from "react";

export type SyncReport = {
  status: "SYNCED" | "OUT_OF_SYNC" | "UNVERIFIED";
  reason: string;
  scope: string;
  differences: string[];
};

export function FirewallSync({
  report,
  compact = false,
}: {
  report?: SyncReport;
  compact?: boolean;
}) {
  const mismatch = report?.status === "OUT_OF_SYNC";
  const matched = report?.status === "SYNCED";
  const label = matched
    ? "Đã xác minh và đồng bộ"
    : mismatch
      ? "Chưa đồng bộ"
      : "Chưa xác minh";
  const details = mismatch ? report.differences.join(" · ") : undefined;
  return compact
    ? h(
        "span",
        {
          className:
            "badge " + (matched ? "good" : mismatch ? "danger" : "warn"),
          title: details,
        },
        label,
      )
    : h(
        "p",
        { className: mismatch ? "error" : "notice" },
        "DB / Firewall — ",
        label,
        details && ` · ${details}`,
      );
}
