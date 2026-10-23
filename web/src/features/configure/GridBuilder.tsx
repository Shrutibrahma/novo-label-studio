import { ArrowDown, ArrowUp, Image as ImageIcon, LayoutTemplate, Minus, PenLine, Plus, QrCode, Trash2, Type } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Button } from "../../components/Button";
import { Input, SegmentedControl, Select, Switch } from "../../components/Form";
import type { BinLayout, CustomField, GridCell, GridLayout, GridRow, ManualField } from "../../lib/parts";
import { CORE_FIELD_LABELS, fieldName, GENERATED_KEYS, PART_FIELD_KEYS, type Draft } from "./types";

const MAX_ROWS = 8;
const MAX_CELLS = 6;
const MIN_PCT = 8;

const field = (key: string | null, heading: string | null, width = 1, extra: Partial<GridCell> = {}): GridCell => ({
  kind: "field",
  key,
  text: null,
  heading,
  width,
  size: "auto",
  align: "center",
  bold: true,
  ...extra,
});

/** Custom field whose name contains every word (e.g. "bin", "qty"), for filling templates. */
function finder(custom: CustomField[]) {
  return (...words: string[]) => custom.find((f) => words.every((w) => f.label.toLowerCase().includes(w) || f.key.includes(w)))?.key ?? null;
}

export type TemplateName = "tps" | "bin" | "kanban" | "simple" | "blank";

/** The print-time counter a kanban card prints as "CARD 1/2" (numbered automatically when printing a set). */
export const KANBAN_CARD_FIELD: ManualField = { key: "card", label: "Card", type: "box_sequence", noun: "CARD", required: false };

export function gridTemplate(name: TemplateName, custom: CustomField[]): GridLayout {
  const find = finder(custom);
  if (name === "tps") {
    // Standard TPS card: header block (process, part #, location), the destination code big enough to read from
    // a distance, the standard lot size with min/max, and the QR in the bottom-right corner.
    const loc = find("location") ?? find("supermarket") ?? find("rack") ?? find("bin");
    return {
      rows: [
        { height: 3, cells: [field(find("process") ?? find("station") ?? find("cell"), "PROCESS", 2), field("part_number", "PART #", 3), field(loc, "LOCATION", 2)] },
        { height: 5, cells: [field(loc, null, 1, { size: "xl" })] },
        {
          height: 4,
          cells: [
            field(find("lot") ?? find("qty") ?? find("quantity"), "LOT SIZE", 2),
            field(find("min"), "MIN", 2),
            field(find("max"), "MAX", 2),
            { ...field(null, null, 3), kind: "qr" },
          ],
        },
      ],
    };
  }
  if (name === "kanban") {
    const label = (text: string, width = 1): GridCell => ({ ...field(null, null, width, { size: "small" }), kind: "text", text });
    const value = (key: string | null, width = 1): GridCell => field(key, null, width, { size: "medium", bold: false });
    const writeIn = (width = 1): GridCell => ({ ...field(null, null, width), kind: "blank" });
    return {
      rows: [
        { height: 2, cells: [label("Part Description", 5), label("Part Number", 3)] },
        { height: 3, cells: [value("part_name", 5), value("part_number", 3)] },
        { height: 3, cells: [label("Qty"), value(find("qty") ?? find("quantity")), label("Lead Time"), value(find("lead")), label("Order Date"), writeIn()] },
        { height: 3, cells: [label("Supplier"), value(find("supplier") ?? find("vendor"), 3), label("Due Date"), writeIn()] },
        { height: 3, cells: [label("Planner"), value(find("planner") ?? find("buyer"), 2), value(`manual.${KANBAN_CARD_FIELD.key}`, 2), label("Location"), value(find("location") ?? find("supermarket") ?? find("rack"), 2)] },
      ],
    };
  }
  if (name === "bin") {
    return {
      rows: [
        { height: 2, cells: [{ ...field(null, null), kind: "text", text: "BIN LABEL", size: "large" }] },
        { height: 4, cells: [field("part_number", "PART #", 3, { align: "left" }), field(find("qty") ?? find("quantity"), "BIN QTY"), field(find("bin", "type") ?? find("type"), "BIN TYPE")] },
        { height: 2, cells: [field("part_name", "NAME", 1, { size: "medium", align: "left" })] },
        {
          height: 6,
          cells: [
            { ...field(null, "SCAN", 3), kind: "qr" },
            { ...field(null, "IMAGE", 3), kind: "image" },
            field(find("station"), "STATION #", 2),
            field(find("supermarket") ?? find("location"), "LOCATION", 2),
          ],
        },
      ],
    };
  }
  if (name === "simple") {
    return {
      rows: [
        { height: 3, cells: [field("part_number", "PART #", 1, { align: "left" })] },
        { height: 2, cells: [field("part_name", "NAME", 1, { align: "left", size: "medium" })] },
        { height: 2, cells: [field("description", null, 1, { align: "left", size: "small", bold: false })] },
      ],
    };
  }
  return { rows: [{ height: 1, cells: [field(null, null)] }] };
}

/** An earlier fixed "bin" layout, expressed as rows and boxes (it opens in the builder). */
export function binToGrid(bin: BinLayout, picture: boolean, qr: boolean): GridLayout {
  const f = (s: { key: string | null; heading: string | null }, width = 1, extra: Partial<GridCell> = {}) => field(s.key, s.heading, width, extra);
  const rows: GridRow[] = [];
  if (bin.title.trim()) rows.push({ height: 2, cells: [{ ...field(null, null), kind: "text", text: bin.title, size: "large" }] });
  const top = [bin.main.key ? f(bin.main, 3, { align: "left" }) : null, bin.info1.key ? f(bin.info1) : null, bin.info2.key ? f(bin.info2) : null].filter(Boolean) as GridCell[];
  if (top.length) rows.push({ height: 4, cells: top });
  if (bin.name.key) rows.push({ height: 2, cells: [f(bin.name, 1, { size: "medium", align: "left" })] });
  const bottom = [
    qr ? { ...field(null, bin.qr_heading, 3), kind: "qr" as const } : null,
    picture ? { ...field(null, bin.image_heading, 3), kind: "image" as const } : null,
    bin.info3.key ? f(bin.info3, 2) : null,
    bin.info4.key ? f(bin.info4, 2) : null,
  ].filter(Boolean) as GridCell[];
  if (bottom.length) rows.push({ height: 6, cells: bottom });
  return rows.length ? { rows } : gridTemplate("blank", []);
}

function cellLabel(c: GridCell, custom: Record<string, string>, draft: Draft): string {
  if (c.kind === "blank") return "Write-in";
  if (c.kind === "qr") return "QR code";
  if (c.kind === "image") return "Photo";
  if (c.kind === "text") return c.text?.trim() || "Text";
  return c.key ? fieldName(c.key, custom, draft.spec.manual_fields) : "Pick a field";
}

const KIND_ICON = { field: Type, text: Type, qr: QrCode, image: ImageIcon, blank: PenLine } as const;

/** A row drawn as a bar of its boxes; click a box to edit it, drag a divider to resize the boxes beside it. */
function WidthBar({ row, rowIndex, selected, onSelect, onWidths, label }: {
  row: GridRow;
  rowIndex: number;
  selected: number | null;
  onSelect: (i: number) => void;
  onWidths: (widths: number[]) => void;
  label: (c: GridCell) => string;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const total = row.cells.reduce((s, c) => s + c.width, 0) || 1;
  const startDrag = (i: number) => (e: ReactPointerEvent) => {
    e.preventDefault();
    const el = bar.current;
    if (!el) return;
    const width = el.getBoundingClientRect().width;
    const pct = row.cells.map((c) => (c.width / total) * 100);
    const x0 = e.clientX;
    const move = (ev: PointerEvent) => {
      const d = ((ev.clientX - x0) / width) * 100;
      const pair = pct[i]! + pct[i + 1]!;
      const a = Math.min(pair - MIN_PCT, Math.max(MIN_PCT, pct[i]! + d));
      const next = pct.map((p, j) => (j === i ? a : j === i + 1 ? pair - a : p));
      onWidths(next.map((p) => Math.max(1, Math.round(p))));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div ref={bar} className="flex min-h-[52px] w-full select-none overflow-hidden rounded-[6px] border border-border-strong bg-surface" role="group" aria-label={`Row ${rowIndex + 1} boxes`}>
      {row.cells.map((c, i) => {
        const Icon = KIND_ICON[c.kind];
        return (
          <div key={i} className="relative flex min-w-0" style={{ width: `${(c.width / total) * 100}%` }}>
            <button
              type="button"
              onClick={() => onSelect(i)}
              aria-pressed={selected === i}
              aria-label={`Edit box ${i + 1} in row ${rowIndex + 1}: ${label(c)}`}
              title={c.heading ? `${c.heading}: ${label(c)}` : label(c)}
              className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1.5 py-1 text-center transition-colors duration-150 ${selected === i ? "bg-primary text-white" : "hover:bg-row-hover text-text"}`}
            >
              {c.heading && <span className={`w-full truncate text-[10px] leading-3 font-semibold uppercase ${selected === i ? "text-white/80" : "text-text-muted"}`}>{c.heading}</span>}
              <span className="flex w-full items-start justify-center gap-1 text-[11px] leading-[13px] font-medium">
                <Icon size={11} strokeWidth={1.75} className="mt-px shrink-0" aria-hidden />
                <span className="line-clamp-2 break-words">{label(c)}</span>
              </span>
            </button>
            {i < row.cells.length - 1 && (
              <span
                role="separator"
                aria-orientation="vertical"
                aria-label="Drag to resize"
                title="Drag to resize"
                onPointerDown={startDrag(i)}
                className="z-10 w-1.5 shrink-0 cursor-col-resize bg-border-strong hover:bg-primary"
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Section "Boxes" (grid layout): templates, rows of boxes, and the editor of the selected box. */
export type GridSel = { row: number; cell: number } | null;

/** Where each box sits on the label, as fractions of the label (same arithmetic as the renderer's grid). */
export function gridBoxes(grid: GridLayout, widthDots: number, heightDots: number, marginDots = 13) {
  const shares = (weights: number[], total: number) => {
    const sum = weights.reduce((a, b) => a + b, 0) || 1;
    const out = weights.slice(0, -1).map((w) => Math.floor((total * w) / sum));
    return [...out, total - out.reduce((a, b) => a + b, 0)];
  };
  const w = widthDots - 2 * marginDots;
  const h = heightDots - 2 * marginDots;
  const boxes: { row: number; cell: number; x: number; y: number; w: number; h: number }[] = [];
  let y = marginDots;
  shares(grid.rows.map((r) => r.height), h).forEach((rh, r) => {
    let x = marginDots;
    shares(grid.rows[r]!.cells.map((c) => c.width), w).forEach((cw, c) => {
      boxes.push({ row: r, cell: c, x: x / widthDots, y: y / heightDots, w: cw / widthDots, h: rh / heightDots });
      x += cw;
    });
    y += rh;
  });
  return boxes;
}

/** Click a box on the label preview to edit it. */
export function GridOverlay({ grid, widthDots, heightDots, sel, onSel }: { grid: GridLayout; widthDots: number; heightDots: number; sel: GridSel; onSel: (s: GridSel) => void }) {
  return (
    <>
      {gridBoxes(grid, widthDots, heightDots).map((b) => {
        const on = sel?.row === b.row && sel.cell === b.cell;
        return (
          <button
            key={`${b.row}-${b.cell}`}
            type="button"
            aria-label={`Edit box ${b.cell + 1} in row ${b.row + 1} on the label`}
            title="Click to edit this box"
            onClick={() => onSel({ row: b.row, cell: b.cell })}
            className={`absolute rounded-[2px] transition-colors duration-150 ${on ? "bg-primary/15 outline outline-2 outline-primary" : "hover:bg-primary/10 hover:outline hover:outline-2 hover:outline-primary/60"}`}
            style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
          />
        );
      })}
    </>
  );
}

export function GridBuilder({ draft, custom, onChange, onManualFields, sel: selProp, onSel }: {
  draft: Draft;
  custom: CustomField[];
  onChange: (grid: GridLayout, patch?: Partial<Draft>) => void;
  onManualFields: (manual: ManualField[], grid: GridLayout) => void;
  /** The selected box, when the page shares it with the preview (click a box on the label). */
  sel?: GridSel;
  onSel?: (s: GridSel) => void;
}) {
  const grid: GridLayout = draft.spec.grid ?? gridTemplate("bin", custom);
  const [selLocal, setSelLocal] = useState<GridSel>(grid.rows.length ? { row: 0, cell: 0 } : null);
  const sel = selProp !== undefined ? selProp : selLocal;
  const setSel = onSel ?? setSelLocal;
  useEffect(() => {
    if (sel && (sel.row >= grid.rows.length || sel.cell >= (grid.rows[sel.row]?.cells.length ?? 0))) setSel(grid.rows.length ? { row: 0, cell: 0 } : null);
  }, [grid, sel, setSel]);
  // A box picked on the label preview: bring its row and settings into view.
  useEffect(() => {
    if (sel) document.getElementById(`grid-row-${sel.row}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [sel]);
  const customLabels = Object.fromEntries(custom.map((f) => [f.key, f.label]));
  const label = (c: GridCell) => cellLabel(c, customLabels, draft);

  const setRows = (rows: GridRow[], patch?: Partial<Draft>) => onChange({ rows }, patch);
  const setRow = (r: number, row: GridRow) => setRows(grid.rows.map((x, i) => (i === r ? row : x)));
  const setCell = (r: number, c: number, cell: Partial<GridCell>) => {
    const row = grid.rows[r]!;
    const next = { ...row.cells[c]!, ...cell };
    // A QR box needs the QR code turned on; switch it on (part number) rather than showing an error.
    const patch = next.kind === "qr" && draft.qr_mode === "none" ? { qr_mode: "part" as const } : undefined;
    setRows(grid.rows.map((x, i) => (i === r ? { ...row, cells: row.cells.map((y, j) => (j === c ? next : y)) } : x)), patch);
  };
  const moveRow = (r: number, to: number) => {
    if (to < 0 || to >= grid.rows.length) return;
    const rows = [...grid.rows];
    const [item] = rows.splice(r, 1);
    rows.splice(to, 0, item!);
    setRows(rows);
    setSel({ row: to, cell: 0 });
  };

  const fieldOptions = [
    { value: "", label: "— Pick a field —" },
    ...PART_FIELD_KEYS.map((k) => ({ value: k, label: CORE_FIELD_LABELS[k]! })),
    ...custom.filter((f) => f.printable).map((f) => ({ value: f.key, label: f.label })),
    ...GENERATED_KEYS.map((k) => ({ value: k, label: CORE_FIELD_LABELS[k]! })),
    ...draft.spec.manual_fields.map((m) => ({ value: `manual.${m.key}`, label: `${m.label} (typed at print)` })),
  ];
  const selected = sel ? grid.rows[sel.row]?.cells[sel.cell] : undefined;
  const applyTemplate = (t: TemplateName) => {
    const next = gridTemplate(t, custom);
    if (t === "kanban" && !draft.spec.manual_fields.some((m) => m.type === "box_sequence")) {
      onManualFields([...draft.spec.manual_fields, KANBAN_CARD_FIELD], next);
      return;
    }
    setRows(next.rows, (t === "bin" || t === "tps") && draft.qr_mode === "none" ? { qr_mode: "part" } : undefined);
  };

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 t-small text-text-secondary">
          <LayoutTemplate size={14} strokeWidth={1.75} aria-hidden />
          Start from
        </span>
        {(
          [
            ["tps", "Standard TPS card"],
            ["kanban", "Kanban card"],
            ["bin", "Bin card"],
            ["simple", "Simple"],
            ["blank", "Blank"],
          ] as const
        ).map(([t, name]) => (
          <Button
            key={t}
            variant="secondary"
            size="sm"
            onClick={() => {
              applyTemplate(t);
              setSel({ row: 0, cell: 0 });
            }}
          >
            {name}
          </Button>
        ))}
      </div>

      <ol className="flex flex-col gap-3" aria-label="Rows">
        {grid.rows.map((row, r) => (
          <li key={r} id={`grid-row-${r}`} className={`flex flex-col gap-2 rounded-[8px] border p-2.5 ${sel?.row === r ? "border-primary" : "border-border"}`}>
            <div className="flex items-center gap-2">
              <span className="t-body-strong text-text">Row {r + 1}</span>
              <span className="ml-1 t-caption text-text-muted">Height</span>
              <span className="inline-flex items-center rounded-[6px] border border-border-strong">
                <button type="button" aria-label={`Shorter row ${r + 1}`} disabled={row.height <= 1} onClick={() => setRow(r, { ...row, height: row.height - 1 })} className="p-1 text-text-secondary hover:bg-hover-fill disabled:text-text-muted">
                  <Minus size={14} strokeWidth={1.75} aria-hidden />
                </button>
                <span className="w-6 text-center t-caption tabular-nums text-text">{row.height}</span>
                <button type="button" aria-label={`Taller row ${r + 1}`} disabled={row.height >= 12} onClick={() => setRow(r, { ...row, height: row.height + 1 })} className="p-1 text-text-secondary hover:bg-hover-fill disabled:text-text-muted">
                  <Plus size={14} strokeWidth={1.75} aria-hidden />
                </button>
              </span>
              <span className="flex-1" />
              <button type="button" aria-label={`Move row ${r + 1} up`} disabled={r === 0} onClick={() => moveRow(r, r - 1)} className="rounded p-1 text-text-secondary hover:bg-hover-fill disabled:text-text-muted">
                <ArrowUp size={14} strokeWidth={1.75} aria-hidden />
              </button>
              <button type="button" aria-label={`Move row ${r + 1} down`} disabled={r === grid.rows.length - 1} onClick={() => moveRow(r, r + 1)} className="rounded p-1 text-text-secondary hover:bg-hover-fill disabled:text-text-muted">
                <ArrowDown size={14} strokeWidth={1.75} aria-hidden />
              </button>
              <button type="button" aria-label={`Delete row ${r + 1}`} onClick={() => setRows(grid.rows.filter((_, i) => i !== r))} className="rounded p-1 text-text-secondary hover:bg-danger-bg hover:text-danger">
                <Trash2 size={14} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
            <WidthBar
              row={row}
              rowIndex={r}
              selected={sel?.row === r ? sel.cell : null}
              onSelect={(c) => setSel({ row: r, cell: c })}
              onWidths={(widths) => setRow(r, { ...row, cells: row.cells.map((c, i) => ({ ...c, width: widths[i]! })) })}
              label={label}
            />
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                icon={Plus}
                disabled={row.cells.length >= MAX_CELLS}
                tooltip={row.cells.length >= MAX_CELLS ? "A row can have 6 boxes" : undefined}
                onClick={() => {
                  setRow(r, { ...row, cells: [...row.cells, field(null, null)] });
                  setSel({ row: r, cell: row.cells.length });
                }}
              >
                Add box
              </Button>
              <span className="t-caption text-text-muted">Drag the dividers to resize</span>
            </div>

            {sel?.row === r && selected && (
              <div className="flex flex-col gap-3 rounded-[8px] bg-surface-subtle p-3" aria-label="Box settings">
                <div className="flex items-center justify-between gap-2">
                  <span className="t-small text-text-secondary">Box {sel.cell + 1}</span>
                  <button
                    type="button"
                    onClick={() => {
                      if (row.cells.length === 1) setRows(grid.rows.filter((_, i) => i !== r));
                      else setRow(r, { ...row, cells: row.cells.filter((_, i) => i !== sel.cell) });
                    }}
                    className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 t-caption text-danger hover:bg-danger-bg"
                  >
                    <Trash2 size={12} strokeWidth={1.75} aria-hidden />
                    Remove box
                  </button>
                </div>
                <SegmentedControl
                  ariaLabel="Box shows"
                  value={selected.kind}
                  onChange={(kind) => setCell(r, sel.cell, { kind })}
                  options={[
                    { value: "field", label: "Field" },
                    { value: "text", label: "Text" },
                    { value: "qr", label: "QR" },
                    { value: "image", label: "Photo" },
                    { value: "blank", label: "Write-in" },
                  ]}
                />
                {selected.kind === "field" && (
                  <Select aria-label="Field" className="t-small" value={selected.key ?? ""} options={fieldOptions} onChange={(e) => setCell(r, sel.cell, { key: e.target.value || null })} />
                )}
                {selected.kind === "text" && (
                  <Input aria-label="Text" maxLength={60} placeholder="Text printed on every label" value={selected.text ?? ""} onChange={(e) => setCell(r, sel.cell, { text: e.target.value })} />
                )}
                <label className="flex flex-col gap-1">
                  <span className="t-caption text-text-muted">Heading (optional)</span>
                  <Input aria-label="Heading" heightClass="h-8" className="t-small uppercase" maxLength={24} placeholder="none" value={selected.heading ?? ""} onChange={(e) => setCell(r, sel.cell, { heading: e.target.value || null })} />
                </label>
                {(selected.kind === "field" || selected.kind === "text") && (
                <details>
                  <summary className="cursor-pointer t-small text-text-secondary select-none hover:text-text">More options: text size, alignment, bold</summary>
                  <div className="mt-2 flex flex-col gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="t-caption text-text-muted">Text size (largest)</span>
                      <Select
                        aria-label="Text size"
                        className="t-small"
                        value={selected.size}
                        options={[
                          { value: "auto", label: "Auto (fill the box)" },
                          { value: "small", label: "Small" },
                          { value: "medium", label: "Medium" },
                          { value: "large", label: "Large" },
                          { value: "xl", label: "Extra large" },
                        ]}
                        onChange={(e) => setCell(r, sel.cell, { size: e.target.value as GridCell["size"] })}
                      />
                    </label>
                    <div className="flex flex-wrap items-center gap-4">
                      <SegmentedControl
                        ariaLabel="Alignment"
                        value={selected.align}
                        onChange={(align) => setCell(r, sel.cell, { align })}
                        options={[
                          { value: "left", label: "Left" },
                          { value: "center", label: "Center" },
                        ]}
                      />
                      <Switch label={<span className="t-small text-text-secondary">Bold</span>} checked={selected.bold} onChange={(bold) => setCell(r, sel.cell, { bold })} />
                    </div>
                  </div>
                </details>
                )}
                {selected.kind === "qr" && <p className="t-caption text-text-muted">What the code holds is set under QR code &amp; serial.</p>}
                {selected.kind === "image" && <p className="t-caption text-text-muted">The part's photo, in black-and-white dots. Parts without a photo leave this box empty.</p>}
                {selected.kind === "blank" && <p className="t-caption text-text-muted">An empty box to fill in by hand, like an order or due date. Add a heading so people know what to write.</p>}
              </div>
            )}
          </li>
        ))}
      </ol>

      <div>
        <Button
          variant="secondary"
          size="sm"
          icon={Plus}
          disabled={grid.rows.length >= MAX_ROWS}
          tooltip={grid.rows.length >= MAX_ROWS ? "A label can have 8 rows" : undefined}
          onClick={() => {
            setRows([...grid.rows, { height: 2, cells: [field(null, null)] }]);
            setSel({ row: grid.rows.length, cell: 0 });
          }}
        >
          Add row
        </Button>
      </div>
    </>
  );
}
