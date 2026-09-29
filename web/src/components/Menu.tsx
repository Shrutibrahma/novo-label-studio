import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
}

/** Dropdown menu (dropdown elevation 11.3). Closes on outside click, Esc, or selection. */
export function Menu({
  trigger,
  items,
  header,
  align = "right",
  label,
}: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu"; "aria-controls": string }) => ReactNode;
  items: MenuItem[];
  header?: ReactNode;
  align?: "left" | "right";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    root.current?.querySelector<HTMLElement>("[role=menuitem]:not([disabled])")?.focus();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const onMenuKey = (e: React.KeyboardEvent) => {
    const list = Array.from(root.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([disabled])") ?? []);
    const i = list.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      list[(i + 1) % list.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      list[(i - 1 + list.length) % list.length]?.focus();
    }
  };

  return (
    <div ref={root} className="relative inline-flex">
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": "menu", "aria-controls": id })}
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          className={`absolute top-full z-40 mt-1 min-w-[180px] rounded-[8px] border border-border bg-surface py-1 shadow-dropdown ${align === "right" ? "right-0" : "left-0"}`}
        >
          {header && <div className="border-b border-border px-3 py-2">{header}</div>}
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={`block w-full px-3 py-2 text-left t-body hover:bg-hover-fill focus:bg-hover-fill focus:outline-none disabled:cursor-not-allowed disabled:text-text-muted ${item.danger ? "text-danger" : "text-text"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Anchored popover panel toggled by its trigger. */
export function Popover({
  trigger,
  children,
  side = "top",
}: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean }) => ReactNode;
  children: ReactNode;
  side?: "top" | "bottom";
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={root} className="relative">
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open })}
      {open && (
        <div
          role="dialog"
          className={`absolute left-2 z-40 w-[260px] rounded-[8px] border border-border bg-surface p-4 text-text shadow-dropdown ${side === "top" ? "bottom-full mb-2" : "top-full mt-2"}`}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export interface TabDef<T extends string> {
  value: T;
  label: string;
}

export function Tabs<T extends string>({ value, onChange, tabs, label }: { value: T; onChange: (v: T) => void; tabs: TabDef<T>[]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-6 border-b border-border px-6">
      {tabs.map((t) => {
        const selected = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(t.value)}
            className={`-mb-px border-b-2 py-3 t-body-strong transition-colors duration-150 ${selected ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text"}`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
