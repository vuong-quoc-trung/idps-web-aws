/**
 * UsersPage — ADMIN-only account management
 * Features:
 *   - Paginated user list (all roles)
 *   - Filter by role / enabled status (client-side)
 *   - Create ADMIN or STAFF account (shows one-time activation token)
 *   - Enable / disable account toggle
 *   - Re-issue activation token for pending (passwordSetupRequired) accounts
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppHeader from '../components/AppHeader';
import Modal from '../components/Modal';
import { useAuth } from '../contexts/AuthContext';
import { userApi } from '../api/userApi';
import type { UserSummary, UserDetail, CreateUserPayload } from '../api/userApi';
import type { Page } from '../api/client';
import AccessLogsTab from '../components/admin/AccessLogsTab';
import './UsersPage.css';

/* ---- SVG micro-icons ---- */
const IcoEye = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M1.5 7S4 2.5 7 2.5 12.5 7 12.5 7 10 11.5 7 11.5 1.5 7 1.5z" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="7" cy="7" r="2" stroke="currentColor" strokeWidth="1.25"/>
  </svg>
);
const IcoUsers = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
    <circle cx="7" cy="6" r="3" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M1 18c0-3.314 2.686-6 6-6s6 2.686 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M14 9a3 3 0 100-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M17 18c0-2.761-1.343-5.22-3.5-6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);
const IcoPlus = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);
const IcoCheck = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M2 7.5L5.5 11 12 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoLock = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <rect x="2.5" y="6" width="9" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M4.5 6V4.5a2.5 2.5 0 015 0V6" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoUnlock = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <rect x="2.5" y="6" width="9" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M4.5 6V4.5a2.5 2.5 0 015 0" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
    <circle cx="7" cy="9.25" r="1" fill="currentColor"/>
  </svg>
);
const IcoKey = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <circle cx="5" cy="6" r="3" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M7.5 7.5l4 4M9.5 9.5l1.5-1.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoCopy = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M4 4V2.5A1.5 1.5 0 012.5 1H10" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoSearch = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoWarn = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M7 1.5v4M7 8.5h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M2.5 12.5h9L7 1.5l-4.5 11z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
);
const IcoInfo = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M7 5v3M7 9.5h.01" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoChevLeft = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M7.5 2L4 6l3.5 4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoChevRight = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M4.5 2L8 6l-3.5 4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoShieldLog = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
    <path d="M12 2L3 6v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V6l-9-4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

/* ---- Helpers ---- */
function roleAvatarInitial(username: string) {
  return username.slice(0, 2).toUpperCase();
}

function roleClass(role: string) {
  return role.toLowerCase();
}

const ROLE_LABEL: Record<string, string> = { ADMIN: 'Admin', STAFF: 'Staff', STUDENT: 'Student' };

/* ============================================================
   CREATE USER MODAL
   ============================================================ */
function CreateUserModal({ open, onClose, onCreated }: {
  open: boolean;
  onClose: () => void;
  onCreated: (token: string, username: string) => void;
}) {
  const [form, setForm] = useState<CreateUserPayload>({ username: '', role: 'STAFF' });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) { setForm({ username: '', role: 'STAFF' }); setErr(null); }
  }, [open]);

  async function handleSubmit() {
    if (!form.username.trim()) { setErr('Tên đăng nhập là bắt buộc'); return; }
    setSubmitting(true); setErr(null);
    try {
      const res = await userApi.create({ username: form.username.trim(), role: form.role });
      onCreated(res.activationToken, res.user.username);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi tạo tài khoản');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} title="Tạo tài khoản mới" size="sm" onClose={onClose}
      footer={<>
        <button className="btn-cancel-users" onClick={onClose} disabled={submitting}>Hủy</button>
        <button className="btn-submit-users" onClick={handleSubmit} disabled={submitting}>
          {submitting && <span className="spinner-u sm"/>}
          {submitting ? 'Đang tạo...' : <><IcoPlus/> Tạo tài khoản</>}
        </button>
      </>}
    >
      {err && <div className="users-alert-error" style={{ marginBottom: 12 }}><IcoInfo/>{err}</div>}
      <div className="users-form">
        <div className="users-form-group">
          <label className="users-form-label">Tên đăng nhập <span className="required">*</span></label>
          <input
            id="create-user-username"
            className="users-form-input"
            placeholder="VD: nv.thanhtu"
            autoComplete="off"
            value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          />
          <span className="users-form-hint">Không thể thay đổi sau khi tạo.</span>
        </div>
        <div className="users-form-group">
          <label className="users-form-label">Vai trò <span className="required">*</span></label>
          <select
            id="create-user-role"
            className="users-form-select"
            value={form.role}
            onChange={e => setForm(f => ({ ...f, role: e.target.value as 'ADMIN' | 'STAFF' }))}
          >
            <option value="STAFF">Staff — Quản lý sinh viên</option>
            <option value="ADMIN">Admin — Toàn quyền hệ thống</option>
          </select>
        </div>
        <div className="token-warning">
          <IcoWarn/>
          <span>
            Tài khoản sẽ được tạo với trạng thái <strong>chờ kích hoạt</strong>. Token kích hoạt
            sẽ hiện ngay sau khi tạo — chỉ hiển thị một lần. Chuyển token cho người dùng qua
            kênh đã xác minh.
          </span>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   TOKEN DISPLAY MODAL (after create or reissue)
   ============================================================ */
function TokenDisplayModal({ open, onClose, token, username, isReissue }: {
  open: boolean; onClose: () => void;
  token: string; username: string; isReissue?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(token).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const activateUrl = `${window.location.origin}/activate?token=${encodeURIComponent(token)}`;

  return (
    <Modal open={open} title={isReissue ? 'Token kích hoạt mới' : 'Tài khoản đã được tạo'} size="md" onClose={onClose}
      footer={<button className="btn-submit-users" onClick={onClose}>Đóng</button>}
    >
      <div className="token-display-box">
        <div className="token-display-header">
          <IcoCheck/>
          {isReissue
            ? `Token mới đã được cấp cho @${username}`
            : `Tài khoản @${username} đã được tạo thành công`}
        </div>

        <div className="users-form-group">
          <label className="users-form-label">Token kích hoạt (1 lần dùng, hạn 24h)</label>
          <div className="token-value-wrap">
            <div className="token-value">{token}</div>
            <button
              className="token-copy-btn"
              title={copied ? 'Đã sao chép!' : 'Sao chép token'}
              onClick={copy}
              id="copy-token-btn"
            >
              {copied ? <IcoCheck/> : <IcoCopy/>}
            </button>
          </div>
        </div>

        <div className="users-form-group">
          <label className="users-form-label">Link kích hoạt trực tiếp</label>
          <div className="token-value-wrap">
            <div className="token-value" style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
              {activateUrl}
            </div>
            <button
              className="token-copy-btn"
              title="Sao chép link"
              onClick={() => navigator.clipboard.writeText(activateUrl)}
              id="copy-activate-link-btn"
            >
              <IcoCopy/>
            </button>
          </div>
        </div>

        <div className="token-warning">
          <IcoWarn/>
          <span>
            Token chỉ hiển thị <strong>một lần duy nhất</strong>. Hãy sao chép và chuyển cho
            người dùng qua kênh đã xác minh. Token cũ (nếu có) sẽ bị vô hiệu hóa.
          </span>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   CONFIRM TOGGLE MODAL
   ============================================================ */
function ConfirmToggleModal({ open, onClose, onConfirm, user, loading, err }: {
  open: boolean; onClose: () => void; onConfirm: () => void;
  user: UserSummary | null; loading: boolean; err: string | null;
}) {
  if (!user) return null;
  const enabling = !user.enabled;
  return (
    <Modal open={open} title={enabling ? 'Bật tài khoản' : 'Tắt tài khoản'} size="sm" onClose={onClose}
      footer={<>
        <button className="btn-cancel-users" onClick={onClose} disabled={loading}>Hủy</button>
        <button
          className={enabling ? 'btn-submit-users' : 'btn-danger-users'}
          onClick={onConfirm}
          disabled={loading}
          id={enabling ? 'confirm-enable-btn' : 'confirm-disable-btn'}
        >
          {loading && <span className="spinner-u sm" style={{ borderTopColor: enabling ? '#fff' : 'var(--text-error)' }}/>}
          {enabling ? 'Bật tài khoản' : 'Tắt tài khoản'}
        </button>
      </>}
    >
      <div className="confirm-body">
        <div className={`confirm-icon-wrap ${enabling ? 'info' : 'warn'}`}>
          {enabling ? <IcoUnlock/> : <IcoLock/>}
        </div>
        <h3>{enabling ? 'Bật tài khoản này?' : 'Tắt tài khoản này?'}</h3>
        <p>
          Tài khoản <strong>@{user.username}</strong> ({ROLE_LABEL[user.role]}) sẽ{' '}
          {enabling
            ? 'được phép đăng nhập trở lại.'
            : 'bị khóa và không thể đăng nhập. Session hiện tại sẽ bị từ chối ở request tiếp theo.'}
        </p>
        {err && <div className="users-alert-error" style={{ marginTop: 12, textAlign: 'left' }}><IcoInfo/>{err}</div>}
      </div>
    </Modal>
  );
}

/* ============================================================
   CONFIRM REISSUE TOKEN MODAL
   ============================================================ */
function ConfirmReissueModal({ open, onClose, onConfirm, user, loading, err }: {
  open: boolean; onClose: () => void; onConfirm: () => void;
  user: UserSummary | null; loading: boolean; err: string | null;
}) {
  if (!user) return null;
  return (
    <Modal open={open} title="Cấp lại token kích hoạt" size="sm" onClose={onClose}
      footer={<>
        <button className="btn-cancel-users" onClick={onClose} disabled={loading}>Hủy</button>
        <button className="btn-submit-users" onClick={onConfirm} disabled={loading} id="confirm-reissue-btn">
          {loading && <span className="spinner-u sm"/>}
          <IcoKey/> Cấp lại token
        </button>
      </>}
    >
      <div className="confirm-body">
        <div className="confirm-icon-wrap info">
          <IcoKey/>
        </div>
        <h3>Cấp lại token cho @{user.username}?</h3>
        <p>
          Token kích hoạt cũ (nếu còn) sẽ bị <strong>vô hiệu hóa</strong>. Token mới
          sẽ có hiệu lực trong 24 giờ. Chỉ khả dụng với tài khoản <em>chưa đặt mật khẩu</em>.
        </p>
        {err && <div className="users-alert-error" style={{ marginTop: 12, textAlign: 'left' }}><IcoInfo/>{err}</div>}
      </div>
    </Modal>
  );
}

/* ============================================================
   USER DETAIL MODAL (GET /api/users/{id})
   ============================================================ */
function UserDetailModal({
  userId,
  currentUserId,
  onClose,
  onToggle,
  onReissue,
}: {
  userId: number | null;
  currentUserId?: number;
  onClose: () => void;
  onToggle: (u: UserSummary) => void;
  onReissue: (u: UserSummary) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [detail, setDetail]   = useState<UserDetail | null>(null);
  const [err, setErr]         = useState<string | null>(null);

  useEffect(() => {
    if (!userId) {
      return;
    }
    let active = true;
    setLoading(true);
    setErr(null);
    userApi.get(userId)
      .then(res => { if (active) setDetail(res); })
      .catch(e => { if (active) setErr(e instanceof Error ? e.message : 'Lỗi tải chi tiết người dùng'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [userId]);

  if (!userId) return null;

  return (
    <Modal open={!!userId} title={detail ? `Chi tiết tài khoản: @${detail.username}` : 'Chi tiết tài khoản'} size="md" onClose={onClose}
      footer={<button className="btn-cancel-users" onClick={onClose}>Đóng</button>}
    >
      {loading ? (
        <div style={{ padding: 36, textAlign: 'center', color: 'var(--text-muted)' }}>
          <span className="spinner-u" style={{ margin: '0 auto 8px', display: 'block', width: 22, height: 22 }} />
          Đang tải dữ liệu chi tiết...
        </div>
      ) : err || !detail ? (
        <div className="users-alert-error"><IcoInfo /> {err ?? 'Không tìm thấy người dùng'}</div>
      ) : (
        <div className="user-detail-content">
          <div className="user-detail-header-card">
            <div className={`user-avatar role-${roleClass(detail.role)}`} style={{ width: 44, height: 44, fontSize: 16 }}>
              {roleAvatarInitial(detail.username)}
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 600 }}>@{detail.username}</h3>
              <p style={{ margin: '2px 0 0', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                {detail.fullName ? `${detail.fullName} · ` : ''}ID: #{detail.id}
              </p>
            </div>
          </div>

          <div className="user-detail-grid">
            <div className="user-detail-item">
              <span className="user-detail-label">Vai trò:</span>
              <span className={`role-badge ${roleClass(detail.role)}`}>{ROLE_LABEL[detail.role]}</span>
            </div>
            <div className="user-detail-item">
              <span className="user-detail-label">Trạng thái:</span>
              <span className={`status-badge ${detail.enabled ? 'enabled' : 'disabled'}`}>
                <span className="status-dot" />
                {detail.enabled ? 'Đang hoạt động' : 'Bị vô hiệu hóa'}
              </span>
            </div>
            <div className="user-detail-item">
              <span className="user-detail-label">Mật khẩu:</span>
              <span>
                {detail.passwordSetupRequired ? (
                  <span className="pending-badge"><IcoKey /> Chờ kích hoạt</span>
                ) : (
                  <span style={{ color: 'var(--clr-success-500)', fontWeight: 500 }}>✓ Đã kích hoạt</span>
                )}
              </span>
            </div>
            {detail.studentCode && (
              <div className="user-detail-item">
                <span className="user-detail-label">Mã sinh viên:</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{detail.studentCode}</span>
              </div>
            )}
            {detail.createdAt && (
              <div className="user-detail-item">
                <span className="user-detail-label">Ngày tạo:</span>
                <span style={{ fontSize: 'var(--text-xs)' }}>{new Date(detail.createdAt).toLocaleString('vi-VN')}</span>
              </div>
            )}
            {detail.lastLoginAt && (
              <div className="user-detail-item">
                <span className="user-detail-label">Đăng nhập gần nhất:</span>
                <span style={{ fontSize: 'var(--text-xs)' }}>{new Date(detail.lastLoginAt).toLocaleString('vi-VN')}</span>
              </div>
            )}
          </div>

          {/* Action buttons inside detail */}
          <div className="user-detail-actions">
            {detail.id !== currentUserId && (
              <button
                className={`btn-toggle-action ${detail.enabled ? 'disable' : 'enable'}`}
                onClick={() => { onClose(); onToggle(detail); }}
              >
                {detail.enabled ? <><IcoLock /> Khóa tài khoản</> : <><IcoUnlock /> Bật tài khoản</>}
              </button>
            )}
            {detail.passwordSetupRequired && detail.enabled && (
              <button
                className="btn-reissue-action"
                onClick={() => { onClose(); onReissue(detail); }}
              >
                <IcoKey /> Cấp lại token kích hoạt
              </button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ============================================================
   MAIN PAGE
   ============================================================ */
const PAGE_SIZE = 20;

export default function UsersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') === 'logs' ? 'logs' : 'users';

  const handleTabChange = (t: 'users' | 'logs') => {
    if (t === 'logs') {
      setSearchParams({ tab: 'logs' });
    } else {
      setSearchParams({});
    }
  };

  // ---- Data state ----
  const [data, setData] = useState<Page<UserSummary> | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  // ---- Filters (client-side after fetch) ----
  const [search, setSearch] = useState('');
  const [filterRole, setFilterRole] = useState<string>('');
  const [filterEnabled, setFilterEnabled] = useState<string>('');

  // ---- Modal state ----
  const [showCreate, setShowCreate] = useState(false);
  const [tokenInfo, setTokenInfo] = useState<{ token: string; username: string; isReissue?: boolean } | null>(null);

  const [detailUserId, setDetailUserId] = useState<number | null>(null);
  const [toggleTarget, setToggleTarget] = useState<UserSummary | null>(null);
  const [toggling, setToggling] = useState(false);
  const [toggleErr, setToggleErr] = useState<string | null>(null);

  const [reissueTarget, setReissueTarget] = useState<UserSummary | null>(null);
  const [reissuing, setReissuing] = useState(false);
  const [reissueErr, setReissueErr] = useState<string | null>(null);

  // ---- Guard: ADMIN only ----
  useEffect(() => {
    if (user && user.role !== 'ADMIN') navigate('/', { replace: true });
  }, [user, navigate]);

  // ---- Load users ----
  const load = useCallback(async (p: number) => {
    setLoading(true); setLoadErr(null);
    try {
      const res = await userApi.list({ page: p, size: PAGE_SIZE });
      setData(res);
      setPage(p);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Lỗi tải danh sách');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(0); }, [load]);

  // ---- Client-side filter on loaded page ----
  const filtered = useMemo(() => {
    if (!data) return [];
    return data.content.filter(u => {
      const q = search.toLowerCase();
      const matchSearch = !q || u.username.toLowerCase().includes(q) || (u.fullName ?? '').toLowerCase().includes(q);
      const matchRole = !filterRole || u.role === filterRole;
      const matchEnabled = filterEnabled === '' ? true
        : filterEnabled === 'true' ? u.enabled
        : !u.enabled;
      return matchSearch && matchRole && matchEnabled;
    });
  }, [data, search, filterRole, filterEnabled]);

  // ---- Stats ----
  const allUsers = data?.content ?? [];
  const adminCount = allUsers.filter(u => u.role === 'ADMIN').length;
  const staffCount = allUsers.filter(u => u.role === 'STAFF').length;
  const activeCount = allUsers.filter(u => u.enabled).length;
  const pendingCount = allUsers.filter(u => u.passwordSetupRequired).length;

  // ---- Toggle enable/disable ----
  async function handleToggle() {
    if (!toggleTarget) return;
    setToggling(true); setToggleErr(null);
    try {
      await userApi.setEnabled(toggleTarget.id, !toggleTarget.enabled);
      setToggleTarget(null);
      await load(page);
    } catch (e) {
      setToggleErr(e instanceof Error ? e.message : 'Lỗi cập nhật');
    } finally {
      setToggling(false);
    }
  }

  // ---- Re-issue token ----
  async function handleReissue() {
    if (!reissueTarget) return;
    setReissuing(true); setReissueErr(null);
    try {
      const res = await userApi.reissueToken(reissueTarget.id);
      const username = reissueTarget.username;
      setReissueTarget(null);
      setTokenInfo({ token: res.activationToken, username, isReissue: true });
    } catch (e) {
      setReissueErr(e instanceof Error ? e.message : 'Lỗi cấp token');
    } finally {
      setReissuing(false);
    }
  }

  if (!user) return null;

  return (
    <div className="users-page">
      <AppHeader/>
      <div className="users-inner">

        {/* Page header */}
        <div className="users-page-header">
          <div>
            <div className="users-page-title">
              <div className="users-page-title-icon">
                {activeTab === 'users' ? <IcoUsers/> : <IcoShieldLog/>}
              </div>
              <div>
                <h1>{activeTab === 'users' ? 'Quản trị tài khoản' : 'Nhật ký truy cập hệ thống'}</h1>
                <div className="users-page-subtitle">
                  {activeTab === 'users'
                    ? 'Dành riêng cho ADMIN — quản lý tài khoản và phân quyền hệ thống'
                    : 'Dành riêng cho ADMIN — kiểm toán và theo dõi các yêu cầu bảo mật'}
                </div>
              </div>
            </div>
          </div>
          {activeTab === 'users' && (
            <button
              className="btn-create-user"
              onClick={() => setShowCreate(true)}
              id="open-create-user-modal-btn"
            >
              <IcoPlus/> Tạo tài khoản
            </button>
          )}
        </div>

        {/* Admin Navigation Tabs */}
        <div className="admin-tabs" role="tablist" aria-label="Điều hướng quản trị">
          <button
            type="button"
            role="tab"
            id="admin-tab-users"
            aria-selected={activeTab === 'users'}
            aria-controls="admin-panel-users"
            className={`admin-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => handleTabChange('users')}
          >
            <IcoUsers/> Quản lý tài khoản
          </button>
          <button
            type="button"
            role="tab"
            id="admin-tab-logs"
            aria-selected={activeTab === 'logs'}
            aria-controls="admin-panel-logs"
            className={`admin-tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => handleTabChange('logs')}
          >
            <IcoShieldLog/> Nhật ký truy cập (Audit Trail)
          </button>
        </div>

        {activeTab === 'logs' ? (
          <div id="admin-panel-logs" role="tabpanel" aria-labelledby="admin-tab-logs">
            <AccessLogsTab />
          </div>
        ) : (
          <div id="admin-panel-users" role="tabpanel" aria-labelledby="admin-tab-users">
        {/* Stats */}
        <div className="users-stats-bar">
          <span className="users-stat-chip total">
            <span className="stat-dot" style={{ background: 'var(--text-muted)' }}/>
            Tổng: {data?.totalElements ?? '—'}
          </span>
          <span className="users-stat-chip admin">
            <span className="stat-dot" style={{ background: 'var(--role-admin-text)' }}/>
            Admin: {adminCount}
          </span>
          <span className="users-stat-chip staff">
            <span className="stat-dot" style={{ background: 'var(--role-staff-text)' }}/>
            Staff: {staffCount}
          </span>
          <span className="users-stat-chip active">
            <span className="stat-dot"/>
            Đang hoạt động: {activeCount}
          </span>
          {pendingCount > 0 && (
            <span className="users-stat-chip pending">
              <span className="stat-dot"/>
              Chờ kích hoạt: {pendingCount}
            </span>
          )}
        </div>

        {/* Toolbar */}
        <div className="users-toolbar">
          <div className="users-search-wrap">
            <span className="search-icon"><IcoSearch/></span>
            <input
              id="users-search-input"
              className="users-search-input"
              placeholder="Tìm theo username hoặc họ tên..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select
            id="users-role-filter"
            className="users-filter-select"
            value={filterRole}
            onChange={e => setFilterRole(e.target.value)}
          >
            <option value="">Tất cả vai trò</option>
            <option value="ADMIN">Admin</option>
            <option value="STAFF">Staff</option>
            <option value="STUDENT">Student</option>
          </select>
          <select
            id="users-status-filter"
            className="users-filter-select"
            value={filterEnabled}
            onChange={e => setFilterEnabled(e.target.value)}
          >
            <option value="">Tất cả trạng thái</option>
            <option value="true">Đang bật</option>
            <option value="false">Đã tắt</option>
          </select>
        </div>

        {/* Table */}
        <div className="users-table-card">
          {loadErr ? (
            <div className="users-error-card">
              <IcoInfo/> {loadErr}
              <button className="btn-cancel-users" style={{ marginLeft: 'auto' }} onClick={() => load(page)}>
                Thử lại
              </button>
            </div>
          ) : (
            <>
              <div className="users-table-wrap">
                <table className="users-table" aria-label="Danh sách tài khoản">
                  <thead>
                    <tr>
                      <th>Tài khoản</th>
                      <th>Vai trò</th>
                      <th>Trạng thái</th>
                      <th>Kích hoạt</th>
                      <th style={{ textAlign: 'right' }}>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={5}>
                          <div className="users-empty-state">
                            <span className="spinner-u muted" style={{ width: 20, height: 20, borderWidth: 2.5 }}/>
                            Đang tải...
                          </div>
                        </td>
                      </tr>
                    ) : filtered.length === 0 ? (
                      <tr>
                        <td colSpan={5}>
                          <div className="users-empty-state">
                            <div className="users-empty-icon"><IcoUsers/></div>
                            <span>{data?.content.length === 0 ? 'Chưa có tài khoản nào.' : 'Không tìm thấy tài khoản phù hợp.'}</span>
                          </div>
                        </td>
                      </tr>
                    ) : filtered.map(u => (
                      <tr key={u.id}>
                        {/* Identity */}
                        <td>
                          <div className="user-identity">
                            <div className={`user-avatar role-${roleClass(u.role)}`}>
                              {roleAvatarInitial(u.username)}
                            </div>
                            <div className="user-identity-info">
                              <span className="user-username">@{u.username}</span>
                              {u.fullName && <span className="user-fullname">{u.fullName}</span>}
                            </div>
                          </div>
                        </td>

                        {/* Role */}
                        <td>
                          <span className={`role-badge ${roleClass(u.role)}`}>
                            {ROLE_LABEL[u.role]}
                          </span>
                        </td>

                        {/* Enabled */}
                        <td>
                          <span className={`status-badge ${u.enabled ? 'enabled' : 'disabled'}`}>
                            <span className="status-dot"/>
                            {u.enabled ? 'Đang bật' : 'Đã tắt'}
                          </span>
                        </td>

                        {/* Password setup */}
                        <td>
                          {u.passwordSetupRequired ? (
                            <span className="pending-badge"><IcoKey/> Chờ kích hoạt</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>Đã kích hoạt</span>
                          )}
                        </td>

                        {/* Actions */}
                        <td>
                          <div className="users-actions" style={{ justifyContent: 'flex-end' }}>
                            {/* View details */}
                            <button
                              id={`view-user-${u.id}-btn`}
                              className="users-action-btn view"
                              title="Xem chi tiết tài khoản"
                              onClick={() => setDetailUserId(u.id)}
                            >
                              <IcoEye/>
                            </button>

                            {/* Toggle enable / disable (can't self-disable) */}
                            {u.id !== user.id && (
                              <button
                                id={`toggle-user-${u.id}-btn`}
                                className={`users-action-btn ${u.enabled ? 'disable' : 'enable'}`}
                                title={u.enabled ? 'Tắt tài khoản' : 'Bật tài khoản'}
                                onClick={() => { setToggleErr(null); setToggleTarget(u); }}
                              >
                                {u.enabled ? <IcoLock/> : <IcoUnlock/>}
                              </button>
                            )}

                            {/* Re-issue token: only for enabled + pending */}
                            {u.passwordSetupRequired && u.enabled && (
                              <button
                                id={`reissue-token-${u.id}-btn`}
                                className="users-action-btn token"
                                title="Cấp lại token kích hoạt"
                                onClick={() => { setReissueErr(null); setReissueTarget(u); }}
                              >
                                <IcoKey/>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {data && data.totalPages > 1 && (
                <div className="users-pagination">
                  <span className="users-pagination-info">
                    Trang {data.page + 1} / {data.totalPages} — {data.totalElements} tài khoản
                  </span>
                  <div className="users-pagination-btns">
                    <button
                      id="users-prev-page-btn"
                      className="pagination-btn"
                      onClick={() => load(page - 1)}
                      disabled={page === 0 || loading}
                    >
                      <IcoChevLeft/> Trước
                    </button>
                    <button
                      id="users-next-page-btn"
                      className="pagination-btn"
                      onClick={() => load(page + 1)}
                      disabled={page >= data.totalPages - 1 || loading}
                    >
                      Tiếp <IcoChevRight/>
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
          </div>
        )}
      </div>

      {/* Modals */}
      <CreateUserModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(token, username) => {
          setShowCreate(false);
          load(0); // refresh list
          setTokenInfo({ token, username });
        }}
      />

      {tokenInfo && (
        <TokenDisplayModal
          open={!!tokenInfo}
          onClose={() => setTokenInfo(null)}
          token={tokenInfo.token}
          username={tokenInfo.username}
          isReissue={tokenInfo.isReissue}
        />
      )}

      <ConfirmToggleModal
        open={!!toggleTarget}
        onClose={() => { setToggleTarget(null); setToggleErr(null); }}
        onConfirm={handleToggle}
        user={toggleTarget}
        loading={toggling}
        err={toggleErr}
      />

      <ConfirmReissueModal
        open={!!reissueTarget}
        onClose={() => { setReissueTarget(null); setReissueErr(null); }}
        onConfirm={handleReissue}
        user={reissueTarget}
        loading={reissuing}
        err={reissueErr}
      />

      <UserDetailModal
        userId={detailUserId}
        currentUserId={user.id}
        onClose={() => setDetailUserId(null)}
        onToggle={(u) => { setToggleErr(null); setToggleTarget(u); }}
        onReissue={(u) => { setReissueErr(null); setReissueTarget(u); }}
      />
    </div>
  );
}
