import { CircleCheck, CircleX, Info, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type ToastTone = "success" | "error" | "info" | "warning";
interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

const ICON: Record<ToastTone, { icon: LucideIcon; cls: string }> = {
  success: { icon: CircleCheck, cls: "text-success" },
  error: { icon: CircleX, cls: "text-danger" },
  info: { icon: Info, cls: "text-info" },
  warning: { icon: TriangleAlert, cls: "text-warning" },
};

interface ToastApi {
  show: (message: string, tone?: ToastTone) => void;
  error: (message: string) => void;
}

const Ctx = createContext<ToastApi | null>(null);

/** Toasts: bottom-right, width 360, auto-dismiss 5 s; errors stay until closed (11.4). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const show = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = next.current++;
      setItems((xs) => [...xs, { id, tone, message }]);
      if (tone !== "error") window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );
  const value = useMemo<ToastApi>(() => ({ show, error: (m) => show(m, "error") }), [show]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-6 bottom-6 z-50 flex w-[360px] flex-col gap-2" aria-live="polite">
        {items.map((t) => {
          const { icon: Icon, cls } = ICON[t.tone];
          return (
            <div key={t.id} role={t.tone === "error" ? "alert" : "status"} className="pointer-events-auto flex items-start gap-3 rounded-[8px] border border-border bg-surface px-4 py-3 shadow-dropdown">
              <Icon size={20} strokeWidth={1.75} className={`shrink-0 ${cls}`} aria-hidden />
              <p className="flex-1 t-body text-text">{t.message}</p>
              <button type="button" aria-label="Close" onClick={() => dismiss(t.id)} className="rounded p-0.5 text-text-muted hover:bg-hover-fill">
                <X size={16} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return ctx;
}
