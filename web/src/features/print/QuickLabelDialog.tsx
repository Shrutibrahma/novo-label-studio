import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Printer as PrinterIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Field, NumberStepper, SegmentedControl } from "../../components/Form";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { Dialog } from "../../components/Overlay";
import { api } from "../../lib/api";
import { fitsOnRoll } from "../../lib/format";
import { useLabelTypes } from "../../lib/labelTypes";
import type { ManualField, SizeBrief } from "../../lib/parts";
import { qk, useDefaultPrinter } from "../../lib/queries";
import { printBlock } from "./blocking";
import { ManualInputs, PrinterLine, ResultPanel, rollPreview, SizeBanner, usePrintRunner, type Outcome } from "./PrintBits";

interface QuickConfig {
  size: SizeBrief;
  spec: { manual_fields: ManualField[] };
}

/** 7.4 "Quick label": a label without a part (QC HOLD, workstation signs), typed in and printed. */
export function QuickLabelDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const quickTypes = (useLabelTypes().data ?? []).filter((t) => t.kind === "quick");
  const [typeId, setTypeId] = useState(quickTypes[0]?.id ?? "");
  const [manual, setManual] = useState<Record<string, unknown>>({});
  const [copies, setCopies] = useState(1);
  const [sizeConfirmed, setSizeConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const runner = usePrintRunner();
  const { printer } = useDefaultPrinter();
  const config = useQuery({ queryKey: qk.config(`quick:${typeId}`), queryFn: () => api<QuickConfig>(`/configs/default?type_id=${typeId}`), enabled: !!typeId });
  const preview = usePreview(typeId ? { label_type_id: typeId, manual_values: manual } : null, 250);

  const size = config.data?.size;
  const loaded = printer?.loaded_label_size ?? null;
  const sizeMismatch = size && !sizeConfirmed && !fitsOnRoll(size, loaded) ? size.name : null;
  const block = printBlock({ previews: [preview.data], printer, sizeMismatch });

  const print = async () => {
    const result = await runner.runQuick({ label_type_id: typeId, manual_values: manual, copies, loaded_size_confirmed: sizeConfirmed });
    if (result) {
      setOutcome(result);
      void qc.invalidateQueries({ queryKey: qk.printers });
    }
  };

  return (
    <Dialog open onClose={onClose} width={960} title="Quick label">
      <div className="flex h-[min(560px,calc(100vh-170px))] gap-6">
        <div className="w-[560px] shrink-0">
          <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={460} roll={rollPreview(size, printer)} />
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
              <div className="-mr-2 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto pr-2">
                {quickTypes.length > 1 && (
                  <SegmentedControl
                    ariaLabel="Quick label type"
                    value={typeId}
                    onChange={(id) => {
                      setTypeId(id);
                      setManual({});
                      setSizeConfirmed(false);
                    }}
                    options={quickTypes.map((t) => ({ value: t.id, label: t.name }))}
                  />
                )}
                <ManualInputs fields={config.data?.spec.manual_fields ?? []} values={manual} onChange={(k, v) => setManual({ ...manual, [k]: v })} />
                <Field label="Copies" htmlFor="quick-copies">
                  <NumberStepper id="quick-copies" label="Copies" min={1} max={50} value={copies} onChange={setCopies} />
                </Field>
                <PrinterLine printer={printer} />
                {sizeMismatch && <SizeBanner loaded={loaded?.name ?? null} size={sizeMismatch} onConfirm={() => setSizeConfirmed(true)} />}
                {runner.error && <p role="alert" className="t-small text-danger">{runner.error}</p>}
              </div>
              <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border pt-4">
                <Button variant="ghost" onClick={onClose}>
                  Cancel
                </Button>
                <Button size="big" icon={runner.busy ? undefined : PrinterIcon} loading={runner.busy} disabled={block.blocked || !typeId} tooltip={block.blocked ? block.reason : null} onClick={() => void print()}>
                  {runner.busy ? "Sending…" : "Print"}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </Dialog>
  );
}
