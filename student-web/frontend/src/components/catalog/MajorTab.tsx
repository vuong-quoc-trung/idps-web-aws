import { useState, useEffect, useCallback } from 'react';
import { majorApi, facultyApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import type { Major, MajorPayload, Faculty } from '../../types/academic';
import type { Page } from '../../api/client';
import Modal from '../Modal';
import { CatalogTable, Pagination, SectionError, DeleteConfirm } from './CatalogShared';

const EMPTY: MajorPayload = { shortCode: '', name: '', description: '', active: true, facultyId: 0 };

function validate(f: MajorPayload): Partial<Record<keyof MajorPayload, string>> {
  const e: Partial<Record<keyof MajorPayload, string>> = {};
  if (!f.shortCode.trim()) e.shortCode = 'Mã ngành là bắt buộc';
  else if (!/^[A-Z][A-Z0-9]{0,9}$/i.test(f.shortCode.trim())) e.shortCode = 'Mã viết tắt gồm 1–10 chữ/số, bắt đầu bằng chữ';
  if (!f.name.trim()) e.name = 'Tên ngành là bắt buộc';
  if (!f.facultyId) e.facultyId = 'Phải chọn khoa';
  return e;
}

export default function MajorTab() {
  const { user } = useAuth();
  const readOnly = user?.role === 'STUDENT';
  const [data, setData]         = useState<Page<Major> | null>(null);
  const [page, setPage]         = useState(0);
  const [loading, setLoading]   = useState(false);
  const [tableErr, setTableErr] = useState<string | null>(null);

  const [faculties, setFaculties] = useState<Faculty[]>([]);

  const [modal, setModal]       = useState<{ mode: 'add' | 'edit'; item?: Major } | null>(null);
  const [form, setForm]         = useState<MajorPayload>(EMPTY);
  const [fieldErr, setFieldErr] = useState<Partial<Record<keyof MajorPayload, string>>>({});
  const [formErr, setFormErr]   = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Major | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [deleteErr, setDeleteErr]   = useState<string | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true); setTableErr(null);
    try { setData(await majorApi.list(p)); }
    catch (e) { setTableErr(e instanceof Error ? e.message : 'Lỗi tải dữ liệu'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(page); }, [page, load]);

  // Load faculty list for select
  useEffect(() => {
    facultyApi.listAll().then(r => setFaculties(r.content)).catch(() => {});
  }, []);

  function openAdd() { setForm(EMPTY); setFieldErr({}); setFormErr(null); setModal({ mode: 'add' }); }
  function openEdit(item: Major) {
    setForm({ shortCode: item.shortCode ?? '', name: item.name, description: item.description ?? '', active: item.active, facultyId: item.facultyId });
    setFieldErr({}); setFormErr(null); setModal({ mode: 'edit', item });
  }
  function closeModal() { setModal(null); }

  async function handleSubmit() {
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      const payload = { ...form, facultyId: Number(form.facultyId) };
      if (modal?.mode === 'add') await majorApi.create(payload);
      else await majorApi.update(modal!.item!.id, payload);
      closeModal(); load(page);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 409
        ? 'Mã ngành đã tồn tại hoặc không thể thay đổi khoa khi ngành đang được sử dụng'
        : e instanceof Error ? e.message : 'Lỗi không xác định';
      setFormErr(msg);
    } finally { setSubmitting(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await majorApi.remove(deleteTarget.id);
      setDeleteTarget(null); load(page);
    } catch (e) {
      setDeleteErr(e instanceof ApiError && e.status === 409
        ? 'Không thể xóa: Ngành đang được sử dụng bởi chương trình đào tạo'
        : e instanceof Error ? e.message : 'Lỗi xóa');
    } finally { setDeleting(false); }
  }

  const columns = [
    { key: 'id',          label: 'ID',        cls: 'col-id' },
    { key: 'code',        label: 'Mã ngành',  cls: 'col-code', render: (r: Major) => <span>{r.code}</span> },
    { key: 'name',        label: 'Tên ngành' },
    { key: 'facultyName', label: 'Khoa',      render: (r: Major) => <span style={{ color: 'var(--text-muted)' }}>{r.facultyName ?? `#${r.facultyId}`}</span> },
    { key: 'active', label: 'Trạng thái', cls: 'col-active', render: (r: Major) =>
        <span className={`badge ${r.active ? 'badge-active' : 'badge-inactive'}`}>{r.active ? '● Hoạt động' : '○ Ngừng'}</span> },
  ];

  return (
    <>
      {tableErr && <SectionError message={tableErr} />}
      <CatalogTable columns={columns} rows={data?.content ?? []} loading={loading}
        emptyText="Chưa có ngành nào." addLabel="Thêm ngành" onAdd={openAdd} onEdit={openEdit} onDelete={setDeleteTarget} readOnly={readOnly} />
      {data && data.totalPages > 1 && <Pagination page={page} totalPages={data.totalPages} totalElements={data.totalElements} onChange={setPage} />}

      <Modal open={!!modal} title={modal?.mode === 'add' ? 'Thêm ngành mới' : `Chỉnh sửa: ${modal?.item?.name}`}
        onClose={closeModal}
        footer={<>
          <button className="btn-cancel" onClick={closeModal} disabled={submitting}>Hủy</button>
          <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
            {submitting && <span className="spinner spinner-sm" />}
            {modal?.mode === 'add' ? 'Thêm ngành' : 'Lưu thay đổi'}
          </button>
        </>}
      >
        {formErr && <div className="form-alert"><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>{formErr}</div>}
        <div className="catalog-form">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Mã viết tắt ngành <span className="required">*</span></label>
              <input className={`form-input ${fieldErr.shortCode ? 'invalid' : ''}`} placeholder="Vd: IT"
                value={form.shortCode} onChange={e => setForm(f => ({ ...f, shortCode: e.target.value }))}
                disabled={submitting} />
              {fieldErr.shortCode && <p className="form-error-text">{fieldErr.shortCode}</p>}
            </div>
            <div className="form-group">
              <label className="form-label">Tên ngành <span className="required">*</span></label>
              <input className={`form-input ${fieldErr.name ? 'invalid' : ''}`} placeholder="Vd: Công nghệ thông tin"
                value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} disabled={submitting} />
              {fieldErr.name && <p className="form-error-text">{fieldErr.name}</p>}
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Khoa <span className="required">*</span></label>
            <select className={`form-select ${fieldErr.facultyId ? 'invalid' : ''}`}
              value={form.facultyId}
              onChange={e => setForm(f => ({ ...f, facultyId: Number(e.target.value) }))}
              disabled={submitting || (modal?.mode === 'edit')}>
              <option value={0}>— Chọn khoa —</option>
              {faculties.map(f => <option key={f.id} value={f.id}>{f.name} ({f.shortCode})</option>)}
            </select>
            {fieldErr.facultyId && <p className="form-error-text">{fieldErr.facultyId}</p>}
            {modal?.mode === 'edit' && <p className="form-hint">Không thể thay đổi khoa nếu ngành đang được sử dụng</p>}
          </div>
          <div className="form-group full">
            <label className="form-label">Mô tả</label>
            <textarea className="form-textarea" placeholder="Mô tả về ngành (tùy chọn)"
              value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} disabled={submitting} />
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
            {deleting && <span className="spinner spinner-sm" />} Xóa ngành
          </button>
        </>}
      >
        <DeleteConfirm icon="📚" title="Xóa ngành này?"
          description={<>Ngành <code>{deleteTarget?.code}</code> — <strong>{deleteTarget?.name}</strong> sẽ bị xóa. Không thể xóa nếu còn chương trình đào tạo thuộc ngành này.</>}
          error={deleteErr} />
      </Modal>
    </>
  );
}
