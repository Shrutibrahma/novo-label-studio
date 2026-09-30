import { CircleCheck, CircleX, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { Tone } from "../lib/status";

const BADGE_TONE: Record<Tone, string> = {
  success: "bg-success-bg text-success",
  info: "bg-info-bg text-info",
  warning: "bg-warning-bg text-warning",
  danger: "bg-danger-bg text-danger",
  neutral: "bg-neutral-bg text-neutral-text",
  archived: "bg-neutral-bg text-neutral-text italic",
};

/** Badge: h 22, px 8, pill, Caption text (11.4). */
export function Badge({ tone, children, className = "" }: { tone: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-[22px] items-center rounded-full px-2 t-caption whitespace-nowrap ${BADGE_TONE[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function PrimaryBadge({ children }: { children: ReactNode }) {
  return <span className="inline-flex h-[22px] items-center rounded-full bg-primary-subtle px-2 t-caption text-primary">{children}</span>;
}

const DOT: Record<Tone, string> = {
  success: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-text-muted",
  archived: "bg-text-muted",
};

export function StatusDot({ tone }: { tone: Tone }) {
  return <span aria-hidden className={`inline-block h-2 w-2 shrink-0 rounded-full ${DOT[tone]}`} />;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-[8px] border border-border bg-surface shadow-card p-6 ${className}`}>{children}</div>;
}

/** Empty state: centred 40 px muted icon, H3 title, body text, one primary button (11.4). */
export function EmptyState({ icon: Icon, title, body, action }: { icon: LucideIcon; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <Icon size={40} strokeWidth={1.75} className="text-text-muted" aria-hidden />
      <h3 className="t-h3 text-text">{title}</h3>
      {body && <div className="t-body text-text-secondary">{body}</div>}
      {action && <div className="mt-3 flex items-center gap-2">{action}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

const BANNER: Record<"info" | "warning" | "danger" | "success", { cls: string; icon: LucideIcon }> = {
  info: { cls: "bg-info-bg text-info", icon: Info },
  warning: { cls: "bg-warning-bg text-warning", icon: TriangleAlert },
  danger: { cls: "bg-danger-bg text-danger", icon: CircleX },
  success: { cls: "bg-success-bg text-success", icon: CircleCheck },
};

export function Banner({ tone, children, action }: { tone: keyof typeof BANNER; children: ReactNode; action?: ReactNode }) {
  const { cls, icon: Icon } = BANNER[tone];
  return (
    <div role={tone === "danger" || tone === "warning" ? "alert" : "status"} className={`flex items-start gap-3 rounded-[8px] px-4 py-3 ${cls}`}>
      <Icon size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden />
      <div className="flex-1 t-body">{children}</div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-text-secondary" role="status">
      <span className="spinner" aria-hidden />
      {label && <span className="t-body">{label}</span>}
    </span>
  );
}

export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`t-mono ${className}`}>{children}</span>;
}
