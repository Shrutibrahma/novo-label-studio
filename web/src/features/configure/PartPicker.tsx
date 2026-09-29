import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { useDebounced, type PartList, type PartListItem } from "../../lib/parts";

export type PickedPart = Pick<PartListItem, "id" | "part_number" | "part_name" | "label_name">;

/** "Preview with part" combobox: search parts, pick one (12.11). */
export function PartPicker({ value, onChange }: { value: PickedPart | null; onChange: (p: PickedPart) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 200);
  const root = useRef<HTMLDivElement>(null);
  const results = useQuery({
    queryKey: ["parts", { picker: dq }],
    queryFn: () => api<PartList>(`/parts?limit=8&status=active${dq ? `&q=${encodeURIComponent(dq)}` : ""}`),
    enabled: open,
  });
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  const label = value ? `${value.part_number} · ${value.label_name ?? value.part_name}` : "";
  return (
    <div ref={root} className="relative">
      <label htmlFor="preview-part" className="mb-1.5 block t-body-strong text-text">
        Preview with part
      </label>
      <div className="relative">
        <input
          id="preview-part"
          role="combobox"
          aria-expanded={open}
          aria-controls="preview-part-list"
          autoComplete="off"
          className="h-9 w-full rounded-[6px] border border-border-strong bg-surface pr-9 pl-3 text-text focus:border-primary focus:outline-2 focus:outline-offset-2 focus:outline-focus-ring"
          value={open ? q : label}
          placeholder={label}
          onFocus={() => {
            setOpen(true);
            setQ("");
          }}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        />
        <ChevronDown size={16} strokeWidth={1.75} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-text-muted" aria-hidden />
      </div>
      {open && (
        <ul id="preview-part-list" role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-[8px] border border-border bg-surface py-1 shadow-dropdown">
          {(results.data?.items ?? []).map((p) => (
            <li key={p.id} role="option" aria-selected={p.id === value?.id}>
              <button
                type="button"
                className="flex w-full flex-col px-3 py-2 text-left hover:bg-hover-fill"
                onClick={() => {
                  onChange(p);
                  setOpen(false);
                }}
              >
                <span className="t-mono text-text">{p.part_number}</span>
                <span className="t-small text-text-secondary">{p.label_name ?? p.part_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
