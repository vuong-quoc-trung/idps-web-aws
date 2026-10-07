/**
 * AccessLogsTab — Audit Trail & Access Log Explorer
 * Connects to GET /api/access-logs and GET /api/access-logs/{id}
 * Displays HTTP methods, latency, response status, client IP, and inspection modal.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import Modal from '../Modal';
import { accessLogApi, type AccessLogSummary } from '../../api/accessLogApi';
import type { Page } from '../../api/client';
import './AccessLogsTab.css';

/* ---- SVG Micro-icons ---- */
const IcoSearch = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);

const IcoRefresh = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M12.5 7A5.5 5.5 0 1111 3.5L12.5 2M12.5 5.5V2H9" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const IcoEye = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M1.5 7S4 2.5 7 2.5 12.5 7 12.5 7 10 11.5 7 11.5 1.5 7 1.5 7z" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="7" cy="7" r="2" stroke="currentColor" strokeWidth="1.25"/>
  </svg>
);

const IcoCopy = () => (
  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
    <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M4 4V2.5A1.5 1.5 0 012.5 1H10" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);

const IcoCheck = () => (
  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
    <path d="M2 7.5L5.5 11 12 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const IcoShieldLog = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
    <path d="M12 2L3 6v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V6l-9-4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

function formatTimestamp(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return isoString;
  }
}

function methodBadgeClass(method: string): string {
  switch (method?.toUpperCase()) {
    case 'GET': return 'method-get';
    case 'POST': return 'method-post';
    case 'PUT': return 'method-put';
    case 'PATCH': return 'method-patch';
    case 'DELETE': return 'method-delete';
    default: return 'method-other';
  }
}

function statusBadgeClass(status: number): string {
  if (status >= 200 && status < 300) return 'status-2xx';
  if (status >= 300 && status < 400) return 'status-3xx';
  if (status >= 400 && status < 500) return 'status-4xx';
  return 'status-5xx';
}

function latencyClass(ms?: number | null): string {
  if (ms == null) return '';
  if (ms < 100) return 'latency-fast';
  if (ms < 400) return 'latency-medium';
  return 'latency-slow';
}

export default function AccessLogsTab() {
  const [data, setData] = useState<Page<AccessLogSummary> | null>(null);
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [methodFilter, setMethodFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Detail Modal
  const [selectedLog, setSelectedLog] = useState<AccessLogSummary | null>(null);
  const [copied, setCopied] = useState(false);

  const loadLogs = useCallback(async (p: number, s: number) => {
    setLoading(true);
    setErr(null);
    try {
      const res = await accessLogApi.list({ page: p, size: s });
      setData(res);
      setPage(p);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Không thể tải nhật ký truy cập');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs(0, size);
  }, [loadLogs, size]);

  // Client-side filtering on current page items
  const filteredLogs = useMemo(() => {
    if (!data) return [];
    return data.content.filter(log => {
      const q = search.trim().toLowerCase();
      const matchSearch =
        !q ||
        log.path.toLowerCase().includes(q) ||
        (log.clientIp ?? '').toLowerCase().includes(q) ||
        (log.action ?? '').toLowerCase().includes(q) ||
        (log.userId != null && String(log.userId).includes(q));

      const matchMethod = !methodFilter || log.method.toUpperCase() === methodFilter;

      let matchStatus = true;
      if (statusFilter === '2xx') matchStatus = log.statusCode >= 200 && log.statusCode < 300;
      else if (statusFilter === '3xx') matchStatus = log.statusCode >= 300 && log.statusCode < 400;
      else if (statusFilter === '4xx') matchStatus = log.statusCode >= 400 && log.statusCode < 500;
      else if (statusFilter === '5xx') matchStatus = log.statusCode >= 500;

      return matchSearch && matchMethod && matchStatus;
    });
  }, [data, search, methodFilter, statusFilter]);

  // Derived stats
  const totalElements = data?.totalElements ?? 0;
  const currentLogs = data?.content ?? [];
  const successCount = currentLogs.filter(l => l.statusCode >= 200 && l.statusCode < 300).length;
  const errorCount = currentLogs.filter(l => l.statusCode >= 400).length;
  const avgLatency = currentLogs.length > 0
    ? Math.round(
        currentLogs.reduce((acc, l) => acc + (l.requestTimeMs ?? 0), 0) / currentLogs.length,
      )
    : 0;

  function copyLogJson() {
    if (!selectedLog) return;
    navigator.clipboard.writeText(JSON.stringify(selectedLog, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="access-logs-container">
      {/* Header */}
      <div className="logs-header-row">
        <div className="logs-header-title">
          <h2>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" style={{ verticalAlign: 'middle', marginRight: 8 }}>
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Nhật ký truy cập hệ thống (Audit Trail)
          </h2>
          <p>Lịch sử các yêu cầu HTTP và kiểm toán truy cập bảo mật được ghi nhận qua REST API.</p>
        </div>
        <div className="logs-header-actions">
          <button
            className={`btn-refresh-logs ${loading ? 'spinning' : ''}`}
            onClick={() => loadLogs(page, size)}
            disabled={loading}
            title="Làm mới danh sách"
          >
            <IcoRefresh/>
            Làm mới
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="logs-stats-bar">
        <div className="logs-stat-card">
          <div className="logs-stat-icon blue">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12M2 8h12M2 13h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="logs-stat-content">
            <span className="logs-stat-label">Tổng bản ghi</span>
            <span className="logs-stat-val">{totalElements.toLocaleString()}</span>
          </div>
        </div>

        <div className="logs-stat-card">
          <div className="logs-stat-icon green">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <path d="M3 8.5l3.5 3.5 6.5-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div className="logs-stat-content">
            <span className="logs-stat-label">Thành công (2xx)</span>
            <span className="logs-stat-val">{successCount}</span>
          </div>
        </div>

        <div className="logs-stat-card">
          <div className="logs-stat-icon amber">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 5v3.5l2.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="logs-stat-content">
            <span className="logs-stat-label">Độ trễ trung bình</span>
            <span className="logs-stat-val">{avgLatency} ms</span>
          </div>
        </div>

        <div className="logs-stat-card">
          <div className="logs-stat-icon purple">
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <path d="M8 2l6 11H2L8 2z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
              <path d="M8 7v2.5M8 11.5h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="logs-stat-content">
            <span className="logs-stat-label">Lỗi (4xx / 5xx)</span>
            <span className="logs-stat-val" style={{ color: errorCount > 0 ? '#f85149' : 'inherit' }}>
              {errorCount}
            </span>
          </div>
        </div>
      </div>

      {/* Filter controls */}
      <div className="logs-controls">
        <div className="logs-search-wrap">
          <span className="logs-search-icon"><IcoSearch/></span>
          <input
            className="logs-search-input"
            type="text"
            placeholder="Tìm theo đường dẫn path, IP client, action..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <select
          className="logs-select"
          value={methodFilter}
          onChange={e => setMethodFilter(e.target.value)}
          aria-label="Lọc theo phương thức HTTP"
        >
          <option value="">Tất cả phương thức</option>
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="PATCH">PATCH</option>
          <option value="DELETE">DELETE</option>
        </select>

        <select
          className="logs-select"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          aria-label="Lọc theo mã trạng thái"
        >
          <option value="">Tất cả trạng thái</option>
          <option value="2xx">2xx Thành công</option>
          <option value="3xx">3xx Chuyển hướng</option>
          <option value="4xx">4xx Lỗi client</option>
          <option value="5xx">5xx Lỗi server</option>
        </select>

        <select
          className="logs-select"
          value={size}
          onChange={e => setSize(Number(e.target.value))}
          aria-label="Số bản ghi mỗi trang"
        >
          <option value={10}>10 / trang</option>
          <option value={20}>20 / trang</option>
          <option value={50}>50 / trang</option>
        </select>
      </div>

      {/* Table Card */}
      <div className="logs-table-card">
        {loading && !data ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="spinner" style={{ margin: '0 auto 12px', display: 'block', width: 24, height: 24, borderWidth: 2.5 }}/>
            Đang tải dữ liệu nhật ký truy cập...
          </div>
        ) : err ? (
          <div className="logs-empty-state">
            <div className="logs-empty-icon" style={{ color: 'var(--text-error)' }}>
              <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </div>
            <h3 className="logs-empty-title">Lỗi kết nối nhật ký</h3>
            <p className="logs-empty-desc">{err}</p>
            <button className="btn-refresh-logs" style={{ marginTop: 8 }} onClick={() => loadLogs(page, size)}>
              Thử lại
            </button>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="logs-empty-state">
            <div className="logs-empty-icon">
              <IcoShieldLog/>
            </div>
            <h3 className="logs-empty-title">Chưa có bản ghi nhật ký</h3>
            <p className="logs-empty-desc">
              {search || methodFilter || statusFilter
                ? 'Không tìm thấy nhật ký truy cập nào khớp với bộ lọc hiện tại.'
                : 'Hệ thống lưu trữ lịch sử qua endpoint /api/access-logs. Hiện tại chưa có yêu cầu nào được ghi nhận vào cơ sở dữ liệu.'}
            </p>
            {(search || methodFilter || statusFilter) && (
              <button
                className="btn-refresh-logs"
                style={{ marginTop: 8 }}
                onClick={() => {
                  setSearch('');
                  setMethodFilter('');
                  setStatusFilter('');
                }}
              >
                Xóa bộ lọc
              </button>
            )}
          </div>
        ) : (
          <div className="logs-table-wrap">
            <table className="logs-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Thời gian</th>
                  <th>Phương thức</th>
                  <th>Đường dẫn API</th>
                  <th>Trạng thái</th>
                  <th>Độ trễ</th>
                  <th>IP Client</th>
                  <th>User ID / Action</th>
                  <th style={{ textAlign: 'center', width: 60 }}>Chi tiết</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map(log => (
                  <tr key={log.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                      #{log.id}
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                      {formatTimestamp(log.createdAt)}
                    </td>
                    <td>
                      <span className={`method-badge ${methodBadgeClass(log.method)}`}>
                        {log.method}
                      </span>
                    </td>
                    <td>
                      <span className="log-path-code" title={log.path}>
                        {log.path}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${statusBadgeClass(log.statusCode)}`}>
                        {log.statusCode}
                      </span>
                    </td>
                    <td>
                      <span className={`latency-badge ${latencyClass(log.requestTimeMs)}`}>
                        {log.requestTimeMs != null ? `${log.requestTimeMs} ms` : '—'}
                      </span>
                    </td>
                    <td>
                      <span className="log-ip-code">
                        {log.clientIp ?? '—'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {log.userId != null && (
                          <span style={{ fontSize: 11, color: 'var(--text-primary)' }}>
                            User #{log.userId}
                          </span>
                        )}
                        {log.action && (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            {log.action}
                          </span>
                        )}
                        {log.userId == null && !log.action && '—'}
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        className="btn-view-log"
                        onClick={() => setSelectedLog(log)}
                        title="Xem chi tiết bản ghi"
                      >
                        <IcoEye/>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination bar */}
        {data && data.totalPages > 1 && (
          <div className="logs-pagination">
            <span>
              Trang {page + 1} / {data.totalPages} ({totalElements.toLocaleString()} bản ghi)
            </span>
            <div className="logs-page-btns">
              <button
                className="btn-page-nav"
                onClick={() => loadLogs(page - 1, size)}
                disabled={page <= 0 || loading}
              >
                Trang trước
              </button>
              <button
                className="btn-page-nav"
                onClick={() => loadLogs(page + 1, size)}
                disabled={page >= data.totalPages - 1 || loading}
              >
                Trang kế
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Log Detail Modal */}
      {selectedLog && (
        <Modal
          open={!!selectedLog}
          title={`Chi tiết nhật ký truy cập #${selectedLog.id}`}
          size="md"
          onClose={() => setSelectedLog(null)}
          footer={
            <button className="btn-cancel" onClick={() => setSelectedLog(null)}>
              Đóng
            </button>
          }
        >
          <div className="log-detail-grid">
            <div className="log-detail-item">
              <span className="log-detail-label">Phương thức HTTP</span>
              <span className="log-detail-value">
                <span className={`method-badge ${methodBadgeClass(selectedLog.method)}`}>
                  {selectedLog.method}
                </span>
              </span>
            </div>

            <div className="log-detail-item">
              <span className="log-detail-label">Mã phản hồi</span>
              <span className="log-detail-value">
                <span className={`status-badge ${statusBadgeClass(selectedLog.statusCode)}`}>
                  {selectedLog.statusCode}
                </span>
              </span>
            </div>

            <div className="log-detail-item">
              <span className="log-detail-label">Thời điểm ghi nhận</span>
              <span className="log-detail-value">{formatTimestamp(selectedLog.createdAt)}</span>
            </div>

            <div className="log-detail-item">
              <span className="log-detail-label">Thời gian xử lý</span>
              <span className={`log-detail-value mono ${latencyClass(selectedLog.requestTimeMs)}`}>
                {selectedLog.requestTimeMs != null ? `${selectedLog.requestTimeMs} ms` : '—'}
              </span>
            </div>

            <div className="log-detail-item" style={{ gridColumn: 'span 2' }}>
              <span className="log-detail-label">Đường dẫn yêu cầu (Request Path)</span>
              <span className="log-detail-value mono">{selectedLog.path}</span>
            </div>

            <div className="log-detail-item">
              <span className="log-detail-label">Địa chỉ IP Client</span>
              <span className="log-detail-value mono">{selectedLog.clientIp ?? '—'}</span>
            </div>

            <div className="log-detail-item">
              <span className="log-detail-label">User ID liên quan</span>
              <span className="log-detail-value">{selectedLog.userId != null ? `User #${selectedLog.userId}` : 'Khách vãng lai / N/A'}</span>
            </div>

            {selectedLog.action && (
              <div className="log-detail-item" style={{ gridColumn: 'span 2' }}>
                <span className="log-detail-label">Hành động kiểm toán (Action)</span>
                <span className="log-detail-value">{selectedLog.action}</span>
              </div>
            )}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Payload JSON chi tiết
              </span>
              <button
                className="btn-copy-json"
                onClick={copyLogJson}
                title="Sao chép nội dung JSON"
                style={{ position: 'static', top: 'auto', right: 'auto' }}
              >
                {copied ? <><IcoCheck/> Đã chép</> : <><IcoCopy/> Chép JSON</>}
              </button>
            </div>
            <pre className="log-json-viewer">
              {JSON.stringify(selectedLog, null, 2)}
            </pre>
          </div>
        </Modal>
      )}
    </div>
  );
}
