import { useQueries, useQueryClient } from "@tanstack/react-query";
import { Printer as PrinterIcon, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { Badge, Banner, Mono } from "../../components/Display";
import { NumberStepper, Select } from "../../components/Form";
import { LabelPreview, type PreviewResult } from "../../components/LabelPreview";
import { fitsOnRoll } from "../../lib/format";
import { useCurrentLabelType, useLabelTypes } from "../../lib/labelTypes";
import { api } from "../../lib/api";
import { useDebounced, type PartDetail, type PartListItem, type SizeBrief } from "../../lib/parts";
import { qk, useDefaultPrinter } from "../../lib/queries";
import { printBlock } from "./blocking";
import { ManualInputs, PrinterLine, ResultPanel, rollPreview, SizeBanner, usePrintRunner, type Outcome, type PrintItem } from "./PrintBits";

interface RowState {
  manual: Record<string, unknown>;
  quantity: number;
  copies: number;
}

interface Group {
  typeId: string;
  name: string;
  size: SizeBrief | undefined;
  ids: string[];
}

/** 12.6 batch mode (from "Print selected"). Each part prints with its own label type (v1.1 5.4), grouped by type. */
export function BatchPrint({ parts, onClose }: { parts: PartListItem[]; onClose: () => void }) {
  const printAs = useCurrentLabelType();
  const types = useLabelTypes();
  const qc = useQueryClient();
  const { printer } = useDefaultPrinter();
  const [ids, setIds] = useState(parts.map((p) => p.id));
  const [rows, setRows] = useState<Record<string, RowState>>(() => Object.fromEntries(parts.map((p) => [p.id, { manual: {}, quantity: 1, copies: 1 }])));
  const [index, setIndex] = useState(0);
  const [sizeConfirmed, setSizeConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // "Print all as": one type for every part, instead of each part's own.
  const [allAs, setAllAs] = useState<string | null>(null);
  const [allAsPick, setAllAsPick] = useState("");
  const runner = usePrintRunner();

  const typeQuery = allAs ? `type_id=${allAs}` : printAs ? `print_as=${printAs.id}` : "";
  const details = useQueries({
    queries: ids.map((id) => ({ queryKey: [...qk.part(id), allAs ?? "resolved", printAs?.id ?? null], queryFn: () => api<PartDetail>(`/parts/${id}?${typeQuery}`) })),
  });
  const debouncedRows = useDebounced(rows, 250);
  const previews = useQueries({
    queries: ids.map((id) => {
      const manual = debouncedRows[id]?.manual ?? {};
      return {
        queryKey: ["preview", "batch", allAs, printAs?.id, id, manual],
        queryFn: () => api<PreviewResult>("/render/preview", { body: { part_id: id, manual_values: manual, label_type_id: allAs, print_as: printAs?.id ?? null } }),
        staleTime: 60_000,
      };
    }),
  });

  const byId = new Map(ids.map((id, i) => [id, { detail: details[i]?.data, preview: previews[i]?.data }]));
  // Parts that don't fit (for a reason other than a missing print-time value) are listed first in their group.
  const doesntFit = (id: string) => !!byId.get(id)?.preview?.warnings.some((w) => w.code !== "REQUIRED_VALUE_MISSING");
  const groups = useMemo(() => {
    const out = new Map<string, Group>();
    for (const id of ids) {
      const cfg = byId.get(id)?.detail?.config;
      const key = cfg?.label_type_id ?? "…";
      const g = out.get(key) ?? { typeId: key, name: cfg?.label_type_name ?? "…", size: cfg?.size, ids: [] };
      g.ids.push(id);
      out.set(key, g);
    }
    for (const g of out.values()) g.ids.sort((a, b) => Number(doesntFit(b)) - Number(doesntFit(a)));
    return [...out.values()];
  }, [ids, details, previews]); // eslint-disable-line react-hooks/exhaustive-deps
  const ordered = groups.flatMap((g) => g.ids);

  const current = ordered[Math.min(index, ordered.length - 1)];
  const currentPreview = current ? byId.get(current)?.preview : undefined;
  const loadedSize = printer?.loaded_label_size;
  const sizeIds = new Set(groups.map((g) => g.size?.id).filter(Boolean));
  const mixedSizes = sizeIds.size > 1;
  // With one size the usual "I've loaded … labels" confirmation applies. With several, only the groups that
  // fit the loaded roll print; the others wait until their roll is loaded.
  const groupBlocked = (g: Group) => mixedSizes && !!g.size && !fitsOnRoll(g.size, loadedSize);
  const printable = groups.filter((g) => !groupBlocked(g)).flatMap((g) => g.ids);
  const mismatchSize = mixedSizes ? undefined : groups.map((g) => g.size).find((s) => s && !fitsOnRoll(s, loadedSize));
  const sizeMismatch = !sizeConfirmed && mismatchSize ? mismatchSize.name : null;
  const block = printBlock({ previews: printable.map((id) => byId.get(id)?.preview), printer, sizeMismatch });

  const distinct = (id: string) => (byId.get(id)?.detail?.config.serial_mode === "required" ? (rows[id]?.quantity ?? 1) : 1);
  const labelsOf = (list: string[]) => list.reduce((n, id) => n + distinct(id) * (rows[id]?.copies ?? 1), 0);
  const totalLabels = labelsOf(printable);
  const totalSerials = printable.reduce((n, id) => n + (byId.get(id)?.detail?.config.serial_mode === "required" ? distinct(id) : 0), 0);

  const set = (id: string, patch: Partial<RowState>) => setRows({ ...rows, [id]: { ...rows[id]!, ...patch } });

  const print = async () => {
    const items: PrintItem[] = printable.map((id) => ({
      part_id: id,
      copies: rows[id]?.copies ?? 1,
      quantity: distinct(id),
      manual_values: rows[id]?.manual ?? {},
      label_type_id: byId.get(id)?.detail?.config.label_type_id,
    }));
    const result = await runner.run(items, sizeConfirmed, printAs?.id);
    if (result) {
      setOutcome(result);
      void qc.invalidateQueries({ queryKey: ["parts"] });
      void qc.invalidateQueries({ queryKey: qk.printers });
    }
  };

  return (
    <div className="flex h-[min(680px,calc(100vh-170px))] gap-6">
      <div className="flex w-[560px] shrink-0 flex-col gap-2">
        <LabelPreview result={currentPreview} loading={!currentPreview} maxHeight={420} roll={rollPreview(current ? byId.get(current)?.detail?.config.size : null, printer)} />
        <div className="flex items-center justify-center gap-3 t-body text-text-secondary">
          <button type="button" aria-label="Previous label" disabled={index <= 0} onClick={() => setIndex(index - 1)} className="rounded px-2 hover:bg-hover-fill disabled:text-text-muted">
            ‹
          </button>
          <span className="tabular-nums">
            {Math.min(index, ordered.length - 1) + 1} of {ordered.length}
          </span>
          <button type="button" aria-label="Next label" disabled={index >= ordered.length - 1} onClick={() => setIndex(index + 1)} className="rounded px-2 hover:bg-hover-fill disabled:text-text-muted">
            ›
          </button>
        </div>
      </div>
      <div className="flex w-[400px] min-w-0 flex-col gap-4">
        {outcome ? (
          <ResultPanel
            outcome={outcome}
            saved={false}
            busy={runner.busy}
            nextBox={null}
            onNextBox={() => undefined}
            onAnother={() => setOutcome(null)}
            onDone={onClose}
            onRetry={() => void print()}
          />
        ) : (
          <>
            {mixedSizes && (
              <Banner tone="warning">
                <div className="flex flex-col gap-2">
                  <span>These labels use different sizes. Load the right roll for each group, or print everything as one type.</span>
                  <div className="flex items-center gap-2">
                    <Select
                      aria-label="Print all as"
                      className="t-small"
                      value={allAsPick}
                      options={[{ value: "", label: "Print all as…" }, ...(types.data ?? []).map((t) => ({ value: t.id, label: t.name }))]}
                      onChange={(e) => setAllAsPick(e.target.value)}
                    />
                    <Button variant="secondary" size="sm" disabled={!allAsPick} onClick={() => { setAllAs(allAsPick); setIndex(0); }}>
                      Use this type
                    </Button>
                  </div>
                </div>
              </Banner>
            )}
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
              {groups.map((g) => {
                const blocked = groupBlocked(g);
                return (
                  <section key={g.typeId} aria-label={`${g.name} labels`} className="flex flex-col gap-1">
                    <h3 className="flex items-center justify-between gap-2 t-body-strong text-text">
                      <span>
                        {g.name} · {labelsOf(g.ids)} labels
                      </span>
                      {blocked && g.size && <span className="t-caption text-warning">Load {g.size.name} labels to print these</span>}
                    </h3>
                    <ul className={`flex flex-col divide-y divide-border rounded-[8px] border border-border ${blocked ? "opacity-60" : ""}`}>
                      {g.ids.map((id) => {
                        const i = ordered.indexOf(id);
                        const d = byId.get(id)?.detail;
                        const bad = doesntFit(id);
                        const serialOn = d?.config.serial_mode === "required";
                        const required = (d?.config.spec.manual_fields ?? []).filter((m) => m.required && m.type !== "box_sequence");
                        return (
                          <li key={id} className={`flex flex-col gap-2 p-3 ${i === index ? "bg-primary-subtle" : ""}`} onFocus={() => setIndex(i)}>
                            <div className="flex items-center gap-2">
                              <button type="button" className="min-w-0 flex-1 truncate text-left t-body-strong text-text" onClick={() => setIndex(i)}>
                                {d ? (d.label_name ?? d.part_name) : "…"}
                              </button>
                              {bad && (
                                <Badge tone="warning">
                                  <TriangleAlert size={12} strokeWidth={1.75} className="mr-1" aria-hidden />
                                  {byId.get(id)?.preview?.warnings[0]?.message}
                                </Badge>
                              )}
                              {bad && (
                                <button type="button" className="t-small text-primary hover:underline" onClick={() => { setIds(ids.filter((x) => x !== id)); setIndex(0); }}>
                                  Remove
                                </button>
                              )}
                            </div>
                            {d && <Mono className="t-small text-text-secondary">{d.part_number}</Mono>}
                            {required.length > 0 && (
                              <ManualInputs fields={required} values={rows[id]?.manual ?? {}} onChange={(k, v) => set(id, { manual: { ...rows[id]?.manual, [k]: v } })} />
                            )}
                            <div className="flex flex-wrap items-center gap-3">
                              {serialOn && (
                                <label className="inline-flex items-center gap-2 t-small text-text-secondary">
                                  Quantity
                                  <NumberStepper label="Quantity" min={1} max={200} value={rows[id]?.quantity ?? 1} onChange={(v) => set(id, { quantity: v })} />
                                </label>
                              )}
                              <label className="inline-flex items-center gap-2 t-small text-text-secondary">
                                Copies
                                <NumberStepper label="Copies" min={1} max={50} value={rows[id]?.copies ?? 1} onChange={(v) => set(id, { copies: v })} />
                              </label>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                );
              })}
            </div>
            <PrinterLine printer={printer} />
            {sizeMismatch && mismatchSize && <SizeBanner loaded={printer?.loaded_label_size?.name ?? null} size={mismatchSize.name} onConfirm={() => setSizeConfirmed(true)} />}
            <p className="t-body text-text-secondary">
              {totalLabels} labels · {totalSerials} serials
            </p>
            {runner.error && <p role="alert" className="t-small text-danger">{runner.error}</p>}
            <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border pt-4">
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button size="big" icon={runner.busy ? undefined : PrinterIcon} loading={runner.busy} disabled={block.blocked || printable.length === 0} tooltip={block.blocked ? block.reason : printable.length === 0 ? "Load the right roll first" : null} onClick={() => void print()}>
                {runner.busy ? "Sending…" : totalLabels > 1 ? `Print ${totalLabels} labels` : "Print"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
