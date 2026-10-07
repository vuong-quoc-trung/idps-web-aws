import { useState, useEffect, useCallback } from 'react';
import { facultyApi } from '../../api/academicApi';
import { ApiError } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import type { Faculty, FacultyPayload } from '../../types/academic';
import type { Page } from '../../api/client';
import Modal from '../Modal';
import { CatalogTable, type Column, Pagination, SectionError, DeleteConfirm } from './CatalogShared';

// ---- Empty form state ----
const EMPTY: FacultyPayload = { shortCode: '', name: '', description: '', active: true };

// ---- Validation ----
function validate(f: FacultyPayload): Partial<Record<keyof FacultyPayload, string>> {
  const e: Partial<Record<keyof FacultyPayload, string>> = {};
  if (!f.shortCode.trim()) e.shortCode = 'Mã khoa là bắt buộc';
  else if (!/^[A-Z][A-Z0-9]{0,9}$/i.test(f.shortCode.trim())) e.shortCode = 'Mã viết tắt gồm 1–10 chữ/số, bắt đầu bằng chữ';
  if (!f.name.trim()) e.name = 'Tên khoa là bắt buộc';
  return e;
}

export default function FacultyTab() {
  const { user } = useAuth();
  const readOnly = user?.role === 'STUDENT';
  const [data, setData]       = useState<Page<Faculty> | null>(null);
  const [page, setPage]       = useState(0);
  const [loading, setLoading] = useState(false);
  const [tableErr, setTableErr] = useState<string | null>(null);

  const [modal, setModal]     = useState<{ mode: 'add' | 'edit'; item?: Faculty } | null>(null);
  const [form, setForm]       = useState<FacultyPayload>(EMPTY);
  const [fieldErr, setFieldErr] = useState<Partial<Record<keyof FacultyPayload, string>>>({});
  const [formErr, setFormErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Faculty | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true); setTableErr(null);
    try { setData(await facultyApi.list(p)); }
    catch (e) { setTableErr(e instanceof Error ? e.message : 'Lỗi tải dữ liệu'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(page); }, [page, load]);

  function openAdd() { setForm(EMPTY); setFieldErr({}); setFormErr(null); setModal({ mode: 'add' }); }
  function openEdit(item: Faculty) {
    setForm({ shortCode: item.shortCode ?? '', name: item.name, description: item.description ?? '', active: item.active });
    setFieldErr({}); setFormErr(null);
    setModal({ mode: 'edit', item });
  }
  function closeModal() { setModal(null); }

  async function handleSubmit() {
    const errs = validate(form);
    if (Object.keys(errs).length) { setFieldErr(errs); return; }
    setSubmitting(true); setFormErr(null);
    try {
      if (modal?.mode === 'add') await facultyApi.create(form);
      else await facultyApi.update(modal!.item!.id, form);
      closeModal();
      load(page);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 409
        ? 'Mã khoa đã tồn tại trong hệ thống'
        : e instanceof Error ? e.message : 'Lỗi không xác định';
      setFormErr(msg);
    } finally { setSubmitting(false); }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try {
      await facultyApi.remove(deleteTarget.id);
      setDeleteTarget(null);
      load(page);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 409
        ? 'Không thể xóa: Khoa đang được sử dụng bởi ngành khác'
        : e instanceof Error ? e.message : 'Lỗi xóa dữ liệu';
      setDeleteErr(msg);
    } finally { setDeleting(false); }
  }

  const columns: Column<Faculty>[] = [
    { key: 'id',     label: 'ID',        cls: 'col-id' },
    { key: 'code',   label: 'Mã khoa',   cls: 'col-code', render: (r: Faculty) => <span>{r.code}</span> },
    { key: 'name',   label: 'Tên khoa' },
    { key: 'description', label: 'Mô tả', render: (r: Faculty) => <span style={{ color: 'var(--text-muted)' }}>{r.description || '—'}</span> },
    { key: 'active', label: 'Trạng thái', cls: 'col-active', render: (r: Faculty) =>
        <span className={`badge ${r.active ? 'badge-active' : 'badge-inactive'}`}>{r.active ? '● Hoạt động' : '○ Ngừng'}</span> },
  ];

  return (
    <>
      {tableErr && <SectionError message={tableErr} />}

      <CatalogTable
        columns={columns}
        rows={data?.content ?? []}
        loading={loading}
        emptyText="Chưa có khoa nào. Nhấn «Thêm khoa» để tạo mới."
        onAdd={openAdd}
        addLabel="Thêm khoa"
        onEdit={openEdit}
        onDelete={row => setDeleteTarget(row)}
        readOnly={readOnly}
      />

      {data && data.totalPages > 1 && (
        <Pagination page={page} totalPages={data.totalPages} totalElements={data.totalElements} onChange={setPage} />
      )}

      {/* Add / Edit modal */}
      <Modal
        open={!!modal}
        title={modal?.mode === 'add' ? 'Thêm khoa mới' : `Chỉnh sửa: ${modal?.item?.name}`}
        onClose={closeModal}
        footer={
          <>
            <button className="btn-cancel" onClick={closeModal} disabled={submitting}>Hủy</button>
            <button className="btn-submit" onClick={handleSubmit} disabled={submitting}>
              {submitting && <span className="spinner spinner-sm" />}
              {modal?.mode === 'add' ? 'Thêm khoa' : 'Lưu thay đổi'}
            </button>
          </>
        }
      >
        {formErr && (
          <div className="form-alert">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            {formErr}
          </div>
        )}
        <div className="catalog-form">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="faculty-shortcode-input">Mã viết tắt khoa <span className="required">*</span></label>
              <input className={`form-input ${fieldErr.shortCode ? 'invalid' : ''}`}
                id="faculty-shortcode-input"
                aria-describedby={fieldErr.shortCode ? 'faculty-shortcode-error' : undefined}
                aria-invalid={!!fieldErr.shortCode}
                placeholder="Vd: IT" value={form.shortCode}
                onChange={e => setForm(f => ({ ...f, shortCode: e.target.value }))}
                disabled={submitting} />
              {fieldErr.shortCode && <p className="form-error-text" id="faculty-shortcode-error">{fieldErr.shortCode}</p>}
              {modal?.mode === 'edit' && <p className="form-hint">Mã không thể thay đổi sau khi tạo</p>}
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="faculty-name-input">Tên khoa <span className="required">*</span></label>
              <input className={`form-input ${fieldErr.name ? 'invalid' : ''}`}
                id="faculty-name-input"
                aria-describedby={fieldErr.name ? 'faculty-name-error' : undefined}
                aria-invalid={!!fieldErr.name}
                placeholder="Vd: Khoa Công nghệ thông tin" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))} disabled={submitting} />
              {fieldErr.name && <p className="form-error-text" id="faculty-name-error">{fieldErr.name}</p>}
            </div>
          </div>
          <div className="form-group full">
            <label className="form-label" htmlFor="faculty-description-textarea">Mô tả</label>
            <textarea className="form-textarea" id="faculty-description-textarea" placeholder="Mô tả về khoa (tùy chọn)" value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))} disabled={submitting} />
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

      {/* Delete confirm */}
      <Modal open={!!deleteTarget} title="Xác nhận xóa" onClose={() => { setDeleteTarget(null); setDeleteErr(null); }} size="sm"
        footer={
          <>
            <button className="btn-cancel" onClick={() => { setDeleteTarget(null); setDeleteErr(null); }} disabled={deleting}>Hủy</button>
            <button className="btn-danger" onClick={handleDelete} disabled={deleting}>
              {deleting && <span className="spinner spinner-sm" />} Xóa khoa
            </button>
          </>
        }
      >
        <DeleteConfirm
          title="Xóa khoa này?"
          description={<>Khoa <code>{deleteTarget?.code}</code> — <strong>{deleteTarget?.name}</strong> sẽ bị xóa vĩnh viễn. Không thể xóa nếu còn ngành thuộc khoa này.</>}
          error={deleteErr}
        />
      </Modal>
    </>
  );
}
