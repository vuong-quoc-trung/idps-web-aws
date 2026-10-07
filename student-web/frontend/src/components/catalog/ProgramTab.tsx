/** ProgramTab — CRUD for /api/training-programs */
import { useState, useEffect, useCallback } from 'react';
import { programApi, majorApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import type { TrainingProgram, TrainingProgramPayload, Major, DegreeType } from '../../types/academic';
import type { Page } from '../../api/client';
import Modal from '../Modal';
import { CatalogTable, type Column, Pagination, SectionError, DeleteConfirm } from './CatalogShared';

const DEGREE_OPTIONS: { value: DegreeType; label: string }[] = [
  { value: 'BACHELOR', label: 'Cử nhân (Bachelor)' },
  { value: 'ENGINEER', label: 'Kỹ sư (Engineer)' },
  { value: 'MASTER',   label: 'Thạc sĩ (Master)' },
];

const EMPTY: TrainingProgramPayload = {
  name: '', active: true, majorId: 0,
  cohort: null, degreeType: null, variantCode: null,
  numberOfSemesters: null, totalCredits: null,
  requiredCredits: null, electiveCredits: null,
};

function validate(f: TrainingProgramPayload): Partial<Record<string, string>> {
  const e: Partial<Record<string, string>> = {};
  if (!f.name.trim()) e.name = 'Tên chương trình là bắt buộc';
  if (!f.cohort || !Number.isInteger(f.cohort) || f.cohort < 1000 || f.cohort > 9999) e.cohort = 'Khóa phải là năm có 4 chữ số';
  if (!f.degreeType) e.degreeType = 'Phải chọn loại bằng';
  if (f.variantCode?.trim() && !/^[A-Z][A-Z0-9]{0,5}$/i.test(f.variantCode.trim())) e.variantCode = 'Nhập 1–6 chữ cái hoặc số, bắt đầu bằng chữ';
  if (!f.majorId) e.majorId = 'Phải chọn ngành';
  if (f.numberOfSemesters != null && f.numberOfSemesters <= 0) e.numberOfSemesters = 'Số học kỳ phải > 0';
  if (f.totalCredits != null && f.totalCredits < 0) e.totalCredits = 'Tổng tín chỉ phải ≥ 0';
  if (f.requiredCredits != null && f.requiredCredits < 0) e.requiredCredits = 'Tín chỉ bắt buộc phải ≥ 0';
  if (f.electiveCredits != null && f.electiveCredits < 0) e.electiveCredits = 'Tín chỉ tự chọn phải ≥ 0';
  // credit sum check
  const tc = f.totalCredits, rc = f.requiredCredits, ec = f.electiveCredits;
  if (tc != null && rc != null && rc > tc) e.requiredCredits = 'Tín chỉ bắt buộc vượt tổng tín chỉ';
  if (tc != null && ec != null && ec > tc) e.electiveCredits = 'Tín chỉ tự chọn vượt tổng tín chỉ';
  if (tc != null && rc != null && ec != null && rc + ec !== tc) e.electiveCredits = 'Bắt buộc + Tự chọn phải bằng Tổng tín chỉ';
  return e;
}

function numOrNull(v: string): number | null {
  const n = parseInt(v, 10);
  return isNaN(n) ? null : n;
}

export default function ProgramTab() {
  const { user } = useAuth();
  const readOnly = user?.role === 'STUDENT';
  const [data, setData]         = useState<Page<TrainingProgram> | null>(null);
  const [page, setPage]         = useState(0);
  const [loading, setLoading]   = useState(false);
  const [tableErr, setTableErr] = useState<string | null>(null);

  const [majors, setMajors]     = useState<Major[]>([]);

  const [modal, setModal]       = useState<{ mode: 'add' | 'edit'; item?: TrainingProgram } | null>(null);
  const [form, setForm]         = useState<TrainingProgramPayload>(EMPTY);
  const [fieldErr, setFieldErr] = useState<Partial<Record<string, string>>>({});
  const [formErr, setFormErr]   = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<TrainingProgram | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [deleteErr, setDeleteErr]   = useState<string | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true); setTableErr(null);
    try { setData(await programApi.list(p)); }
    catch (e) { setTableErr(e instanceof Error ? e.message : 'Lỗi tải dữ liệu'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(page); }, [page, load]);
  useEffect(() => { majorApi.listAll().then(r => setMajors(r.content)).catch(() => {}); }, []);

  function openAdd() { setForm(EMPTY); setFieldErr({}); setFormErr(null); setModal({ mode: 'add' }); }
  function openEdit(item: TrainingProgram) {
    setForm({
      name: item.name, active: item.active, majorId: item.majorId,
      cohort: item.cohort ?? null, degreeType: item.degreeType ?? null, variantCode: item.variantCode ?? null,
      numberOfSemesters: item.numberOfSemesters ?? null, totalCredits: item.totalCredits ?? null,
      requiredCredits: item.requiredCredits ?? null, electiveCredits: item.electiveCredits ?? null,
    });
    setFieldErr({}); setFormErr(null); setModal({ mode: 'edit', item });
  }
  function closeModal() { setModal(null); }

  function setNum(key: keyof TrainingProgramPayload, v: string) {
    setForm(f => ({ ...f, [key]: v === '' ? null : numOrNull(v) }));
  }

  async function handleSubmit() {
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      const payload = { ...form, majorId: Number(form.majorId) };
      if (modal?.mode === 'add') await programApi.create(payload);
      else await programApi.update(modal!.item!.id, payload);
      closeModal(); load(page);
    } catch (e) {
      setFormErr(e instanceof ApiError && e.status === 409
        ? 'Mã chương trình đã tồn tại hoặc không thể thay đổi ngành đang được sử dụng'
        : e instanceof Error ? e.message : 'Lỗi không xác định');
    } finally { setSubmitting(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await programApi.remove(deleteTarget.id);
      setDeleteTarget(null); load(page);
    } catch (e) {
      setDeleteErr(e instanceof ApiError && e.status === 409
        ? 'Không thể xóa: Chương trình đang được sử dụng bởi lớp học'
        : e instanceof Error ? e.message : 'Lỗi xóa');
    } finally { setDeleting(false); }
  }

  const degreeLabel = (d?: DegreeType | null) => DEGREE_OPTIONS.find(o => o.value === d)?.label ?? '—';

  const columns: Column<TrainingProgram>[] = [
    { key: 'id',          label: 'ID',           cls: 'col-id' },
    { key: 'code',        label: 'Mã',            cls: 'col-code', render: (r: TrainingProgram) => <span>{r.code}</span> },
    { key: 'name',        label: 'Tên chương trình' },
    { key: 'majorName',   label: 'Ngành',         render: (r: TrainingProgram) => <span style={{ color: 'var(--text-muted)' }}>{r.majorName ?? `#${r.majorId}`}</span> },
    { key: 'degreeType',  label: 'Bằng cấp',      render: (r: TrainingProgram) => <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{degreeLabel(r.degreeType)}</span> },
    { key: 'totalCredits',label: 'Tín chỉ',       render: (r: TrainingProgram) => <span>{r.totalCredits ?? '—'}</span> },
    { key: 'active', label: 'Trạng thái', cls: 'col-active', render: (r: TrainingProgram) =>
        <span className={`badge ${r.active ? 'badge-active' : 'badge-inactive'}`}>{r.active ? '● Hoạt động' : '○ Ngừng'}</span> },
  ];

  const fv = fieldErr;

  return (
    <>
      {tableErr && <SectionError message={tableErr} />}
      <CatalogTable columns={columns} rows={data?.content ?? []} loading={loading}
        emptyText="Chưa có chương trình đào tạo nào." addLabel="Thêm chương trình"
        onAdd={openAdd} onEdit={openEdit} onDelete={row => setDeleteTarget(row)} readOnly={readOnly} />
      {data && data.totalPages > 1 && <Pagination page={page} totalPages={data.totalPages} totalElements={data.totalElements} onChange={setPage} />}

      <Modal open={!!modal} size="lg"
        title={modal?.mode === 'add' ? 'Thêm chương trình đào tạo' : `Chỉnh sửa: ${modal?.item?.name}`}
        onClose={closeModal}
        footer={<>
          <button className="btn-cancel" onClick={closeModal} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm" />}
            {modal?.mode === 'add' ? 'Thêm chương trình' : 'Lưu thay đổi'}
          </button>
        </>}
      >
        {formErr && <div className="form-alert" style={{ marginBottom: 16 }}><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>{formErr}</div>}
        <div className="catalog-form">
          {/* Row 1: code + name */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="program-code-input">Mã chương trình</label>
              <input className="form-input" id="program-code-input" value={modal?.mode === 'edit' ? (modal.item?.code ?? '') : '(Tự động sinh)'} disabled style={{ opacity: 0.7 }} />
              <p className="form-hint">Mã chương trình được hệ thống tự sinh</p>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="program-name-input">Tên chương trình <span className="required">*</span></label>
              <input className={`form-input ${fv.name ? 'invalid' : ''}`} id="program-name-input" placeholder="Vd: Chương trình CNTT CLC"
                value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} disabled={submitting} />
              {fv.name && <p className="form-error-text" id="program-name-error">{fv.name}</p>}
            </div>
          </div>
          {/* Row 2: major + degreeType */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="program-major-select">Ngành <span className="required">*</span></label>
              <select className={`form-select ${fv.majorId ? 'invalid' : ''}`} id="program-major-select" value={form.majorId}
                onChange={e => setForm(f => ({ ...f, majorId: Number(e.target.value) }))}
                disabled={submitting || modal?.mode === 'edit'}>
                <option value={0}>— Chọn ngành —</option>
                {majors.map(m => <option key={m.id} value={m.id}>{m.name} ({m.code})</option>)}
              </select>
              {fv.majorId && <p className="form-error-text" id="program-major-error">{fv.majorId}</p>}
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="program-degree-select">Loại bằng <span className="required">*</span></label>
              <select className={`form-select ${fv.degreeType ? 'invalid' : ''}`} id="program-degree-select" value={form.degreeType ?? ''} disabled={submitting}
                onChange={e => setForm(f => ({ ...f, degreeType: (e.target.value as DegreeType) || null }))}>
                <option value="">— Chọn loại bằng —</option>
                {DEGREE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              {fv.degreeType && <p className="form-error-text" id="program-degree-error">{fv.degreeType}</p>}
            </div>
          </div>
          <div className="form-group full">
            <label className="form-label" htmlFor="program-variant-input">Mã phân biệt chương trình</label>
            <input className={`form-input ${fv.variantCode ? 'invalid' : ''}`} id="program-variant-input" maxLength={6}
              placeholder="CLC, HTDN, TALENT" value={form.variantCode ?? ''} disabled={submitting}
              onChange={e => setForm(f => ({ ...f, variantCode: e.target.value.toUpperCase() || null }))} />
            <p className="form-hint">Để trống với chương trình thường. Dùng để phân biệt các chương trình cùng ngành, khóa và loại bằng.</p>
            {fv.variantCode && <p className="form-error-text" id="program-variant-error">{fv.variantCode}</p>}
          </div>
          {/* Row 3: cohort + numberOfSemesters */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="program-cohort-input">Khoá (cohort)</label>
              <input className={`form-input ${fv.cohort ? 'invalid' : ''}`} id="program-cohort-input" type="number" placeholder="Vd: 2026"
                value={form.cohort ?? ''} onChange={e => setNum('cohort', e.target.value)} disabled={submitting}
                aria-describedby={fv.cohort ? 'program-cohort-error' : undefined}
                aria-invalid={!!fv.cohort} />
              {fv.cohort && <p className="form-error-text" id="program-cohort-error">{fv.cohort}</p>}
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="program-semesters-input">Số học kỳ</label>
              <input className={`form-input ${fv.numberOfSemesters ? 'invalid' : ''}`} id="program-semesters-input" type="number" placeholder="Vd: 10"
                value={form.numberOfSemesters ?? ''} onChange={e => setNum('numberOfSemesters', e.target.value)} disabled={submitting} />
              {fv.numberOfSemesters && <p className="form-error-text">{fv.numberOfSemesters}</p>}
            </div>
          </div>
          {/* Row 4: totalCredits + requiredCredits + electiveCredits */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="program-total-credits-input">Tổng tín chỉ</label>
              <input className={`form-input ${fv.totalCredits ? 'invalid' : ''}`} id="program-total-credits-input" type="number" placeholder="Vd: 150"
                value={form.totalCredits ?? ''} onChange={e => setNum('totalCredits', e.target.value)} disabled={submitting} />
              {fv.totalCredits && <p className="form-error-text">{fv.totalCredits}</p>}
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="program-required-credits-input">Tín chỉ bắt buộc</label>
              <input className={`form-input ${fv.requiredCredits ? 'invalid' : ''}`} id="program-required-credits-input" type="number" placeholder="Vd: 120"
                value={form.requiredCredits ?? ''} onChange={e => setNum('requiredCredits', e.target.value)} disabled={submitting} />
              {fv.requiredCredits && <p className="form-error-text">{fv.requiredCredits}</p>}
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="program-elective-credits-input">Tín chỉ tự chọn</label>
              <input className={`form-input ${fv.electiveCredits ? 'invalid' : ''}`} id="program-elective-credits-input" type="number" placeholder="Vd: 30"
                value={form.electiveCredits ?? ''} onChange={e => setNum('electiveCredits', e.target.value)} disabled={submitting} />
              {fv.electiveCredits && <p className="form-error-text">{fv.electiveCredits}</p>}
              <p className="form-hint">Bắt buộc + Tự chọn = Tổng tín chỉ</p>
            </div>
            <div className="form-group" style={{ justifyContent: 'flex-end' }}>
              <div className="toggle-row" style={{ marginTop: 'auto', paddingBottom: 4 }}>
                <label className="toggle-switch">
                  <input type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
                  <span className="toggle-track" />
                </label>
                <span className="toggle-label">{form.active ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>
              </div>
            </div>
          </div>
        </div>
      </Modal>

      <Modal open={!!deleteTarget} title="Xác nhận xóa" size="sm"
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        footer={<>
          <button className="btn-cancel" onClick={() => { setDeleteTarget(null); setDeleteErr(null); }} disabled={deleting}>Hủy</button>
          <button className="btn-danger" onClick={handleDelete} disabled={deleting}>
            {deleting && <span className="spinner spinner-sm" />} Xóa chương trình
          </button>
        </>}
      >
        <DeleteConfirm title="Xóa chương trình này?"
          description={<>Chương trình <code>{deleteTarget?.code}</code> — <strong>{deleteTarget?.name}</strong> sẽ bị xóa. Không thể xóa nếu còn lớp thuộc chương trình này.</>}
          error={deleteErr} />
      </Modal>
    </>
  );
}
