import { ChevronDown, GripVertical, Image as ImageIcon, Plus, X, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "../../components/Button";
import { Input, SegmentedControl, Select, Switch } from "../../components/Form";
import { Tooltip } from "../../components/Tooltip";
import { inches } from "../../lib/format";
import type { CustomField, LabelStyle, ManualField, SpecField } from "../../lib/parts";
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
    </>
  );
}

export { FONT_FAMILY };
