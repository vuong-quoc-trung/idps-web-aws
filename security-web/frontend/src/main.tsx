import {
  Component,
  StrictMode,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type User = { username: string; role: "admin" | "viewer" };
type Alert = {
  id: number;
  occurred_at: string;
  source: string;
  src_ip: string | null;
  dest_ip: string | null;
  rule_name: string;
  severity: number;
  action: string;
  evidence: string;
};
type Stats = {
  total_alerts: number;
  critical_alerts: number;
  blocked_attacks: number;
  trend: { hour: string; count: number }[];
  types: { name: string; count: number }[];
  system: {
    load_average_1m: number | null;
    memory_percent: number | null;
    interface_rx_bytes: number | null;
    established_tcp_connections: number | null;
  };
};
type Blocked = {
  database: { ip: string; reason: string; blocked_at: string }[];
  kernel: string[] | null;
  in_sync: boolean;
  error: string | null;
};
type Audit = {
  id: number;
  ip: string;
  action: string;
  actor: string;
  reason: string;
  status: string;
  details: string | null;
  created_at: string;
};
type Rule = {
  sid: number;
  name: string;
  severity: number;
  auto_block_eligible: boolean;
};
type Health = {
  healthy: boolean;
  database: boolean;
  firewall: boolean;
  firewall_in_sync: boolean;
  watchers: Record<string, string>;
  ingestion_errors: number | null;
};
class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main>
        <h1>Không thể hiển thị dashboard</h1>
        <button onClick={() => location.reload()}>Tải lại trang</button>
      </main>
    ) : (
      this.props.children
    );
  }
}
function App() {
  // Session token is memory-only: never localStorage or an automatically sent cookie.
  const [session, setSession] = useState<{ token: string; user: User } | null>(
    null,
  );
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [tab, setTab] = useState("overview");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(0);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [blocked, setBlocked] = useState<Blocked | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [ip, setIp] = useState("");
  const [reason, setReason] = useState("");
  const refreshing = useRef(false);
  const requestKey = `${session?.token ?? ""}:${page}:${filter}:${severity}`;
  const latestKey = useRef(requestKey);
  latestKey.current = requestKey;
  const api = useCallback(
    async (path: string, options: RequestInit = {}) => {
      const response = await fetch(path, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.token ?? ""}`,
          ...options.headers,
        },
      });
      if (response.status === 401) {
        setSession(null);
        throw new Error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      }
      if (
        !response.ok &&
        !(path === "/api/status" && response.status === 503)
      ) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.message ?? `Yêu cầu thất bại (${response.status})`,
        );
      }
      return response.status === 204 ? null : response.json();
    },
    [session],
  );
  const refresh = useCallback(async () => {
    if (!session || refreshing.current) return;
    refreshing.current = true;
    setLoading(true);
    try {
      const results = await Promise.all([
        api(
          `/api/alerts?limit=25&offset=${page * 25}&search=${encodeURIComponent(filter)}${severity ? `&severity=${severity}` : ""}`,
        ),
        api("/api/stats"),
        api("/api/blocked-ips"),
        api("/api/audit"),
        api("/api/rules"),
        api("/api/status"),
      ]);
      if (latestKey.current !== requestKey) return;
      setAlerts(results[0]);
      setStats(results[1]);
      setBlocked(results[2]);
      setAudit(results[3]);
      setRules(results[4]);
      setHealth(results[5]);
      setUpdated(new Date().toLocaleTimeString());
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      refreshing.current = false;
      setLoading(false);
    }
  }, [session, page, filter, severity, api, requestKey]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  async function login(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoginBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      if (!res.ok)
        throw new Error(
          res.status === 429
            ? "Đăng nhập quá nhiều lần. Thử lại sau một phút."
            : "Tên đăng nhập hoặc mật khẩu không đúng.",
        );
      const responseData = await res.json();
      setSession(responseData);
      setPage(0);
      setNotice("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoginBusy(false);
    }
  }
  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (e) {
      setError(
        `Đã xóa phiên trên trình duyệt, nhưng chưa xác nhận thu hồi trên server: ${(e as Error).message}`,
      );
    } finally {
      setSession(null);
      setAlerts([]);
      setStats(null);
      setBlocked(null);
      setAudit([]);
      setHealth(null);
      setUpdated(null);
    }
  }
  async function action(address: string, unblock = false) {
    if (unblock && !window.confirm(`Bỏ chặn ${address}?`)) return;
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await api(
        unblock
          ? `/api/blocked-ips/${encodeURIComponent(address)}`
          : "/api/blocked-ips",
        {
          method: unblock ? "DELETE" : "POST",
          ...(!unblock
            ? { body: JSON.stringify({ ip: address, reason }) }
            : {}),
        },
      );
      setNotice(
        `Yêu cầu #${result.id} đã được tiếp nhận. Xem kết quả trong Nhật ký thao tác.`,
      );
      if (!unblock) {
        setIp("");
        setReason("");
      }
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function exportPage() {
    const cell = (value: unknown) =>
      `"${String(value ?? "")
        .replace(/^[=+@\-\t\r]/, "'$&")
        .replaceAll('"', '""')}"`;
    const csv = [
      ["ID", "Thời gian", "Nguồn", "IP", "Rule", "Severity", "Hành động"],
      ...alerts.map((a) => [
        a.id,
        a.occurred_at,
        a.source,
        a.src_ip,
        a.rule_name,
        a.severity,
        a.action,
      ]),
    ]
      .map((row) => row.map(cell).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "security-alerts-page.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  if (!session)
    return (
      <main className="login">
        <form onSubmit={login}>
          <p className="eyebrow">PBL4 / SECURITY PLATFORM</p>
          <h1>Đăng nhập giám sát</h1>
          <p className="muted">Theo dõi cảnh báo và quản lý bảo vệ website.</p>
          <label>
            Tên đăng nhập
            <input
              name="username"
              autoComplete="username"
              required
              autoFocus
              maxLength={128}
            />
          </label>
          <label>
            Mật khẩu
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="primary" disabled={loginBusy}>
            {loginBusy ? "Đang xác thực…" : "Đăng nhập"}
          </button>
        </form>
      </main>
    );
  const admin = session.user.role === "admin";
  const tabs = [
    ["overview", "Tổng quan"],
    ["alerts", "Cảnh báo"],
    ["blocked", "IP bị chặn"],
    ["audit", "Nhật ký thao tác"],
    ["rules", "Luật phát hiện"],
    ["status", "Trạng thái hệ thống"],
  ];
  const fmt = (v: number | null | undefined, suffix = "") =>
    v == null ? "Chưa có dữ liệu" : `${v.toLocaleString()}${suffix}`;
  return (
    <div className="shell">
      <aside>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("overview");
          }}
        >
          PBL4 <span>SECURITY</span>
        </a>
        <p className="eyebrow">ĐIỀU HÀNH BẢO MẬT</p>
        <nav aria-label="Điều hướng">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="account">
          <strong>{session.user.username}</strong>
          <p>{admin ? "Quản trị viên" : "Chỉ xem"}</p>
          <button onClick={() => void logout()}>Đăng xuất</button>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="eyebrow">SECURITY OPERATIONS</p>
            <h1>{tabs.find(([id]) => id === tab)?.[1]}</h1>
          </div>
          <div>
            <span
              className={`badge ${!error && health?.healthy ? "good" : "warn"}`}
            >
              {error
                ? "Mất kết nối / dữ liệu có thể cũ"
                : health?.healthy
                  ? "Hệ thống sẵn sàng"
                  : "Cần kiểm tra hệ thống"}
            </span>
            <p className="muted">
              {updated ? `Cập nhật ${updated}` : "Đang tải dữ liệu"}
            </p>
            <button onClick={() => void refresh()} disabled={loading}>
              {loading ? "Đang tải…" : "Làm mới"}
            </button>
          </div>
        </header>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {tab === "overview" && (
          <>
            <section className="cards" aria-label="Thống kê">
              {[
                ["Tổng cảnh báo", stats?.total_alerts],
                ["Mức nghiêm trọng 1", stats?.critical_alerts],
                ["Sự kiện auto-block thành công", stats?.blocked_attacks],
                ["IP hiện có trong firewall", blocked?.kernel?.length],
              ].map(([label, value]) => (
                <article key={String(label)}>
                  <p>{label}</p>
                  <strong>{fmt(value as number | undefined)}</strong>
                </article>
              ))}
            </section>
            <section className="panel">
              <h2>Cảnh báo theo giờ</h2>
              <p className="muted">
                24 giờ gần nhất · số sự kiện đã lưu trong database
              </p>
              <div
                className="chart"
                role="img"
                aria-label="Số cảnh báo theo từng giờ"
              >
                {stats?.trend.map((point) => (
                  <div
                    className="bar-column"
                    key={point.hour}
                    title={`${new Date(point.hour).toLocaleString()}: ${point.count} cảnh báo`}
                  >
                    <span>{point.count}</span>
                    <div
                      className="bar"
                      style={{
                        height: `${(point.count / Math.max(1, ...stats.trend.map((p) => p.count))) * 130}px`,
                      }}
                    />
                    <small>{new Date(point.hour).getHours()}h</small>
                  </div>
                ))}
              </div>
              <details>
                <summary>Xem dữ liệu biểu đồ</summary>
                <ul>
                  {stats?.trend.map((p) => (
                    <li key={p.hour}>
                      {new Date(p.hour).toLocaleString()}: {p.count}
                    </li>
                  ))}
                </ul>
              </details>
            </section>
            <section className="panel">
              <h2>Nhóm cảnh báo phổ biến</h2>
              {!stats?.types.length ? (
                <p>Chưa có cảnh báo.</p>
              ) : (
                stats.types.map((t) => (
                  <div className="type-row" key={t.name}>
                    <span>{t.name}</span>
                    <strong>{t.count}</strong>
                  </div>
                ))
              )}
            </section>
          </>
        )}
        {tab === "alerts" && (
          <section className="panel">
            <form
              className="filters"
              onSubmit={(e) => {
                e.preventDefault();
                setFilter(search);
                setPage(0);
              }}
            >
              <label>
                Tìm rule hoặc IP
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <label>
                Mức độ
                <select
                  value={severity}
                  onChange={(e) => {
                    setSeverity(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="">Tất cả</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <button>Tìm kiếm</button>
              <button
                type="button"
                onClick={exportPage}
                disabled={!alerts.length}
              >
                Xuất CSV trang này
              </button>
            </form>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Thời gian</th>
                    <th>Nguồn / Rule</th>
                    <th>IP nguồn → đích</th>
                    <th>Mức độ</th>
                    <th>Hành động</th>
                    <th>Bằng chứng</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((a) => (
                    <tr key={a.id}>
                      <td>{new Date(a.occurred_at).toLocaleString()}</td>
                      <td>
                        {a.rule_name}
                        <small>{a.source}</small>
                      </td>
                      <td>
                        {a.src_ip ?? "—"} → {a.dest_ip ?? "—"}
                      </td>
                      <td>
                        <span
                          className={
                            a.severity === 1 ? "badge danger" : "badge"
                          }
                        >
                          Severity {a.severity}
                        </span>
                      </td>
                      <td>{a.action}</td>
                      <td>
                        <details>
                          <summary>Xem</summary>
                          <pre>{a.evidence}</pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!alerts.length && <p>Không có cảnh báo phù hợp.</p>}
            <div className="pagination">
              <button
                disabled={page === 0 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <span>Trang {page + 1}</span>
              <button
                disabled={alerts.length < 25 || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Tiếp
              </button>
            </div>
          </section>
        )}
        {tab === "blocked" && (
          <>
            <section className="panel">
              <h2>Trạng thái firewall</h2>
              <p className={blocked?.in_sync ? "notice" : "error"}>
                {blocked?.in_sync
                  ? "Database khớp với nftables."
                  : (blocked?.error ??
                    "Database và nftables chưa đồng bộ. Kiểm tra danh sách thực tế trước khi thao tác.")}
              </p>
              <p>
                IP thực tế:{" "}
                {blocked?.kernel?.join(", ") ||
                  (blocked?.kernel ? "Không có" : "Chưa đọc được")}
              </p>
              {admin && (
                <form
                  className="filters"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action(ip);
                  }}
                >
                  <label>
                    IP cần chặn
                    <input
                      value={ip}
                      onChange={(e) => setIp(e.target.value)}
                      placeholder="192.168.10.10"
                      required
                    />
                  </label>
                  <label>
                    Lý do
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      maxLength={500}
                      required
                    />
                  </label>
                  <button className="primary" disabled={busy}>
                    Gửi yêu cầu chặn
                  </button>
                </form>
              )}
            </section>
            <section className="panel">
              <h2>Danh sách từ DB và kernel</h2>
              {Array.from(
                new Set([
                  ...(blocked?.database.map((b) => b.ip) ?? []),
                  ...(blocked?.kernel ?? []),
                ]),
              ).map((address) => {
                const row = blocked?.database.find((b) => b.ip === address);
                return (
                  <div className="type-row" key={address}>
                    <div>
                      <strong>{address}</strong>
                      <p>
                        {row?.reason ?? "Chỉ có trong kernel"} ·{" "}
                        {blocked?.kernel?.includes(address)
                          ? "Có trong kernel"
                          : "Chưa xác nhận trong kernel"}
                      </p>
                    </div>
                    {admin && (
                      <button
                        disabled={busy}
                        onClick={() => void action(address, true)}
                      >
                        Bỏ chặn
                      </button>
                    )}
                  </div>
                );
              })}
              {!blocked?.database.length && !blocked?.kernel?.length && (
                <p>Chưa có IP bị chặn.</p>
              )}
            </section>
          </>
        )}
        {tab === "audit" && (
          <section className="panel">
            <h2>100 thao tác gần nhất</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID / Thời gian</th>
                    <th>Người thực hiện</th>
                    <th>Thao tác / IP</th>
                    <th>Lý do</th>
                    <th>Kết quả</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td>
                        #{a.id}
                        <small>{new Date(a.created_at).toLocaleString()}</small>
                      </td>
                      <td>{a.actor}</td>
                      <td>
                        {a.action} {a.ip}
                      </td>
                      <td>{a.reason}</td>
                      <td>
                        <span
                          className={`badge ${a.status === "SUCCESS" ? "good" : a.status === "ERROR" ? "danger" : "warn"}`}
                        >
                          {a.status}
                        </span>
                        {a.details && <p>{a.details}</p>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!audit.length && <p>Chưa có thao tác.</p>}
          </section>
        )}
        {tab === "rules" && (
          <section className="panel">
            <h2>Luật và chính sách hiện tại</h2>
            <p className="muted">
              Chính sách được cấu hình trên server. Danh mục dưới đây mô tả bộ
              rule đi kèm dự án.
            </p>
            {rules.map((r) => (
              <div className="type-row" key={r.sid}>
                <div>
                  <strong>{r.name}</strong>
                  <p>
                    SID {r.sid} · Severity {r.severity}
                  </p>
                </div>
                <span className="badge">
                  {r.auto_block_eligible
                    ? "Cho phép auto-block"
                    : "Chỉ cảnh báo"}
                </span>
              </div>
            ))}
          </section>
        )}
        {tab === "status" && (
          <>
            <section className="panel">
              <h2>Dịch vụ</h2>
              <p>
                Database: {health?.database ? "Kết nối được" : "Chưa sẵn sàng"}
              </p>
              <p>Firewall: {health?.firewall ? "Đọc được" : "Chưa sẵn sàng"}</p>
              <p>
                DB / firewall:{" "}
                {health?.firewall_in_sync ? "Đồng bộ" : "Chưa đồng bộ"}
              </p>
              {Object.entries(health?.watchers ?? {}).map(([name, value]) => (
                <p key={name}>
                  {name}: {value}
                </p>
              ))}
              <p>Dòng log không hợp lệ: {fmt(health?.ingestion_errors)}</p>
            </section>
            <section className="cards">
              <article>
                <p>Load average 1 phút</p>
                <strong>{fmt(stats?.system.load_average_1m)}</strong>
              </article>
              <article>
                <p>Bộ nhớ đang dùng</p>
                <strong>{fmt(stats?.system.memory_percent, "%")}</strong>
              </article>
              <article>
                <p>Byte nhận trên NIC từ khi khởi động/reset</p>
                <strong>{fmt(stats?.system.interface_rx_bytes)}</strong>
              </article>
              <article>
                <p>Kết nối TCP established trên máy</p>
                <strong>
                  {fmt(stats?.system.established_tcp_connections)}
                </strong>
              </article>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Boundary>
      <App />
    </Boundary>
  </StrictMode>,
);
