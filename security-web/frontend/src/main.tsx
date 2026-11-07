import {
  freshness,
  triageLabels,
  ruleDeployment,
  type Verification,
} from "./operations";
import { applicationEvidence } from "./applicationEvidence";
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
import { AlertDetail } from "./AlertDetail";
import { ApplicationAudit } from "./ApplicationAudit";
import { AiShadow } from "./AiShadow";
import { Icon } from "./Icon";
import { EmptyState } from "./UiState";
import { AlertTrend, type TrendPoint } from "./AlertTrend";
import { createAlertTracker, type AlertUpdates } from "./alertUpdates";

const securityLogo = new URL("./assets/logo-security.png", import.meta.url)
  .href;

type User = { username: string; role: "admin" | "viewer" };
type Alert = {
  triage_status?: string;
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
type IpSummary = {
  ip: string;
  count: number;
  severity: number;
  last_seen: string;
};
type Stats = {
  alert_updates?: AlertUpdates;
  range: string;
  from: string;
  to: string;
  unknown_destinations: number;
  unique_sources: number;
  sources: { name: string; count: number }[];
  severities: { severity: number; count: number }[];
  source_ips: IpSummary[];
  destination_ips: IpSummary[];
  recent: Alert[];
  jobs: { status: string; count: number }[];
  total_alerts: number;
  critical_alerts: number;
  blocked_attacks: number;
  trend: TrendPoint[];
  types: { name: string; count: number }[];
  system: {
    hostname?: string | null;
    interface?: string;
    sampled_at?: string;
    interface_tx_bytes?: number | null;
    rx_bytes_per_second?: number | null;
    tx_bytes_per_second?: number | null;
    network_error?: string | null;
    disk_path?: string;
    disk?: { total_bytes: number; available_bytes: number } | null;
    disk_error?: string | null;
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
function auditSource(source: string) {
  return (
    (
      {
        AUTO: "Hệ thống tự động",
        RESTORE: "Hệ thống khôi phục",
        UI: "Quản trị viên",
        API: "Quản trị viên qua API",
        MANUAL: "Thủ công",
      } as Record<string, string>
    )[source] ?? source
  );
}
type Audit = {
  source: string;
  completed_at: string | null;
  event_id: number | null;
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
  verification?: Verification;
  sid: number | null;
  code: string;
  source: string;
  action_mode: string;
  threshold?: number;
  window_seconds?: number;
  name: string;
  severity: number;
  auto_block_eligible: boolean;
};
type Health = {
  checked_at?: string;
  dataset_collection?: boolean;
  operations?: {
    sampled_at?: string;
    receiver?: { active: string; load: string; sub: string };
    suricata?: { active: string; load: string; sub: string };
  };
  healthy: boolean;
  database: boolean;
  firewall: boolean;
  firewall_in_sync: boolean;
  watchers: Record<
    string,
    {
      state: string;
      last_success_at: string | null;
      last_data_at: string | null;
      pending_bytes: number | null;
      error: string | null;
    }
  >;
  collection: Record<
    string,
    {
      last_ingested_at?: string | null;
      last_ingested_event_at?: string | null;
      last_alert_at: string | null;
      error_count: number;
      last_error: { at: string; reason: string } | null;
    }
  > | null;
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
  const [selectedAlert, setSelectedAlert] = useState<number | null>(null);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [alertFilters, setAlertFilters] = useState({
    from: "",
    to: "",
    source: "",
    action: "",
    dest_ip: "",
    triage_status: "",
  });
  const filterParams = new URLSearchParams();
  Object.entries(alertFilters).forEach(([key, value]) => {
    if (value)
      filterParams.set(
        key,
        key === "from" || key === "to" ? new Date(value).toISOString() : value,
      );
  });
  const extraFilters = filterParams.toString();
  const [page, setPage] = useState(0);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [range, setRange] = useState("24h");
  const [stats, setStats] = useState<Stats | null>(null);
  const [blocked, setBlocked] = useState<Blocked | null>(null);
  const [auditEvent, setAuditEvent] = useState<number | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [applicationAuditRefresh, setApplicationAuditRefresh] = useState(0);
  const [rules, setRules] = useState<Rule[]>([]);
  const [ruleSearch, setRuleSearch] = useState("");
  const [ruleSeverity, setRuleSeverity] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [ruleSource, setRuleSource] = useState("SURICATA");
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [ip, setIp] = useState("");
  const [reason, setReason] = useState("");
  const tracker = useRef(createAlertTracker());
  const [alertFeedback, setAlertFeedback] = useState<AlertUpdates | null>(null);
  const feedbackCooldown = useRef(0);
  const [effectsEnabled, setEffectsEnabled] = useState(true);
  useEffect(() => {
    if (!alertFeedback) return;
    const timer = setTimeout(() => setAlertFeedback(null), 6000);
    return () => clearTimeout(timer);
  }, [alertFeedback]);
  const refreshing = useRef(false);
  const requestKey = `${session?.token ?? ""}:${page}:${filter}:${severity}:${range}:${extraFilters}:${auditEvent}`;
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
          `/api/alerts/search?${extraFilters}&limit=25&offset=${page * 25}&search=${encodeURIComponent(filter)}${severity ? `&severity=${severity}` : ""}`,
        ),
        api(
          `/api/stats?range=${range}${tracker.current.cursor() === null ? "" : `&after_alert_id=${tracker.current.cursor()}`}`,
        ),
        api("/api/blocked-ips"),
        api(
          `/api/audit${auditEvent !== null ? `?event_id=${auditEvent}` : ""}`,
        ),
        api("/api/rules"),
        api("/api/status"),
      ]);
      if (latestKey.current !== requestKey) return;
      setAlerts(results[0].items);
      setTotalAlerts(results[0].total);
      setStats(results[1]);
      const incoming = tracker.current.accept(results[1].alert_updates);
      if (incoming && effectsEnabled) {
        if (Date.now() >= feedbackCooldown.current) {
          setAlertFeedback(incoming);
          feedbackCooldown.current = Date.now() + 6000;
        } else {
          setAlertFeedback((previous) =>
            previous
              ? {
                  ...incoming,
                  count: previous.count + incoming.count,
                  severity: Math.min(
                    previous.severity ?? 5,
                    incoming.severity ?? 5,
                  ),
                  items: [...previous.items, ...incoming.items].slice(-200),
                }
              : incoming,
          );
        }
      }
      setBlocked(results[2]);
      setAudit(results[3]);
      setRules(results[4]);
      setHealth(results[5]);
      setUpdated(new Date().toLocaleTimeString("vi-VN", { hour12: false }));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      refreshing.current = false;
      setLoading(false);
    }
  }, [
    session,
    page,
    filter,
    severity,
    range,
    extraFilters,
    auditEvent,
    api,
    requestKey,
    effectsEnabled,
  ]);
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
      tracker.current.reset();
      setAlertFeedback(null);
      feedbackCooldown.current = 0;
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
      tracker.current.reset();
      setAlertFeedback(null);
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
      [
        "ID",
        "Thời gian",
        "Nguồn",
        "IP",
        "Rule",
        "Severity",
        "Hành động",
        "Xử lý",
      ],
      ...alerts.map((a) => [
        a.id,
        a.occurred_at,
        a.source,
        a.src_ip,
        a.rule_name,
        a.severity,
        a.action,
        triageLabels[a.triage_status ?? "NEW"],
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
          <div className="login-emblem">
            <img src={securityLogo} alt="" width="64" height="64" />
          </div>
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
            <Icon name="arrow" />
          </button>
        </form>
      </main>
    );
  const feedbackClass = (id: number) => {
    const item = alertFeedback?.items.find((a) => a.id === id);
    return effectsEnabled && item
      ? `new-alert new-alert-s${item.severity}`
      : "";
  };
  const admin = session.user.role === "admin";
  const tabs = [
    ["overview", "Tổng quan"],
    ["alerts", "Cảnh báo"],
    ["application-audit", "Audit ứng dụng"],
    ["ai-shadow", "AI shadow"],
    ["blocked", "IP bị chặn"],
    ["audit", "Nhật ký thao tác"],
    ["rules", "Luật phát hiện"],
    ["status", "Trạng thái hệ thống"],
  ];
  const fmt = (v: number | null | undefined, suffix = "") =>
    v == null ? "Chưa có dữ liệu" : `${v.toLocaleString("vi-VN")}${suffix}`;
  return (
    <div className="shell">
      <a className="skip-link" href="#dashboard-content">
        Đi tới nội dung chính
      </a>
      <aside>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("overview");
          }}
        >
          <span className="brand-mark">
            <img src={securityLogo} alt="" width="46" height="46" />
          </span>
          <span className="brand-wordmark">
            WebSentinel <span>Security Operations</span>
          </span>
        </a>
        <p className="eyebrow">ĐIỀU HÀNH BẢO MẬT</p>
        <button
          className="mobile-menu"
          aria-expanded={menuOpen}
          aria-controls="dashboard-navigation"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <Icon name="overview" /> Điều hướng
        </button>
        <nav
          id="dashboard-navigation"
          className={menuOpen ? "menu-open" : ""}
          aria-label="Điều hướng"
        >
          {tabs.map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => {
                setTab(id);
                setMenuOpen(false);
              }}
            >
              <Icon name={id} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="account">
          <div className="account-profile">
            <span className="avatar" aria-hidden="true">
              {session.user.username.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong>{session.user.username}</strong>
              <p>{admin ? "Quản trị viên" : "Chỉ xem"}</p>
            </div>
          </div>
          <button onClick={() => void logout()}>
            <Icon name="logout" />
            Đăng xuất
          </button>
        </div>
      </aside>
      <main id="dashboard-content" tabIndex={-1}>
        <header>
          <div>
            <p className="eyebrow">SECURITY OPERATIONS</p>
            <h1>
              <span className="heading-icon">
                <Icon name={tab} />
              </span>
              {tabs.find(([id]) => id === tab)?.[1]}
            </h1>
          </div>
          <div className="header-actions">
            <label className="effects-toggle">
              <input
                type="checkbox"
                checked={effectsEnabled}
                onChange={(e) => {
                  setEffectsEnabled(e.target.checked);
                  setAlertFeedback(null);
                }}
              />
              Hiệu ứng cảnh báo mới
            </label>
            <span
              className={`badge status-badge ${!error && health?.healthy ? "good" : "warn"}`}
            >
              {error
                ? "Mất kết nối / dữ liệu có thể cũ"
                : health?.healthy
                  ? "Hệ thống sẵn sàng"
                  : "Cần kiểm tra hệ thống"}
            </span>
            <p className="muted updated-at">
              <Icon name="clock" />
              {updated
                ? `${tab === "application-audit" ? "Dữ liệu chung (không gồm Audit)" : "Dashboard tải dữ liệu thành công"}: ${updated}`
                : "Đang tải dữ liệu"}
            </p>
            <button
              onClick={() => {
                if (tab === "application-audit")
                  setApplicationAuditRefresh((value) => value + 1);
                void refresh();
              }}
              disabled={loading}
            >
              <Icon name="refresh" className={loading ? "is-spinning" : ""} />
              {loading ? "Đang tải…" : "Làm mới"}
            </button>
          </div>
        </header>
        {alertFeedback && effectsEnabled && (
          <div
            className={`alert-toast new-alert-s${alertFeedback.severity ?? 3}`}
            role="status"
            aria-live="polite"
          >
            <strong>
              {alertFeedback.severity === 1
                ? "Phát hiện cảnh báo nghiêm trọng"
                : "Có cảnh báo mới"}
            </strong>
            <p>
              {alertFeedback.count} cảnh báo mới toàn hệ thống · Severity cao
              nhất: {alertFeedback.severity ?? "—"}. Chưa khẳng định tấn công
              thành công hoặc IP đã bị chặn.
            </p>
            <button onClick={() => setAlertFeedback(null)}>
              Đóng thông báo
            </button>
          </div>
        )}
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
        {tab === "application-audit" && (
          <ApplicationAudit api={api} refreshSignal={applicationAuditRefresh} />
        )}
        {tab === "ai-shadow" && <AiShadow api={api} />}
        {tab === "overview" && (
          <div className="overview-layout">
            <section className="panel overview-toolbar">
              <label>
                Khoảng thời gian
                <select
                  value={range}
                  onChange={(e) => {
                    setStats(null);
                    setRange(e.target.value);
                  }}
                >
                  <option value="1h">1 giờ gần nhất</option>
                  <option value="24h">24 giờ gần nhất</option>
                  <option value="7d">7 ngày gần nhất</option>
                </select>
              </label>
              <p className="muted">
                Số cảnh báo không phải số cuộc tấn công: một request có thể được
                nhiều nguồn phát hiện.
                {stats && (
                  <small>
                    {new Date(stats.from).toLocaleString("vi-VN", {
                      hour12: false,
                    })}{" "}
                    →{" "}
                    {new Date(stats.to).toLocaleString("vi-VN", {
                      hour12: false,
                    })}{" "}
                    · giờ địa phương
                  </small>
                )}
                {!stats && (
                  <small>
                    {loading ? "Đang tải dữ liệu…" : "Chưa tải được dữ liệu."}
                  </small>
                )}
              </p>
            </section>
            <section className="cards" aria-label="Thống kê">
              {[
                ["Tổng cảnh báo", stats?.total_alerts],
                ["Mức nghiêm trọng 1", stats?.critical_alerts],
                ["Sự kiện auto-block thành công", stats?.blocked_attacks],
                ["IP nguồn khác nhau", stats?.unique_sources],
              ].map(([label, value], index) => (
                <article
                  className={`metric-card metric-${index} ${index === 1 && effectsEnabled && alertFeedback?.severity === 1 ? "new-alert new-alert-s1" : ""}`}
                  key={String(label)}
                >
                  <div className="metric-heading">
                    <p>{label}</p>
                    <span className="metric-icon">
                      <Icon
                        name={["status", "alerts", "blocked", "network"][index]}
                      />
                    </span>
                  </div>
                  <strong>{fmt(value as number | undefined)}</strong>
                  <button
                    className="metric-link"
                    onClick={() => {
                      if (index === 2) {
                        setTab("audit");
                        return;
                      }
                      setSearch("");
                      setFilter("");
                      setSeverity(index === 1 ? "1" : "");
                      setAlertFilters({
                        from: stats?.from
                          ? new Date(
                              new Date(stats.from).getTime() -
                                new Date(stats.from).getTimezoneOffset() *
                                  60000,
                            )
                              .toISOString()
                              .slice(0, 16)
                          : "",
                        to: stats?.to
                          ? new Date(
                              new Date(stats.to).getTime() -
                                new Date(stats.to).getTimezoneOffset() * 60000,
                            )
                              .toISOString()
                              .slice(0, 16)
                          : "",
                        source: "",
                        action: "",
                        dest_ip: "",
                        triage_status: "",
                      });
                      setPage(0);
                      setTab("alerts");
                    }}
                  >
                    {index === 2 ? "Xem nhật ký thao tác →" : "Xem cảnh báo →"}
                  </button>
                </article>
              ))}
            </section>
            <section className="panel overview-trend">
              <h2>
                <Icon name="status" />
                Diễn biến cảnh báo
              </h2>
              <p className="muted">
                Trong khoảng thời gian đã chọn · số cảnh báo đã lưu trong
                database
              </p>
              <AlertTrend points={stats?.trend} range={range} />
            </section>
            <section className="panel overview-recent">
              <h2>10 cảnh báo mới nhất trong khoảng đã chọn</h2>
              <p className="muted">
                Mở từng cảnh báo để xem IP, hành động và bằng chứng gốc.
              </p>
              {stats?.recent.map((a) => (
                <details
                  className={`overview-alert ${feedbackClass(a.id)}`}
                  key={a.id}
                >
                  <summary>
                    <span className="recent-alert-title">{a.rule_name}</span>
                    <span className="recent-alert-meta">
                      <span>
                        #{a.id} ·{" "}
                        {new Date(a.occurred_at).toLocaleString("vi-VN", {
                          hour12: false,
                        })}
                      </span>
                      <span className={`source-label source-${a.source}`}>
                        {a.source}
                      </span>
                      <span
                        className={`badge ${a.severity === 1 ? "danger" : a.severity === 2 ? "warn" : ""}`}
                      >
                        {a.severity === 1
                          ? "Cao · S1"
                          : a.severity === 2
                            ? "Trung bình · S2"
                            : `Thấp · S${a.severity}`}
                      </span>
                    </span>
                  </summary>
                  <p>
                    Nguồn: {a.source} · IP: {a.src_ip ?? "Không có"} →{" "}
                    {a.dest_ip ?? "Không có"} · Hành động: {a.action}
                  </p>
                  <button onClick={() => setSelectedAlert(a.id)}>
                    Mở chi tiết điều tra
                  </button>
                  <pre>{a.evidence}</pre>
                </details>
              ))}
              {stats?.recent.length === 0 && (
                <EmptyState title="Chưa có cảnh báo trong khoảng này." />
              )}
            </section>
            <section className="panel overview-types">
              <h2>
                <Icon name="overview" />
                Nhóm cảnh báo phổ biến
              </h2>
              {!stats?.types.length ? (
                <p>Chưa có cảnh báo.</p>
              ) : (
                stats.types.map((t, index) => (
                  <div className="type-row attack-row" key={t.name}>
                    <span className="type-rank" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div className="type-main">
                      <span>{t.name}</span>
                      <div className="type-track" aria-hidden="true">
                        <div
                          style={{
                            width: `${(t.count / Math.max(1, ...stats.types.map((item) => item.count))) * 100}%`,
                          }}
                        />
                      </div>
                    </div>
                    <strong className="count-pill">{t.count}</strong>
                  </div>
                ))
              )}
            </section>
            <section className="panel overview-sources">
              <h2>Nguồn dữ liệu</h2>
              {["SURICATA", "NGINX", "STUDENT_AUDIT"].map((source) => {
                const w = health?.watchers[source];
                return (
                  <div className="source-summary" key={source}>
                    <strong className={`source-label source-${source}`}>
                      {source === "STUDENT_AUDIT" ? "Student Audit" : source}
                    </strong>
                    <span
                      className={`badge ${w?.state === "error" ? "danger" : ""}`}
                    >
                      {w?.state === "watching"
                        ? "Đọc được file"
                        : w?.state === "error"
                          ? "Lỗi đọc log"
                          : "Chưa xác định"}
                    </span>
                    <small>
                      Dữ liệu gần nhất:{" "}
                      {w?.last_data_at
                        ? new Date(w.last_data_at).toLocaleString("vi-VN", {
                            hour12: false,
                          })
                        : "Chưa ghi nhận"}
                    </small>
                  </div>
                );
              })}
              <button onClick={() => setTab("status")}>
                Xem trạng thái hệ thống
              </button>
            </section>
            <div className="overview-grid">
              {(
                [
                  ["IP nguồn nổi bật", stats?.source_ips],
                  ["Đích bị nhắm tới", stats?.destination_ips],
                ] as const
              ).map(([title, rows]) => (
                <section className="panel" key={title}>
                  <h2>{title}</h2>
                  <p className="muted">
                    Top 5 · mức độ cao nhất là số severity nhỏ nhất
                  </p>
                  {rows?.map((row) => (
                    <div className="type-row" key={row.ip}>
                      <div>
                        <strong>{row.ip}</strong>
                        <small>
                          Severity {row.severity} · Gần nhất:{" "}
                          {new Date(row.last_seen).toLocaleString("vi-VN", {
                            hour12: false,
                          })}
                        </small>
                      </div>
                      <span className="count-pill">{row.count}</span>
                    </div>
                  ))}
                  {rows?.length === 0 && (
                    <p>Không có IP được ghi nhận trong khoảng này.</p>
                  )}
                  {title === "Đích bị nhắm tới" && (
                    <p className="muted">
                      {fmt(stats?.unknown_destinations)} cảnh báo không có IP
                      đích; không tính vào bảng này.
                    </p>
                  )}
                </section>
              ))}
              <section className="panel">
                <h2>Phân bố mức độ</h2>
                <p className="muted">
                  1 là mức ưu tiên cao nhất; số càng lớn, ưu tiên càng thấp theo
                  rule nguồn.
                </p>
                {[1, 2, 3, 4, 5].map((level) => (
                  <div className="type-row" key={level}>
                    <span className={`badge ${level === 1 ? "danger" : ""}`}>
                      Severity {level}
                    </span>
                    <strong>
                      {stats
                        ? (stats.severities.find((x) => x.severity === level)
                            ?.count ?? 0)
                        : "—"}
                    </strong>
                  </div>
                ))}
                {stats?.severities
                  .filter((x) => x.severity < 1 || x.severity > 5)
                  .map((x) => (
                    <p key={x.severity}>
                      Mức khác ({x.severity}): {x.count}
                    </p>
                  ))}
              </section>
              <section className="panel">
                <h2>Nguồn phát hiện</h2>
                {Array.from(
                  new Set([
                    "NGINX",
                    "SURICATA",
                    ...(stats?.sources.map((x) => x.name) ?? []),
                  ]),
                ).map((name) => (
                  <div className="type-row" key={name}>
                    <strong>{name}</strong>
                    <span className="count-pill">
                      {stats
                        ? (stats.sources.find((x) => x.name === name)?.count ??
                          0)
                        : "—"}
                    </span>
                  </div>
                ))}
                <p className="muted">
                  Không có cảnh báo không đồng nghĩa nguồn đang ngừng hoạt động.
                </p>
              </section>
            </div>
            <section className="panel">
              <h2>Tác vụ chặn</h2>
              <p className="muted">
                Trạng thái hiện tại của yêu cầu BLOCK được tạo trong khoảng đã
                chọn, gồm tự động và thủ công.
              </p>
              <div className="overview-jobs">
                {[
                  ["PENDING", "Đang chờ"],
                  ["SUCCESS", "Thành công"],
                  ["ERROR", "Thất bại"],
                ].map(([status, label]) => (
                  <button
                    key={status}
                    onClick={() => {
                      setAudit([]);
                      setAuditEvent(null);
                      setTab("audit");
                    }}
                  >
                    <span>{label}</span>
                    <strong>
                      {stats
                        ? (stats.jobs.find((x) => x.status === status)?.count ??
                          0)
                        : "—"}
                    </strong>
                    <small>Xem audit gần nhất →</small>
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}
        {tab === "alerts" && (
          <section className="panel">
            <form
              className="filters"
              onSubmit={(e) => {
                e.preventDefault();
                setFilter(search);
                setAlertFilters({
                  ...alertFilters,
                  dest_ip: String(
                    new FormData(e.currentTarget).get("dest_ip") ?? "",
                  ).trim(),
                });
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
              <label>
                Từ (giờ địa phương)
                <input
                  type="datetime-local"
                  value={alertFilters.from}
                  onChange={(e) => {
                    setAlertFilters({ ...alertFilters, from: e.target.value });
                    setPage(0);
                  }}
                />
              </label>
              <label>
                Đến (không gồm mốc này)
                <input
                  type="datetime-local"
                  value={alertFilters.to}
                  onChange={(e) => {
                    setAlertFilters({ ...alertFilters, to: e.target.value });
                    setPage(0);
                  }}
                />
              </label>
              <label>
                Nguồn
                <select
                  value={alertFilters.source}
                  onChange={(e) => {
                    setAlertFilters({
                      ...alertFilters,
                      source: e.target.value,
                    });
                    setPage(0);
                  }}
                >
                  <option value="">Tất cả</option>
                  <option>NGINX</option>
                  <option>SURICATA</option>
                  <option>AI_SHADOW</option>
                  <option value="STUDENT_AUDIT">Student Audit</option>
                </select>
              </label>
              <label>
                Trạng thái xử lý
                <select
                  value={alertFilters.triage_status}
                  onChange={(e) => {
                    setAlertFilters({
                      ...alertFilters,
                      triage_status: e.target.value,
                    });
                    setPage(0);
                  }}
                >
                  <option value="">Tất cả</option>
                  {Object.entries(triageLabels).map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <details className="advanced-filters">
                <summary>Bộ lọc nâng cao</summary>
                <div className="advanced-fields">
                  <label>
                    Hành động
                    <select
                      value={alertFilters.action}
                      onChange={(e) => {
                        setAlertFilters({
                          ...alertFilters,
                          action: e.target.value,
                        });
                        setPage(0);
                      }}
                    >
                      <option value="">Tất cả</option>
                      <option>ALERT</option>
                      <option>AUTO-BLOCK</option>
                      <option>BLOCK</option>
                    </select>
                  </label>
                  <label>
                    IP đích chính xác
                    <input
                      name="dest_ip"
                      defaultValue={alertFilters.dest_ip}
                      placeholder="192.168.20.10"
                    />
                  </label>
                </div>
              </details>
              <button>Tìm kiếm</button>
              <button
                type="button"
                onClick={exportPage}
                disabled={!alerts.length}
              >
                Xuất CSV trang này
              </button>
            </form>
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Bảng dữ liệu, có thể cuộn"
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Thời gian</th>
                    <th scope="col">Nguồn / Rule</th>
                    <th scope="col">IP nguồn → đích</th>
                    <th scope="col">Mức độ</th>
                    <th scope="col">Hành động</th>
                    <th scope="col">Xử lý</th>
                    <th scope="col">Tổng hợp ứng dụng</th>
                    <th scope="col">Bằng chứng</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((a) => (
                    <tr key={a.id} className={feedbackClass(a.id)}>
                      <td>
                        {new Date(a.occurred_at).toLocaleString("vi-VN", {
                          hour12: false,
                        })}
                      </td>
                      <td>
                        <strong className="alert-rule-name">
                          {a.rule_name}
                        </strong>
                        <small className={`source-label source-${a.source}`}>
                          {a.source}
                        </small>
                      </td>
                      <td>
                        {a.src_ip ?? "—"} → {a.dest_ip ?? "—"}
                      </td>
                      <td>
                        <span
                          className={
                            a.severity === 1
                              ? "badge danger"
                              : a.severity === 2
                                ? "badge warn"
                                : "badge"
                          }
                        >
                          {a.severity === 1
                            ? "Cao · S1"
                            : a.severity === 2
                              ? "Trung bình · S2"
                              : `Thấp · S${a.severity}`}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`badge ${a.action === "AUTO-BLOCK" ? "good" : "warn"}`}
                        >
                          {a.action}
                        </span>
                      </td>
                      <td>
                        <span className="badge">
                          {triageLabels[a.triage_status ?? "NEW"] ??
                            "Chưa xác định"}
                        </span>
                      </td>
                      <td>
                        {(() => {
                          const app = applicationEvidence(a.evidence);
                          return app ? (
                            <>
                              <strong>{app.count} sự kiện (đỉnh cửa sổ)</strong>
                              <small>{app.endpoint}</small>
                              <small>{app.reason}</small>
                              <small>
                                Đề xuất: {app.recommendation} · Không tự chặn
                              </small>
                            </>
                          ) : (
                            "—"
                          );
                        })()}
                      </td>
                      <td>
                        <button onClick={() => setSelectedAlert(a.id)}>
                          Chi tiết #{a.id}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!alerts.length && (
              <EmptyState
                title="Không có cảnh báo phù hợp."
                description="Kiểm tra nguồn, khoảng thời gian và các bộ lọc đã chọn."
              />
            )}
            <div className="pagination">
              <button
                disabled={page === 0 || loading}
                onClick={() => setPage((p) => p - 1)}
              >
                Trước
              </button>
              <span>
                {totalAlerts} kết quả · Trang {page + 1} /{" "}
                {Math.max(1, Math.ceil(totalAlerts / 25))}
              </span>
              <button
                disabled={(page + 1) * 25 >= totalAlerts || loading}
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
              <h2>
                <Icon name="blocked" />
                Trạng thái firewall
              </h2>
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
              <h2>
                <Icon name="network" />
                Danh sách từ DB và kernel
              </h2>
              {Array.from(
                new Set([
                  ...(blocked?.database.map((b) => b.ip) ?? []),
                  ...(blocked?.kernel ?? []),
                ]),
              ).map((address) => {
                const row = blocked?.database.find((b) => b.ip === address);
                return (
                  <div className="type-row blocked-row" key={address}>
                    <div>
                      <strong>{address}</strong>
                      <p>
                        {blocked?.kernel == null
                          ? "Có trong DB · Chưa xác định trong kernel"
                          : row && blocked.kernel.includes(address)
                            ? "Có trong cả DB và kernel"
                            : row
                              ? "Chỉ có trong DB"
                              : "Chỉ có trong kernel"}
                      </p>
                      <p>Lý do: {row?.reason ?? "Không có bản ghi DB"}</p>
                      <small>
                        Thời điểm chặn (DB):{" "}
                        {row
                          ? new Date(row.blocked_at).toLocaleString("vi-VN", {
                              hour12: false,
                            })
                          : "Không xác định"}
                      </small>
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
              {blocked?.kernel == null ? (
                <p>Chưa xác định được trạng thái firewall.</p>
              ) : !blocked.database.length && !blocked.kernel.length ? (
                <EmptyState title="Chưa có IP bị chặn trong DB và kernel." />
              ) : null}
            </section>
          </>
        )}
        {tab === "audit" && (
          <section className="panel">
            <h2>
              <Icon name="audit" />
              {auditEvent === null
                ? "100 thao tác gần nhất"
                : `Tác vụ liên quan cảnh báo #${auditEvent}`}
            </h2>
            {auditEvent !== null && (
              <button
                onClick={() => {
                  setAudit([]);
                  setAuditEvent(null);
                }}
              >
                Xem tất cả thao tác
              </button>
            )}
            <div
              className="table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Bảng dữ liệu, có thể cuộn"
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">ID / Thời gian</th>
                    <th scope="col">Người thực hiện / Nguồn yêu cầu</th>
                    <th scope="col">Thao tác / IP</th>
                    <th scope="col">Lý do</th>
                    <th scope="col">Kết quả</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td>
                        #{a.id}
                        <small>
                          {new Date(a.created_at).toLocaleString("vi-VN", {
                            hour12: false,
                          })}
                        </small>
                      </td>
                      <td>
                        {a.actor}
                        <small>{auditSource(a.source)}</small>
                      </td>
                      <td>
                        {a.action} {a.ip}
                        {a.event_id !== null && (
                          <button onClick={() => setSelectedAlert(a.event_id)}>
                            Cảnh báo #{a.event_id}
                          </button>
                        )}
                      </td>
                      <td>{a.reason}</td>
                      <td>
                        <span
                          className={`badge ${a.status === "SUCCESS" ? "good" : a.status === "ERROR" ? "danger" : "warn"}`}
                        >
                          {a.status}
                        </span>
                        <small>
                          Hoàn tất:{" "}
                          {a.completed_at
                            ? new Date(a.completed_at).toLocaleString("vi-VN", {
                                hour12: false,
                              })
                            : a.status === "PENDING"
                              ? "Đang chờ"
                              : "Chưa có dữ liệu"}
                        </small>
                        {a.details && <p>{a.details}</p>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!audit.length && <EmptyState title="Chưa có thao tác." />}
          </section>
        )}
        {tab === "rules" && (
          <section className="panel">
            <h2>
              <Icon name="rules" />
              Luật và chính sách hiện tại
            </h2>
            <p className="muted">
              Chính sách được cấu hình trên server. Danh mục dưới đây mô tả bộ
              rule đi kèm dự án.
            </p>
            <div
              className="rule-source-picker"
              role="group"
              aria-label="Chọn tầng phát hiện"
            >
              {[
                {
                  source: "SURICATA",
                  title: "Mạng",
                  label: "Suricata · Quan sát lưu lượng mạng",
                },
                {
                  source: "NGINX",
                  title: "Web/Proxy",
                  label: "NGINX · Phân tích HTTP/access log",
                },
                {
                  source: "STUDENT_AUDIT",
                  title: "Ứng dụng",
                  label: "Student Audit · Phân tích hành vi request",
                },
              ].map((group) => (
                <button
                  key={group.source}
                  className={`source-${group.source}`}
                  type="button"
                  aria-pressed={ruleSource === group.source}
                  aria-controls="rule-source-list"
                  onClick={() => setRuleSource(group.source)}
                >
                  <span>
                    <strong>{group.title}</strong>
                    <small>{group.label}</small>
                  </span>
                  <span className="badge">
                    {
                      rules.filter(
                        (r) =>
                          (r.source === "APPLICATION"
                            ? "STUDENT_AUDIT"
                            : r.source) === group.source,
                      ).length
                    }{" "}
                    luật
                  </span>
                </button>
              ))}
            </div>
            <div className="rule-tools">
              <label>
                Tìm luật
                <input
                  value={ruleSearch}
                  onChange={(e) => setRuleSearch(e.target.value)}
                  placeholder="Tên luật hoặc mã rule…"
                />
              </label>
              <label>
                Mức độ
                <select
                  value={ruleSeverity}
                  onChange={(e) => setRuleSeverity(e.target.value)}
                >
                  <option value="">Tất cả mức độ</option>
                  <option value="1">Cao · S1</option>
                  <option value="2">Trung bình · S2</option>
                  <option value="3">Thấp · S3</option>
                </select>
              </label>
            </div>
            <div id="rule-source-list">
              <h3>
                {ruleSource === "SURICATA"
                  ? "Mạng — Suricata"
                  : ruleSource === "NGINX"
                    ? "Web/Proxy — NGINX"
                    : "Ứng dụng — Student Audit"}
              </h3>
              <p className="muted">
                {ruleSource === "SURICATA"
                  ? "Phát hiện từ gói tin và giao thức, bao gồm HTTP. Danh mục này không xác nhận Suricata đã nạp các luật trên máy chạy sensor."
                  : ruleSource === "NGINX"
                    ? "Phân tích HTTP request/access log đã thực sự tới reverse proxy. Các luật chạy trong Rust trên dữ liệu NGINX, không phải luật Suricata."
                    : "Phân tích audit do Student Web ghi nhận, tổng hợp nhiều request theo cửa sổ thời gian. Khuyến nghị chặn không đồng nghĩa tự động chặn."}
              </p>
              {!rules.some(
                (r) =>
                  (r.source === "APPLICATION" ? "STUDENT_AUDIT" : r.source) ===
                    ruleSource &&
                  (!ruleSeverity || String(r.severity) === ruleSeverity) &&
                  `${r.name} ${r.code}`
                    .toLowerCase()
                    .includes(ruleSearch.toLowerCase().trim()),
              ) && (
                <p className="muted">
                  Không có luật khớp nguồn, tên và mức độ đã chọn.
                </p>
              )}
              {rules
                .filter(
                  (r) =>
                    (r.source === "APPLICATION"
                      ? "STUDENT_AUDIT"
                      : r.source) === ruleSource,
                )
                .filter(
                  (r) =>
                    (!ruleSeverity || String(r.severity) === ruleSeverity) &&
                    `${r.name} ${r.code}`
                      .toLowerCase()
                      .includes(ruleSearch.toLowerCase().trim()),
                )
                .map((r) => (
                  <div className="type-row rule-row" key={r.code}>
                    <div>
                      <strong>{r.name}</strong>
                      <p>
                        {r.source} · {r.code} · Severity {r.severity}
                        {r.threshold
                          ? ` · ${r.threshold}/${r.window_seconds}s`
                          : ""}
                      </p>
                      <p className="muted">{ruleDeployment(r.verification)}</p>
                      {r.verification?.last_alert ? (
                        <p>
                          <button
                            onClick={() =>
                              setSelectedAlert(
                                r.verification!.last_alert!.alert_id,
                              )
                            }
                          >
                            Xem bằng chứng #{r.verification.last_alert.alert_id}
                          </button>
                          <small>
                            {" "}
                            Đã lưu lúc{" "}
                            {new Date(
                              r.verification.last_alert.ingested_at,
                            ).toLocaleString("vi-VN")}
                            . Đây là lịch sử, không xác nhận bản triển khai hiện
                            tại đã qua kiểm thử.
                          </small>
                        </p>
                      ) : (
                        <small>
                          {r.verification?.evidence_available
                            ? "Chưa có cảnh báo đối chiếu được mã rule trong DB; không đồng nghĩa rule bị lỗi."
                            : "Chưa tải được bằng chứng từ DB."}
                        </small>
                      )}
                    </div>
                    <span className="badge">
                      {r.auto_block_eligible
                        ? "Cho phép auto-block"
                        : "Chỉ cảnh báo"}
                    </span>
                  </div>
                ))}
            </div>
          </section>
        )}
        {tab === "status" && (
          <>
            <section className="panel">
              <h2>
                <Icon name="status" />
                Dịch vụ
              </h2>
              <div className="service-summary">
                {[
                  [
                    "Database",
                    health?.database,
                    "Kết nối được",
                    "Chưa sẵn sàng",
                  ],
                  ["Firewall", health?.firewall, "Đọc được", "Chưa sẵn sàng"],
                  [
                    "DB / firewall",
                    health?.firewall_in_sync,
                    "Đồng bộ",
                    "Chưa đồng bộ",
                  ],
                ].map(([label, ready, yes, no]) => (
                  <div className="service-item" key={String(label)}>
                    <span>{label}</span>
                    <span className={`badge ${ready ? "good" : "warn"}`}>
                      {ready ? yes : no}
                    </span>
                  </div>
                ))}
              </div>
              <p className="muted">
                Watcher chỉ xác nhận khả năng đọc log; không xác nhận tiến trình
                Nginx/Suricata/Student Web hoặc đường truyền RELP đang hoạt
                động. Không có cảnh báo mới có thể là bình thường.
              </p>
              <article className="panel">
                <h3>Đường truyền Student Audit</h3>
                <p>
                  Web VM → RELP receiver → file local → Rust ingest → DB →
                  Dashboard
                </p>
                <dl className="detail-fields">
                  <div>
                    <dt>Sender trên Web VM</dt>
                    <dd>
                      Chưa xác minh từ host; kiểm tra pbl4-audit-sender.service
                      trên VM.
                    </dd>
                  </div>
                  <div>
                    <dt>Receiver trên host</dt>
                    <dd>
                      {health?.operations?.receiver
                        ? `${health.operations.receiver.active} / ${health.operations.receiver.sub}`
                        : "Chưa có mẫu kiểm tra"}
                    </dd>
                  </div>
                  <div>
                    <dt>Sensor Suricata trên host</dt>
                    <dd>
                      {health?.operations?.suricata
                        ? `${health.operations.suricata.active} / ${health.operations.suricata.sub}`
                        : "Chưa có mẫu kiểm tra"}
                    </dd>
                  </div>
                  <div>
                    <dt>Mẫu kiểm tra dịch vụ</dt>
                    <dd>
                      {health?.operations?.sampled_at
                        ? new Date(health.operations.sampled_at).toLocaleString(
                            "vi-VN",
                          )
                        : "Chưa có"}
                    </dd>
                  </div>
                  <div>
                    <dt>Lưu audit đầy đủ</dt>
                    <dd>
                      {health?.dataset_collection == null
                        ? "Chưa xác định"
                        : health.dataset_collection
                          ? "Đang bật"
                          : "Đang tắt — mốc DB có thể là lịch sử"}
                    </dd>
                  </div>
                </dl>
                <p className="muted">
                  Service active không chứng minh kết nối RELP hay dữ liệu đầu
                  cuối đang hoạt động. Không thực hiện SSH hoặc restart dịch vụ
                  từ dashboard.
                </p>
              </article>
              <div className="source-health-grid">
                {["NGINX", "SURICATA", "STUDENT_AUDIT"].map((name) => {
                  const watcher = health?.watchers[name];
                  const collection = health?.collection?.[name];
                  const time = (value: string | null | undefined) =>
                    value
                      ? new Date(value).toLocaleString("vi-VN", {
                          hour12: false,
                        })
                      : "Chưa ghi nhận";
                  return (
                    <article
                      className={`panel source-health source-${name}`}
                      key={name}
                    >
                      <h3 className="source-label">
                        {name === "STUDENT_AUDIT"
                          ? "Student Audit — Tầng ứng dụng"
                          : name}
                      </h3>
                      <p
                        className={`badge ${watcher?.state === "error" ? "danger" : watcher?.state === "watching" ? "good" : "warn"}`}
                      >
                        {watcher?.state === "error"
                          ? "Lỗi đọc / xử lý nguồn log"
                          : watcher?.state === "watching"
                            ? "Đọc log thành công"
                            : name === "STUDENT_AUDIT" && health && !watcher
                              ? "Chưa cấu hình nguồn log"
                              : "Chưa có kết quả kiểm tra"}
                      </p>
                      {name === "STUDENT_AUDIT" && (
                        <p className="muted">
                          {health && !watcher
                            ? "Backend chưa có watcher Student Audit. Kiểm tra STUDENT_AUDIT_LOG_PATH."
                            : "Theo dõi file audit local mà backend đọc. Đọc được file không chứng minh Web VM đang gửi log mới qua RELP."}
                        </p>
                      )}
                      {watcher?.error && (
                        <p className="error">{watcher.error}</p>
                      )}
                      <p role="status">
                        {freshness(watcher?.last_data_at, health?.checked_at)}
                      </p>
                      <p className="muted">
                        Im lặng không đồng nghĩa mất kết nối. Tạo một request
                        kiểm thử rồi đối chiếu mốc nhận và lưu dữ liệu.
                      </p>
                      <dl className="detail-fields">
                        <div>
                          <dt>Lần lưu sự kiện vào DB</dt>
                          <dd>{time(collection?.last_ingested_at)}</dd>
                        </div>
                        <div>
                          <dt>Thời gian sự kiện vừa lưu</dt>
                          <dd>{time(collection?.last_ingested_event_at)}</dd>
                        </div>
                        <div>
                          <dt>Lần đọc thành công</dt>
                          <dd>{time(watcher?.last_success_at)}</dd>
                        </div>
                        <div>
                          <dt>Lần thấy dữ liệu mới</dt>
                          <dd>{time(watcher?.last_data_at)}</dd>
                        </div>
                        <div>
                          <dt>Lần lưu cảnh báo</dt>
                          <dd>{time(collection?.last_alert_at)}</dd>
                        </div>
                        <div>
                          <dt>Log còn chờ</dt>
                          <dd>
                            {watcher?.pending_bytes == null
                              ? "Chưa xác định"
                              : `${fmt(watcher.pending_bytes)} byte`}
                          </dd>
                        </div>
                        <div>
                          <dt>Dòng sai định dạng</dt>
                          <dd>
                            {collection
                              ? fmt(collection.error_count)
                              : "Chưa tải được"}
                          </dd>
                        </div>
                        <div>
                          <dt>Lỗi phân tích gần nhất</dt>
                          <dd>
                            {collection?.last_error ? (
                              <>
                                {time(collection.last_error.at)}
                                <br />
                                {collection.last_error.reason}
                              </>
                            ) : collection ? (
                              "Chưa ghi nhận"
                            ) : (
                              "Chưa tải được"
                            )}
                          </dd>
                        </div>
                      </dl>
                      {!watcher?.last_data_at &&
                        watcher?.state === "watching" && (
                          <p className="muted">
                            Đọc được file nhưng chưa quan sát thấy dữ liệu trong
                            phiên backend này.
                          </p>
                        )}
                      <p className="muted">
                        Mốc đọc và nhận dữ liệu tính từ lần khởi động backend;
                        dữ liệu sẵn có khi mở file cũng được tính là lần quan
                        sát. Cảnh báo và lỗi lấy từ lịch sử DB. Byte chờ gồm cả
                        dòng chưa kết thúc, không gồm file .gz.
                      </p>
                    </article>
                  );
                })}
              </div>
            </section>
            <section className="panel">
              <h2>Tài nguyên máy chạy backend</h2>
              <p>
                Máy:{" "}
                <strong>{stats?.system.hostname ?? "Chưa xác định"}</strong> ·
                Interface:{" "}
                <strong>{stats?.system.interface ?? "Chưa xác định"}</strong>
              </p>
              <p className="muted">
                Số liệu của môi trường chạy backend, không mặc nhiên là Security
                VM. Nếu chạy trong container, một số số liệu có thể thuộc
                container hoặc host tùy cách triển khai.
              </p>
              <p className="muted">
                Mẫu mạng/đĩa:{" "}
                {stats?.system.sampled_at
                  ? new Date(stats.system.sampled_at).toLocaleString("vi-VN", {
                      hour12: false,
                    })
                  : "Đang chờ mẫu đầu tiên"}{" "}
                · Dữ liệu hiện tại, không theo bộ lọc thời gian Tổng quan.
              </p>
              {stats?.system.network_error && (
                <p className="error">
                  {stats.system.network_error}. Kiểm tra ATTACKER_IFACE.
                </p>
              )}
              {stats?.system.disk_error && (
                <p className="error">{stats.system.disk_error}</p>
              )}
              <div className="cards">
                <article>
                  <p>Load average 1 phút</p>
                  <strong>{fmt(stats?.system.load_average_1m)}</strong>
                  <small>Không phải phần trăm CPU</small>
                </article>
                <article>
                  <p>Bộ nhớ đang dùng</p>
                  <strong>{fmt(stats?.system.memory_percent, "%")}</strong>
                </article>
                <article>
                  <p>RX — tốc độ nhận</p>
                  <strong>
                    {stats?.system.rx_bytes_per_second == null
                      ? "Chưa đo được"
                      : `${fmt(stats.system.rx_bytes_per_second / 1024)} KiB/s`}
                  </strong>
                </article>
                <article>
                  <p>TX — tốc độ gửi</p>
                  <strong>
                    {stats?.system.tx_bytes_per_second == null
                      ? "Chưa đo được"
                      : `${fmt(stats.system.tx_bytes_per_second / 1024)} KiB/s`}
                  </strong>
                </article>
                <article>
                  <p>RX tích lũy</p>
                  <strong>
                    {stats?.system.interface_rx_bytes == null
                      ? "—"
                      : `${fmt(stats.system.interface_rx_bytes / 1048576)} MiB`}
                  </strong>
                  <small>Từ lúc interface khởi động/reset</small>
                </article>
                <article>
                  <p>TX tích lũy</p>
                  <strong>
                    {stats?.system.interface_tx_bytes == null
                      ? "—"
                      : `${fmt(stats.system.interface_tx_bytes / 1048576)} MiB`}
                  </strong>
                  <small>Từ lúc interface khởi động/reset</small>
                </article>
                <article>
                  <p>Đĩa khả dụng: {stats?.system.disk_path ?? "—"}</p>
                  <strong>
                    {stats?.system.disk
                      ? `${fmt(stats.system.disk.available_bytes / 1073741824)} GiB`
                      : "Chưa đo được"}
                  </strong>
                  <small>
                    Tổng:{" "}
                    {stats?.system.disk
                      ? `${fmt(stats.system.disk.total_bytes / 1073741824)} GiB`
                      : "—"}
                  </small>
                </article>
                <article>
                  <p>Kết nối TCP established</p>
                  <strong>
                    {fmt(stats?.system.established_tcp_connections)}
                  </strong>
                </article>
              </div>
              <p className="muted">
                RX/TX là trung bình giữa hai mẫu liên tiếp; cần hai mẫu để tính,
                reset bộ đếm sẽ chờ mẫu mới. Đĩa là filesystem chứa đường dẫn
                trên; không đại diện dung lượng DB nếu DB ở máy hoặc volume
                khác.
              </p>
              <p>
                Lần thấy log mới:{" "}
                {["NGINX", "SURICATA", "STUDENT_AUDIT"]
                  .map(
                    (name) =>
                      `${name}: ${health?.watchers[name]?.last_data_at ? new Date(health.watchers[name].last_data_at!).toLocaleString("vi-VN", { hour12: false }) : "chưa ghi nhận"}`,
                  )
                  .join(" · ")}
              </p>
              <p className="muted">
                Dashboard tải thành công chỉ xác nhận lấy được API; không có
                nghĩa nguồn log vừa nhận dữ liệu mới.
              </p>
            </section>
          </>
        )}
        {selectedAlert !== null && (
          <AlertDetail
            id={selectedAlert}
            admin={admin}
            onChanged={() => void refresh()}
            api={api}
            onBlock={
              admin
                ? async (alert) => {
                    if (!alert.src_ip) return;
                    const reason = window.prompt(
                      `Lý do chặn ${alert.src_ip} từ cảnh báo #${alert.id}:`,
                      alert.rule_name,
                    );
                    if (!reason?.trim()) return;
                    const result = await api("/api/blocked-ips", {
                      method: "POST",
                      body: JSON.stringify({
                        ip: alert.src_ip,
                        reason,
                        event_id: alert.id,
                      }),
                    });
                    setNotice(
                      `Yêu cầu #${result.id} đang chờ xử lý; xem Nhật ký thao tác.`,
                    );
                    await refresh();
                  }
                : undefined
            }
            onClose={() => setSelectedAlert(null)}
            onSelect={setSelectedAlert}
            onAudit={(id) => {
              setSelectedAlert(null);
              setAudit([]);
              setAuditEvent(id);
              setTab("audit");
            }}
          />
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
