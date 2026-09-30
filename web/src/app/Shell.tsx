import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, CircleUser, History, Package, Printer, Settings, SlidersHorizontal, Tag, type LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { Banner, StatusDot } from "../components/Display";
import { Menu, Popover } from "../components/Menu";
import { api, isServerReachable, onReachabilityChange, SERVER_UNREACHABLE } from "../lib/api";
import { formatRelative, sizeText } from "../lib/format";
import { qk, useDefaultPrinter, useSettings } from "../lib/queries";
import { effectivePrinterStatus, PRINTER_STATUS_TONE, PRINTER_STATUS_WORD } from "../lib/status";
import { useIsAdmin, useUser } from "./auth";
import { usePageTitle } from "./page";
import { TestLabelButton } from "../features/print/TestLabelButton";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
}

/** Order per 12.1; operators see Print Labels, Parts (read-only), History. */
const NAV: NavItem[] = [
  { to: "/print", label: "Print Labels", icon: Printer },
  { to: "/parts", label: "Parts", icon: Package },
  { to: "/configure", label: "Configure", icon: SlidersHorizontal, adminOnly: true },
  { to: "/history", label: "History", icon: History },
  { to: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function BrandMark() {
  return (
    <span className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] bg-primary">
      <Tag size={20} strokeWidth={1.75} className="text-white" aria-hidden />
    </span>
  );
}

/** The Novo Lean Solutions logo. It has white knock-outs, so it always sits on a white tile. */
export function BrandLogo({ className = "h-12" }: { className?: string }) {
  return <img src="/brand/novo-lean-solutions.svg" alt="Novo Lean Solutions" className={`block w-auto ${className}`} draggable={false} />;
}

/** Full-screen brand backdrop (engineering line art) behind the sign-in and setup cards. */
export function AuthBackdrop({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden bg-nav-bg bg-cover bg-center p-6" style={{ backgroundImage: "url(/art/backdrop.svg)" }}>
      <div className="relative flex w-full flex-col items-center">{children}</div>
    </div>
  );
}

function PrinterStatusBlock() {
  const { printer } = useDefaultPrinter();
  const isAdmin = useIsAdmin();
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 5000);
    return () => window.clearInterval(t);
  }, []);
  if (!printer) return null;
  const status = effectivePrinterStatus(printer);
  const word = PRINTER_STATUS_WORD[status];
  return (
    <Popover
      trigger={(p) => (
        <button type="button" {...p} className="flex w-full items-center gap-3 rounded-[6px] px-4 py-3 text-left hover:bg-nav-item-hover">
          <StatusDot tone={PRINTER_STATUS_TONE[status]} />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-[13px] leading-[18px] font-semibold text-white">{printer.name}</span>
            <span className="text-[12px] leading-4 text-nav-text">{word}</span>
          </span>
        </button>
      )}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <StatusDot tone={PRINTER_STATUS_TONE[status]} />
          <span className="t-body-strong">{word}</span>
        </div>
        <p className="t-small text-text-secondary">Last seen {formatRelative(printer.agent_last_seen_at)}</p>
        <p className="t-small text-text-secondary">Loaded labels: {printer.loaded_label_size ? `${printer.loaded_label_size.name} · ${sizeText(printer.loaded_label_size)}` : "—"}</p>
        {isAdmin && <TestLabelButton printer={printer} />}
      </div>
    </Popover>
  );
}

function Sidebar() {
  const isAdmin = useIsAdmin();
  const settings = useSettings();
  return (
    <aside className="fixed inset-y-0 left-0 flex w-60 flex-col bg-nav-bg bg-[length:280px_280px]" style={{ backgroundImage: "url(/art/pattern.svg)" }}>
      <div className="flex flex-col gap-3 px-4 pt-4 pb-3">
        <div className="rounded-[8px] bg-surface px-3 py-2 shadow-card">
          <BrandLogo className="h-11" />
        </div>
        <div className="flex min-w-0 items-center gap-2 px-1">
          <Tag size={16} strokeWidth={1.75} className="shrink-0 text-nav-text" aria-hidden />
          <div className="flex min-w-0 flex-col">
            <span className="text-[15px] leading-5 font-semibold text-white">Novo Smart Labels</span>
            {settings.data?.company_name && <span className="truncate t-caption text-nav-text">{settings.data.company_name}</span>}
          </div>
        </div>
      </div>
      <div className="mx-4 border-t border-nav-divider" />
      <nav aria-label="Main" className="mt-3 flex flex-col gap-0.5 px-2">
        {NAV.filter((n) => !n.adminOnly || isAdmin).map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `flex h-10 items-center gap-3 rounded-[6px] px-4 t-body-strong transition-colors duration-150 ease-out ${isActive ? "bg-nav-item-active text-nav-text-active shadow-card" : "text-nav-text hover:bg-nav-item-hover hover:text-nav-text-active"}`
            }
          >
            <n.icon size={20} strokeWidth={1.75} aria-hidden />
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto border-t border-nav-divider p-2">
        <PrinterStatusBlock />
      </div>
    </aside>
  );
}

function UserMenu() {
  const user = useUser();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(qk.me, null);
      navigate("/login", { replace: true });
    },
  });
  return (
    <Menu
      label="User menu"
      header={<span className="t-caption text-text-muted">{user.role === "admin" ? "Admin" : "Operator"}</span>}
      items={[{ label: "Log out", onSelect: () => logout.mutate() }]}
      trigger={(p) => (
        <button type="button" {...p} className="flex h-9 items-center gap-2 rounded-[6px] px-2 text-text hover:bg-hover-fill">
          <CircleUser size={20} strokeWidth={1.75} aria-hidden />
          <span className="t-body-strong">{user.display_name}</span>
          <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
        </button>
      )}
    />
  );
}

function ReachabilityBanner() {
  const [ok, setOk] = useState(isServerReachable());
  useEffect(() => onReachabilityChange(setOk), []);
  if (ok) return null;
  return (
    <div className="px-8 pt-4">
      <Banner tone="danger">{SERVER_UNREACHABLE}</Banner>
    </div>
  );
}

/** `/` focuses the page search (12.1). */
function useSlashFocus() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable=true]")) return;
      const search = document.querySelector<HTMLInputElement>("[data-page-search]");
      if (search) {
        e.preventDefault();
        search.focus();
        search.select();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}

export function Shell({ children }: { children?: ReactNode }) {
  const title = usePageTitle();
  useSlashFocus();
  return (
    <div className="min-h-full">
      <Sidebar />
      <div className="ml-60 flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-8 backdrop-blur">
          <h1 className="flex items-center gap-3 t-h1 text-text">
            <span className="h-6 w-1 rounded-full bg-primary" aria-hidden />
            {title}
          </h1>
          <UserMenu />
        </header>
        <ReachabilityBanner />
        <main className="relative flex-1">{children ?? <Outlet />}</main>
      </div>
    </div>
  );
}

/** Standard page body: padding 32, max-width 1440, left-aligned (11.3). */
export function Page({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`max-w-[1440px] p-8 ${className}`}>{children}</div>;
}
