/**
 * ProfilePage — Student self-service profile management
 * Fixed according to backend Spring Security contracts:
 *   - Uses /api/me/profile, /api/me/completion, and /api/me/* sub-resources
 *   - Solves 403 Forbidden for role STUDENT (no longer accesses /api/students/**)
 *   - Fixes fail-on-unknown-properties: separates school-managed bank info from editable personal fields
 *   - Adds editable demographic fields needed to reach 100% completion (placeOfBirth, nationality, citizenIdIssueDate...)
 *   - Maps completion missing fields to user-friendly Vietnamese labels
 */
import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import AppHeader from '../components/AppHeader';
import Modal from '../components/Modal';
import { useAuth } from '../contexts/AuthContext';
import {
  myProfileApi,
  myAddressApi,
  myFamilyApi,
  myEmergencyApi,
  myPostGradApi,
  type UpdateStudentProfilePayload,
} from '../api/profileApi';
import type {
  StudentDetail,
  CompletionStatus,
  Address,
  AddressPayload,
  FamilyMember,
  FamilyMemberPayload,
  EmergencyContact,
  EmergencyContactPayload,
  PostGradContact,
  PostGradContactPayload,
} from '../types/student';
import './ProfilePage.css';
import { AddressLocationFields, countryLabel, CatalogSelect, CountrySelect, ProvinceField, useProfileOptions } from '../components/profile/ProfileFields';
import { validPhone, validEmail, PHONE_ERROR, EMAIL_ERROR } from '../utils/contactValidation';

const GENDER_LABELS: Record<string, string> = { MALE: 'Nam', FEMALE: 'Nữ', OTHER: 'Khác' };
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Đang học',
  GRADUATED: 'Tốt nghiệp',
  SUSPENDED: 'Đình chỉ',
  INACTIVE: 'Ngừng HĐ',
};

const MISSING_FIELD_LABELS: Record<string, string> = {
  dateOfBirth: 'Ngày sinh',
  gender: 'Giới tính',
  placeOfBirth: 'Nơi sinh',
  oldPlaceOfBirth: 'Quê quán',
  ethnicity: 'Dân tộc',
  nationality: 'Quốc tịch',
  citizenId: 'Số CCCD',
  citizenIdIssueDate: 'Ngày cấp CCCD',
  healthInsuranceNumber: 'Số thẻ BHYT',
  healthInsuranceExpiry: 'Hạn thẻ BHYT',
  trainingProgram: 'Chương trình đào tạo',
  personalEmail: 'Email cá nhân',
  phoneNumber: 'Số điện thoại',
  currentAddress: 'Địa chỉ thường trú hiện tại',
  permanentOrFamilyAddress: 'Hộ khẩu hoặc nhà gia đình',
  father: 'Thông tin Bố (tên, ngày sinh hoặc đánh dấu đã mất)',
  mother: 'Thông tin Mẹ (tên, ngày sinh hoặc đánh dấu đã mất)',
  emergencyContact: 'Liên hệ khẩn cấp (tên, SĐT, ưu tiên)',
};

type TabId = 'overview' | 'personal' | 'addresses' | 'family' | 'emergency' | 'postgrad';
interface Tab {
  id: TabId;
  label: string;
  icon: ReactNode;
}

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
const IcoPhone = () => (
  <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
    <path d="M12 9.5l-2 2a1 1 0 01-1 0C7.5 10.5 3.5 6.5 2.5 5a1 1 0 010-1l2-2 1 1L4 5.5S6 9 8.5 10l2-1.5L12 9.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
  </svg>
);

const TABS: Tab[] = [
  {
    id: 'overview',
    label: 'Tổng quan',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <rect x="1.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
        <rect x="8.5" y="1.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
        <rect x="1.5" y="8.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
        <rect x="8.5" y="8.5" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.25"/>
      </svg>
    ),
  },
  {
    id: 'personal',
    label: 'Cập nhật cá nhân',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <circle cx="7" cy="4" r="2.5" stroke="currentColor" strokeWidth="1.25"/>
        <path d="M1.5 12.5c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    id: 'addresses',
    label: 'Địa chỉ',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <path d="M7 1.5C4.791 1.5 3 3.291 3 5.5c0 3.375 4 7 4 7s4-3.625 4-7c0-2.209-1.791-4-4-4z" stroke="currentColor" strokeWidth="1.25"/>
        <circle cx="7" cy="5.5" r="1.25" stroke="currentColor" strokeWidth="1.25"/>
      </svg>
    ),
  },
  {
    id: 'family',
    label: 'Nhân thân',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <circle cx="4" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
        <circle cx="10" cy="4.5" r="1.75" stroke="currentColor" strokeWidth="1.25"/>
        <path d="M0.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
        <path d="M6.5 12.5c0-1.933 1.567-3.5 3.5-3.5s3.5 1.567 3.5 3.5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
      </svg>
    ),
  },
  { id: 'emergency', label: 'Khẩn cấp', icon: <IcoWarn/> },
  {
    id: 'postgrad',
    label: 'Sau tốt nghiệp',
    icon: (
      <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
        <path d="M7 1L1.5 4.5 7 8l5.5-3.5L7 1z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
        <path d="M1.5 4.5v4.5M7 8v4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
      </svg>
    ),
  },
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
  if (loading) {
    return (
      <div className="completion-widget">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
          <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}/>
          Đang kiểm tra tiến độ hoàn thiện hồ sơ...
        </div>
      </div>
    );
  }
  if (!completion) return null;

  const isComplete = completion.status === 'COMPLETE' || completion.complete === true || (completion.missingFields && completion.missingFields.length === 0);
  const missingCount = completion.missingFields?.length ?? 0;
  const totalFields = 17;
  const pct = isComplete ? 100 : Math.max(0, Math.min(99, Math.round(((totalFields - missingCount) / totalFields) * 100)));
  const displayPct = isComplete ? 100 : pct;

  return (
    <div className="completion-widget">
      <div className="completion-widget-header">
        <div className="completion-widget-left">
          <span className="completion-widget-title"><IcoCheck/> Mức độ hoàn thiện hồ sơ</span>
          <span className="completion-widget-sub">
            {isComplete ? 'Hồ sơ đã được hoàn thiện đầy đủ theo quy định của nhà trường' : `Còn thiếu ${missingCount} mục thông tin cần bổ sung`}
          </span>
        </div>
        <span className={`completion-pct-badge ${isComplete ? 'complete' : ''}`}>{displayPct}%</span>
      </div>
      <div className="completion-progress-track">
        <div className={`completion-progress-fill ${isComplete ? 'complete' : ''}`} style={{ width: `${displayPct}%` }}/>
      </div>
      {missingCount > 0 && (
        <div className="completion-missing-tags">
          {completion.missingFields.map(f => (
            <span key={f} className="missing-field-tag" title={`Cần bổ sung: ${f}`}>
              <IcoInfo/>
              {MISSING_FIELD_LABELS[f] ?? f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function DeleteConfirmModal({ open, onClose, onConfirm, deleting, error }:
  { open: boolean; onClose: () => void; onConfirm: () => void; deleting: boolean; error: string | null }) {
  return (
    <Modal
      open={open}
      title="Xác nhận xóa"
      size="sm"
      onClose={onClose}
      footer={
        <>
          <button className="btn-cancel" onClick={onClose} disabled={deleting}>Hủy</button>
          <button className="btn-danger" onClick={onConfirm} disabled={deleting}>
            {deleting && <span className="spinner spinner-sm"/>} Xóa
          </button>
        </>
      }
    >
      <div className="profile-delete-confirm">
        <div className="profile-delete-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h3>Xóa bản ghi này?</h3>
        <p>Hành động này không thể hoàn tác.</p>
        {error && <div className="profile-alert-error" style={{ width: '100%' }}>{error}</div>}
      </div>
    </Modal>
  );
}

/* ============================================================
   ADDRESS TAB (/api/me/addresses)
   ============================================================ */
function AddressTab({ onModified }: { onModified?: () => void }) {
  const [items, setItems] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<Address | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Address | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setItems(await myAddressApi.list());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await myAddressApi.remove(deleteTarget.id);
      await reload();
      setDeleteTarget(null);
      onModified?.();
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa địa chỉ');
    } finally {
      setDeleting(false);
    }
  }

  const ADDR_LABELS: Record<string, string> = {
    CURRENT: 'Thường trú',
    PERMANENT: 'Hộ khẩu thường trú',
    FAMILY_HOME: 'Nhà gia đình',
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
        <div className="profile-empty-state"><span className="spinner" style={{ width: 20, height: 20, borderWidth: 2.5 }}/></div>
      ) : items.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" stroke="currentColor" strokeWidth="1.5"/>
              <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
            </svg>
          </div>
          <p>Chưa có địa chỉ nào. Hãy thêm địa chỉ thường trú và địa chỉ hiện tại để hoàn thiện hồ sơ.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {items.map(addr => (
            <div key={addr.id} className="profile-sub-card">
              <span className="profile-sub-card-type-badge">
                {ADDR_LABELS[addr.addressType] ?? addr.addressType}
                {addr.current && <span style={{ marginLeft: 4, color: 'var(--text-success)' }}>• Hiện tại</span>}
              </span>
              {addr.addressLine && <div className="profile-sub-card-title">{addr.addressLine}</div>}
              <div className="profile-sub-card-row"><span className="profile-sub-card-label">Quốc gia:</span><span>{countryLabel(addr.countryCode)}</span></div>
              {addr.provinceCity && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Tỉnh/TP:</span>
                  <span>{addr.provinceCity}</span>
                </div>
              )}
              {addr.wardCommune && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Xã/Phường:</span>
                  <span>{addr.wardCommune}</span>
                </div>
              )}
              {addr.residenceRelation && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Quan hệ:</span>
                  <span>{addr.residenceRelation}</span>
                </div>
              )}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(addr); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(addr)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <AddressModal
          item={editItem}
          open={showModal}
          onClose={() => setShowModal(false)}
          onSaved={() => {
            setShowModal(false);
            reload();
            onModified?.();
          }}
        />
      )}
      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        onConfirm={handleDelete}
        deleting={deleting}
        error={deleteErr}
      />
    </div>
  );
}

function AddressModal({ item, open, onClose, onSaved }:
  { item: Address | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<AddressPayload>({ addressType: 'CURRENT', current: false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) {
      setForm({
        addressType: item.addressType, countryCode: item.countryCode ?? 'VN',
        addressLine: item.addressLine ?? '',
        provinceCity: item.provinceCity ?? '',
        wardCommune: item.wardCommune ?? '',
        residenceRelation: item.residenceRelation ?? '',
        current: item.current,
      });
    } else {
      setForm({ countryCode: 'VN', addressType: 'CURRENT', addressLine: '', provinceCity: '', wardCommune: '', residenceRelation: '', current: false });
    }
    setErr(null);
  }, [item, open]);

  async function save() {
    setSubmitting(true); setErr(null);
    try {
      if (item) await myAddressApi.update(item.id, form);
      else await myAddressApi.create(form);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi lưu địa chỉ');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? 'Cập nhật địa chỉ' : 'Thêm địa chỉ mới'}
      size="md"
      onClose={onClose}
      footer={
        <>
          <button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={save} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm"/>}
            {item ? 'Lưu thay đổi' : 'Thêm mới'}
          </button>
        </>
      }
    >
      {err && <div className="profile-alert-error" style={{ marginBottom: 12 }}>{err}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="profile-form-group">
          <label className="profile-form-label">Loại địa chỉ</label>
          <select className="profile-form-input" value={form.addressType} onChange={e => setForm(f => ({ ...f, addressType: e.target.value as AddressPayload['addressType'] }))}>
            <option value="CURRENT">Thường trú</option>
            <option value="PERMANENT">Hộ khẩu thường trú</option>
            <option value="FAMILY_HOME">Nhà gia đình</option>
          </select>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Số nhà, đường</label>
          <input className="profile-form-input" value={form.addressLine ?? ''} onChange={e => setForm(f => ({ ...f, addressLine: e.target.value }))} placeholder="VD: 123 Nguyễn Văn A"/>
        </div>
        <AddressLocationFields form={form} onChange={setForm} />
        <label className="profile-toggle-row">
          <input type="checkbox" className="profile-checkbox" checked={form.current} onChange={e => setForm(f => ({ ...f, current: e.target.checked }))}/>
          <span className="profile-toggle-label">Đây là địa chỉ hiện tại đang cư trú</span>
        </label>
      </div>
    </Modal>
  );
}

/* ============================================================
   FAMILY TAB (/api/me/family-members)
   ============================================================ */
const REL_LABELS: Record<string, string> = { MOTHER: 'Mẹ', FATHER: 'Bố', GUARDIAN: 'Người giám hộ', OTHER: 'Khác' };

function FamilyTab({ onModified }: { onModified?: () => void }) {
  const [items, setItems] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<FamilyMember | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FamilyMember | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setItems(await myFamilyApi.list());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await myFamilyApi.remove(deleteTarget.id);
      await reload();
      setDeleteTarget(null);
      onModified?.();
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa thông tin nhân thân');
    } finally {
      setDeleting(false);
    }
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
        <div className="profile-empty-state"><span className="spinner" style={{ width: 20, height: 20, borderWidth: 2.5 }}/></div>
      ) : items.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <circle cx="9" cy="7" r="4" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M1 21v-2a4 4 0 0 1 4-4h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M17 11v6M14 14h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <p>Chưa có thông tin nhân thân. Thêm thông tin cha và mẹ để hoàn thiện hồ sơ.</p>
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
              {m.unavailable && <div className="profile-sub-card-row"><span style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: 'var(--text-xs)' }}>Đã mất / Không liên lạc được</span></div>}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(m); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(m)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <FamilyModal
          item={editItem}
          open={showModal}
          onClose={() => setShowModal(false)}
          onSaved={() => {
            setShowModal(false);
            reload();
            onModified?.();
          }}
        />
      )}
      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        onConfirm={handleDelete}
        deleting={deleting}
        error={deleteErr}
      />
    </div>
  );
}

function FamilyModal({ item, open, onClose, onSaved }:
  { item: FamilyMember | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FamilyMemberPayload>({ relationship: 'OTHER', hasCollegeDegree: false, unavailable: false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) {
      setForm({
        relationship: item.relationship,
        fullName: item.fullName ?? '',
        dateOfBirth: item.dateOfBirth ?? '',
        hasCollegeDegree: item.hasCollegeDegree,
        unavailable: item.unavailable,
        phoneNumber: item.phoneNumber ?? '',
      });
    } else {
      setForm({ relationship: 'OTHER', fullName: '', dateOfBirth: '', hasCollegeDegree: false, unavailable: false, phoneNumber: '' });
    }
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = {
        ...form,
        fullName: form.fullName?.trim() || undefined,
        dateOfBirth: form.dateOfBirth || undefined,
        phoneNumber: form.phoneNumber?.trim() || undefined,
      };
      if (item) await myFamilyApi.update(item.id, payload);
      else await myFamilyApi.create(payload);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi lưu thông tin nhân thân');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? 'Cập nhật nhân thân' : 'Thêm thành viên nhân thân'}
      size="md"
      onClose={onClose}
      footer={
        <>
          <button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={save} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm"/>}
            {item ? 'Lưu' : 'Thêm mới'}
          </button>
        </>
      }
    >
      {err && <div className="profile-alert-error" style={{ marginBottom: 12 }}>{err}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Quan hệ <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <select className="profile-form-input" value={form.relationship} onChange={e => setForm(f => ({ ...f, relationship: e.target.value as FamilyMemberPayload['relationship'] }))}>
              <option value="MOTHER">Mẹ</option>
              <option value="FATHER">Bố</option>
              <option value="GUARDIAN">Người giám hộ</option>
              <option value="OTHER">Khác</option>
            </select>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Họ và tên</label>
            <input className="profile-form-input" value={form.fullName ?? ''} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Ngày sinh</label>
            <input className="profile-form-input" type="date" value={form.dateOfBirth ?? ''} onChange={e => setForm(f => ({ ...f, dateOfBirth: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại</label>
            <input className="profile-form-input" value={form.phoneNumber ?? ''} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))}/>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24 }}>
          <label className="profile-toggle-row">
            <input type="checkbox" className="profile-checkbox" checked={form.hasCollegeDegree} onChange={e => setForm(f => ({ ...f, hasCollegeDegree: e.target.checked }))}/>
            <span className="profile-toggle-label">Có bằng đại học</span>
          </label>
          <label className="profile-toggle-row">
            <input type="checkbox" className="profile-checkbox" checked={form.unavailable} onChange={e => setForm(f => ({ ...f, unavailable: e.target.checked }))}/>
            <span className="profile-toggle-label">Đã mất / Không liên lạc</span>
          </label>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   EMERGENCY TAB (/api/me/emergency-contacts)
   ============================================================ */
function EmergencyTab({ onModified }: { onModified?: () => void }) {
  const [items, setItems] = useState<EmergencyContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<EmergencyContact | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EmergencyContact | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setItems(await myEmergencyApi.list());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await myEmergencyApi.remove(deleteTarget.id);
      await reload();
      setDeleteTarget(null);
      onModified?.();
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa liên hệ');
    } finally {
      setDeleting(false);
    }
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
        <div className="profile-empty-state"><span className="spinner" style={{ width: 20, height: 20, borderWidth: 2.5 }}/></div>
      ) : sorted.length === 0 ? (
        <div className="profile-empty-state">
          <div className="profile-empty-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.82a19.79 19.79 0 01-3.07-8.64A2 2 0 012 .01h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 14v2.92z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            </svg>
          </div>
          <p>Chưa có liên hệ khẩn cấp. Thêm ít nhất 1 liên hệ có tên, SĐT và thứ tự ưu tiên &ge; 1 để bảo đảm an toàn.</p>
        </div>
      ) : (
        <div className="profile-sub-grid" style={{ marginTop: 'var(--space-3)' }}>
          {sorted.map(c => (
            <div key={c.id} className="profile-sub-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--space-2)' }}>
                <span className="priority-badge">{c.priority}</span>
                <div className="profile-sub-card-title" style={{ margin: 0 }}>{c.fullName}</div>
              </div>
              {c.relationship && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Quan hệ:</span>
                  <span>{c.relationship}</span>
                </div>
              )}
              <div className="profile-sub-card-row">
                <span className="profile-sub-card-label">SĐT:</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--accent)' }}>{c.phoneNumber}</span>
              </div>
              {c.address && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Địa chỉ:</span>
                  <span>{c.address}</span>
                </div>
              )}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(c); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(c)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <EmergencyModal
          item={editItem}
          open={showModal}
          onClose={() => setShowModal(false)}
          onSaved={() => {
            setShowModal(false);
            reload();
            onModified?.();
          }}
        />
      )}
      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        onConfirm={handleDelete}
        deleting={deleting}
        error={deleteErr}
      />
    </div>
  );
}

function EmergencyModal({ item, open, onClose, onSaved }:
  { item: EmergencyContact | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<EmergencyContactPayload>({ fullName: '', phoneNumber: '', priority: 1 });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) {
      setForm({ fullName: item.fullName, relationship: item.relationship ?? '', phoneNumber: item.phoneNumber, address: item.address ?? '', priority: item.priority });
    } else {
      setForm({ fullName: '', relationship: '', phoneNumber: '', address: '', priority: 1 });
    }
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    if (!form.fullName.trim()) { setErr('Họ tên là bắt buộc'); return; }
    if (!form.phoneNumber.trim()) { setErr('Số điện thoại là bắt buộc'); return; }
    if (!form.priority || form.priority < 1) { setErr('Thứ tự ưu tiên phải ≥ 1'); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = { ...form, relationship: form.relationship?.trim() || undefined, address: form.address?.trim() || undefined };
      if (item) await myEmergencyApi.update(item.id, payload);
      else await myEmergencyApi.create(payload);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi lưu liên hệ khẩn cấp');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? 'Cập nhật liên hệ khẩn cấp' : 'Thêm liên hệ khẩn cấp'}
      size="md"
      onClose={onClose}
      footer={
        <>
          <button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={save} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm"/>}
            {item ? 'Lưu' : 'Thêm mới'}
          </button>
        </>
      }
    >
      {err && <div className="profile-alert-error" style={{ marginBottom: 12 }}>{err}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Họ và tên <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" value={form.fullName} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" value={form.phoneNumber} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Mối quan hệ</label>
            <input className="profile-form-input" placeholder="VD: Cha, Mẹ, Anh/Chị..." value={form.relationship ?? ''} onChange={e => setForm(f => ({ ...f, relationship: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Thứ tự ưu tiên <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" type="number" min={1} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: Number(e.target.value) }))}/>
          </div>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Địa chỉ</label>
          <input className="profile-form-input" value={form.address ?? ''} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}/>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   POST-GRAD TAB (/api/me/post-graduation-contacts)
   ============================================================ */
function PostGradTab() {
  const [items, setItems] = useState<PostGradContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<PostGradContact | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PostGradContact | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      setItems(await myPostGradApi.list());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await myPostGradApi.remove(deleteTarget.id);
      await reload();
      setDeleteTarget(null);
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa liên hệ');
    } finally {
      setDeleting(false);
    }
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
        <div className="profile-empty-state"><span className="spinner" style={{ width: 20, height: 20, borderWidth: 2.5 }}/></div>
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
              {c.phoneNumber && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">SĐT:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{c.phoneNumber}</span>
                </div>
              )}
              {c.email && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Email:</span>
                  <span style={{ color: 'var(--accent)' }}>{c.email}</span>
                </div>
              )}
              {c.address && (
                <div className="profile-sub-card-row">
                  <span className="profile-sub-card-label">Địa chỉ:</span>
                  <span>{c.address}</span>
                </div>
              )}
              <div className="profile-sub-card-actions">
                <button className="profile-sub-action-btn" title="Chỉnh sửa" onClick={() => { setEditItem(c); setShowModal(true); }}><IcoEdit/></button>
                <button className="profile-sub-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(c)}><IcoTrash/></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {showModal && (
        <PostGradModal
          item={editItem}
          open={showModal}
          onClose={() => setShowModal(false)}
          onSaved={() => {
            setShowModal(false);
            reload();
          }}
        />
      )}
      <DeleteConfirmModal
        open={!!deleteTarget}
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        onConfirm={handleDelete}
        deleting={deleting}
        error={deleteErr}
      />
    </div>
  );
}

function PostGradModal({ item, open, onClose, onSaved }:
  { item: PostGradContact | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<PostGradContactPayload>({});
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) {
      setForm({ fullName: item.fullName ?? '', phoneNumber: item.phoneNumber ?? '', email: item.email ?? '', address: item.address ?? '' });
    } else {
      setForm({ fullName: '', phoneNumber: '', email: '', address: '' });
    }
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    if (!validEmail(form.email)) { setErr(EMAIL_ERROR); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = {
        fullName: form.fullName?.trim() || undefined,
        phoneNumber: form.phoneNumber?.trim() || undefined,
        email: form.email?.trim() || undefined,
        address: form.address?.trim() || undefined,
      };
      if (item) await myPostGradApi.update(item.id, payload);
      else await myPostGradApi.create(payload);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi lưu liên hệ');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={item ? 'Cập nhật liên hệ sau TN' : 'Thêm liên hệ sau tốt nghiệp'}
      size="md"
      onClose={onClose}
      footer={
        <>
          <button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={save} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm"/>}
            {item ? 'Lưu' : 'Thêm mới'}
          </button>
        </>
      }
    >
      {err && <div className="profile-alert-error" style={{ marginBottom: 12 }}>{err}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="profile-form-group">
          <label className="profile-form-label">Họ và tên</label>
          <input className="profile-form-input" value={form.fullName ?? ''} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))}/>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại</label>
            <input className="profile-form-input" value={form.phoneNumber ?? ''} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Email</label>
            <input className="profile-form-input" type="email" value={form.email ?? ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}/>
          </div>
        </div>
        <div className="profile-form-group">
          <label className="profile-form-label">Địa chỉ</label>
          <input className="profile-form-input" value={form.address ?? ''} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}/>
        </div>
      </div>
    </Modal>
  );
}

/* ============================================================
   PERSONAL INFO EDIT TAB (/api/me/profile)
   ============================================================ */
function PersonalTab({
  student,
  onUpdated,
}: {
  student: StudentDetail;
  onUpdated: (s: StudentDetail, comp?: CompletionStatus) => void;
}) {
  const { options, error: catalogError, retry: retryCatalog } = useProfileOptions();
  const [form, setForm] = useState({
    personalEmail: student.personalEmail ?? '',
    phoneNumber: student.phoneNumber ?? '',
    facebookUrl: student.facebookUrl ?? '',
    avatarUrl: student.avatarUrl ?? '',
    placeOfBirth: student.placeOfBirth ?? '',
    oldPlaceOfBirth: student.oldPlaceOfBirth ?? '',
    ethnicity: student.ethnicity ?? '',
    nationality: student.nationality ?? 'Việt Nam',
      birthCountryCode: student.birthCountryCode ?? 'VN',
      originCountryCode: student.originCountryCode ?? 'VN',
    religion: student.religion ?? '',
    citizenIdIssueDate: student.citizenIdIssueDate ?? '',
    healthInsuranceNumber: student.healthInsuranceNumber ?? '',
    healthInsuranceExpiry: student.healthInsuranceExpiry ?? '',
    freeHealthInsurance: student.freeHealthInsurance ?? false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setForm({
      personalEmail: student.personalEmail ?? '',
      phoneNumber: student.phoneNumber ?? '',
      facebookUrl: student.facebookUrl ?? '',
      avatarUrl: student.avatarUrl ?? '',
      placeOfBirth: student.placeOfBirth ?? '',
      oldPlaceOfBirth: student.oldPlaceOfBirth ?? '',
      ethnicity: student.ethnicity ?? '',
      nationality: student.nationality ?? 'Việt Nam',
      birthCountryCode: student.birthCountryCode ?? 'VN',
      originCountryCode: student.originCountryCode ?? 'VN',
      religion: student.religion ?? '',
      citizenIdIssueDate: student.citizenIdIssueDate ?? '',
      healthInsuranceNumber: student.healthInsuranceNumber ?? '',
      healthInsuranceExpiry: student.healthInsuranceExpiry ?? '',
      freeHealthInsurance: student.freeHealthInsurance ?? false,
    });
  }, [student]);

  function reset() {
    setForm({
      personalEmail: student.personalEmail ?? '',
      phoneNumber: student.phoneNumber ?? '',
      facebookUrl: student.facebookUrl ?? '',
      avatarUrl: student.avatarUrl ?? '',
      placeOfBirth: student.placeOfBirth ?? '',
      oldPlaceOfBirth: student.oldPlaceOfBirth ?? '',
      ethnicity: student.ethnicity ?? '',
      nationality: student.nationality ?? 'Việt Nam',
      birthCountryCode: student.birthCountryCode ?? 'VN',
      originCountryCode: student.originCountryCode ?? 'VN',
      religion: student.religion ?? '',
      citizenIdIssueDate: student.citizenIdIssueDate ?? '',
      healthInsuranceNumber: student.healthInsuranceNumber ?? '',
      healthInsuranceExpiry: student.healthInsuranceExpiry ?? '',
      freeHealthInsurance: student.freeHealthInsurance ?? false,
    });
    setErr(null); setSuccess(false);
  }

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    if (!validEmail(form.personalEmail)) { setErr(EMAIL_ERROR); return; }
    setSubmitting(true); setErr(null); setSuccess(false);
    try {
      const payload: UpdateStudentProfilePayload = {
        avatarUrl: form.avatarUrl.trim() || null,
        birthCountryCode: form.birthCountryCode,
        originCountryCode: form.originCountryCode,
        placeOfBirth: form.placeOfBirth.trim() || null,
        oldPlaceOfBirth: form.oldPlaceOfBirth.trim() || null,
        ethnicity: form.ethnicity.trim() || null,
        nationality: form.nationality.trim() || null,
        religion: form.religion.trim() || null,
        citizenIdIssueDate: form.citizenIdIssueDate || null,
        healthInsuranceNumber: form.healthInsuranceNumber.trim() || null,
        healthInsuranceExpiry: form.healthInsuranceExpiry || null,
        freeHealthInsurance: form.freeHealthInsurance,
        personalEmail: form.personalEmail.trim() || null,
        phoneNumber: form.phoneNumber.trim() || null,
        facebookUrl: form.facebookUrl.trim() || null,
      };

      const comp = await myProfileApi.updateProfile(payload);
      const updated = await myProfileApi.getProfile();
      onUpdated(updated, comp);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Lỗi cập nhật hồ sơ cá nhân');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="profile-edit-section">
      <div className="profile-immutable-notice">
        <IcoInfo/>
        <span>
          Các thông tin như Họ tên, MSSV, Ngày sinh, Giới tính, Số CCCD, Ngành/Lớp và Tài khoản ngân hàng do Nhà trường quản lý và xác thực.
          Bạn có thể tự cập nhật các thông tin liên lạc, nơi sinh, dân tộc, BHYT bên dưới.
        </span>
      </div>

      {/* Liên lạc & Ảnh đại diện */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title"><IcoPhone/> Ảnh đại diện & Thông tin liên lạc cá nhân</span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', marginBottom: 'var(--space-4)', padding: 'var(--space-3)', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--accent-btn)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0, border: '2px solid var(--border-brand)', position: 'relative' }}>
            {form.avatarUrl ? (
              <img src={form.avatarUrl} alt="Xem trước avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { (e.currentTarget as HTMLElement).style.display = 'none'; }} />
            ) : null}
            <span style={{ color: '#fff', fontSize: 'var(--text-sm)', fontWeight: 600 }}>{student.fullName.slice(0, 2).toUpperCase()}</span>
          </div>
          <div style={{ flex: 1 }}>
            <label className="profile-form-label" htmlFor="personal-avatar-url">Đường dẫn ảnh đại diện (Avatar URL)</label>
            <input
              id="personal-avatar-url"
              className="profile-form-input"
              type="url"
              placeholder="https://example.com/avatar.jpg"
              value={form.avatarUrl}
              onChange={e => setForm(f => ({ ...f, avatarUrl: e.target.value }))}
            />
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4, display: 'block' }}>Hỗ trợ liên kết ảnh trực tiếp (JPG, PNG, WebP)</span>
          </div>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Email cá nhân <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" type="email" placeholder="example@gmail.com" value={form.personalEmail} onChange={e => setForm(f => ({ ...f, personalEmail: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Số điện thoại cá nhân <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" type="tel" placeholder="0912 345 678" value={form.phoneNumber} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))}/>
          </div>
        </div>
        <div style={{ marginTop: 'var(--space-3)' }}>
          <div className="profile-form-group">
            <label className="profile-form-label">Facebook / Mạng xã hội</label>
            <input className="profile-form-input" placeholder="https://facebook.com/..." value={form.facebookUrl} onChange={e => setForm(f => ({ ...f, facebookUrl: e.target.value }))}/>
          </div>
        </div>
      </div>

      <div className="profile-form-divider"/>

      {/* Nơi sinh & nhân khẩu */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <path d="M7 1.5C4.515 1.5 2.5 3.515 2.5 6S4.515 10.5 7 10.5 11.5 8.485 11.5 6 9.485 1.5 7 1.5z" stroke="currentColor" strokeWidth="1.25"/>
              <path d="M4 12.5c0-1.657 1.343-3 3-3s3 1.343 3 3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
            </svg>
            Nơi sinh, dân tộc, tôn giáo
          </span>
        </div>
        {catalogError && (
          <div role="alert" className="profile-alert-error" style={{ marginBottom: 'var(--space-3)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 4.5zm0 7a.875.875 0 110-1.75.875.875 0 010 1.75z"/>
              </svg>
              {catalogError}
            </span>
            <button type="button" onClick={retryCatalog}>Thử lại</button>
          </div>
        )}
        <div className="profile-form-row">
          <CountrySelect label="Quốc gia nơi sinh" value={form.birthCountryCode} countries={options?.countries ?? []}
            onChange={birthCountryCode => setForm(f => ({ ...f, birthCountryCode, placeOfBirth: '' }))} />
          <ProvinceField label="Nơi sinh *" value={form.placeOfBirth} countryCode={form.birthCountryCode} options={options}
            onChange={placeOfBirth => setForm(f => ({ ...f, placeOfBirth }))} />
        </div>
        <div className="profile-form-row">
          <CountrySelect label="Quốc gia quê quán" value={form.originCountryCode} countries={options?.countries ?? []}
            onChange={originCountryCode => setForm(f => ({ ...f, originCountryCode, oldPlaceOfBirth: '' }))} />
          <ProvinceField label="Quê quán / nơi sinh trước đây" value={form.oldPlaceOfBirth} countryCode={form.originCountryCode} options={options} historical
            onChange={oldPlaceOfBirth => setForm(f => ({ ...f, oldPlaceOfBirth }))} />
        </div>
        <div className="profile-form-row-3" style={{ marginTop: 'var(--space-3)' }}>
          <CatalogSelect label="Dân tộc *" value={form.ethnicity} options={options?.ethnicities ?? []} disabled={!options}
            onChange={ethnicity => setForm(f => ({ ...f, ethnicity }))} />
          <CatalogSelect label="Quốc tịch *" value={form.nationality} options={options?.countries.map(c => c.name) ?? []} disabled={!options}
            onChange={nationality => setForm(f => ({ ...f, nationality }))} />
          <CatalogSelect label="Tôn giáo" value={form.religion} options={options?.religions ?? []} disabled={!options}
            onChange={religion => setForm(f => ({ ...f, religion }))} />
        </div>
      </div>

      <div className="profile-form-divider"/>

      {/* CCCD bổ sung */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
              <circle cx="5" cy="6" r="1.5" fill="currentColor"/>
              <path d="M8 5h3M8 7h2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            Căn cước công dân
          </span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Số CCCD (Nhà trường quản lý)</label>
            <input className="profile-form-input mono" value={student.citizenId ?? 'Chưa cập nhật'} disabled style={{ opacity: 0.7 }}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Ngày cấp CCCD <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" type="date" value={form.citizenIdIssueDate} onChange={e => setForm(f => ({ ...f, citizenIdIssueDate: e.target.value }))}/>
          </div>
        </div>
      </div>

      <div className="profile-form-divider"/>

      {/* BHYT */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title"><IcoShield/> Bảo hiểm y tế (BHYT)</span>
        </div>
        <div className="profile-form-row">
          <div className="profile-form-group">
            <label className="profile-form-label">Số thẻ BHYT <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input mono" placeholder="VD: HS4010..." value={form.healthInsuranceNumber} onChange={e => setForm(f => ({ ...f, healthInsuranceNumber: e.target.value }))}/>
          </div>
          <div className="profile-form-group">
            <label className="profile-form-label">Ngày hết hạn BHYT <span style={{ color: 'var(--text-error)' }}>*</span></label>
            <input className="profile-form-input" type="date" value={form.healthInsuranceExpiry} onChange={e => setForm(f => ({ ...f, healthInsuranceExpiry: e.target.value }))}/>
          </div>
        </div>
        <label className="profile-toggle-row" style={{ marginTop: 'var(--space-2)' }}>
          <input type="checkbox" className="profile-checkbox" checked={form.freeHealthInsurance} onChange={e => setForm(f => ({ ...f, freeHealthInsurance: e.target.checked }))}/>
          <span className="profile-toggle-label">Được cấp BHYT miễn phí (diện hộ nghèo, chính sách xã hội...)</span>
        </label>
      </div>

      {success && <div className="profile-alert-success"><IcoCheck/> Cập nhật thông tin cá nhân thành công! Mức độ hoàn thiện hồ sơ đã được đồng bộ.</div>}
      {err && <div className="profile-alert-error"><IcoWarn/> {err}</div>}

      <div className="profile-save-bar">
        <button className="btn-profile-cancel" onClick={reset} disabled={submitting}>Đặt lại</button>
        <button className="btn-profile-save" onClick={save} disabled={submitting}>
          {submitting ? <><span className="spinner spinner-sm"/> Đang lưu...</> : <><IcoCheck/> Lưu thay đổi</>}
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      {/* Thông tin học vụ do trường quản lý */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title">
            <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
              <rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.25"/>
              <path d="M4 6h6M4 8h4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round"/>
            </svg>
            Thông tin định danh &amp; học vụ (do nhà trường quản lý)
          </span>
        </div>
        <div className="profile-info-grid">
          <InfoItem label="MSSV" value={student.studentCode} mono/>
          <InfoItem label="Họ và tên" value={student.fullName}/>
          <InfoItem label="Ngày sinh" value={student.dateOfBirth}/>
          <InfoItem label="Giới tính" value={student.gender ? GENDER_LABELS[student.gender] : undefined}/>
          <InfoItem label="Số CCCD" value={student.citizenId} mono/>
          <InfoItem label="Email trường" value={student.schoolEmail} mono/>
          <InfoItem label="SĐT gia đình" value={student.familyPhoneNumber}/>
          <InfoItem label="Số tài khoản NH" value={student.bankAccountNumber} mono/>
          <InfoItem label="Ngân hàng" value={student.bankName}/>
          <InfoItem
            label="Trạng thái hồ sơ"
            value={student.profileStatus === 'COMPLETE' ? 'Hoàn thiện' : 'Chưa hoàn thiện'}
          />
        </div>
      </div>

      {/* Thông tin cá nhân sinh viên tự khai */}
      <div>
        <div className="profile-section-header" style={{ marginBottom: 'var(--space-3)' }}>
          <span className="profile-section-title">
            <IcoCheck/> Thông tin cá nhân (sinh viên tự khai báo)
          </span>
        </div>
        <div className="profile-info-grid">
          <InfoItem label="Quốc gia nơi sinh" value={countryLabel(student.birthCountryCode)}/>
          <InfoItem label="Nơi sinh" value={student.placeOfBirth}/>
          <InfoItem label="Quê quán" value={student.oldPlaceOfBirth}/>
          <InfoItem label="Dân tộc" value={student.ethnicity}/>
          <InfoItem label="Quốc tịch" value={student.nationality}/>
          <InfoItem label="Tôn giáo" value={student.religion}/>
          <InfoItem label="Ngày cấp CCCD" value={student.citizenIdIssueDate}/>
          <InfoItem label="Email cá nhân" value={student.personalEmail} mono/>
          <InfoItem label="Số điện thoại" value={student.phoneNumber} mono/>
          <InfoItem label="Facebook" value={student.facebookUrl}/>
          <InfoItem label="Số thẻ BHYT" value={student.healthInsuranceNumber} mono/>
          <InfoItem label="Hạn BHYT" value={student.healthInsuranceExpiry}/>
          <InfoItem label="BHYT miễn phí" value={student.freeHealthInsurance ? 'Có' : 'Không'}/>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   MAIN PROFILE PAGE
   ============================================================ */
export default function ProfilePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [completion, setCompletion] = useState<CompletionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [completionLoading, setCompletionLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const refreshCompletion = useCallback(async () => {
    try {
      const comp = await myProfileApi.getCompletion();
      setCompletion(comp);
    } catch {
      /* ignore background refresh failure */
    }
  }, []);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setLoadErr(null);
    setCompletionLoading(true);
    try {
      const [sv, comp] = await Promise.all([
        myProfileApi.getProfile(),
        myProfileApi.getCompletion().catch(() => null),
      ]);
      setStudent(sv);
      setCompletion(comp);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Lỗi tải hồ sơ sinh viên');
    } finally {
      setLoading(false);
      setCompletionLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.role === 'STUDENT') {
      loadProfile();
    }
  }, [user, loadProfile]);

  useEffect(() => {
    if (user && user.role !== 'STUDENT') {
      navigate('/', { replace: true });
    }
  }, [user, navigate]);

  if (!user) return null;

  if (loading) {
    return (
      <div className="profile-page">
        <AppHeader/>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-3)', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
            <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3, borderTopColor: 'var(--accent)' }}/>
            Đang tải hồ sơ sinh viên...
          </div>
        </div>
      </div>
    );
  }

  if (loadErr || !student) {
    return (
      <div className="profile-page">
        <AppHeader/>
        <div className="profile-inner">
          <div className="profile-alert-error">
            <IcoInfo/>
            <div>
              <strong>Không thể tải hồ sơ:</strong> {loadErr ?? 'Không tìm thấy dữ liệu sinh viên.'}
            </div>
          </div>
          <button className="btn-secondary" style={{ width: 'fit-content' }} onClick={loadProfile}>
            Thử lại
          </button>
        </div>
      </div>
    );
  }

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
                <div className="profile-avatar">
                  {student.avatarUrl ? (
                    <img
                      src={student.avatarUrl}
                      alt={student.fullName}
                      className="profile-avatar-img"
                      onError={e => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
                    />
                  ) : null}
                  <span>{initials(student.fullName)}</span>
                </div>
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
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }}/>
                    {STATUS_LABELS[student.status] ?? student.status}
                  </span>
                  {student.gender && <span className="profile-chip">{GENDER_LABELS[student.gender] ?? student.gender}</span>}
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

          <div
            id={`profile-tabpanel-${activeTab}`}
            className="profile-tab-panel"
            role="tabpanel"
            aria-labelledby={`profile-tab-${activeTab}`}
          >
            {activeTab === 'overview' && <OverviewTab student={student}/>}
            {activeTab === 'personal' && (
              <PersonalTab
                student={student}
                onUpdated={(updatedStudent, updatedCompletion) => {
                  setStudent(updatedStudent);
                  if (updatedCompletion) setCompletion(updatedCompletion);
                  else refreshCompletion();
                }}
              />
            )}
            {activeTab === 'addresses' && <AddressTab onModified={refreshCompletion}/>}
            {activeTab === 'family' && <FamilyTab onModified={refreshCompletion}/>}
            {activeTab === 'emergency' && <EmergencyTab onModified={refreshCompletion}/>}
            {activeTab === 'postgrad' && <PostGradTab/>}
          </div>
        </div>
      </div>
    </div>
  );
}
