import { useQueries, useQueryClient } from "@tanstack/react-query";
import { Printer as PrinterIcon, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { Badge, Mono } from "../../components/Display";
import { NumberStepper } from "../../components/Form";
import { LabelPreview, type PreviewResult } from "../../components/LabelPreview";
import { api } from "../../lib/api";
import { useDebounced, type PartDetail, type PartListItem } from "../../lib/parts";
import { qk, useDefaultPrinter } from "../../lib/queries";
import { printBlock } from "./blocking";
import { ManualInputs, PrinterLine, ResultPanel, SizeBanner, usePrintRunner, type Outcome, type PrintItem } from "./PrintBits";

interface RowState {
  manual: Record<string, unknown>;
  quantity: number;
  copies: number;
}

/** 12.6 batch mode (from "Print selected"). Each part prints with its saved label. */
export function BatchPrint({ parts, onClose }: { parts: PartListItem[]; onClose: () => void }) {
  const qc = useQueryClient();
  const { printer } = useDefaultPrinter();
  const [ids, setIds] = useState(parts.map((p) => p.id));
  const [rows, setRows] = useState<Record<string, RowState>>(() => Object.fromEntries(parts.map((p) => [p.id, { manual: {}, quantity: 1, copies: 1 }])));
  const [index, setIndex] = useState(0);
  const [sizeConfirmed, setSizeConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const runner = usePrintRunner();

  const details = useQueries({ queries: ids.map((id) => ({ queryKey: qk.part(id), queryFn: () => api<PartDetail>(`/parts/${id}`) })) });
  const debouncedRows = useDebounced(rows, 250);
  const previews = useQueries({
    queries: ids.map((id) => {
      const manual = debouncedRows[id]?.manual ?? {};
      return {
        queryKey: ["preview", "batch", id, manual],
        queryFn: () => api<PreviewResult>("/render/preview", { body: { part_id: id, manual_values: manual } }),
        staleTime: 60_000,
      };
    }),
  });

  const byId = new Map(ids.map((id, i) => [id, { detail: details[i]?.data, preview: previews[i]?.data }]));
  // Parts that don't fit (for a reason other than a missing print-time value) are listed first.
  const doesntFit = (id: string) => !!byId.get(id)?.preview?.warnings.some((w) => w.code !== "REQUIRED_VALUE_MISSING");
  const ordered = useMemo(() => [...ids].sort((a, b) => Number(doesntFit(b)) - Number(doesntFit(a))), [ids, previews]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = ordered[Math.min(index, ordered.length - 1)];
  const currentPreview = current ? byId.get(current)?.preview : undefined;
  const loadedId = printer?.loaded_label_size?.id;
  const mismatchSize = ids.map((id) => byId.get(id)?.detail?.config.size).find((s) => s && s.id !== loadedId);
  const sizeMismatch = !sizeConfirmed && mismatchSize ? mismatchSize.name : null;
  const block = printBlock({ previews: ids.map((id) => byId.get(id)?.preview), printer, sizeMismatch });

  const distinct = (id: string) => (byId.get(id)?.detail?.config.serial_mode === "required" ? (rows[id]?.quantity ?? 1) : 1);
  const totalLabels = ids.reduce((n, id) => n + distinct(id) * (rows[id]?.copies ?? 1), 0);
  const totalSerials = ids.reduce((n, id) => n + (byId.get(id)?.detail?.config.serial_mode === "required" ? distinct(id) : 0), 0);

  const set = (id: string, patch: Partial<RowState>) => setRows({ ...rows, [id]: { ...rows[id]!, ...patch } });

  const print = async () => {
    const items: PrintItem[] = ids.map((id) => ({
      part_id: id,
      copies: rows[id]?.copies ?? 1,
      quantity: distinct(id),
      manual_values: rows[id]?.manual ?? {},
    }));
    const result = await runner.run(items, sizeConfirmed);
    if (result) {
      setOutcome(result);
      void qc.invalidateQueries({ queryKey: ["parts"] });
      void qc.invalidateQueries({ queryKey: qk.printers });
    }
  };

  return (
    <div className="flex h-[min(680px,calc(100vh-170px))] gap-6">
      <div className="flex w-[560px] shrink-0 flex-col gap-2">
        <LabelPreview result={currentPreview} loading={!currentPreview} maxHeight={420} />
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
            <ul className="flex min-h-0 flex-1 flex-col divide-y divide-border overflow-y-auto rounded-[8px] border border-border">
              {ordered.map((id, i) => {
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
              <Button size="big" icon={runner.busy ? undefined : PrinterIcon} loading={runner.busy} disabled={block.blocked || ids.length === 0} tooltip={block.blocked ? block.reason : null} onClick={() => void print()}>
                {runner.busy ? "Sending…" : totalLabels > 1 ? `Print ${totalLabels} labels` : "Print"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
