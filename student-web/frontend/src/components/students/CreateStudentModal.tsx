/**
 * CreateStudentModal — form tạo sinh viên mới
 * Sau khi tạo thành công hiển thị activation token để admin copy.
 */
import { useState, useEffect } from 'react';
import Modal from '../Modal';
import { studentApi } from '../../api/studentApi';
import { classApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import type { CreateStudentPayload, CreateStudentResponse, Gender } from '../../types/student';
import type { StudentClass } from '../../types/academic';

const EMPTY: CreateStudentPayload = {
  fullName: '', dateOfBirth: '', gender: undefined,
  citizenId: '', classId: 0, secondaryProgramId: null,
  familyPhoneNumber: '',
};

function validate(f: CreateStudentPayload): Partial<Record<string, string>> {
  const e: Partial<Record<string, string>> = {};
  if (!f.fullName.trim()) e.fullName = 'Họ tên là bắt buộc';
  if (!f.classId) e.classId = 'Phải chọn lớp';
  if (f.dateOfBirth && !/^\d{4}-\d{2}-\d{2}$/.test(f.dateOfBirth)) e.dateOfBirth = 'Định dạng YYYY-MM-DD';
  return e;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function CreateStudentModal({ open, onClose, onCreated }: Props) {
  const [form, setForm]         = useState<CreateStudentPayload>(EMPTY);
  const [fieldErr, setFieldErr] = useState<Partial<Record<string, string>>>({});
  const [formErr, setFormErr]   = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult]     = useState<CreateStudentResponse | null>(null);
  const [copied, setCopied]     = useState(false);
  const [classes, setClasses]   = useState<StudentClass[]>([]);

  useEffect(() => {
    classApi.listAll().then(r => setClasses(r.content)).catch(() => {});
  }, []);

  function handleClose() {
    setForm(EMPTY); setFieldErr({}); setFormErr(null); setResult(null); setCopied(false);
    if (result) onCreated();
    onClose();
  }

  async function handleSubmit() {
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      const payload: CreateStudentPayload = {
        ...form,
        classId: Number(form.classId),
        dateOfBirth: form.dateOfBirth || undefined,
        gender: form.gender || undefined,
        citizenId: form.citizenId || undefined,
        familyPhoneNumber: form.familyPhoneNumber || undefined,
        secondaryProgramId: form.secondaryProgramId || null,
      };
      const res = await studentApi.create(payload);
      setResult(res);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 409
        ? 'MSSV hoặc CCCD đã tồn tại trong hệ thống'
        : e instanceof Error ? e.message : 'Lỗi tạo sinh viên';
      setFormErr(msg);
    } finally { setSubmitting(false); }
  }

  function copyToken() {
    if (!result) return;
    navigator.clipboard.writeText(result.activationToken).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  }

  const fv = fieldErr;

  // Success screen: show token
  if (result) {
    return (
      <Modal open={open} title="Sinh viên đã được tạo" onClose={handleClose} size="md"
        footer={<button className="btn-submit" onClick={handleClose}>Xong ✓</button>}
      >
        <div className="token-display">
          <div className="token-success-icon">✓</div>
          <h3>Tạo tài khoản thành công!</h3>
          <p>
            Sinh viên <strong>{result.student.fullName}</strong> (MSSV: <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{result.student.studentCode}</code>) đã được tạo.
            Hãy sao chép token kích hoạt bên dưới và gửi cho sinh viên qua kênh đã xác minh.
          </p>
          <div className="token-box">
            <span className="token-value">{result.activationToken}</span>
            <button className={`token-copy-btn ${copied ? 'copied' : ''}`} onClick={copyToken}>
              {copied ? '✓ Đã sao chép' : 'Sao chép'}
            </button>
          </div>
          <div className="token-warning">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0, marginTop: 1 }}>
              <path d="M8 1L15 14H1L8 1z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <path d="M8 6v4M8 12h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <span>Token chỉ hiển thị <strong>một lần</strong> và có hiệu lực trong 24 giờ. Không lưu token trong hệ thống sau khi đóng cửa sổ này.</span>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={open} title="Thêm sinh viên mới" onClose={handleClose} size="lg"
      footer={<>
        <button className="btn-cancel" onClick={handleClose} disabled={submitting}>Hủy</button>
        <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
          {submitting && <span className="spinner spinner-sm" />} Tạo sinh viên
        </button>
      </>}
    >
      {formErr && (
        <div className="form-alert" style={{ marginBottom: 16 }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          {formErr}
        </div>
      )}
      <div className="catalog-form">
        {/* Row 1: MSSV + Họ tên */}
        <div className="form-row">
          <p className="form-hint">Mã sinh viên được tự sinh theo khóa của lớp và giữ nguyên khi chuyển lớp.</p>
          <div className="form-group">
            <label className="form-label">Họ và tên <span className="required">*</span></label>
            <input className={`form-input ${fv.fullName ? 'invalid' : ''}`} placeholder="Vd: Nguyễn Văn A"
              value={form.fullName} onChange={e => setForm(f => ({ ...f, fullName: e.target.value }))} disabled={submitting} />
            {fv.fullName && <p className="form-error-text">{fv.fullName}</p>}
          </div>
        </div>
        {/* Row 2: Ngày sinh + Giới tính */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Ngày sinh</label>
            <input className={`form-input ${fv.dateOfBirth ? 'invalid' : ''}`} placeholder="YYYY-MM-DD"
              value={form.dateOfBirth} onChange={e => setForm(f => ({ ...f, dateOfBirth: e.target.value }))} disabled={submitting} />
            {fv.dateOfBirth && <p className="form-error-text">{fv.dateOfBirth}</p>}
          </div>
          <div className="form-group">
            <label className="form-label">Giới tính</label>
            <select className="form-select" value={form.gender ?? ''}
              onChange={e => setForm(f => ({ ...f, gender: (e.target.value as Gender) || undefined }))}>
              <option value="">— Không xác định —</option>
              <option value="MALE">Nam</option>
              <option value="FEMALE">Nữ</option>
              <option value="OTHER">Khác</option>
            </select>
          </div>
        </div>
        {/* Row 3: CCCD + Lớp */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Số CCCD</label>
            <input className="form-input" placeholder="Vd: 001234567890"
              value={form.citizenId} onChange={e => setForm(f => ({ ...f, citizenId: e.target.value }))} disabled={submitting} />
          </div>
          <div className="form-group">
            <label className="form-label">Lớp <span className="required">*</span></label>
            <select className={`form-select ${fv.classId ? 'invalid' : ''}`} value={form.classId}
              onChange={e => setForm(f => ({ ...f, classId: Number(e.target.value) }))}>
              <option value={0}>— Chọn lớp —</option>
              {classes.map(c => <option key={c.id} value={c.id}>{c.name || c.code} ({c.code})</option>)}
            </select>
            {fv.classId && <p className="form-error-text">{fv.classId}</p>}
          </div>
        </div>
        {/* Row 4: Email + SĐT gia đình */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Email trường</label>
            <p className="form-hint">Email trường được tự sinh từ mã sinh viên.</p>
          </div>
          <div className="form-group">
            <label className="form-label">SĐT gia đình</label>
            <input className="form-input" placeholder="Vd: 0900123456"
              value={form.familyPhoneNumber} onChange={e => setForm(f => ({ ...f, familyPhoneNumber: e.target.value }))} disabled={submitting} />
          </div>
        </div>
      </div>
    </Modal>
  );
}
