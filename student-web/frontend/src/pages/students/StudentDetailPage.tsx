import { validPhone, validEmail, PHONE_ERROR, EMAIL_ERROR } from '../../utils/contactValidation';
import { AddressLocationFields, countryLabel } from '../../components/profile/ProfileFields';
/**
 * StudentDetailPage — xem chi tiết sinh viên, completion status,
 * và quản lý sub-resources: địa chỉ, nhân thân, liên hệ khẩn cấp, liên hệ sau TN
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AppHeader from '../../components/AppHeader';
import Modal from '../../components/Modal';
import EditStudentModal from '../../components/students/EditStudentModal';
import SubResourceSection from '../../components/students/SubResourceSection';
import { studentApi, addressApi, familyApi, emergencyApi, postGradApi } from '../../api/studentApi';
import { majorApi, classApi, programApi } from '../../api/academicApi';
import type {
  StudentDetail, CompletionStatus,
  Address, AddressPayload,
  FamilyMember, FamilyMemberPayload,
  EmergencyContact, EmergencyContactPayload,
  PostGradContact, PostGradContactPayload,
} from '../../types/student';
import '../StudentsPage.css';

const GENDER_LABELS: Record<string, string> = { MALE: 'Nam', FEMALE: 'Nữ', OTHER: 'Khác' };
const STATUS_COLORS: Record<string, string> = {
  ACTIVE: '#16a34a', GRADUATED: '#2563eb', SUSPENDED: '#ca8a04', INACTIVE: '#9ca3af',
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Đang học', GRADUATED: 'Tốt nghiệp', SUSPENDED: 'Đình chỉ', INACTIVE: 'Ngừng HĐ',
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
  currentAddress: 'Địa chỉ thường trú',
  permanentOrFamilyAddress: 'Hộ khẩu / Nhà gia đình',
  father: 'Thông tin Bố (họ tên, ngày sinh)',
  mother: 'Thông tin Mẹ (họ tên, ngày sinh)',
  familyMember: 'Nhân thân gia đình',
  emergencyContact: 'Liên hệ khẩn cấp',
};

function initials(name: string) {
  return name.split(' ').map(p => p[0]).slice(-2).join('').toUpperCase();
}

export default function StudentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [student, setStudent]       = useState<StudentDetail | null>(null);
  const [completion, setCompletion] = useState<CompletionStatus | null>(null);
  const [loading, setLoading]       = useState(true);
  const [loadErr, setLoadErr]       = useState<string | null>(null);
  const [showEdit, setShowEdit]     = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [showDeactivate, setShowDeactivate] = useState(false);

  // Sub-resources
  const [addresses, setAddresses]     = useState<Address[]>([]);
  const [family, setFamily]           = useState<FamilyMember[]>([]);
  const [emergency, setEmergency]     = useState<EmergencyContact[]>([]);
  const [postGrad, setPostGrad]       = useState<PostGradContact[]>([]);

  const studentId = Number(id);

  // Academic lookup maps
  const [classMap, setClassMap]     = useState<Record<number, string>>({});
  const [majorMap, setMajorMap]     = useState<Record<number, string>>({});
  const [programMap, setProgramMap] = useState<Record<number, string>>({});

  useEffect(() => {
    classApi.listAll().then(r => setClassMap(Object.fromEntries(r.content.map(c => [c.id, c.code])))).catch(() => {});
    majorApi.listAll().then(r => setMajorMap(Object.fromEntries(r.content.map(m => [m.id, m.name])))).catch(() => {});
    programApi.listAll().then(r => setProgramMap(Object.fromEntries(r.content.map(p => [p.id, p.name])))).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setLoadErr(null);
    try {
      const [sv, cmp, addrs, fam, emg, pg] = await Promise.all([
        studentApi.get(studentId),
        studentApi.completion(studentId),
        addressApi.list(studentId),
        familyApi.list(studentId),
        emergencyApi.list(studentId),
        postGradApi.list(studentId),
      ]);
      setStudent(sv); setCompletion(cmp);
      setAddresses(addrs); setFamily(fam);
      setEmergency(emg); setPostGrad(pg);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Lỗi tải dữ liệu');
    } finally { setLoading(false); }
  }, [studentId]);

  useEffect(() => { load(); }, [load]);

  async function handleDeactivate() {
    if (!student) return;
    setDeactivating(true);
    try { await studentApi.deactivate(student.id); navigate('/students'); }
    catch (e) { alert(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setDeactivating(false); }
  }

  if (loading) return (
    <div className="students-page">
      <AppHeader />
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
      </div>
    </div>
  );

  if (loadErr || !student) return (
    <div className="students-page">
      <AppHeader />
      <div className="student-detail-inner">
        <button className="back-btn" onClick={() => navigate('/students')}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          Quay lại
        </button>
        <div className="section-error">{loadErr ?? 'Không tìm thấy sinh viên'}</div>
      </div>
    </div>
  );

  const isComplete = completion?.status === 'COMPLETE' || completion?.complete === true || (completion?.missingFields && completion.missingFields.length === 0);
  const missingCount = completion?.missingFields?.length ?? 0;
  const totalFields = 17;
  const pct = isComplete ? 100 : Math.max(0, Math.min(99, Math.round(((totalFields - missingCount) / totalFields) * 100)));
  const displayPct = isComplete ? 100 : pct;

  return (
    <div className="student-detail-page">
      <AppHeader />
      <div className="student-detail-inner">
        {/* Back */}
        <button className="back-btn" onClick={() => navigate('/students')}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          Quay lại danh sách
        </button>

        {/* Profile card */}
        <div className="student-profile-card">
          <div className="student-avatar" style={{ position: 'relative', overflow: 'hidden' }}>
            {student.avatarUrl ? (
              <img
                src={student.avatarUrl}
                alt={student.fullName}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }}
                onError={e => { (e.currentTarget as HTMLElement).style.display = 'none'; }}
              />
            ) : null}
            <span>{initials(student.fullName)}</span>
          </div>
          <div className="student-info">
            <h2>{student.fullName}</h2>
            <div className="student-meta">
              <span className="meta-chip" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{student.studentCode}</span>
              <span className="meta-chip">
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS_COLORS[student.status], display: 'inline-block' }} />
                {STATUS_LABELS[student.status]}
              </span>
              {student.classId && <span className="meta-chip">🏫 {classMap[student.classId] ?? `Lớp #${student.classId}`}</span>}
              {student.majorId && <span className="meta-chip">📚 {majorMap[student.majorId] ?? `Ngành #${student.majorId}`}</span>}
              {student.gender && <span className="meta-chip">{GENDER_LABELS[student.gender]}</span>}
            </div>
          </div>
          <div className="student-card-actions">
            <button className="btn-secondary" onClick={() => setShowEdit(true)}>
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M9.5 2.5L11.5 4.5L5 11H3V9L9.5 2.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/></svg>
              Chỉnh sửa
            </button>
            {student.status !== 'INACTIVE' && (
              <button className="btn-danger" style={{ fontSize: 'var(--text-sm)' }} onClick={() => setShowDeactivate(true)}>
                Ngừng HĐ
              </button>
            )}
          </div>
        </div>

        {/* Completion */}
        {completion && (
          <div className="completion-card">
            <div className="completion-header">
              <span className="completion-title">📋 Mức độ hoàn thiện hồ sơ</span>
              <span className="completion-pct" style={{ color: isComplete ? '#16a34a' : 'var(--accent)' }}>
                {isComplete ? '✓ Hoàn thiện' : `${displayPct}%`}
              </span>
            </div>
            <div className="completion-bar">
              <div className={`completion-fill ${isComplete ? 'complete' : ''}`} style={{ width: `${displayPct}%` }} />
            </div>
            {missingCount > 0 && (
              <div className="missing-fields">
                {completion.missingFields.map(f => (
                  <span key={f} className="missing-tag" title={f}>
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M5 2v4M5 8h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    {MISSING_FIELD_LABELS[f] ?? f}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Basic info */}
        <div className="detail-section">
          <div className="detail-section-header">
            <span className="detail-section-title">👤 Thông tin cơ bản</span>
          </div>
          <div className="detail-section-body">
            <div className="info-grid">
              <InfoItem label="MSSV" value={student.studentCode} mono />
              <InfoItem label="Họ tên" value={student.fullName} />
              <InfoItem label="Ngày sinh" value={student.dateOfBirth} />
              <InfoItem label="Giới tính" value={student.gender ? GENDER_LABELS[student.gender] : undefined} />
              <InfoItem label="Số CCCD" value={student.citizenId} mono />
              <InfoItem label="Email trường" value={student.schoolEmail} mono />
              <InfoItem label="SĐT gia đình" value={student.familyPhoneNumber} />
            </div>
          </div>
        </div>

        {/* Academic info */}
        <div className="detail-section">
          <div className="detail-section-header">
            <span className="detail-section-title">🎓 Thông tin học vụ</span>
          </div>
          <div className="detail-section-body">
            <div className="info-grid">
              <InfoItem label="Lớp" value={student.classId ? (classMap[student.classId] ?? `Lớp #${student.classId}`) : undefined} />
              <InfoItem label="Ngành" value={student.majorId ? (majorMap[student.majorId] ?? `Ngành #${student.majorId}`) : undefined} />
              <InfoItem label="Chương trình chính" value={student.trainingProgramId ? (programMap[student.trainingProgramId] ?? `CT #${student.trainingProgramId}`) : undefined} />
              {student.secondaryProgramId && <InfoItem label="Chương trình phụ" value={programMap[student.secondaryProgramId] ?? `CT #${student.secondaryProgramId}`} />}
              <InfoItem label="Trạng thái" value={STATUS_LABELS[student.status]} />
            </div>
          </div>
        </div>

        {/* Bank info */}
        <div className="detail-section">
          <div className="detail-section-header">
            <span className="detail-section-title">🏦 Tài khoản ngân hàng</span>
          </div>
          <div className="detail-section-body">
            <div className="info-grid">
              <InfoItem label="Số tài khoản" value={student.bankAccountNumber} mono />
              <InfoItem label="Ngân hàng" value={student.bankName} />
            </div>
          </div>
        </div>

        {/* Personal & Demographic declared info */}
        <div className="detail-section">
          <div className="detail-section-header">
            <span className="detail-section-title">📋 Thông tin nhân khẩu & Khai báo cá nhân</span>
          </div>
          <div className="detail-section-body">
            <div className="info-grid">
              <InfoItem label="Nơi sinh" value={student.placeOfBirth} />
              <InfoItem label="Quê quán" value={student.oldPlaceOfBirth} />
              <InfoItem label="Dân tộc" value={student.ethnicity} />
              <InfoItem label="Quốc tịch" value={student.nationality} />
              <InfoItem label="Tôn giáo" value={student.religion} />
              <InfoItem label="Ngày cấp CCCD" value={student.citizenIdIssueDate} />
              <InfoItem label="Số thẻ BHYT" value={student.healthInsuranceNumber} mono />
              <InfoItem label="Hạn thẻ BHYT" value={student.healthInsuranceExpiry} />
              <InfoItem label="BHYT miễn phí" value={student.freeHealthInsurance ? '✓ Có' : 'Không'} />
              <InfoItem label="Email cá nhân" value={student.personalEmail} mono />
              <InfoItem label="SĐT cá nhân" value={student.phoneNumber} />
              <InfoItem label="Facebook URL" value={student.facebookUrl} />
              <InfoItem label="Trạng thái hồ sơ" value={student.profileStatus === 'COMPLETE' ? '✓ Đã hoàn thiện' : 'Chưa hoàn thiện'} />
              {student.profileCompletedAt && (
                <InfoItem label="Thời gian hoàn thiện" value={student.profileCompletedAt.replace('T', ' ')} />
              )}
            </div>
          </div>
        </div>

        {/* Addresses */}
        <SubResourceSection
          title="📍 Địa chỉ"
          items={addresses}
          onRefresh={async () => setAddresses(await addressApi.list(studentId))}
          renderItem={(addr: Address) => (
            <div key={addr.id} className="sub-card">
              <div className="sub-card-title">{addr.addressType === 'CURRENT' ? '🏠 Thường trú' : addr.addressType === 'PERMANENT' ? '🏡 Hộ khẩu' : '🏘 Gia đình'}</div>
              <div className="sub-card-row"><span className="sub-card-label">Địa chỉ:</span><span>{addr.addressLine ?? '—'}</span></div>
              <div className="sub-card-row"><span className="sub-card-label">Quốc gia:</span><span>{countryLabel(addr.countryCode)}</span></div>
              <div className="sub-card-row"><span className="sub-card-label">Tỉnh/TP:</span><span>{addr.provinceCity ?? '—'}</span></div>
              <div className="sub-card-row"><span className="sub-card-label">Xã/Phường:</span><span>{addr.wardCommune ?? '—'}</span></div>
              {addr.residenceRelation && <div className="sub-card-row"><span className="sub-card-label">Quan hệ:</span><span>{addr.residenceRelation}</span></div>}
              <div className="sub-card-row"><span className="sub-card-label">Hiện tại:</span><span>{addr.current ? '✓ Có' : 'Không'}</span></div>
            </div>
          )}
          AddEditModal={(props) => (
            <AddressModal
              studentId={studentId}
              item={props.item as Address | null}
              open={props.open}
              onClose={props.onClose}
              onSaved={async () => setAddresses(await addressApi.list(studentId))}
            />
          )}
          onDelete={(item) => addressApi.remove(studentId, (item as Address).id)}
          emptyText="Chưa có địa chỉ nào."
        />

        {/* Family */}
        <SubResourceSection
          title="👨‍👩‍👦 Nhân thân"
          items={family}
          onRefresh={async () => setFamily(await familyApi.list(studentId))}
          renderItem={(m: FamilyMember) => (
            <div key={m.id} className="sub-card">
              <div className="sub-card-title">{m.fullName ?? '(Chưa có tên)'}</div>
              <div className="sub-card-row"><span className="sub-card-label">Quan hệ:</span><span>{{ MOTHER: 'Mẹ', FATHER: 'Bố', GUARDIAN: 'Người giám hộ', OTHER: 'Khác' }[m.relationship]}</span></div>
              {m.dateOfBirth && <div className="sub-card-row"><span className="sub-card-label">Ngày sinh:</span><span>{m.dateOfBirth}</span></div>}
              {m.phoneNumber && <div className="sub-card-row"><span className="sub-card-label">SĐT:</span><span>{m.phoneNumber}</span></div>}
              <div className="sub-card-row"><span className="sub-card-label">Bằng ĐH:</span><span>{m.hasCollegeDegree ? '✓ Có' : 'Không'}</span></div>
              {m.unavailable && <div className="sub-card-row"><span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>Đã mất</span></div>}
            </div>
          )}
          AddEditModal={(props) => (
            <FamilyModal
              studentId={studentId}
              item={props.item as FamilyMember | null}
              open={props.open}
              onClose={props.onClose}
              onSaved={async () => setFamily(await familyApi.list(studentId))}
            />
          )}
          onDelete={(item) => familyApi.remove(studentId, (item as FamilyMember).id)}
          emptyText="Chưa có thông tin nhân thân."
        />

        {/* Emergency contacts */}
        <SubResourceSection
          title="🆘 Liên hệ khẩn cấp"
          items={emergency}
          onRefresh={async () => setEmergency(await emergencyApi.list(studentId))}
          renderItem={(c: EmergencyContact) => (
            <div key={c.id} className="sub-card">
              <div className="sub-card-title">{c.fullName} <span style={{ color: 'var(--accent)', fontSize: 'var(--text-xs)' }}>#{c.priority}</span></div>
              {c.relationship && <div className="sub-card-row"><span className="sub-card-label">Quan hệ:</span><span>{c.relationship}</span></div>}
              <div className="sub-card-row"><span className="sub-card-label">SĐT:</span><span>{c.phoneNumber}</span></div>
              {c.address && <div className="sub-card-row"><span className="sub-card-label">Địa chỉ:</span><span>{c.address}</span></div>}
            </div>
          )}
          AddEditModal={(props) => (
            <EmergencyModal
              studentId={studentId}
              item={props.item as EmergencyContact | null}
              open={props.open}
              onClose={props.onClose}
              onSaved={async () => setEmergency(await emergencyApi.list(studentId))}
            />
          )}
          onDelete={(item) => emergencyApi.remove(studentId, (item as EmergencyContact).id)}
          emptyText="Chưa có liên hệ khẩn cấp."
        />

        {/* Post-grad contacts */}
        <SubResourceSection
          title="🎯 Liên hệ sau tốt nghiệp"
          items={postGrad}
          onRefresh={async () => setPostGrad(await postGradApi.list(studentId))}
          renderItem={(c: PostGradContact) => (
            <div key={c.id} className="sub-card">
              <div className="sub-card-title">{c.fullName ?? '(Chưa có tên)'}</div>
              {c.phoneNumber && <div className="sub-card-row"><span className="sub-card-label">SĐT:</span><span>{c.phoneNumber}</span></div>}
              {c.email && <div className="sub-card-row"><span className="sub-card-label">Email:</span><span>{c.email}</span></div>}
              {c.address && <div className="sub-card-row"><span className="sub-card-label">Địa chỉ:</span><span>{c.address}</span></div>}
            </div>
          )}
          AddEditModal={(props) => (
            <PostGradModal
              studentId={studentId}
              item={props.item as PostGradContact | null}
              open={props.open}
              onClose={props.onClose}
              onSaved={async () => setPostGrad(await postGradApi.list(studentId))}
            />
          )}
          onDelete={(item) => postGradApi.remove(studentId, (item as PostGradContact).id)}
          emptyText="Chưa có liên hệ sau tốt nghiệp."
        />
      </div>

      {/* Edit modal */}
      <EditStudentModal open={showEdit} student={student} onClose={() => setShowEdit(false)} onUpdated={load} />

      {/* Deactivate confirm */}
      <Modal open={showDeactivate} title="Ngừng hoạt động sinh viên" size="sm"
        onClose={() => setShowDeactivate(false)}
        footer={<>
          <button className="btn-cancel" onClick={() => setShowDeactivate(false)} disabled={deactivating}>Hủy</button>
          <button className="btn-danger" onClick={handleDeactivate} disabled={deactivating}>
            {deactivating && <span className="spinner spinner-sm" />} Xác nhận ngừng
          </button>
        </>}
      >
        <div className="deactivate-confirm">
          <div className="deactivate-icon">⚠️</div>
          <h3>Ngừng hoạt động?</h3>
          <p>Sinh viên <strong>{student.fullName}</strong> sẽ bị chuyển sang INACTIVE. Tài khoản bị khóa nhưng hồ sơ được giữ nguyên.</p>
        </div>
      </Modal>
    </div>
  );
}

// ── Helper components ──────────────────────────────────────────
function InfoItem({ label, value, mono }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="info-item">
      <span className="info-label">{label}</span>
      <span className={`info-value ${mono ? 'mono' : ''} ${!value ? 'muted' : ''}`}>{value ?? '—'}</span>
    </div>
  );
}

// ── Sub-resource modals ────────────────────────────────────────
function AddressModal({ studentId, item, open, onClose, onSaved }:
  { studentId: number; item: Address | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<AddressPayload>({ addressType: 'CURRENT', current: false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) setForm({ countryCode: item.countryCode ?? 'VN', addressType: item.addressType, addressLine: item.addressLine ?? '', provinceCity: item.provinceCity ?? '', wardCommune: item.wardCommune ?? '', residenceRelation: item.residenceRelation ?? '', current: item.current });
    else setForm({ countryCode: 'VN', addressType: 'CURRENT', addressLine: '', provinceCity: '', wardCommune: '', residenceRelation: '', current: false });
    setErr(null);
  }, [item, open]);

  async function save() {
    setSubmitting(true); setErr(null);
    try {
      if (item) await addressApi.update(studentId, item.id, form);
      else await addressApi.create(studentId, form);
      onSaved(); onClose();
    } catch (e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật địa chỉ' : 'Thêm địa chỉ'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{item ? 'Lưu' : 'Thêm'}</button></>}
    >
      {err && <div className="form-alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="catalog-form">
        <div className="form-group">
          <label className="form-label">Loại địa chỉ</label>
          <select className="form-select" value={form.addressType} onChange={e => setForm(f => ({ ...f, addressType: e.target.value as AddressPayload['addressType'] }))}>
            <option value="CURRENT">Thường trú</option>
            <option value="PERMANENT">Hộ khẩu thường trú</option>
            <option value="FAMILY_HOME">Nhà gia đình</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Số nhà, đường</label>
          <input className="form-input" value={form.addressLine ?? ''} onChange={e => setForm(f => ({ ...f, addressLine: e.target.value }))} />
        </div>
        <AddressLocationFields form={form} onChange={setForm} />
        <label className="toggle-row" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <input type="checkbox" checked={form.current} onChange={e => setForm(f => ({ ...f, current: e.target.checked }))} />
          <span className="form-label" style={{ margin: 0 }}>Đây là địa chỉ hiện tại</span>
        </label>
      </div>
    </Modal>
  );
}

function FamilyModal({ studentId, item, open, onClose, onSaved }:
  { studentId: number; item: FamilyMember | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FamilyMemberPayload>({ relationship: 'OTHER', hasCollegeDegree: false, unavailable: false });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) setForm({ relationship: item.relationship, fullName: item.fullName ?? '', dateOfBirth: item.dateOfBirth ?? '', hasCollegeDegree: item.hasCollegeDegree, unavailable: item.unavailable, phoneNumber: item.phoneNumber ?? '' });
    else setForm({ relationship: 'OTHER', fullName: '', dateOfBirth: '', hasCollegeDegree: false, unavailable: false, phoneNumber: '' });
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = { ...form, fullName: form.fullName || undefined, dateOfBirth: form.dateOfBirth || undefined, phoneNumber: form.phoneNumber || undefined };
      if (item) await familyApi.update(studentId, item.id, payload);
      else await familyApi.create(studentId, payload);
      onSaved(); onClose();
    } catch (e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật nhân thân' : 'Thêm nhân thân'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{item ? 'Lưu' : 'Thêm'}</button></>}
    >
      {err && <div className="form-alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="catalog-form">
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Quan hệ <span className="required">*</span></label>
            <select className="form-select" value={form.relationship} onChange={e => setForm(f => ({ ...f, relationship: e.target.value as FamilyMemberPayload['relationship'] }))}>
              <option value="MOTHER">Mẹ</option>
              <option value="FATHER">Bố</option>
              <option value="GUARDIAN">Người giám hộ</option>
              <option value="OTHER">Khác</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Họ và tên</label>
            <input className="form-input" value={form.fullName ?? ''} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))} />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Ngày sinh</label>
            <input className="form-input" placeholder="YYYY-MM-DD" value={form.dateOfBirth ?? ''} onChange={e => setForm(f => ({ ...f, dateOfBirth: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Số điện thoại</label>
            <input className="form-input" value={form.phoneNumber ?? ''} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 20 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-sm)' }}>
            <input type="checkbox" checked={form.hasCollegeDegree} onChange={e => setForm(f => ({ ...f, hasCollegeDegree: e.target.checked }))} />
            Có bằng đại học
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-sm)' }}>
            <input type="checkbox" checked={form.unavailable} onChange={e => setForm(f => ({ ...f, unavailable: e.target.checked }))} />
            Đã mất / Không liên lạc được
          </label>
        </div>
      </div>
    </Modal>
  );
}

function EmergencyModal({ studentId, item, open, onClose, onSaved }:
  { studentId: number; item: EmergencyContact | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<EmergencyContactPayload>({ fullName: '', phoneNumber: '', priority: 1 });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) setForm({ fullName: item.fullName, relationship: item.relationship ?? '', phoneNumber: item.phoneNumber, address: item.address ?? '', priority: item.priority });
    else setForm({ fullName: '', relationship: '', phoneNumber: '', address: '', priority: 1 });
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    if (!form.fullName.trim()) { setErr('Họ tên là bắt buộc'); return; }
    if (!form.phoneNumber.trim()) { setErr('Số điện thoại là bắt buộc'); return; }
    if (!form.priority || form.priority < 1) { setErr('Thứ tự ưu tiên phải ≥ 1'); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = { ...form, relationship: form.relationship || undefined, address: form.address || undefined };
      if (item) await emergencyApi.update(studentId, item.id, payload);
      else await emergencyApi.create(studentId, payload);
      onSaved(); onClose();
    } catch (e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật liên hệ khẩn cấp' : 'Thêm liên hệ khẩn cấp'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{item ? 'Lưu' : 'Thêm'}</button></>}
    >
      {err && <div className="form-alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="catalog-form">
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Họ và tên <span className="required">*</span></label>
            <input className="form-input" value={form.fullName} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Số điện thoại <span className="required">*</span></label>
            <input className="form-input" value={form.phoneNumber} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))} />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Mối quan hệ</label>
            <input className="form-input" placeholder="Vd: Cha, Mẹ, Anh/Chị…" value={form.relationship ?? ''} onChange={e => setForm(f => ({ ...f, relationship: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Thứ tự ưu tiên <span className="required">*</span></label>
            <input className="form-input" type="number" min={1} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: Number(e.target.value) }))} />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Địa chỉ</label>
          <input className="form-input" value={form.address ?? ''} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
        </div>
      </div>
    </Modal>
  );
}

function PostGradModal({ studentId, item, open, onClose, onSaved }:
  { studentId: number; item: PostGradContact | null; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<PostGradContactPayload>({});
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (item) setForm({ fullName: item.fullName ?? '', phoneNumber: item.phoneNumber ?? '', email: item.email ?? '', address: item.address ?? '' });
    else setForm({ fullName: '', phoneNumber: '', email: '', address: '' });
    setErr(null);
  }, [item, open]);

  async function save() {
    if (!validPhone(form.phoneNumber)) { setErr(PHONE_ERROR); return; }
    if (!validEmail(form.email)) { setErr(EMAIL_ERROR); return; }
    setSubmitting(true); setErr(null);
    try {
      const payload = { fullName: form.fullName || undefined, phoneNumber: form.phoneNumber || undefined, email: form.email || undefined, address: form.address || undefined };
      if (item) await postGradApi.update(studentId, item.id, payload);
      else await postGradApi.create(studentId, payload);
      onSaved(); onClose();
    } catch (e) { setErr(e instanceof Error ? e.message : 'Lỗi'); }
    finally { setSubmitting(false); }
  }

  return (
    <Modal open={open} title={item ? 'Cập nhật liên hệ sau TN' : 'Thêm liên hệ sau TN'} size="md" onClose={onClose}
      footer={<><button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
      <button className="btn-submit" onClick={save} disabled={submitting}>{item ? 'Lưu' : 'Thêm'}</button></>}
    >
      {err && <div className="form-alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="catalog-form">
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Họ và tên</label>
            <input className="form-input" value={form.fullName ?? ''} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Số điện thoại</label>
            <input className="form-input" value={form.phoneNumber ?? ''} onChange={e => setForm(f => ({ ...f, phoneNumber: e.target.value }))} />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-input" type="email" value={form.email ?? ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Địa chỉ</label>
            <input className="form-input" value={form.address ?? ''} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
          </div>
        </div>
      </div>
    </Modal>
  );
}
