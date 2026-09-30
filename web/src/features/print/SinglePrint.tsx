import { useQueryClient } from "@tanstack/react-query";
import { Printer as PrinterIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { Mono } from "../../components/Display";
import { Checkbox, Field, NumberStepper, SegmentedControl } from "../../components/Form";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { api } from "../../lib/api";
import { inches } from "../../lib/format";
import { qk, useDefaultPrinter, useSizes } from "../../lib/queries";
import { useCustomFields, type LabelSpec, type PartDetail, type SpecField } from "../../lib/parts";
import { defaultRole, fieldName } from "../configure/types";
import { printBlock } from "./blocking";
import { ManualInputs, PrinterLine, ResultPanel, SizeBanner, usePrintRunner, type Outcome, type PrintItem } from "./PrintBits";

type Emphasis = LabelSpec["style"]["emphasis"];

/** The "Show on label" choices: every printable field that has a value for this part (12.6 step 2). */
function showOnLabelKeys(part: PartDetail, custom: { key: string; label: string; printable: boolean }[], serialOn: boolean): string[] {
  const keys: string[] = [];
  if (part.label_name) keys.push("label_name");
  keys.push("part_number", "part_name");
  if (part.description) keys.push("description");
  if (part.revision) keys.push("revision");
  for (const f of custom) if (f.printable && part.custom_data[f.key] !== undefined && part.custom_data[f.key] !== "") keys.push(f.key);
  if (serialOn) keys.push("serial");
  keys.push("print_date");
  return keys;
}

export function SinglePrint({ part, onClose }: { part: PartDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const { printer } = useDefaultPrinter();
  const sizes = useSizes();
  const custom = useCustomFields();
  const cfg = part.config;
  const spec = cfg.spec;
  const box = spec.manual_fields.find((m) => m.type === "box_sequence");
  const serialOn = cfg.serial_mode === "required";

  const [fields, setFields] = useState<SpecField[]>(spec.fields);
  const [sizeId, setSizeId] = useState(cfg.size.id);
  const [emphasis, setEmphasis] = useState<Emphasis>(spec.style.emphasis);
  const [manual, setManual] = useState<Record<string, unknown>>({});
  const [boxTotal, setBoxTotal] = useState(1);
  const [boxMode, setBoxMode] = useState<"all" | "one">("all");
  const [boxNumber, setBoxNumber] = useState(1);
  const [groupId, setGroupId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [copies, setCopies] = useState(1);
  const [sizeConfirmed, setSizeConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [saved, setSaved] = useState(false);
  const runner = usePrintRunner();

  const customLabels = Object.fromEntries((custom.data ?? []).map((f) => [f.key, f.label]));
  const draft = useMemo(
    () => ({ label_size_id: sizeId, spec: { ...spec, fields, style: { ...spec.style, emphasis } }, qr_mode: cfg.qr_mode, serial_mode: cfg.serial_mode }),
    [sizeId, spec, fields, emphasis, cfg.qr_mode, cfg.serial_mode],
  );
  const boxIndex = boxMode === "all" ? 1 : boxNumber;
  const manualForPreview = box ? { ...manual, [box.key]: { index: boxIndex, total: boxTotal } } : manual;
  const preview = usePreview({ part_id: part.id, config: draft, manual_values: manualForPreview }, 250);

  const size = sizes.data?.find((s) => s.id === sizeId) ?? cfg.size;
  const loaded = printer?.loaded_label_size ?? null;
  const sizeMismatch = !sizeConfirmed && loaded?.id !== sizeId ? size.name : null;
  const block = printBlock({ previews: [preview.data], printer, sizeMismatch });

  const distinct = box ? (boxMode === "all" ? boxTotal : 1) : serialOn ? quantity : 1;
  const totalLabels = distinct * copies;
  const totalSerials = serialOn ? distinct : 0;
  const selectionChanged = JSON.stringify(fields) !== JSON.stringify(spec.fields) || sizeId !== cfg.size.id || emphasis !== spec.style.emphasis;

  const toggle = (key: string, on: boolean) => {
    if (on) {
      const role = defaultRole(fields);
      if (role) setFields([...fields, { key, role, uppercase: false, caption: null }]);
    } else setFields(fields.filter((f) => f.key !== key));
  };

  const items = (start: number, count: number, gid: string | null): PrintItem[] => [
    {
      part_id: part.id,
      copies,
      quantity: box ? 1 : serialOn ? quantity : 1,
      manual_values: manual,
      ...(box ? { group: { total: boxTotal, start_index: start, count, group_id: gid } } : {}),
    },
  ];

  const print = async (start = box && boxMode === "one" ? boxNumber : 1, count = box ? (boxMode === "all" ? boxTotal : 1) : 1, gid = groupId) => {
    if (selectionChanged) {
      await api(`/parts/${part.id}/selection`, { method: "PUT", body: { fields, label_size_id: sizeId, emphasis } });
      setSaved(true);
      void qc.invalidateQueries({ queryKey: qk.part(part.id) });
    }
    const result = await runner.run(items(start, count, gid), sizeConfirmed);
    if (result) {
      setOutcome(result);
      if (result.kind === "sent") {
        if (result.groupIds[0]) setGroupId(result.groupIds[0]);
        if (box && boxMode === "one") setBoxNumber(start);
      }
      void qc.invalidateQueries({ queryKey: ["parts"] });
      void qc.invalidateQueries({ queryKey: qk.printers });
    }
  };

  const nextBox = outcome?.kind === "sent" && box && boxMode === "one" && boxNumber < boxTotal ? { n: boxNumber + 1, total: boxTotal } : null;
  const keys = showOnLabelKeys(part, custom.data ?? [], serialOn);
  const detailFull = defaultRole(fields) === null;

  return (
    <div className="flex h-[min(680px,calc(100vh-170px))] gap-6">
      <div className="w-[560px] shrink-0">
        <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={460} />
      </div>
      <div className="flex w-[400px] min-w-0 flex-col gap-4">
        <div className="shrink-0">
          <p className="text-[16px] leading-6 font-semibold text-text">{part.label_name ?? part.part_name}</p>
          <Mono className="t-body text-text-secondary">{part.part_number}</Mono>
          <p className="t-small text-text-secondary">{part.part_name}</p>
        </div>

        <div className="-mr-2 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pr-2">
        {outcome ? (
          <ResultPanel
            outcome={outcome}
            saved={saved}
            busy={runner.busy}
            nextBox={nextBox}
            onNextBox={() => nextBox && void print(nextBox.n, 1, groupId)}
            onAnother={() => {
              setOutcome(null);
              setSaved(false);
              setGroupId(null);
            }}
            onDone={onClose}
            onRetry={() => void print()}
          />
        ) : (
          <>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 t-body-strong text-text">Show on label</legend>
              {keys.map((k) => {
                const on = fields.some((f) => f.key === k);
                return (
                  <Checkbox
                    key={k}
                    label={fieldName(k, customLabels, spec.manual_fields)}
                    checked={on}
                    disabled={!on && detailFull}
                    tooltip={!on && detailFull ? "Limit reached" : null}
                    onChange={(v) => toggle(k, v)}
                  />
                );
              })}
              {/* QR mode is part of the saved config (admin, Configure); shown here as it stands. */}
              <Checkbox label="QR code" checked={cfg.qr_mode !== "none"} disabled onChange={() => undefined} />
            </fieldset>

            <div className="flex flex-col gap-1.5">
              <span className="t-body-strong text-text">Size</span>
              <div role="radiogroup" aria-label="Size" className="grid grid-cols-2 gap-2">
                {(sizes.data ?? []).filter((s) => s.active).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    role="radio"
                    aria-checked={s.id === sizeId}
                    onClick={() => setSizeId(s.id)}
                    className={`rounded-[8px] border px-3 py-2 text-left ${s.id === sizeId ? "border-primary bg-primary-subtle" : "border-border hover:bg-row-hover"}`}
                  >
                    <span className="block t-body-strong text-text">{s.name}</span>
                    <span className="block t-small text-text-secondary">
                      {inches(s.width_in)} × {inches(s.height_in)} in
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="t-body-strong text-text">Text size</span>
              <SegmentedControl ariaLabel="Text size" value={emphasis} onChange={setEmphasis}
                options={[{ value: "small", label: "Small" }, { value: "medium", label: "Medium" }, { value: "large", label: "Large" }]} />
            </div>

            <ManualInputs fields={spec.manual_fields} values={manual} onChange={(k, v) => setManual({ ...manual, [k]: v })} />

            {box && (
              <div className="flex flex-col gap-3">
                <Field label="Total boxes" htmlFor="total-boxes">
                  <NumberStepper id="total-boxes" label="Total boxes" min={1} max={999} value={boxTotal} onChange={(v) => { setBoxTotal(v); if (boxNumber > v) setBoxNumber(v); }} />
                </Field>
                <label className="inline-flex items-center gap-2 t-body">
                  <input type="radio" name="box-mode" checked={boxMode === "all"} onChange={() => setBoxMode("all")} />
                  Print all {boxTotal} boxes
                </label>
                <label className="inline-flex items-center gap-2 t-body">
                  <input type="radio" name="box-mode" checked={boxMode === "one"} onChange={() => setBoxMode("one")} />
                  Print one box
                </label>
                {boxMode === "one" && (
                  <Field label="Box number" htmlFor="box-number">
                    <NumberStepper id="box-number" label="Box number" min={1} max={boxTotal} value={boxNumber} onChange={setBoxNumber} />
                  </Field>
                )}
              </div>
            )}

            {serialOn && !box && (
              <Field label="Quantity" htmlFor="quantity" helper="Each label gets its own serial.">
                <NumberStepper id="quantity" label="Quantity" min={1} max={200} value={quantity} onChange={setQuantity} />
              </Field>
            )}
            <Field label="Copies of each" htmlFor="copies" helper="Identical copies, same serial.">
              <NumberStepper id="copies" label="Copies of each" min={1} max={50} value={copies} onChange={setCopies} />
            </Field>

            <PrinterLine printer={printer} />
            {sizeMismatch && <SizeBanner loaded={loaded?.name ?? null} size={size.name} onConfirm={() => setSizeConfirmed(true)} />}
            <p className="t-body text-text-secondary">
              {totalLabels} labels · {totalSerials} serials
            </p>
            {runner.error && <p role="alert" className="t-small text-danger">{runner.error}</p>}
          </>
        )}
        </div>

        {!outcome && (
          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border pt-4">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button size="big" icon={runner.busy ? undefined : PrinterIcon} loading={runner.busy} disabled={block.blocked} tooltip={block.blocked ? block.reason : null} onClick={() => void print()}>
              {runner.busy ? "Sending…" : totalLabels > 1 ? `Print ${totalLabels} labels` : "Print"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
