/** ClassTab — CRUD for /api/classes */
import { useState, useEffect, useCallback } from 'react';
import { classApi, programApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import type { StudentClass, StudentClassPayload, TrainingProgram } from '../../types/academic';
import type { Page } from '../../api/client';
import Modal from '../Modal';
import { CatalogTable, Pagination, SectionError, DeleteConfirm } from './CatalogShared';

const EMPTY: StudentClassPayload = {
  code: '', name: '', active: true, programId: 0,
  cohort: null, academicYear: '',
};

function validate(f: StudentClassPayload): Partial<Record<string, string>> {
  const e: Partial<Record<string, string>> = {};
  if (!f.code.trim()) e.code = 'Mã lớp là bắt buộc';
  else if (!/^[\w\-]+$/.test(f.code.trim())) e.code = 'Mã chỉ gồm chữ, số, gạch dưới, gạch ngang';
  if (!f.programId) e.programId = 'Phải chọn chương trình đào tạo';
  if (f.academicYear && !/^\d{4}-\d{4}$/.test(f.academicYear.trim()))
    e.academicYear = 'Định dạng năm học: YYYY-YYYY (Vd: 2026-2031)';
  return e;
}

export default function ClassTab() {
  const [data, setData]         = useState<Page<StudentClass> | null>(null);
  const [page, setPage]         = useState(0);
  const [loading, setLoading]   = useState(false);
  const [tableErr, setTableErr] = useState<string | null>(null);

  const [programs, setPrograms] = useState<TrainingProgram[]>([]);

  const [modal, setModal]       = useState<{ mode: 'add' | 'edit'; item?: StudentClass } | null>(null);
  const [form, setForm]         = useState<StudentClassPayload>(EMPTY);
  const [fieldErr, setFieldErr] = useState<Partial<Record<string, string>>>({});
  const [formErr, setFormErr]   = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<StudentClass | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [deleteErr, setDeleteErr]   = useState<string | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true); setTableErr(null);
    try { setData(await classApi.list(p)); }
    catch (e) { setTableErr(e instanceof Error ? e.message : 'Lỗi tải dữ liệu'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(page); }, [page, load]);
  useEffect(() => { programApi.listAll().then(r => setPrograms(r.content)).catch(() => {}); }, []);

  function openAdd() { setForm(EMPTY); setFieldErr({}); setFormErr(null); setModal({ mode: 'add' }); }
  function openEdit(item: StudentClass) {
    setForm({
      code: item.code, name: item.name ?? '', active: item.active,
      programId: item.programId, cohort: item.cohort ?? null,
      academicYear: item.academicYear ?? '',
    });
    setFieldErr({}); setFormErr(null); setModal({ mode: 'edit', item });
  }
  function closeModal() { setModal(null); }

  async function handleSubmit() {
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      const payload: StudentClassPayload = {
        ...form,
        programId: Number(form.programId),
        name: form.name || undefined,
        cohort: form.cohort,
        academicYear: form.academicYear || undefined,
      };
      if (modal?.mode === 'add') await classApi.create(payload);
      else await classApi.update(modal!.item!.id, payload);
      closeModal(); load(page);
    } catch (e) {
      setFormErr(e instanceof ApiError && e.status === 409
        ? 'Mã lớp đã tồn tại hoặc không thể thay đổi chương trình đang được sử dụng'
        : e instanceof Error ? e.message : 'Lỗi không xác định');
    } finally { setSubmitting(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await classApi.remove(deleteTarget.id);
      setDeleteTarget(null); load(page);
    } catch (e) {
      setDeleteErr(e instanceof ApiError && e.status === 409
        ? 'Không thể xóa: Lớp đang có sinh viên thuộc'
        : e instanceof Error ? e.message : 'Lỗi xóa');
    } finally { setDeleting(false); }
  }

  const columns = [
    { key: 'id',          label: 'ID',          cls: 'col-id' },
    { key: 'code',        label: 'Mã lớp',      cls: 'col-code', render: (r: StudentClass) => <span>{r.code}</span> },
    { key: 'name',        label: 'Tên lớp',     render: (r: StudentClass) => <span>{r.name || '—'}</span> },
    { key: 'programName', label: 'Chương trình', render: (r: StudentClass) => <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{r.programName ?? `#${r.programId}`}</span> },
    { key: 'cohort',      label: 'Khoá',        render: (r: StudentClass) => <span>{r.cohort ?? '—'}</span> },
    { key: 'academicYear',label: 'Năm học',     render: (r: StudentClass) => <span style={{ color: 'var(--text-muted)' }}>{r.academicYear ?? '—'}</span> },
    { key: 'active', label: 'Trạng thái', cls: 'col-active', render: (r: StudentClass) =>
        <span className={`badge ${r.active ? 'badge-active' : 'badge-inactive'}`}>{r.active ? '● Hoạt động' : '○ Ngừng'}</span> },
  ];

  const fv = fieldErr;

  return (
    <>
      {tableErr && <SectionError message={tableErr} />}
      <CatalogTable columns={columns} rows={data?.content ?? []} loading={loading}
        emptyText="Chưa có lớp nào." addLabel="Thêm lớp"
        onAdd={openAdd} onEdit={openEdit} onDelete={setDeleteTarget} />
      {data && data.totalPages > 1 && <Pagination page={page} totalPages={data.totalPages} totalElements={data.totalElements} onChange={setPage} />}

      <Modal open={!!modal}
        title={modal?.mode === 'add' ? 'Thêm lớp mới' : `Chỉnh sửa lớp: ${modal?.item?.code}`}
        onClose={closeModal}
        footer={<>
          <button className="btn-cancel" onClick={closeModal} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm" />}
            {modal?.mode === 'add' ? 'Thêm lớp' : 'Lưu thay đổi'}
          </button>
        </>}
      >
        {formErr && <div className="form-alert" style={{ marginBottom: 16 }}><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>{formErr}</div>}
        <div className="catalog-form">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Mã lớp <span className="required">*</span></label>
              <input className={`form-input ${fv.code ? 'invalid' : ''}`} placeholder="Vd: 26T1"
                value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
                disabled={submitting || modal?.mode === 'edit'} />
              {fv.code && <p className="form-error-text">{fv.code}</p>}
            </div>
            <div className="form-group">
              <label className="form-label">Tên lớp</label>
              <input className="form-input" placeholder="Vd: Lớp 26T1 CNTT CLC"
                value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} disabled={submitting} />
            </div>
          </div>
          <div className="form-group full">
            <label className="form-label">Chương trình đào tạo <span className="required">*</span></label>
            <select className={`form-select ${fv.programId ? 'invalid' : ''}`} value={form.programId}
              onChange={e => setForm(f => ({ ...f, programId: Number(e.target.value) }))}
              disabled={submitting || modal?.mode === 'edit'}>
              <option value={0}>— Chọn chương trình —</option>
              {programs.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
            </select>
            {fv.programId && <p className="form-error-text">{fv.programId}</p>}
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Khoá nhập học</label>
              <input className="form-input" type="number" placeholder="Vd: 2026"
                value={form.cohort ?? ''} onChange={e => setForm(f => ({ ...f, cohort: e.target.value ? parseInt(e.target.value) : null }))} disabled={submitting} />
            </div>
            <div className="form-group">
              <label className="form-label">Năm học</label>
              <input className={`form-input ${fv.academicYear ? 'invalid' : ''}`} placeholder="Vd: 2026-2031"
                value={form.academicYear} onChange={e => setForm(f => ({ ...f, academicYear: e.target.value }))} disabled={submitting} />
              {fv.academicYear
                ? <p className="form-error-text">{fv.academicYear}</p>
                : <p className="form-hint">Định dạng: YYYY-YYYY</p>}
            </div>
          </div>
          <div className="toggle-row">
            <label className="toggle-switch">
              <input type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
              <span className="toggle-track" />
            </label>
            <span className="toggle-label">{form.active ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span>
          </div>
        </div>
      </Modal>

      <Modal open={!!deleteTarget} title="Xác nhận xóa" size="sm"
        onClose={() => { setDeleteTarget(null); setDeleteErr(null); }}
        footer={<>
          <button className="btn-cancel" onClick={() => { setDeleteTarget(null); setDeleteErr(null); }} disabled={deleting}>Hủy</button>
          <button className="btn-danger" onClick={handleDelete} disabled={deleting}>
            {deleting && <span className="spinner spinner-sm" />} Xóa lớp
          </button>
        </>}
      >
        <DeleteConfirm icon="🎓" title="Xóa lớp này?"
          description={<>Lớp <code>{deleteTarget?.code}</code>{deleteTarget?.name ? ` — ${deleteTarget.name}` : ''} sẽ bị xóa. Không thể xóa nếu còn sinh viên thuộc lớp này.</>}
          error={deleteErr} />
      </Modal>
    </>
  );
}
