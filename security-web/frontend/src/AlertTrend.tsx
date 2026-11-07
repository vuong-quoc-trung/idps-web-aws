import { useState } from "react";

export type TrendPoint = {
  hour: string;
  count: number;
  sources?: Record<string, number>;
};
const series = [
  ["SURICATA", "Suricata", "#8cbfff"],
  ["NGINX", "NGINX", "#ceb0ff"],
  ["STUDENT_AUDIT", "Student Audit", "#73e2c0"],
] as const;

export function AlertTrend({
  points,
  range,
}: {
  points?: TrendPoint[];
  range: string;
}) {
  const [mode, setMode] = useState<"total" | "source">("total");
  const [hidden, setHidden] = useState<string[]>([]);
  const [hover, setHover] = useState<number | null>(null);
  const hasSources =
    !!points?.length &&
    points.every(
      (p) =>
        p.sources &&
        series.every(([key]) => typeof p.sources?.[key] === "number"),
    );
  const sourceMode = mode === "source" && hasSources;
  const rows = points ?? [];
  const detailRows = rows.filter(
    (point) =>
      point.count !== 0 ||
      Object.values(point.sources ?? {}).some((count) => count !== 0),
  );
  const step = range === "1h" ? 300000 : range === "7d" ? 86400000 : 3600000;
  const segments: number[][] = [];
  rows.forEach((p, i) => {
    if (
      !i ||
      Math.abs(Date.parse(p.hour) - Date.parse(rows[i - 1].hour) - step) > 1000
    )
      segments.push([]);
    segments[segments.length - 1].push(i);
  });
  const max = Math.max(
    1,
    ...rows.map((p) =>
      sourceMode
        ? Math.max(
            ...series
              .filter(([key]) => !hidden.includes(key))
              .map(([key]) => p.sources![key]),
            0,
          )
        : p.count,
    ),
  );
  const x = (i: number) =>
    40 + (rows.length <= 1 ? 270 : (i * 540) / (rows.length - 1));
  const y = (v: number) => 180 - (v / max) * 145;
  const label = (date: string) =>
    new Date(date).toLocaleString(
      "vi-VN",
      range === "7d"
        ? { day: "2-digit", month: "2-digit" }
        : { hour: "2-digit", minute: "2-digit", hour12: false },
    );
  const fullTime = (date: string) =>
    new Date(date).toLocaleString("vi-VN", { hour12: false });
  const active = hover === null ? null : rows[hover];
  return (
    <>
      <div className="trend-controls" role="group" aria-label="Chế độ biểu đồ">
        <button
          type="button"
          aria-pressed={!sourceMode}
          onClick={() => setMode("total")}
        >
          Tổng quan — Cột
        </button>
        <button
          type="button"
          aria-pressed={sourceMode}
          disabled={!hasSources}
          onClick={() => setMode("source")}
        >
          Theo nguồn — Đường
        </button>
      </div>
      {!hasSources && (
        <p className="muted">
          API hiện chưa cung cấp số cảnh báo theo nguồn cho từng bucket.
        </p>
      )}
      {hasSources && rows.some((p) => (p.sources?.OTHER ?? 0) > 0) && (
        <p className="notice">
          Tổng có thêm nguồn khác ngoài ba nguồn hiển thị. Số lượng được giữ
          trong dữ liệu chi tiết.
        </p>
      )}
      {sourceMode && (
        <div
          className="trend-legend"
          role="group"
          aria-label="Các nguồn hiển thị"
        >
          {series.map(([key, name, color]) => (
            <button
              key={key}
              type="button"
              aria-pressed={!hidden.includes(key)}
              onClick={() =>
                setHidden((v) =>
                  v.includes(key) ? v.filter((s) => s !== key) : [...v, key],
                )
              }
            >
              <span style={{ background: color }} aria-hidden="true" />
              {name}
            </button>
          ))}
        </div>
      )}
      <div className="trend-graphic">
        <svg
          viewBox="0 0 620 220"
          aria-label={
            sourceMode
              ? "Diễn biến cảnh báo theo nguồn"
              : "Diễn biến tổng cảnh báo"
          }
        >
          {[0, max].map((v) => (
            <g key={v}>
              <line
                x1="35"
                x2="590"
                y1={y(v)}
                y2={y(v)}
                stroke="var(--border)"
              />
              <text x="30" y={y(v) + 4} textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          {sourceMode
            ? series
                .filter(([key]) => !hidden.includes(key))
                .map(([key, , color]) => (
                  <g key={key}>
                    {segments.map((indices, segment) => (
                      <polyline
                        key={segment}
                        points={indices
                          .map((i) => `${x(i)},${y(rows[i].sources![key])}`)
                          .join(" ")}
                        fill="none"
                        stroke={color}
                        strokeWidth="2"
                      />
                    ))}
                    {rows.map((p, i) => (
                      <circle
                        key={p.hour}
                        cx={x(i)}
                        cy={y(p.sources![key])}
                        r="3"
                        fill={color}
                      />
                    ))}
                  </g>
                ))
            : rows.map((p, i) => (
                <g key={p.hour}>
                  <rect
                    x={x(i) - Math.min(12, 200 / rows.length)}
                    y={y(p.count)}
                    width={Math.min(24, 400 / rows.length)}
                    height={Math.max(1, 180 - y(p.count))}
                    rx="2"
                    fill="var(--accent)"
                  />
                  {p.count > 0 && rows.length <= 12 && (
                    <text x={x(i)} y={y(p.count) - 7} textAnchor="middle">
                      {p.count}
                    </text>
                  )}
                </g>
              ))}
          {rows.map((p, i) => (
            <g key={p.hour}>
              {(i % Math.max(1, Math.ceil(rows.length / 5)) === 0 ||
                i === rows.length - 1) && (
                <text x={x(i)} y="207" textAnchor="middle">
                  {label(p.hour)}
                </text>
              )}
              <rect
                className="trend-hit"
                x={x(i) - Math.min(18, 250 / rows.length)}
                y="20"
                width={Math.min(36, 500 / rows.length)}
                height="170"
                tabIndex={0}
                role="img"
                aria-label={`${fullTime(p.hour)} · Tổng ${p.count}${hasSources ? series.map(([key, name]) => ` · ${name} ${p.sources![key]}`).join("") : ""}`}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
              >
                <title>
                  {fullTime(p.hour)} · Tổng {p.count}
                </title>
              </rect>
            </g>
          ))}
        </svg>
        <div className="trend-readout" aria-live="off">
          {active ? (
            <>
              <strong>
                {fullTime(active.hour)} · Tổng: {active.count}
              </strong>
              {hasSources && (
                <span>
                  {series
                    .map(([key, name]) => `${name}: ${active.sources![key]}`)
                    .join(" · ")}{" "}
                  · Khác: {active.sources?.OTHER ?? 0}
                </span>
              )}
            </>
          ) : (
            <span>
              {rows.length
                ? "Di chuột hoặc dùng Tab trên biểu đồ để xem số liệu."
                : "Chưa có dữ liệu biểu đồ."}
            </span>
          )}
        </div>
      </div>
      <details>
        <summary>Xem dữ liệu biểu đồ</summary>
        <p className="muted">Chỉ hiển thị các khoảng có số liệu khác 0.</p>
        {detailRows.length === 0 ? (
          <p className="muted">
            {rows.length
              ? "Không có cảnh báo trong khoảng thời gian đã chọn."
              : "Chưa có dữ liệu biểu đồ."}
          </p>
        ) : (
          <div
            className="table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Dữ liệu gốc của biểu đồ"
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">Thời gian bắt đầu bucket</th>
                  <th scope="col">Tổng</th>
                  {hasSources &&
                    series.map(([key, name]) => (
                      <th scope="col" key={key}>
                        {name}
                      </th>
                    ))}
                  {hasSources && <th scope="col">Khác</th>}
                </tr>
              </thead>
              <tbody>
                {detailRows.map((p) => (
                  <tr key={p.hour}>
                    <td>{fullTime(p.hour)}</td>
                    <td>{p.count}</td>
                    {hasSources &&
                      series.map(([key]) => (
                        <td key={key}>{p.sources![key]}</td>
                      ))}
                    {hasSources && <td>{p.sources?.OTHER ?? 0}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </>
  );
}
