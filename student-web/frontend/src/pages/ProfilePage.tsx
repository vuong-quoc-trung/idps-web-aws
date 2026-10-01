/**
 * ProfilePage — Student self-service profile management
 * Features:
 *   - View full profile (read-only immutable fields)
 *   - Edit personal contact/demographic info
 *   - CRUD: Addresses, Family members, Emergency contacts, Post-grad contacts
 *   - Completion widget
 */
import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import AppHeader from '../components/AppHeader';
import Modal from '../components/Modal';
import { useAuth } from '../contexts/AuthContext';
import {
  fetchMyStudent, updateMyProfile,
  addressApi, familyApi, emergencyApi, postGradApi, studentApi,
} from '../api/profileApi';
import type {
  StudentDetail, CompletionStatus,
  Address, AddressPayload,
  FamilyMember, FamilyMemberPayload,
  EmergencyContact, EmergencyContactPayload,
  PostGradContact, PostGradContactPayload,
} from '../types/student';
import './ProfilePage.css';

const GENDER_LABELS: Record<string, string> = { MALE: 'Nam', FEMALE: 'Nữ', OTHER: 'Khác' };
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Đang học', GRADUATED: 'Tốt nghiệp', SUSPENDED: 'Đình chỉ', INACTIVE: 'Ngừng HĐ',
};
type TabId = 'overview' | 'personal' | 'addresses' | 'family' | 'emergency' | 'postgrad';
interface Tab { id: TabId; label: string; icon: ReactNode; }

function initials(name: string) {
  return name.split(' ').map(p => p[0]).slice(-2).join('').toUpperCase();
}

/* ---- SVG icon helpers ---- */
const IcoEdit = () => (
  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
    <path d="M9.5 2.5L11.5 4.5L5 11H3V9L9.5 2.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
);
const IcoTrash = () => (
  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
    <path d="M2.5 4h9M5.5 4V2.5h3V4M6 6.5v4M8 6.5v4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoPlus = () => (
  <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
    <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);
const IcoCheck = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M2 7.5L5.5 11 12 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoInfo = () => (
  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
    <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.25"/>
    <path d="M7 5v3M7 9.5h.01" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoWarn = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M7 1.5v4M7 8.5h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M2.5 12.5h9L7 1.5l-4.5 11z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
);
const IcoShield = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M7 1.5L2 4.5v4c0 2.209 2.239 4.5 5 4.5s5-2.291 5-4.5v-4L7 1.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
    <path d="M5 7l1.5 1.5L9 5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IcoBank = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M1.5 5.5h11M2.5 3L7 1.5 11.5 3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
    <path d="M3 5.5v5M5.5 5.5v5M8.5 5.5v5M11 5.5v5M1.5 10.5h11" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
  </svg>
);
const IcoPhone = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M12 9.5l-2 2a1 1 0 01-1 0C7.5 10.5 3.5 6.5 2.5 5a1 1 0 010-1l2-2 1 1L4 5.5S6 9 8.5 10l2-1.5L12 9.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
);

const TABS: Tab[] = [
  { id: 'overview', label: 'Tổng quan', icon: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <rect x="1.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
      <rect x="8.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
      <rect x="1.5" y="8.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
      <rect x="8.5" y="8.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
    </svg>
  )},
  { id: 'personal', label: 'Thông tin cá nhân', icon: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <circle cx="7" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.25"/>
      <path d="M1.5 12.5c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
    </svg>
  )},
  { id: 'addresses', label: 'Địa chỉ', icon: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <path d="M7 1.5C4.791 1.5 3 3.291 3 5.5c0 3.375 4 7 4 7s4-3.625 4-7c0-2.209-1.791-4-4-4z" stroke="currentColor" strokeWidth="1.25"/>
      <circle cx="7" cy="5.5" r="1.25" stroke="currentColor" strokeWidth="1.25"/>
    </svg>
  )},
  { id: 'family', label: 'Nhân thân', icon: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <circle cx="4" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
      <circle cx="10" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
      <path d="M0.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
      <path d="M6.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
    </svg>
  )},
  { id: 'emergency', label: 'Khẩn cấp', icon: <IcoWarn/> },
  { id: 'postgrad', label: 'Sau tốt nghiệp', icon: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
      <path d="M7 1L1.5 4.5 7 8l5.5-3.5L7 1z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
      <path d="M1.5 4.5v4.5M7 8v4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
    </svg>
  )},
];

/* ---- Shared helpers ---- */
function InfoItem({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="profile-info-item">
      <span className="profile-info-label">{label}</span>
      <span className={`profile-info-value ${mono ? 'mono' : ''} ${!value ? 'muted' : ''}`}>{value ?? '—'}</span>
    </div>
  );
}

function CompletionWidget({ completion, loading }: { completion: CompletionStatus | null; loading: boolean }) {
  if (loading) return (
    <div className="completion-widget">
      <div style={{ display:'flex', alignItems:'center', gap:8, color:'var(--text-muted)', fontSize:'var(--text-sm)' }}>
        <span className="spinner" style={{ width:14, height:14, borderWidth:2 }}/>
        Đang tải tiến độ...
      </div>
    </div>
  );
  if (!completion) return null;
  const pct = completion.complete ? 100
    : completion.percentage != null ? Math.round(completion.percentage)
    : Math.max(0, Math.round(100 - (completion.missingFields.length / Math.max(1, completion.missingFields.length + 1)) * 100));
  const displayPct = completion.complete ? 100 : Math.min(pct, 99);
  return (
    <div className="completion-widget">
      <div className="completion-widget-header">
        <div className="completion-widget-left">
          <span className="completion-widget-title"><IcoCheck/> Mức độ hoàn thiện hồ sơ</span>
          <span className="completion-widget-sub">
            {completion.complete ? 'Hồ sơ đã được hoàn thiện đầy đủ' : `Còn thiếu ${completion.missingFields.length} trường thông tin`}
          </span>
        </div>
        <span className={`completion-pct-badge ${completion.complete ? 'complete' : ''}`}>{displayPct}%</span>
      </div>
      <div className="completion-progress-track">
        <div className={`completion-progress-fill ${completion.complete ? 'complete' : ''}`} style={{ width:`${displayPct}%` }}/>
      </div>
      {completion.missingFields.length > 0 && (
        <div className="completion-missing-tags">
          {completion.missingFields.map(f => (
            <span key={f} className="missing-field-tag"><IcoInfo/>{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function DeleteConfirmModal({ open, onClose, onConfirm, deleting, error }:
  { open:boolean; onClose:()=>void; onConfirm:()=>void; deleting:boolean; error:string|null }) {
  return (
    <Modal open={open} title="Xác nhận xóa" size="sm" onClose={onClose}
      footer={<>
        <button className="btn-cancel" onClick={onClose} disabled={deleting}>Hủy</button>
        <button className="btn-danger" onClick={onConfirm} disabled={deleting}>
          {deleting && <span className="spinner spinner-sm"/>} Xóa
        </button>
      </>}
    >
      <div className="profile-delete-confirm">
        <div className="profile-delete-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h3>Xóa bản ghi này?</h3>
        <p>Hành động này không thể hoàn tác.</p>
        {error && <div className="profile-alert-error" style={{ width:'100%' }}>{error}</div>}
      </div>
    </Modal>
  );
}

/* ============================================================
   ADDRESS TAB
   ============================================================ */
function AddressTab({ studentId }: { studentId: number }) {
  const [items, setItems] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<Address | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Address | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try { setLoading(true); setItems(await addressApi.list(studentId)); }
    finally { setLoading(false); }
  }, [studentId]);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try { await addressApi.remove(studentId, deleteTarget.id); await reload(); setDeleteTarget(null); }
    catch (e) { setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa'); }
    finally { setDeleting(false); }
  }

  const ADDR_LABELS: Record<string, string> = {
    CURRENT: 'Thường trú', PERMANENT: 'Hộ khẩu thường trú', FAMILY_HOME: 'Nhà gia đình',
  };

  return (
    <div>
      <div className="profile-section-header">
        <span className="profile-section-title">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1.5C4.791 1.5 3 3.291 3 5.5c0 3.375 4 7 4 7s4-3.625 4-7c0-2.209-1.791-4-4-4z" stroke="currentColor" strokeWidth="1.25"/>
            <circle cx="7" cy="5.5" r="1.25" stroke="currentColor" strokeWidth="1.25"/>
          </svg>
          Danh sách địa chỉ
        </span>
        <button className="profile-add-card-btn" onClick={() => { setEditItem(null); setShowModal(true); }}>
          <IcoPlus/> Thêm địa chỉ
        </button>
      </div>
      {loading ? (
        <div className="profile-empty-state"><span className="spinner" style={{ width:20, height:20, borderWidth:2.5 }}/></div>
      ) : items.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" stroke="currentColor" strokeWidth="1.5"/>
              <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
            </svg>
          </div>
          <p>Chưa có địa chỉ nào. Hãy thêm địa chỉ để hoàn thiện hồ sơ.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {items.map(addr => (
            <div key={addr.id} className="profile-sub-card">
              <span className="profile-sub-card-type-badge">
                {ADDR_LABELS[addr.addressType] ?? addr.addressType}
                {addr.current && <span style={{ marginLeft:4, color:'var(--text-success)' }}>• Hiện tại</span>}
              </span>
              {addr.addressLine && <div className="profile-sub-card-title">{addr.addressLine}</div>}
              {addr.provinceCity && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Tỉnh/TP:</span><span>{addr.provinceCity}</span></div>}
              {addr.wardCommune && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Xã/Phường:</span><span>{addr.wardCommune}</span></div>}
              {addr.residenceRelation && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Quan hệ:</span><span>{addr.residenceRelation}</span></div>}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(addr); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(addr)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && <AddressModal studentId={studentId} item={editItem} open={showModal} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); reload(); }}/>}
      <DeleteConfirmModal open={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteErr(null); }} onConfirm={handleDelete} deleting={deleting} error={deleteErr}/>
    </div>
  );
}

function AddressModal({ studentId, item, open, onClose, onSaved }:
  { studentId:number; item:Address|null; open:boolean; onClose:()=>void; onSaved:()=>void }) {
  const [form, setForm] = useState<AddressPayload>({ addressType:'CURRENT', current:false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string|null>(null);

  useEffect(() => {
    if (item) setForm({ addressType:item.addressType, addressLine:item.addressLine??'', provinceCity:item.provinceCity??'', wardCommune:item.wardCommune??'', residenceRelation:item.residenceRelation??'', current:item.current });
    else setForm({ addressType:'CURRENT', addressLine:'', provinceCity:'', wardCommune:'', residenceRelation:'', current:false });
    setErr(null);
  }, [item, open]);

  async function save() {
    setSubmitting(true); setErr(null);
    try {
      if (item) await addressApi.update(studentId, item.id, form);
      else await addressApi.create(studentId, form);
      onSaved();
    } catch(e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật địa chỉ' : 'Thêm địa chỉ mới'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{submitting && <span className="spinner spinner-sm"/>}{item ? 'Lưu thay đổi' : 'Thêm mới'}</button></>}
    >
      {err && <div className="profile-alert-error" style={{ marginBottom:12 }}>{err}</div>}
      <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-3)' }}>
        <div className="profile-form-group">
          <label className="profile-form-label">Loại địa chỉ</label>
          <select className="profile-form-input" value={form.addressType} onChange={e => setForm(f => ({ ...f, addressType:e.target.value as AddressPayload['addressType'] }))}>
            <option value="CURRENT">Thường trú</option>
            <option value="PERMANENT">Hộ khẩu thường trú</option>
            <option value="FAMILY_HOME">Nhà gia đình</option>
          </select>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Số nhà, đường, phường/xã</label>
          <input className="profile-form-input" value={form.addressLine??''} onChange={e => setForm(f => ({ ...f, addressLine:e.target.value }))} placeholder="VD: 123 Nguyễn Văn A, Phường 1"/>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Tỉnh / Thành phố</label>
            <input className="profile-form-input" value={form.provinceCity??''} onChange={e => setForm(f => ({ ...f, provinceCity:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Xã / Phường</label>
            <input className="profile-form-input" value={form.wardCommune??''} onChange={e => setForm(f => ({ ...f, wardCommune:e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Quan hệ với nơi ở</label>
          <input className="profile-form-input" placeholder="VD: Chủ hộ, Thuê nhà..." value={form.residenceRelation??''} onChange={e => setForm(f => ({ ...f, residenceRelation:e.target.value }))}/>
        </div>
        <label className="profile-toggle-row">
          <input type="checkbox" className="profile-checkbox" checked={form.current} onChange={e => setForm(f => ({ ...f, current:e.target.checked }))}/>
          <span className="profile-toggle-label">Đây là địa chỉ hiện tại đang cư trú</span>
        </label>
      </div>
    </Modal>
  );
}

/* ============================================================
   FAMILY TAB
   ============================================================ */
const REL_LABELS: Record<string, string> = { MOTHER:'Mẹ', FATHER:'Bố', GUARDIAN:'Người giám hộ', OTHER:'Khác' };

function FamilyTab({ studentId }: { studentId: number }) {
  const [items, setItems] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<FamilyMember|null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FamilyMember|null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string|null>(null);

  const reload = useCallback(async () => {
    try { setLoading(true); setItems(await familyApi.list(studentId)); }
    finally { setLoading(false); }
  }, [studentId]);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try { await familyApi.remove(studentId, deleteTarget.id); await reload(); setDeleteTarget(null); }
    catch(e) { setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa'); }
    finally { setDeleting(false); }
  }

  return (
    <div>
      <div className="profile-section-header">
        <span className="profile-section-title">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="4" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
            <circle cx="10" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
            <path d="M0.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
            <path d="M6.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
          </svg>
          Nhân thân (cha, mẹ, người giám hộ)
        </span>
        <button className="profile-add-card-btn" onClick={() => { setEditItem(null); setShowModal(true); }}>
          <IcoPlus/> Thêm thành viên
        </button>
      </div>
      {loading ? (
        <div className="profile-empty-state"><span className="spinner" style={{ width:20, height:20, borderWidth:2.5 }}/></div>
      ) : items.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <circle cx="9" cy="7" r="4" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M1 21v-2a4 4 0 0 1 4-4h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M17 11v6M14 14h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <p>Chưa có thông tin nhân thân. Thêm để hoàn thiện hồ sơ.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {items.map(m => (
            <div key={m.id} className="profile-sub-card">
              <span className="profile-sub-card-type-badge">{REL_LABELS[m.relationship] ?? m.relationship}</span>
              <div className="profile-sub-card-title">{m.fullName ?? '(Chưa có tên)'}</div>
              {m.dateOfBirth && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Ngày sinh:</span><span>{m.dateOfBirth}</span></div>}
              {m.phoneNumber && <div className="profile-sub-card-row"><span className="profile-sub-card-label">SĐT:</span><span>{m.phoneNumber}</span></div>}
              <div className="profile-sub-card-row">
                <span className="profile-sub-card-label">Bằng ĐH:</span>
                <span style={{ color: m.hasCollegeDegree ? 'var(--text-success)' : 'var(--text-muted)' }}>{m.hasCollegeDegree ? 'Có' : 'Không'}</span>
              </div>
              {m.unavailable && <div className="profile-sub-card-row"><span style={{ color:'var(--text-muted)', fontStyle:'italic', fontSize:'var(--text-xs)' }}>Đã mất / Không liên lạc được</span></div>}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(m); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(m)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && <FamilyModal studentId={studentId} item={editItem} open={showModal} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); reload(); }}/>}
      <DeleteConfirmModal open={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteErr(null); }} onConfirm={handleDelete} deleting={deleting} error={deleteErr}/>
    </div>
  );
}

function FamilyModal({ studentId, item, open, onClose, onSaved }:
  { studentId:number; item:FamilyMember|null; open:boolean; onClose:()=>void; onSaved:()=>void }) {
  const [form, setForm] = useState<FamilyMemberPayload>({ relationship:'OTHER', hasCollegeDegree:false, unavailable:false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string|null>(null);

  useEffect(() => {
    if (item) setForm({ relationship:item.relationship, fullName:item.fullName??'', dateOfBirth:item.dateOfBirth??'', hasCollegeDegree:item.hasCollegeDegree, unavailable:item.unavailable, phoneNumber:item.phoneNumber??'' });
    else setForm({ relationship:'OTHER', fullName:'', dateOfBirth:'', hasCollegeDegree:false, unavailable:false, phoneNumber:'' });
    setErr(null);
  }, [item, open]);

  async function save() {
    setSubmitting(true); setErr(null);
    try {
      const payload = { ...form, fullName:form.fullName||undefined, dateOfBirth:form.dateOfBirth||undefined, phoneNumber:form.phoneNumber||undefined };
      if (item) await familyApi.update(studentId, item.id, payload);
      else await familyApi.create(studentId, payload);
      onSaved();
    } catch(e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật nhân thân' : 'Thêm thành viên nhân thân'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{submitting && <span className="spinner spinner-sm"/>}{item ? 'Lưu' : 'Thêm mới'}</button></>}
    >
      {err && <div className="profile-alert-error" style={{ marginBottom:12 }}>{err}</div>}
      <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-3)' }}>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Quan hệ <span style={{color:'var(--text-error)'}}>*</span></label>
            <select className="profile-form-input" value={form.relationship} onChange={e => setForm(f => ({ ...f, relationship:e.target.value as FamilyMemberPayload['relationship'] }))}>
              <option value="MOTHER">Mẹ</option>
              <option value="FATHER">Bố</option>
              <option value="GUARDIAN">Người giám hộ</option>
              <option value="OTHER">Khác</option>
            </select>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Họ và tên</label>
            <input className="profile-form-input" value={form.fullName??''} onChange={e => setForm(f => ({ ...f, fullName:e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Ngày sinh</label>
            <input className="profile-form-input" type="date" value={form.dateOfBirth??''} onChange={e => setForm(f => ({ ...f, dateOfBirth:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại</label>
            <input className="profile-form-input" value={form.phoneNumber??''} onChange={e => setForm(f => ({ ...f, phoneNumber:e.target.value }))}/>
          </div>
        </div>
        <div style={{ display:'flex', gap:24 }}>
          <label className="profile-toggle-row">
            <input type="checkbox" className="profile-checkbox" checked={form.hasCollegeDegree} onChange={e => setForm(f => ({ ...f, hasCollegeDegree:e.target.checked }))}/>
            <span className="profile-toggle-label">Có bằng đại học</span>
          </label>
          <label className="profile-toggle-row">
            <input type="checkbox" className="profile-checkbox" checked={form.unavailable} onChange={e => setForm(f => ({ ...f, unavailable:e.target.checked }))}/>
            <span className="profile-toggle-label">Đã mất / Không liên lạc</span>
          </label>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   EMERGENCY TAB
   ============================================================ */
function EmergencyTab({ studentId }: { studentId: number }) {
  const [items, setItems] = useState<EmergencyContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<EmergencyContact|null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EmergencyContact|null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string|null>(null);

  const reload = useCallback(async () => {
    try { setLoading(true); setItems(await emergencyApi.list(studentId)); }
    finally { setLoading(false); }
  }, [studentId]);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try { await emergencyApi.remove(studentId, deleteTarget.id); await reload(); setDeleteTarget(null); }
    catch(e) { setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa'); }
    finally { setDeleting(false); }
  }

  const sorted = [...items].sort((a, b) => a.priority - b.priority);

  return (
    <div>
      <div className="profile-section-header">
        <span className="profile-section-title"><IcoWarn/> Liên hệ khẩn cấp</span>
        <button className="profile-add-card-btn" onClick={() => { setEditItem(null); setShowModal(true); }}>
          <IcoPlus/> Thêm liên hệ
        </button>
      </div>
      {loading ? (
        <div className="profile-empty-state"><span className="spinner" style={{ width:20, height:20, borderWidth:2.5 }}/></div>
      ) : sorted.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.82a19.79 19.79 0 01-3.07-8.64A2 2 0 012 .01h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 14v2.92z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            </svg>
          </div>
          <p>Chưa có liên hệ khẩn cấp. Thêm ít nhất 1 liên hệ để bảo đảm an toàn.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {sorted.map(c => (
            <div key={c.id} className="profile-sub-card">
              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:'var(--space-2)' }}>
                <span className="priority-badge">{c.priority}</span>
                <div className="profile-sub-card-title" style={{ margin:0 }}>{c.fullName}</div>
              </div>
              {c.relationship && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Quan hệ:</span><span>{c.relationship}</span></div>}
              <div className="profile-sub-card-row">
                <span className="profile-sub-card-label">SĐT:</span>
                <span style={{ fontFamily:'var(--font-mono)', fontSize:'0.8rem', color:'var(--accent)' }}>{c.phoneNumber}</span>
              </div>
              {c.address && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Địa chỉ:</span><span>{c.address}</span></div>}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(c); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(c)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && <EmergencyModal studentId={studentId} item={editItem} open={showModal} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); reload(); }}/>}
      <DeleteConfirmModal open={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteErr(null); }} onConfirm={handleDelete} deleting={deleting} error={deleteErr}/>
    </div>
  );
}

function EmergencyModal({ studentId, item, open, onClose, onSaved }:
  { studentId:number; item:EmergencyContact|null; open:boolean; onClose:()=>void; onSaved:()=>void }) {
  const [form, setForm] = useState<EmergencyContactPayload>({ fullName:'', phoneNumber:'', priority:1 });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string|null>(null);

  useEffect(() => {
    if (item) setForm({ fullName:item.fullName, relationship:item.relationship??'', phoneNumber:item.phoneNumber, address:item.address??'', priority:item.priority });
    else setForm({ fullName:'', relationship:'', phoneNumber:'', address:'', priority:1 });
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!form.fullName.trim()) { setErr('Họ tên là bắt buộc'); return; }
    if (!form.phoneNumber.trim()) { setErr('Số điện thoại là bắt buộc'); return; }
    if (!form.priority || form.priority < 1) { setErr('Thứ tự ưu tiên phải ≥ 1'); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = { ...form, relationship:form.relationship||undefined, address:form.address||undefined };
      if (item) await emergencyApi.update(studentId, item.id, payload);
      else await emergencyApi.create(studentId, payload);
      onSaved();
    } catch(e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật liên hệ khẩn cấp' : 'Thêm liên hệ khẩn cấp'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{submitting && <span className="spinner spinner-sm"/>}{item ? 'Lưu' : 'Thêm mới'}</button></>}
    >
      {err && <div className="profile-alert-error" style={{ marginBottom:12 }}>{err}</div>}
      <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-3)' }}>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Họ và tên <span style={{color:'var(--text-error)'}}>*</span></label>
            <input className="profile-form-input" value={form.fullName} onChange={e => setForm(f => ({ ...f, fullName:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại <span style={{color:'var(--text-error)'}}>*</span></label>
            <input className="profile-form-input" value={form.phoneNumber} onChange={e => setForm(f => ({ ...f, phoneNumber:e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Mối quan hệ</label>
            <input className="profile-form-input" placeholder="VD: Cha, Mẹ, Anh/Chị..." value={form.relationship??''} onChange={e => setForm(f => ({ ...f, relationship:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Thứ tự ưu tiên <span style={{color:'var(--text-error)'}}>*</span></label>
            <input className="profile-form-input" type="number" min={1} value={form.priority} onChange={e => setForm(f => ({ ...f, priority:Number(e.target.value) }))}/>
          </div>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Địa chỉ</label>
          <input className="profile-form-input" value={form.address??''} onChange={e => setForm(f => ({ ...f, address:e.target.value }))}/>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   POST-GRAD TAB
   ============================================================ */
function PostGradTab({ studentId }: { studentId: number }) {
  const [items, setItems] = useState<PostGradContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<PostGradContact|null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PostGradContact|null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string|null>(null);

  const reload = useCallback(async () => {
    try { setLoading(true); setItems(await postGradApi.list(studentId)); }
    finally { setLoading(false); }
  }, [studentId]);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try { await postGradApi.remove(studentId, deleteTarget.id); await reload(); setDeleteTarget(null); }
    catch(e) { setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa'); }
    finally { setDeleting(false); }
  }

  return (
    <div>
      <div className="profile-section-header">
        <span className="profile-section-title">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1L1.5 4.5 7 8l5.5-3.5L7 1z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
            <path d="M1.5 4.5v4.5M7 8v4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
          </svg>
          Liên hệ sau tốt nghiệp
        </span>
        <button className="profile-add-card-btn" onClick={() => { setEditItem(null); setShowModal(true); }}>
          <IcoPlus/> Thêm liên hệ
        </button>
      </div>
      {loading ? (
        <div className="profile-empty-state"><span className="spinner" style={{ width:20, height:20, borderWidth:2.5 }}/></div>
      ) : items.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M22 4L12 14.01l-3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <p>Chưa có thông tin liên hệ sau tốt nghiệp.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {items.map(c => (
            <div key={c.id} className="profile-sub-card">
              <div className="profile-sub-card-title">{c.fullName ?? '(Chưa có tên)'}</div>
              {c.phoneNumber && <div className="profile-sub-card-row"><span className="profile-sub-card-label">SĐT:</span><span style={{ fontFamily:'var(--font-mono)', fontSize:'0.8rem' }}>{c.phoneNumber}</span></div>}
              {c.email && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Email:</span><span style={{ color:'var(--accent)' }}>{c.email}</span></div>}
              {c.address && <div className="profile-sub-card-row"><span className="profile-sub-card-label">Địa chỉ:</span><span>{c.address}</span></div>}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(c); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(c)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && <PostGradModal studentId={studentId} item={editItem} open={showModal} onClose={() => setShowModal(false)} onSaved={() => { setShowModal(false); reload(); }}/>}
      <DeleteConfirmModal open={!!deleteTarget} onClose={() => { setDeleteTarget(null); setDeleteErr(null); }} onConfirm={handleDelete} deleting={deleting} error={deleteErr}/>
    </div>
  );
}

function PostGradModal({ studentId, item, open, onClose, onSaved }:
  { studentId:number; item:PostGradContact|null; open:boolean; onClose:()=>void; onSaved:()=>void }) {
  const [form, setForm] = useState<PostGradContactPayload>({});
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string|null>(null);

  useEffect(() => {
    if (item) setForm({ fullName:item.fullName??'', phoneNumber:item.phoneNumber??'', email:item.email??'', address:item.address??'' });
    else setForm({ fullName:'', phoneNumber:'', email:'', address:'' });
    setErr(null);
  }, [item, open]);

  async function save() {
    setSubmitting(true); setErr(null);
    try {
      const payload = { fullName:form.fullName||undefined, phoneNumber:form.phoneNumber||undefined, email:form.email||undefined, address:form.address||undefined };
      if (item) await postGradApi.update(studentId, item.id, payload);
      else await postGradApi.create(studentId, payload);
      onSaved();
    } catch(e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật liên hệ sau TN' : 'Thêm liên hệ sau tốt nghiệp'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{submitting && <span className="spinner spinner-sm"/>}{item ? 'Lưu' : 'Thêm mới'}</button></>}
    >
      {err && <div className="profile-alert-error" style={{ marginBottom:12 }}>{err}</div>}
      <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-3)' }}>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Họ và tên</label>
            <input className="profile-form-input" value={form.fullName??''} onChange={e => setForm(f => ({ ...f, fullName:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại</label>
            <input className="profile-form-input" value={form.phoneNumber??''} onChange={e => setForm(f => ({ ...f, phoneNumber:e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Email</label>
            <input className="profile-form-input" type="email" value={form.email??''} onChange={e => setForm(f => ({ ...f, email:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Địa chỉ</label>
            <input className="profile-form-input" value={form.address??''} onChange={e => setForm(f => ({ ...f, address:e.target.value }))}/>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   PERSONAL INFO EDIT TAB
   ============================================================ */
function PersonalTab({ student, onUpdated }: { student: StudentDetail; onUpdated: (s: StudentDetail) => void }) {
  const [form, setForm] = useState({
    personalEmail: student.personalEmail ?? '',
    phoneNumber: student.phoneNumber ?? '',
    ethnicity: student.ethnicity ?? '',
    religion: student.religion ?? '',
    healthInsuranceNumber: student.healthInsuranceNumber ?? '',
    healthInsuranceExpiry: student.healthInsuranceExpiry ?? '',
    freeHealthInsurance: student.freeHealthInsurance ?? false,
    facebookUrl: student.facebookUrl ?? '',
    bankAccountNumber: student.bankAccountNumber ?? '',
    bankName: student.bankName ?? '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [err, setErr] = useState<string|null>(null);

  useEffect(() => {
    setForm({
      personalEmail:student.personalEmail??'', phoneNumber:student.phoneNumber??'',
      ethnicity:student.ethnicity??'', religion:student.religion??'',
      healthInsuranceNumber:student.healthInsuranceNumber??'', healthInsuranceExpiry:student.healthInsuranceExpiry??'',
      freeHealthInsurance:student.freeHealthInsurance??false, facebookUrl:student.facebookUrl??'',
      bankAccountNumber:student.bankAccountNumber??'', bankName:student.bankName??'',
    });
  }, [student]);

  function reset() {
    setForm({
      personalEmail:student.personalEmail??'', phoneNumber:student.phoneNumber??'',
      ethnicity:student.ethnicity??'', religion:student.religion??'',
      healthInsuranceNumber:student.healthInsuranceNumber??'', healthInsuranceExpiry:student.healthInsuranceExpiry??'',
      freeHealthInsurance:student.freeHealthInsurance??false, facebookUrl:student.facebookUrl??'',
      bankAccountNumber:student.bankAccountNumber??'', bankName:student.bankName??'',
    });
    setErr(null); setSuccess(false);
  }

  async function save() {
    setSubmitting(true); setErr(null); setSuccess(false);
    try {
      const updated = await updateMyProfile(student.id, student, {
        personalEmail:form.personalEmail||null, phoneNumber:form.phoneNumber||null,
        ethnicity:form.ethnicity||null, religion:form.religion||null,
        healthInsuranceNumber:form.healthInsuranceNumber||null, healthInsuranceExpiry:form.healthInsuranceExpiry||null,
        freeHealthInsurance:form.freeHealthInsurance,
        facebookUrl:form.facebookUrl||null,
        bankAccountNumber:form.bankAccountNumber||null, bankName:form.bankName||null,
      });
      onUpdated(updated);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
    } catch(e) { setErr(e instanceof Error ? e.message : 'Lỗi cập nhật'); }
    finally { setSubmitting(false); }
  }

  return (
    <div className="profile-edit-section">
      <div className="profile-immutable-notice">
        <IcoInfo/>
        <span>Các trường như họ tên, MSSV, ngày sinh, số CCCD, email trường và lớp học được quản lý bởi nhà trường và không thể tự chỉnh sửa.</span>
      </div>

      {/* Contact */}
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title"><IcoPhone/> Thông tin liên lạc cá nhân</span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Email cá nhân</label>
            <input className="profile-form-input" type="email" placeholder="example@gmail.com" value={form.personalEmail} onChange={e => setForm(f => ({ ...f, personalEmail:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại</label>
            <input className="profile-form-input" type="tel" placeholder="0912 345 678" value={form.phoneNumber} onChange={e => setForm(f => ({ ...f, phoneNumber:e.target.value }))}/>
          </div>
        </div>
        <div style={{ marginTop:'var(--space-3)' }}>
          <div className="profile-form-group">
            <label className="profile-form-label">Facebook / Mạng xã hội</label>
            <input className="profile-form-input" placeholder="https://facebook.com/..." value={form.facebookUrl} onChange={e => setForm(f => ({ ...f, facebookUrl:e.target.value }))}/>
          </div>
        </div>
      </div>

      <div className="profile-form-divider"/>

      {/* Demographics */}
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M7 1.5C4.515 1.5 2.5 3.515 2.5 6S4.515 10.5 7 10.5 11.5 8.485 11.5 6 9.485 1.5 7 1.5z" stroke="currentColor" strokeWidth="1.25"/>
              <path d="M4 12.5c0-1.657 1.343-3 3-3s3 1.343 3 3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
            </svg>
            Dân tộc, tôn giáo
          </span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Dân tộc</label>
            <input className="profile-form-input" placeholder="VD: Kinh, Tày, Nùng..." value={form.ethnicity} onChange={e => setForm(f => ({ ...f, ethnicity:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Tôn giáo</label>
            <input className="profile-form-input" placeholder="VD: Không, Phật giáo, Cơ đốc..." value={form.religion} onChange={e => setForm(f => ({ ...f, religion:e.target.value }))}/>
          </div>
        </div>
      </div>

      <div className="profile-form-divider"/>

      {/* Health insurance */}
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title"><IcoShield/> Bảo hiểm y tế (BHYT)</span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Số thẻ BHYT</label>
            <input className="profile-form-input" placeholder="VD: HS4010..." value={form.healthInsuranceNumber} onChange={e => setForm(f => ({ ...f, healthInsuranceNumber:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Ngày hết hạn BHYT</label>
            <input className="profile-form-input" type="date" value={form.healthInsuranceExpiry} onChange={e => setForm(f => ({ ...f, healthInsuranceExpiry:e.target.value }))}/>
          </div>
        </div>
        <label className="profile-toggle-row" style={{ marginTop:'var(--space-2)' }}>
          <input type="checkbox" className="profile-checkbox" checked={form.freeHealthInsurance} onChange={e => setForm(f => ({ ...f, freeHealthInsurance:e.target.checked }))}/>
          <span className="profile-toggle-label">Được cấp BHYT miễn phí (diện từ thiện, chính sách...)</span>
        </label>
      </div>

      <div className="profile-form-divider"/>

      {/* Bank */}
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title"><IcoBank/> Tài khoản ngân hàng</span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Số tài khoản</label>
            <input className="profile-form-input" placeholder="VD: 0123456789" value={form.bankAccountNumber} onChange={e => setForm(f => ({ ...f, bankAccountNumber:e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Tên ngân hàng</label>
            <input className="profile-form-input" placeholder="VD: Vietcombank, Techcombank..." value={form.bankName} onChange={e => setForm(f => ({ ...f, bankName:e.target.value }))}/>
          </div>
        </div>
      </div>

      {success && <div className="profile-alert-success"><IcoCheck/> Cập nhật thông tin cá nhân thành công!</div>}
      {err && <div className="profile-alert-error">{err}</div>}

      <div className="profile-save-bar">
        <button className="btn-profile-cancel" onClick={reset} disabled={submitting}>Đặt lại</button>
        <button className="btn-profile-save" onClick={save} disabled={submitting}>
          {submitting ? <><span className="spinner spinner-sm"/>  Đang lưu...</> : <><IcoCheck/> Lưu thay đổi</>}
        </button>
      </div>
    </div>
  );
}

/* ============================================================
   OVERVIEW TAB
   ============================================================ */
function OverviewTab({ student }: { student: StudentDetail }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-6)' }}>
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
              <path d="M4 6h6M4 8h4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
            </svg>
            Thông tin cơ bản (do nhà trường quản lý)
          </span>
        </div>
        <div className="profile-info-grid">
          <InfoItem label="MSSV" value={student.studentCode} mono/>
          <InfoItem label="Họ và tên" value={student.fullName}/>
          <InfoItem label="Ngày sinh" value={student.dateOfBirth}/>
          <InfoItem label="Giới tính" value={student.gender ? GENDER_LABELS[student.gender] : undefined}/>
          <InfoItem label="Số CCCD/CMND" value={student.citizenId} mono/>
          <InfoItem label="Nơi sinh" value={student.placeOfBirth}/>
          <InfoItem label="Email trường" value={student.schoolEmail} mono/>
          <InfoItem label="SĐT gia đình" value={student.familyPhoneNumber}/>
        </div>
      </div>
      <div>
        <div className="profile-section-header" style={{ marginBottom:'var(--space-3)' }}>
          <span className="profile-section-title">
            <IcoCheck/> Thông tin tự khai (do sinh viên cập nhật)
          </span>
        </div>
        <div className="profile-info-grid">
          <InfoItem label="Email cá nhân" value={student.personalEmail}/>
          <InfoItem label="Số điện thoại" value={student.phoneNumber}/>
          <InfoItem label="Dân tộc" value={student.ethnicity}/>
          <InfoItem label="Tôn giáo" value={student.religion}/>
          <InfoItem label="Số thẻ BHYT" value={student.healthInsuranceNumber} mono/>
          <InfoItem label="Hạn BHYT" value={student.healthInsuranceExpiry}/>
          {student.freeHealthInsurance && <InfoItem label="BHYT miễn phí" value="Có"/>}
          <InfoItem label="Facebook" value={student.facebookUrl}/>
          <InfoItem label="Số tài khoản" value={student.bankAccountNumber} mono/>
          <InfoItem label="Ngân hàng" value={student.bankName}/>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   MAIN PAGE
   ============================================================ */
export default function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [student, setStudent] = useState<StudentDetail|null>(null);
  const [completion, setCompletion] = useState<CompletionStatus|null>(null);
  const [loading, setLoading] = useState(true);
  const [completionLoading, setCompletionLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string|null>(null);

  const loadProfile = useCallback(async () => {
    if (!user?.studentCode) return;
    setLoading(true); setLoadErr(null);
    try {
      const sv = await fetchMyStudent(user.studentCode);
      setStudent(sv);
      setCompletionLoading(true);
      studentApi.completion(sv.id)
        .then(c => setCompletion(c))
        .catch(() => {})
        .finally(() => setCompletionLoading(false));
    } catch(e) {
      setLoadErr(e instanceof Error ? e.message : 'Lỗi tải hồ sơ');
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { loadProfile(); }, [loadProfile]);

  useEffect(() => {
    if (user && user.role !== 'STUDENT') navigate('/', { replace:true });
  }, [user, navigate]);

  if (!user) return null;

  if (loading) return (
    <div className="profile-page">
      <AppHeader/>
      <div style={{ flex:1, display:'flex', alignItems:'center', justifyContent:'center' }}>
        <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:'var(--space-3)', color:'var(--text-muted)', fontSize:'var(--text-sm)' }}>
          <span className="spinner" style={{ width:28, height:28, borderWidth:3, borderTopColor:'var(--accent)' }}/>
          Đang tải hồ sơ...
        </div>
      </div>
    </div>
  );

  if (loadErr || !student) return (
    <div className="profile-page">
      <AppHeader/>
      <div className="profile-inner">
        <div className="profile-alert-error"><IcoInfo/> {loadErr ?? 'Không tìm thấy hồ sơ sinh viên.'}</div>
      </div>
    </div>
  );

  return (
    <div className="profile-page">
      <AppHeader/>
      <div className="profile-inner">
        {/* Hero card */}
        <div className="profile-hero">
          <div className="profile-hero-banner"/>
          <div className="profile-hero-body">
            <div className="profile-hero-row">
              <div className="profile-avatar-wrap">
                <div className="profile-avatar">{initials(student.fullName)}</div>
              </div>
              <div className="profile-hero-info">
                <h1>{student.fullName}</h1>
                <div className="profile-hero-chips">
                  <span className="profile-chip accent">
                    <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                      <rect x="1" y="1" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="1.25"/>
                      <path d="M4 6h4M4 4h4M4 8h2" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
                    </svg>
                    {student.studentCode}
                  </span>
                  <span className={`profile-chip profile-status-badge profile-status-${student.status}`}>
                    <span style={{ width:6, height:6, borderRadius:'50%', background:'currentColor', display:'inline-block' }}/>
                    {STATUS_LABELS[student.status]}
                  </span>
                  {student.gender && <span className="profile-chip">{GENDER_LABELS[student.gender]}</span>}
                  {student.schoolEmail && (
                    <span className="profile-chip">
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                        <rect x="1" y="2.5" width="10" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
                        <path d="M1 4.5l5 3 5-3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
                      </svg>
                      {student.schoolEmail}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Completion widget */}
        <CompletionWidget completion={completion} loading={completionLoading}/>

        {/* Tabs */}
        <div>
          <div className="profile-tabs" role="tablist" aria-label="Quản lý hồ sơ">
            {TABS.map(tab => (
              <button
                key={tab.id}
                id={`profile-tab-${tab.id}`}
                className={`profile-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`profile-tabpanel-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.icon}{tab.label}
              </button>
            ))}
          </div>
          <div id={`profile-tabpanel-${activeTab}`} className="profile-tab-panel" role="tabpanel" aria-labelledby={`profile-tab-${activeTab}`}>
            {activeTab === 'overview' && <OverviewTab student={student}/>}
            {activeTab === 'personal' && (
              <PersonalTab student={student} onUpdated={s => {
                setStudent(s);
                studentApi.completion(s.id).then(setCompletion).catch(() => {});
              }}/>
            )}
            {activeTab === 'addresses' && <AddressTab studentId={student.id}/>}
            {activeTab === 'family' && <FamilyTab studentId={student.id}/>}
            {activeTab === 'emergency' && <EmergencyTab studentId={student.id}/>}
            {activeTab === 'postgrad' && <PostGradTab studentId={student.id}/>}
          </div>
        </div>
      </div>
    </div>
  );
}
