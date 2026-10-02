/**
 * SubResourceSection — generic section for sub-resource CRUD
 * Used for: addresses, family members, emergency contacts, post-grad contacts
 */
import { useState } from 'react';
import Modal from '../Modal';

interface SubResourceSectionProps<T extends { id: number }> {
  title: string;
  items: T[];
  renderItem: (item: T) => React.ReactNode;
  onAdd: () => Promise<void>;
  onRefresh: () => Promise<void>;
  AddEditModal: (props: { open: boolean; item: T | null; onClose: () => void }) => React.ReactNode;
  onDelete: (item: T) => Promise<void>;
  emptyText?: string;
}

export default function SubResourceSection<T extends { id: number }>({
  title, items, renderItem, onRefresh, AddEditModal, onDelete, emptyText = 'Chưa có dữ liệu.',
}: SubResourceSectionProps<T>) {
  const [editItem, setEditItem]     = useState<T | null>(null);
  const [showModal, setShowModal]   = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<T | null>(null);
  const [deleting, setDeleting]     = useState(false);
  const [deleteErr, setDeleteErr]   = useState<string | null>(null);

  function openAdd() { setEditItem(null); setShowModal(true); }
  function openEdit(item: T) { setEditItem(item); setShowModal(true); }
  function closeModal() { setShowModal(false); setEditItem(null); }
  function closeDelete() { setDeleteTarget(null); setDeleteErr(null); }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteErr(null);
    try { await onDelete(deleteTarget); await onRefresh(); closeDelete(); }
    catch (e) { setDeleteErr(e instanceof Error ? e.message : 'Lỗi xóa'); }
    finally { setDeleting(false); }
  }

  // Wrap renderItem to add action buttons
  const renderWithActions = (item: T) => {
    const rendered = renderItem(item) as React.ReactElement;
    return (
      <div key={item.id} style={{ position: 'relative' }}>
        {rendered}
        <div className="sub-card-actions">
          <button className="sv-action-btn" title="Chỉnh sửa" onClick={() => openEdit(item)}>
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M9.5 2.5L11.5 4.5L5 11H3V9L9.5 2.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
            </svg>
          </button>
          <button className="sv-action-btn danger" title="Xóa" onClick={() => setDeleteTarget(item)}>
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path d="M2.5 4h9M5.5 4V2.5h3V4M6 6.5v4M8 6.5v4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="detail-section">
      <div className="detail-section-header">
        <span className="detail-section-title">{title}</span>
        <button className="section-add-btn" onClick={openAdd}>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M5 1v8M1 5h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          Thêm
        </button>
      </div>
      <div className="detail-section-body">
        {items.length === 0 ? (
          <div className="empty-section">{emptyText}</div>
        ) : (
          <div className="sub-cards-grid">
            {items.map(renderWithActions)}
          </div>
        )}
      </div>

      {/* Add/Edit modal */}
      {showModal && AddEditModal({
        open: showModal,
        item: editItem,
        onClose: () => { closeModal(); onRefresh(); },
      })}

      {/* Delete confirm */}
      <Modal open={!!deleteTarget} title="Xác nhận xóa" size="sm"
        onClose={closeDelete}
        footer={<>
          <button className="btn-cancel" onClick={closeDelete} disabled={deleting}>Hủy</button>
          <button className="btn-danger" onClick={handleDelete} disabled={deleting}>
            {deleting && <span className="spinner spinner-sm" />} Xóa
          </button>
        </>}
      >
        <div style={{ textAlign: 'center', padding: '8px 0 4px' }}>
          <div style={{ fontSize: '2rem', marginBottom: 8 }}>🗑️</div>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
            Bạn có chắc chắn muốn xóa bản ghi này? Hành động không thể hoàn tác.
          </p>
          {deleteErr && (
            <div className="form-alert" style={{ marginTop: 12, textAlign: 'left' }}>{deleteErr}</div>
          )}
        </div>
      </Modal>
    </div>
  );
}
