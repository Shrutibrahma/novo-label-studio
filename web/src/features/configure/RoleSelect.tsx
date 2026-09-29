import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Tooltip } from "../../components/Tooltip";
import type { SpecField } from "../../lib/parts";
import { ROLE_LABEL } from "./types";

type Role = SpecField["role"];

/** Role select (Main line / Second line / Detail); full roles are disabled with the tooltip "Limit reached". */
export function RoleSelect({ value, onChange, disabledRoles, label }: { value: Role; onChange: (r: Role) => void; disabledRoles: Set<Role>; label: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
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
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex h-8 w-[124px] items-center justify-between rounded-[6px] border border-border-strong bg-surface px-2 t-small text-text"
      >
        {ROLE_LABEL[value]}
        <ChevronDown size={16} strokeWidth={1.75} className="text-text-muted" aria-hidden />
      </button>
      {open && (
        <ul role="listbox" className="absolute z-30 mt-1 w-[140px] rounded-[8px] border border-border bg-surface py-1 shadow-dropdown">
          {(Object.keys(ROLE_LABEL) as Role[]).map((r) => {
            const disabled = disabledRoles.has(r) && r !== value;
            const item = (
              <button
                type="button"
                role="option"
                aria-selected={r === value}
                aria-disabled={disabled}
                onClick={() => {
                  if (disabled) return;
                  onChange(r);
                  setOpen(false);
                }}
                className={`block w-full px-3 py-1.5 text-left t-small ${disabled ? "cursor-not-allowed text-text-muted" : "text-text hover:bg-hover-fill"} ${r === value ? "font-semibold" : ""}`}
              >
                {ROLE_LABEL[r]}
              </button>
            );
            return <li key={r}>{disabled ? <Tooltip content="Limit reached">{item}</Tooltip> : item}</li>;
          })}
        </ul>
      )}
    </div>
  );
}
