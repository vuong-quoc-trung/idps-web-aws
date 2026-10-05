/**
 * EditStudentModal — cập nhật thông tin sinh viên (status, lớp, ngân hàng…)
 */
import { useState, useEffect } from 'react';
import Modal from '../Modal';
import { studentApi } from '../../api/studentApi';
import { classApi, programApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import type { StudentDetail, UpdateStudentPayload, Gender, StudentStatus } from '../../types/student';
import type { StudentClass, TrainingProgram } from '../../types/academic';

const STATUS_OPTIONS: { value: StudentStatus; label: string }[] = [
  { value: 'ACTIVE',    label: '● Đang học' },
  { value: 'GRADUATED', label: '🎓 Đã tốt nghiệp' },
  { value: 'SUSPENDED', label: '⏸ Đình chỉ' },
  { value: 'INACTIVE',  label: '✕ Ngừng hoạt động' },
];

function toForm(s: StudentDetail): UpdateStudentPayload {
  return {
    fullName: s.fullName,
    dateOfBirth: s.dateOfBirth ?? '',
    gender: s.gender ?? null,
    citizenId: s.citizenId ?? '',
    classId: s.classId ?? 0,
    secondaryProgramId: s.secondaryProgramId ?? null,
    familyPhoneNumber: s.familyPhoneNumber ?? '',
    bankAccountNumber: s.bankAccountNumber ?? '',
    bankName: s.bankName ?? '',
    status: s.status,
  };
}

function validate(f: UpdateStudentPayload): Partial<Record<string, string>> {
  const e: Partial<Record<string, string>> = {};
  if (!f.fullName.trim()) e.fullName = 'Họ tên là bắt buộc';
  if (!f.classId) e.classId = 'Phải chọn lớp';
  if (!f.status) e.status = 'Trạng thái là bắt buộc';
  if (f.dateOfBirth && !/^\d{4}-\d{2}-\d{2}$/.test(f.dateOfBirth)) e.dateOfBirth = 'Định dạng YYYY-MM-DD';
  return e;
}

interface Props {
  open: boolean;
  student: StudentDetail | null;
  onClose: () => void;
  onUpdated: () => void;
}

export default function EditStudentModal({ open, student, onClose, onUpdated }: Props) {
  const [form, setForm]         = useState<UpdateStudentPayload | null>(null);
  const [fieldErr, setFieldErr] = useState<Partial<Record<string, string>>>({});
  const [formErr, setFormErr]   = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [classes, setClasses]   = useState<StudentClass[]>([]);
  const [programs, setPrograms] = useState<TrainingProgram[]>([]);

  useEffect(() => {
    if (student) setForm(toForm(student));
    setFieldErr({}); setFormErr(null);
  }, [student]);

  useEffect(() => {
    Promise.all([
      classApi.listAll(),
      programApi.listAll(),
    ]).then(([clsRes, prgRes]) => {
      setClasses(clsRes.content);
      setPrograms(prgRes.content);
    }).catch(() => {});
  }, []);

  if (!form || !student) return null;

  async function handleSubmit() {
    if (!form) return;
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      const payload: UpdateStudentPayload = {
        ...form,
        classId: Number(form.classId),
        dateOfBirth: form.dateOfBirth || null,
        gender: form.gender || null,
        citizenId: form.citizenId || null,
        familyPhoneNumber: form.familyPhoneNumber || null,
        bankAccountNumber: form.bankAccountNumber || null,
        bankName: form.bankName || null,
        secondaryProgramId: form.secondaryProgramId || null,
      };
      await studentApi.update(student!.id, payload);
      onUpdated(); onClose();
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 409
        ? 'CCCD đã được sử dụng bởi sinh viên khác'
        : e instanceof Error ? e.message : 'Lỗi cập nhật';
      setFormErr(msg);
    } finally { setSubmitting(false); }
  }

  const f = form;
  const fv = fieldErr;
  const set = (key: keyof UpdateStudentPayload, val: unknown) =>
    setForm(prev => prev ? { ...prev, [key]: val } : prev);

  return (
    <Modal open={open} title={`Cập nhật: ${student.fullName}`} onClose={onClose} size="lg"
      footer={<>
        <button className="btn-cancel" onClick={onClose} disabled={submitting}>Hủy</button>
        <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
          {submitting && <span className="spinner spinner-sm" />} Lưu thay đổi
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
        {/* Read-only MSSV */}
        <div className="form-group">
          <label className="form-label">MSSV</label>
          <input className="form-input" value={student.studentCode} disabled style={{ opacity: 0.6 }} />
          <p className="form-hint">MSSV không thể thay đổi sau khi tạo</p>
        </div>
        {/* Row: Họ tên + Trạng thái */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Họ và tên <span className="required">*</span></label>
            <input className={`form-input ${fv.fullName ? 'invalid' : ''}`}
              value={f.fullName} onChange={e => set('fullName', e.target.value)} disabled={submitting} />
            {fv.fullName && <p className="form-error-text">{fv.fullName}</p>}
          </div>
          <div className="form-group">
            <label className="form-label">Trạng thái <span className="required">*</span></label>
            <select className={`form-select ${fv.status ? 'invalid' : ''}`} value={f.status}
              onChange={e => set('status', e.target.value)} disabled={submitting}>
              {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        {/* Row: Ngày sinh + Giới tính */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Ngày sinh</label>
            <input className={`form-input ${fv.dateOfBirth ? 'invalid' : ''}`} placeholder="YYYY-MM-DD"
              value={f.dateOfBirth ?? ''} onChange={e => set('dateOfBirth', e.target.value)} disabled={submitting} />
            {fv.dateOfBirth && <p className="form-error-text">{fv.dateOfBirth}</p>}
          </div>
          <div className="form-group">
            <label className="form-label">Giới tính</label>
            <select className="form-select" value={f.gender ?? ''}
              onChange={e => set('gender', (e.target.value as Gender) || null)} disabled={submitting}>
              <option value="">— Không xác định —</option>
              <option value="MALE">Nam</option>
              <option value="FEMALE">Nữ</option>
              <option value="OTHER">Khác</option>
            </select>
          </div>
        </div>
        {/* Row: CCCD + Lớp */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Số CCCD</label>
            <input className="form-input" placeholder="Số căn cước công dân"
              value={f.citizenId ?? ''} onChange={e => set('citizenId', e.target.value)} disabled={submitting} />
          </div>
          <div className="form-group">
            <label className="form-label">Lớp <span className="required">*</span></label>
            <select className={`form-select ${fv.classId ? 'invalid' : ''}`} value={f.classId}
              onChange={e => set('classId', Number(e.target.value))} disabled={submitting}>
              <option value={0}>— Chọn lớp —</option>
              {classes.map(c => <option key={c.id} value={c.id}>{c.name || c.code} ({c.code})</option>)}
            </select>
            {fv.classId && <p className="form-error-text">{fv.classId}</p>}
          </div>
        </div>
        {/* Row: Chương trình phụ */}
        <div className="form-group full">
          <label className="form-label">Chương trình đào tạo phụ (song ngành)</label>
          <select className="form-select" value={f.secondaryProgramId ?? ''}
            onChange={e => set('secondaryProgramId', e.target.value ? Number(e.target.value) : null)}
            disabled={submitting}>
            <option value="">— Không đăng ký CT phụ (để trống) —</option>
            {programs.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
          </select>
          <p className="form-hint">Dành cho sinh viên đăng ký học song bằng / chương trình thứ hai (tùy chọn).</p>
        </div>
        {/* Row: Email + SĐT */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Email trường</label>
            <p className="form-hint">{student?.schoolEmail ?? '—'}</p>
          </div>
          <div className="form-group">
            <label className="form-label">SĐT gia đình</label>
            <input className="form-input" value={f.familyPhoneNumber ?? ''}
              onChange={e => set('familyPhoneNumber', e.target.value)} disabled={submitting} />
          </div>
        </div>
        {/* Row: Ngân hàng */}
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Số tài khoản ngân hàng</label>
            <input className="form-input" placeholder="Vd: 0123456789"
              value={f.bankAccountNumber ?? ''} onChange={e => set('bankAccountNumber', e.target.value)} disabled={submitting} />
          </div>
          <div className="form-group">
            <label className="form-label">Tên ngân hàng</label>
            <input className="form-input" placeholder="Vd: Vietcombank"
              value={f.bankName ?? ''} onChange={e => set('bankName', e.target.value)} disabled={submitting} />
          </div>
        </div>
      </div>
    </Modal>
  );
}
