import { useEffect, useRef, useId, type ReactNode } from 'react';
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
  const panelRef = useRef<HTMLDivElement>(null);
  const reactId = useId();
  const titleId = `modal-title-${reactId.replace(/:/g, '')}`;

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

  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Move focus into the dialog on open and restore on close
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
      if (panelRef.current) {
        // Priority 1: Explicit autofocus element inside the modal
        // Priority 2: First active form control inside modal body
        // Priority 3: First interactive element inside modal body
        // Priority 4: Dialog title heading (with tabIndex=-1) or dialog panel
        // (Do NOT default focus to the close 'X' button)
        const autoFocusEl = panelRef.current.querySelector<HTMLElement>('[autofocus]');
        const body = panelRef.current.querySelector<HTMLElement>('.modal-body');
        const firstInput = body?.querySelector<HTMLElement>(
          'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])'
        );
        const firstAction = body?.querySelector<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
        );
        const heading = panelRef.current.querySelector<HTMLElement>('.modal-title');

        const target = autoFocusEl ?? firstInput ?? firstAction ?? heading ?? panelRef.current;
        target.focus();
      }
    } else if (previousFocusRef.current && document.contains(previousFocusRef.current)) {
      previousFocusRef.current.focus();
    }
  }, [open]);

  // Focus trap — keep Tab / Shift+Tab inside the dialog
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    function handleTab(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      const focusableAll = Array.from(
        panel!.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (focusableAll.length === 0) { e.preventDefault(); return; }
      const first = focusableAll[0];
      const last = focusableAll[focusableAll.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }

    panel.addEventListener('keydown', handleTab);
    return () => panel.removeEventListener('keydown', handleTab);
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={panelRef}
        className={`modal-panel modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <h2 className="modal-title" id={titleId} tabIndex={-1}>{title}</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Đóng">
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
