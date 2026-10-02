/**
 * CatalogShared — reusable sub-components for all catalog tabs:
 * CatalogTable, Pagination, SectionError, DeleteConfirm
 */
import type { ReactNode } from 'react';

// ============================================================
// Column definition
// ============================================================
export interface Column<T> {
  key: string;
  label: string;
  cls?: string;
  render?: (row: T) => ReactNode;
}

// ============================================================
// CatalogTable
// ============================================================
interface TableProps<T extends { id: number }> {
  columns: Column<T>[];
  rows: T[];
  loading: boolean;
  emptyText: string;
  addLabel: string;
  onAdd: () => void;
  onEdit: (row: T) => void;
  onDelete: (row: T) => void;
}

export function CatalogTable<T extends { id: number }>({
  columns, rows, loading, emptyText, addLabel, onAdd, onEdit, onDelete,
}: TableProps<T>) {
  return (
    <div className="catalog-table-wrap">
      {/* Table header row with Add button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <button className="btn-add" id={`btn-add-${addLabel}`} onClick={onAdd}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          {addLabel}
        </button>
      </div>

      <table className="catalog-table">
        <thead>
          <tr>
            {columns.map(c => <th key={c.key} className={c.cls}>{c.label}</th>)}
            <th className="col-actions">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={columns.length + 1}>
              <div className="table-state">
                <span className="spinner" style={{ width: 20, height: 20, borderWidth: 2 }} />
                <p>Đang tải…</p>
              </div>
            </td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={columns.length + 1}>
              <div className="table-state">
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ color: 'var(--text-muted)' }}>
                  <rect x="4" y="6" width="24" height="20" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M4 12h24" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M10 18h12M10 22h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                <p>{emptyText}</p>
              </div>
            </td></tr>
          ) : rows.map(row => (
            <tr key={row.id}>
              {columns.map(c => (
                <td key={c.key} className={c.cls} data-label={c.label}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '—')}
                </td>
              ))}
              <td className="col-actions">
                <div className="row-actions">
                  <button className="action-btn" id={`edit-${row.id}`} onClick={() => onEdit(row)} title="Chỉnh sửa">
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M9.5 2.5L11.5 4.5L5 11H3V9L9.5 2.5z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round"/>
                    </svg>
                  </button>
                  <button className="action-btn delete" id={`delete-${row.id}`} onClick={() => onDelete(row)} title="Xóa">
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M2 4h10M5 4V3h4v1M5.5 6.5v4M8.5 6.5v4M3 4l.75 8h6.5L11 4" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// Pagination
// ============================================================
interface PaginationProps {
  page: number;
  totalPages: number;
  totalElements: number;
  onChange: (p: number) => void;
}

export function Pagination({ page, totalPages, totalElements, onChange }: PaginationProps) {
  const pages = Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
    if (totalPages <= 7) return i;
    if (page < 4) return i;
    if (page > totalPages - 4) return totalPages - 7 + i;
    return page - 3 + i;
  });

  return (
    <div className="catalog-pagination">
      <span className="pagination-info">
        Tổng cộng <strong>{totalElements}</strong> bản ghi
      </span>
      <div className="pagination-controls">
        <button className="page-btn" onClick={() => onChange(page - 1)} disabled={page === 0}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M8 2L4 6l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        {pages.map(p => (
          <button key={p} className={`page-btn ${p === page ? 'active' : ''}`} onClick={() => onChange(p)}>
            {p + 1}
          </button>
        ))}
        <button className="page-btn" onClick={() => onChange(page + 1)} disabled={page >= totalPages - 1}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

// ============================================================
// SectionError
// ============================================================
export function SectionError({ message }: { message: string }) {
  return (
    <div className="section-error" role="alert">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
      {message}
    </div>
  );
}

// ============================================================
// DeleteConfirm (body content for delete modal)
// ============================================================
interface DeleteConfirmProps {
  icon: string;
  title: string;
  description: ReactNode;
  error: string | null;
}

export function DeleteConfirm({ title, description, error }: DeleteConfirmProps) {
  return (
    <div className="delete-confirm">
      <div className="delete-confirm-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M10 11v6M14 11v6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
        </svg>
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {error && (
        <div className="form-alert" style={{ textAlign: 'left', width: '100%' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M8 4.5v4M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          {error}
        </div>
      )}
    </div>
  );
}
