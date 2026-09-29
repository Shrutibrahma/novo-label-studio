import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";

/** Stack of open overlays so Esc closes only the topmost (12.1 keyboard). */
const stack: symbol[] = [];

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useOverlay(open: boolean, onClose: () => void, panel: React.RefObject<HTMLElement | null>) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const token = Symbol("overlay");
    stack.push(token);
    const previous = document.activeElement as HTMLElement | null;
    const el = panel.current;
    const first = el?.querySelector<HTMLElement>("[data-autofocus]") ?? el?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? el)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (stack[stack.length - 1] !== token) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
      } else if (e.key === "Tab" && el) {
        const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((n) => n.offsetParent !== null);
        if (items.length === 0) return;
        const firstItem = items[0]!;
        const lastItem = items[items.length - 1]!;
        if (e.shiftKey && document.activeElement === firstItem) {
          e.preventDefault();
          lastItem.focus();
        } else if (!e.shiftKey && document.activeElement === lastItem) {
          e.preventDefault();
          firstItem.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      const i = stack.indexOf(token);
      if (i >= 0) stack.splice(i, 1);
      previous?.focus?.();
    };
  }, [open, panel]);
}

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  width?: number;
  children: ReactNode;
  footer?: ReactNode;
  /** Footer content aligned left (e.g. danger actions). */
  footerLeft?: ReactNode;
}

/** Dialog: width 560 default, radius 12, header 20/600, right-aligned footer (11.4). */
export function Dialog({ open, onClose, title, subtitle, width = 560, children, footer, footerLeft }: DialogProps) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useOverlay(open, onClose, panel);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-text/40 p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ width, maxWidth: "100%" }}
        className="flex max-h-[calc(100vh-48px)] flex-col rounded-[12px] bg-surface shadow-dialog outline-none"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="t-h2 text-text">
              {title}
            </h2>
            {subtitle && <div className="mt-0.5 t-small text-text-secondary">{subtitle}</div>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-[6px] p-1 text-text-secondary hover:bg-hover-fill">
            <X size={20} strokeWidth={1.75} aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {(footer || footerLeft) && (
          <div className="flex items-center gap-2 border-t border-border px-6 py-4">
            <div className="flex flex-1 items-center gap-2">{footerLeft}</div>
            <div className="flex items-center gap-2">{footer}</div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  cancelLabel = "Cancel",
  confirmLabel,
  danger,
  loading,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: ReactNode;
  body?: ReactNode;
  cancelLabel?: string;
  confirmLabel: string;
  danger?: boolean;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {body && <div className="t-body text-text-secondary">{body}</div>}
    </Dialog>
  );
}

/** Drawer: right side, width 520, full height, radius 12 on the leading edge (11.4). */
export function Drawer({
  open,
  onClose,
  header,
  children,
  footer,
  label,
}: {
  open: boolean;
  onClose: () => void;
  header: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  label: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useOverlay(open, onClose, panel);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-30 flex justify-end bg-text/25" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className="flex h-full w-[520px] flex-col rounded-l-[12px] bg-surface shadow-dialog outline-none"
      >
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <div className="min-w-0 flex-1">{header}</div>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-[6px] p-1 text-text-secondary hover:bg-hover-fill">
            <X size={20} strokeWidth={1.75} aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="border-t border-border px-6 py-4">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
