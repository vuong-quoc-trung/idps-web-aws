/**
 * Modal — accessible dialog component used across catalog pages
 */
import { useEffect, type ReactNode } from 'react';
import './Modal.css';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Render action buttons (Submit / Cancel) in the footer */
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

export default function Modal({ open, title, onClose, children, footer, size = 'md' }: ModalProps) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handle = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handle);
    return () => document.removeEventListener('keydown', handle);
  }, [open, onClose]);

  // Lock scroll
  useEffect(() => {
    if (open) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={`modal-panel modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title-label"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <h2 className="modal-title" id="modal-title-label">{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Đóng">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">{children}</div>

        {/* Footer */}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
