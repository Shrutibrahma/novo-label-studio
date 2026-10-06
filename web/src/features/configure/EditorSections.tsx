import { ChevronDown, GripVertical, Image as ImageIcon, Plus, X, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "../../components/Button";
import { Input, SegmentedControl, Select, Switch } from "../../components/Form";
import { Tooltip } from "../../components/Tooltip";
import { inches } from "../../lib/format";
import type { BinLayout, BinSlot, CustomField, LabelStyle, ManualField, SpecField } from "../../lib/parts";
import type { LabelSize } from "../../lib/types";
import { ManualFieldDialog } from "./ManualFieldDialog";
import { RoleSelect } from "./RoleSelect";
import { CORE_FIELD_LABELS, defaultRole, fieldName, GENERATED_KEYS, PART_FIELD_KEYS, ROLE_LIMIT, type Draft } from "./types";

/** One step of the editor: a card with a numbered badge, an icon, the title and a one-line explanation. */
export function Section({ title, children, defaultOpen = true, step, icon: Icon, hint }: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  step?: number;
  icon?: LucideIcon;
  hint?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="rounded-[12px] border border-border bg-surface shadow-card">
      <h3>
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 rounded-[12px] px-5 py-4 text-left hover:bg-row-hover">
          {step !== undefined && (
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary t-caption text-white" aria-hidden>
              {step}
            </span>
          )}
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="inline-flex items-center gap-2 t-h3 text-text">
              {Icon && <Icon size={16} strokeWidth={1.75} className="text-primary" aria-hidden />}
              {title}
            </span>
            {hint && <span className="t-small text-text-muted">{hint}</span>}
          </span>
          <ChevronDown size={16} strokeWidth={1.75} className={`shrink-0 text-text-muted transition-transform duration-150 ${open ? "" : "-rotate-90"}`} aria-hidden />
        </button>
      </h3>
      {open && <div className="flex flex-col gap-4 border-t border-border px-5 pt-4 pb-5">{children}</div>}
    </section>
  );
}

const ROLE_HINT: { role: SpecField["role"]; label: string; sample: string }[] = [
  { role: "primary", label: "Main line", sample: "text-[15px] font-bold" },
  { role: "secondary", label: "Second line", sample: "text-[13px] font-semibold" },
  { role: "detail", label: "Detail", sample: "text-[11px]" },
];

/** What the three roles mean, shown above the field list. */
function RoleLegend() {
  return (
    <div className="flex items-end gap-4 rounded-[8px] bg-surface-subtle px-3 py-2">
      {ROLE_HINT.map((r) => (
        <span key={r.role} className="flex flex-col">
          <span className={`leading-tight text-text ${r.sample}`}>Aa</span>
          <span className="whitespace-nowrap t-caption text-text-muted">{r.label}</span>
        </span>
      ))}
      <span className="ml-auto text-right t-caption text-text-muted">Main line prints biggest.<br />Drag rows to reorder.</span>
    </div>
  );
}

/** Section "Size": radio cards for each active size with a proportional rectangle icon. */
export function SizeSection({ sizes, value, onChange }: { sizes: LabelSize[]; value: string; onChange: (id: string) => void }) {
  const maxW = Math.max(...sizes.map((s) => s.width_in), 1);
  const maxH = Math.max(...sizes.map((s) => s.height_in), 1);
  const scale = 28 / Math.max(maxW, maxH);
  return (
    <div role="radiogroup" aria-label="Size" className="grid grid-cols-2 gap-2">
      {sizes.map((s) => {
        const selected = s.id === value;
        return (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(s.id)}
            className={`flex items-center gap-3 rounded-[8px] border p-3 text-left transition-colors duration-150 ${selected ? "border-primary bg-primary-subtle" : "border-border bg-surface hover:bg-row-hover"}`}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center" aria-hidden>
              <span className={`block rounded-[2px] border-2 ${selected ? "border-primary" : "border-text-muted"}`} style={{ width: Math.max(6, s.width_in * scale), height: Math.max(6, s.height_in * scale) }} />
            </span>
            <span className="flex flex-col">
              <span className="t-body-strong text-text">{s.name}</span>
              <span className="t-small text-text-secondary">
                {inches(s.width_in)} × {inches(s.height_in)} in
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Section "What's on the label": ordered fields with role, caption, UPPERCASE and remove; "+ Add field". */
export function FieldsSection({ draft, onFields, custom }: { draft: Draft; onFields: (f: SpecField[]) => void; custom: CustomField[] }) {
  const fields = draft.spec.fields;
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const customLabels = Object.fromEntries(custom.map((f) => [f.key, f.label]));
  const counts = (r: SpecField["role"]) => fields.filter((f) => f.role === r).length;
  const fullRoles = new Set((["primary", "secondary", "detail"] as const).filter((r) => counts(r) >= ROLE_LIMIT[r]));
  const nextRole = defaultRole(fields);

  const update = (i: number, patch: Partial<SpecField>) => onFields(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const move = (from: number, to: number) => {
    if (to < 0 || to >= fields.length || from === to) return;
    const next = [...fields];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item!);
    onFields(next);
  };
  const add = (key: string) => {
    if (!nextRole) return;
    onFields([...fields, { key, role: nextRole, uppercase: false, caption: null }]);
    setMenuOpen(false);
  };
  const used = new Set(fields.map((f) => f.key));
  const groups: { title: string; items: { key: string; label: string }[] }[] = [
    { title: "Part fields", items: PART_FIELD_KEYS.map((k) => ({ key: k, label: CORE_FIELD_LABELS[k]! })) },
    { title: "Custom fields", items: custom.filter((f) => f.printable).map((f) => ({ key: f.key, label: f.label })) },
    { title: "Generated", items: GENERATED_KEYS.map((k) => ({ key: k, label: CORE_FIELD_LABELS[k]! })) },
    { title: "Print-time fields", items: draft.spec.manual_fields.map((m) => ({ key: `manual.${m.key}`, label: m.label })) },
  ];

  return (
    <>
      <RoleLegend />
      <ul className="flex flex-col gap-2" aria-label="Fields on the label">
        {fields.map((f, i) => {
          const name = fieldName(f.key, customLabels, draft.spec.manual_fields);
          return (
            <li
              key={f.key}
              draggable
              onDragStart={() => setDragIndex(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragIndex !== null) move(dragIndex, i);
                setDragIndex(null);
              }}
              onDragEnd={() => setDragIndex(null)}
              className={`flex flex-col gap-2 rounded-[8px] border bg-surface p-2 transition-colors duration-150 hover:border-border-strong ${f.role === "primary" ? "border-l-4 border-l-primary" : ""} ${dragIndex === i ? "border-primary" : "border-border"}`}
            >
              <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label={`Reorder ${name} (Alt+Up / Alt+Down)`}
                className="cursor-grab rounded p-1 text-text-muted hover:bg-hover-fill"
                onKeyDown={(e) => {
                  if (e.altKey && e.key === "ArrowUp") move(i, i - 1);
                  if (e.altKey && e.key === "ArrowDown") move(i, i + 1);
                }}
              >
                <GripVertical size={16} strokeWidth={1.75} aria-hidden />
              </button>
              <span className="min-w-0 flex-1 truncate t-body-strong text-text">{name}</span>
              <button type="button" aria-label={`Remove ${name}`} onClick={() => onFields(fields.filter((_, j) => j !== i))} className="rounded p-1 text-text-secondary hover:bg-hover-fill">
                <X size={16} strokeWidth={1.75} aria-hidden />
              </button>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pl-8">
                <RoleSelect label={`Role for ${name}`} value={f.role} disabledRoles={fullRoles} onChange={(role) => update(i, { role })} />
                <label className="inline-flex items-center gap-2 t-small text-text-secondary" title="Short text printed before the value, e.g. PN or REV">
                  Caption
                  <span className="block w-20 shrink-0">
                    <Input
                      aria-label={`Caption for ${name}`}
                      placeholder="none"
                      maxLength={8}
                      heightClass="h-8"
                      className="t-small"
                      value={f.caption ?? ""}
                      onChange={(e) => update(i, { caption: e.target.value || null })}
                    />
                  </span>
                </label>
                <Switch label={<span className="t-caption text-text-secondary">UPPERCASE</span>} checked={f.uppercase} onChange={(v) => update(i, { uppercase: v })} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="relative">
        <Button variant="secondary" size="sm" icon={Plus} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
          Add field
        </Button>
        {menuOpen && (
          <div role="menu" className="absolute z-30 mt-1 w-[260px] rounded-[8px] border border-border bg-surface py-1 shadow-dropdown" onMouseLeave={() => setMenuOpen(false)}>
            {groups.map((g) => {
              const items = g.items.filter((it) => !used.has(it.key));
              if (items.length === 0) return null;
              return (
                <div key={g.title} className="py-1">
                  <div className="px-3 py-1 t-caption text-text-muted uppercase">{g.title}</div>
                  {items.map((it) => {
                    const btn = (
                      <button
                        key={it.key}
                        type="button"
                        role="menuitem"
                        disabled={!nextRole}
                        onClick={() => add(it.key)}
                        className="block w-full px-3 py-1.5 text-left t-body text-text hover:bg-hover-fill disabled:cursor-not-allowed disabled:text-text-muted"
                      >
                        {it.label}
                      </button>
                    );
                    return nextRole ? btn : <Tooltip key={it.key} content="Limit reached">{btn}</Tooltip>;
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

/** A bin layout to start from: the Excel bin-label boxes, filled with custom fields whose names match. */
export function defaultBin(custom: CustomField[]): BinLayout {
  const find = (...words: string[]) =>
    custom.find((f) => words.every((w) => f.label.toLowerCase().includes(w) || f.key.includes(w)))?.key ?? null;
  return {
    title: "BIN LABEL",
    main: { key: "part_number", heading: "PART #" },
    name: { key: "part_name", heading: "NAME" },
    info1: { key: find("qty") ?? find("quantity"), heading: "BIN QTY" },
    info2: { key: find("bin", "type") ?? find("type"), heading: "BIN TYPE" },
    info3: { key: find("station"), heading: "STATION #" },
    info4: { key: find("supermarket") ?? find("location"), heading: "SUPERMARKET BIN" },
    qr_heading: "SCAN",
    image_heading: "IMAGE",
  };
}

const BIN_SLOTS: { slot: "main" | "name" | "info1" | "info2" | "info3" | "info4"; where: string }[] = [
  { slot: "main", where: "Top left, biggest" },
  { slot: "name", where: "Under the main value" },
  { slot: "info1", where: "Top right, first box" },
  { slot: "info2", where: "Top right, second box" },
  { slot: "info3", where: "Bottom right, upper box" },
  { slot: "info4", where: "Bottom right, lower box" },
];

/** A small drawing of the grid with the chosen slot highlighted. */
function SlotMap({ active }: { active: string }) {
  const cell = (name: string, cls: string) => (
    <span className={`rounded-[2px] border ${active === name ? "border-primary bg-primary" : "border-border-strong bg-surface"} ${cls}`} />
  );
  return (
    <span className="grid h-9 w-14 shrink-0 grid-cols-[3fr_1fr_1fr] grid-rows-[1fr_1fr_1fr] gap-[2px]" aria-hidden>
      {cell("main", "col-start-1 row-start-1")}
      {cell("info1", "col-start-2 row-span-2 row-start-1")}
      {cell("info2", "col-start-3 row-span-2 row-start-1")}
      {cell("name", "col-start-1 row-start-2")}
      <span className="col-span-2 col-start-1 row-start-3 grid grid-cols-2 gap-[2px]">
        <span className="rounded-[2px] border border-border-strong bg-surface-subtle" />
        <span className="rounded-[2px] border border-border-strong bg-surface-subtle" />
      </span>
      <span className="col-start-3 row-start-3 grid grid-rows-2 gap-[1px]">
        {cell("info3", "")}
        {cell("info4", "")}
      </span>
    </span>
  );
}

/** Section "Boxes" (bin layout): the title, then a heading and a field for each box of the grid. */
export function BinSection({ draft, custom, onChange }: { draft: Draft; custom: CustomField[]; onChange: (bin: BinLayout) => void }) {
  const bin = draft.spec.bin ?? defaultBin(custom);
  const options = [
    { value: "", label: "— Empty —" },
    ...PART_FIELD_KEYS.map((k) => ({ value: k, label: CORE_FIELD_LABELS[k]! })),
    ...custom.filter((f) => f.printable).map((f) => ({ value: f.key, label: f.label })),
    ...GENERATED_KEYS.map((k) => ({ value: k, label: CORE_FIELD_LABELS[k]! })),
    ...draft.spec.manual_fields.map((m) => ({ value: `manual.${m.key}`, label: `${m.label} (print-time)` })),
  ];
  const setSlot = (slot: (typeof BIN_SLOTS)[number]["slot"], patch: Partial<BinSlot>) => onChange({ ...bin, [slot]: { ...bin[slot], ...patch } });
  return (
    <>
      <label className="flex flex-col gap-1.5">
        <span className="t-body-strong text-text">Title bar</span>
        <Input aria-label="Title bar" maxLength={40} value={bin.title} placeholder="Leave empty for no title" onChange={(e) => onChange({ ...bin, title: e.target.value })} />
      </label>
      <ul className="flex flex-col gap-2" aria-label="Boxes on the label">
        {BIN_SLOTS.map(({ slot, where }) => (
          <li key={slot} className="flex items-center gap-3 rounded-[8px] border border-border p-2">
            <SlotMap active={slot} />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <span className="t-caption text-text-muted">{where}</span>
              <div className="flex gap-2">
                <span className="block w-[160px] shrink-0">
                  <Input aria-label={`Heading for ${where}`} heightClass="h-8" className="t-small uppercase" maxLength={24} placeholder="Heading" value={bin[slot].heading ?? ""} onChange={(e) => setSlot(slot, { heading: e.target.value || null })} />
                </span>
                <span className="block min-w-0 flex-1">
                  <Select aria-label={`Field for ${where}`} className="h-8 t-small" value={bin[slot].key ?? ""} options={options} onChange={(e) => setSlot(slot, { key: e.target.value || null })} />
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1.5">
          <span className="t-small text-text-secondary">QR box heading</span>
          <Input aria-label="QR box heading" heightClass="h-8" className="t-small uppercase" maxLength={24} value={bin.qr_heading} onChange={(e) => onChange({ ...bin, qr_heading: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="t-small text-text-secondary">Picture box heading</span>
          <Input aria-label="Picture box heading" heightClass="h-8" className="t-small uppercase" maxLength={24} value={bin.image_heading} onChange={(e) => onChange({ ...bin, image_heading: e.target.value })} />
        </label>
      </div>
      <p className="t-caption text-text-muted">Bin quantity, bin type, station and location come from custom fields. Add them in Settings → Custom fields and fill them by importing your parts list.</p>
    </>
  );
}

/** Section "Layout": automatic lines or the bin-label grid. */
export function LayoutSection({ value, onChange }: { value: "lines" | "bin"; onChange: (v: "lines" | "bin") => void }) {
  const card = (v: "lines" | "bin", title: string, body: string, art: ReactNode) => (
    <button
      type="button"
      role="radio"
      aria-checked={value === v}
      onClick={() => onChange(v)}
      className={`flex flex-col gap-2 rounded-[8px] border p-3 text-left transition-colors duration-150 ${value === v ? "border-primary bg-primary-subtle" : "border-border bg-surface hover:bg-row-hover"}`}
    >
      {art}
      <span className="t-body-strong text-text">{title}</span>
      <span className="t-caption text-text-secondary">{body}</span>
    </button>
  );
  return (
    <div role="radiogroup" aria-label="Layout" className="grid grid-cols-2 gap-2">
      {card("lines", "Lines", "Fields stacked as text lines, sized automatically", (
        <span className="flex h-12 flex-col justify-center gap-1 rounded-[4px] border border-border-strong bg-surface px-2" aria-hidden>
          <span className="h-2 w-3/4 rounded-full bg-text" />
          <span className="h-1.5 w-1/2 rounded-full bg-text-muted" />
          <span className="h-1 w-2/3 rounded-full bg-text-muted" />
        </span>
      ))}
      {card("bin", "Bin label", "Boxed grid with headings, QR and photo, like a TPS bin card", (
        <span className="grid h-12 grid-cols-[2fr_1fr_1fr] grid-rows-[1fr_2fr_2fr] gap-[2px] rounded-[4px] border border-border-strong bg-surface p-[2px]" aria-hidden>
          <span className="col-span-3 rounded-[1px] bg-text" />
          <span className="rounded-[1px] border border-text-muted" />
          <span className="row-span-1 rounded-[1px] border border-text-muted" />
          <span className="rounded-[1px] border border-text-muted" />
          <span className="rounded-[1px] border border-text-muted" />
          <span className="rounded-[1px] border border-text-muted" />
          <span className="rounded-[1px] border border-text-muted" />
        </span>
      ))}
    </div>
  );
}

/** Section "Print-time fields": list + "Add print-time field". */
export function ManualSection({ draft, onChange }: { draft: Draft; onChange: (manual: ManualField[], fields: SpecField[]) => void }) {
  const [editing, setEditing] = useState<ManualField | "new" | null>(null);
  const manual = draft.spec.manual_fields;
  const TYPE: Record<ManualField["type"], string> = { text: "Text", number: "Number", choice: "Choice", box_sequence: "Box sequence" };
  return (
    <>
      <ul className="flex flex-col gap-2">
        {manual.map((m) => (
          <li key={m.key} className="flex items-center gap-3 rounded-[8px] border border-border p-2 pl-3">
            <button type="button" className="flex-1 text-left" onClick={() => setEditing(m)}>
              <span className="t-body-strong text-text">{m.label}</span>
              {m.required && <span className="ml-0.5 text-danger">*</span>}
              <span className="ml-2 t-small text-text-secondary">{TYPE[m.type]}</span>
            </button>
            <button
              type="button"
              aria-label={`Remove ${m.label}`}
              onClick={() => onChange(manual.filter((x) => x.key !== m.key), draft.spec.fields.filter((f) => f.key !== `manual.${m.key}`))}
              className="rounded p-1 text-text-secondary hover:bg-hover-fill"
            >
              <X size={16} strokeWidth={1.75} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <div>
        <Button variant="secondary" size="sm" icon={Plus} onClick={() => setEditing("new")}>
          Add print-time field
        </Button>
      </div>
      <ManualFieldDialog
        open={editing !== null}
        editing={editing === "new" ? null : editing}
        existing={manual}
        onClose={() => setEditing(null)}
        onSave={(m) => {
          const next = editing === "new" || editing === null ? [...manual, m] : manual.map((x) => (x.key === m.key ? m : x));
          onChange(next, draft.spec.fields);
          setEditing(null);
        }}
      />
    </>
  );
}

/** Section "Picture": the part's photo on the label, dithered for the thermal printer. */
export function PictureSection({ draft, onChange }: { draft: Draft; onChange: (style: Partial<LabelStyle>) => void }) {
  const style = draft.spec.style;
  const value = style.image_position ?? "none";
  const qrOn = draft.qr_mode !== "none";
  if (style.layout === "bin") {
    return (
      <SegmentedControl
        ariaLabel="Picture"
        value={value === "none" ? "none" : "left"}
        onChange={(v) => onChange({ image_position: v })}
        options={[
          { value: "none", label: "Off" },
          { value: "left", label: "Show photo box" },
        ]}
      />
    );
  }
  return (
    <>
      <div className="flex items-start gap-3 rounded-[8px] bg-surface-subtle p-3">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-primary-subtle text-primary">
          <ImageIcon size={18} strokeWidth={1.75} aria-hidden />
        </span>
        <p className="t-small text-text-secondary">
          Prints the photo from the part, in black-and-white dots (the printer has no grey). Parts without a photo print text only. On tall labels the photo goes above the text.
        </p>
      </div>
      <SegmentedControl
        ariaLabel="Picture"
        value={value}
        onChange={(v) => {
          // The picture and the QR code can't share a side: move the QR code across.
          const flip = qrOn && v !== "none" && v === style.qr_position;
          onChange(flip ? { image_position: v, qr_position: v === "left" ? "right" : "left" } : { image_position: v });
        }}
        options={[
          { value: "none", label: "Off" },
          { value: "left", label: "Left" },
          { value: "right", label: "Right" },
        ]}
      />
    </>
  );
}

/** Section "QR code & serial". */
export function QrSection({ draft, onChange }: { draft: Draft; onChange: (patch: Partial<Draft>, style?: Partial<LabelStyle>) => void }) {
  const serialOn = draft.serial_mode === "required";
  return (
    <>
      <Switch
        label="Serial number"
        description="Give every label a unique serial"
        checked={serialOn}
        onChange={(on) => onChange(on ? { serial_mode: "required" } : { serial_mode: "none", qr_mode: draft.qr_mode === "serial" ? "none" : draft.qr_mode })}
      />
      <div className="flex flex-col gap-1.5">
        <span className="t-body-strong text-text">QR code</span>
        <SegmentedControl
          ariaLabel="QR code"
          value={draft.qr_mode}
          onChange={(v) => onChange({ qr_mode: v })}
          options={[
            { value: "none", label: "None" },
            { value: "part", label: "Part" },
            { value: "serial", label: "Serial", disabled: !serialOn, tooltip: serialOn ? undefined : "Turn on serial numbers first" },
          ]}
        />
      </div>
      {draft.qr_mode !== "none" && (
        <div className="flex flex-col gap-1.5">
          <span className="t-body-strong text-text">QR contains</span>
          <SegmentedControl
            ariaLabel="QR contains"
            value={draft.spec.style.qr_content ?? "part_number"}
            onChange={(v) => onChange({}, { qr_content: v })}
            options={[
              { value: "part_number", label: "Part number" },
              { value: "label_data", label: "All label data" },
            ]}
          />
          <span className="t-caption text-text-muted">
            {(draft.spec.style.qr_content ?? "part_number") === "label_data"
              ? "Scanning shows every value on the label, one per line. Too much text makes the QR too small to print."
              : "Scanning gives PN: and the part number."}
          </span>
        </div>
      )}
      {draft.qr_mode !== "none" && draft.spec.style.layout !== "bin" && (
        <div className="flex flex-col gap-1.5">
          <span className="t-body-strong text-text">QR position</span>
          <SegmentedControl
            ariaLabel="QR position"
            value={draft.spec.style.qr_position}
            onChange={(v) => {
              const img = draft.spec.style.image_position ?? "none";
              onChange({}, img !== "none" && img === v ? { qr_position: v, image_position: v === "left" ? "right" : "left" } : { qr_position: v });
            }}
            options={[
              { value: "left", label: "Left" },
              { value: "right", label: "Right" },
            ]}
          />
        </div>
      )}
    </>
  );
}

const FONT_FAMILY: Record<LabelStyle["font"], string> = {
  inter: "Inter",
  roboto_condensed: "Roboto Condensed",
  atkinson: "Atkinson Hyperlegible",
};

/** Section "Style". */
export function StyleSection({ style, fonts, onChange }: { style: LabelStyle; fonts: string[]; onChange: (s: Partial<LabelStyle>) => void }) {
  const bin = style.layout === "bin";
  const Row = ({ label, children }: { label: string; children: ReactNode }) => (
    <div className="flex flex-col gap-1.5">
      <span className="t-body-strong text-text">{label}</span>
      {children}
    </div>
  );
  return (
    <>
      <Row label="Font">
        <Select
          aria-label="Font"
          value={style.font}
          style={{ fontFamily: FONT_FAMILY[style.font] }}
          onChange={(e) => onChange({ font: e.target.value as LabelStyle["font"] })}
          options={(Object.keys(FONT_FAMILY) as LabelStyle["font"][]).filter((f) => fonts.includes(f)).map((f) => ({ value: f, label: FONT_FAMILY[f], style: { fontFamily: FONT_FAMILY[f] } }))}
        />
      </Row>
      <Row label="Main line weight">
        <SegmentedControl ariaLabel="Main line weight" value={style.primary_weight} onChange={(v) => onChange({ primary_weight: v })}
          options={[{ value: "regular", label: "Regular" }, { value: "bold", label: "Bold" }, { value: "extra_bold", label: "Extra bold" }]} />
      </Row>
      {!bin && (<>
      <Row label="Text size">
        <SegmentedControl ariaLabel="Text size" value={style.emphasis} onChange={(v) => onChange({ emphasis: v })}
          options={[{ value: "small", label: "Small" }, { value: "medium", label: "Medium" }, { value: "large", label: "Large" }]} />
      </Row>
      <Row label="Alignment">
        <SegmentedControl ariaLabel="Alignment" value={style.alignment} onChange={(v) => onChange({ alignment: v })}
          options={[{ value: "left", label: "Left" }, { value: "center", label: "Center" }]} />
      </Row>
      <Row label="Spacing">
        <SegmentedControl ariaLabel="Spacing" value={style.spacing} onChange={(v) => onChange({ spacing: v })}
          options={[{ value: "compact", label: "Compact" }, { value: "standard", label: "Standard" }, { value: "spacious", label: "Spacious" }]} />
      </Row>
      </>)}
    </>
  );
}

export { FONT_FAMILY };
