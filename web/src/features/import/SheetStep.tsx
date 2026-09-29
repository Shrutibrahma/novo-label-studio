import { useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Display";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import type { ImportBatch } from "./types";

/** 10.1: a workbook with more than one non-empty sheet → "Which sheet?". */
export function SheetStep({ batch, onBack, onChosen }: { batch: ImportBatch; onBack: () => void; onChosen: () => void }) {
  const toast = useToast();
  const [sheet, setSheet] = useState(batch.sheets[0]?.name ?? "");
  const [busy, setBusy] = useState(false);
  const choose = async () => {
    setBusy(true);
    try {
      await api<ImportBatch>(`/imports/${batch.id}/sheet`, { method: "PUT", body: { sheet_name: sheet } });
      onChosen();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="max-w-[560px]">
      <h2 className="t-h2 text-text">Which sheet?</h2>
      <fieldset className="mt-4 flex flex-col gap-2">
        <legend className="sr-only">Which sheet?</legend>
        {batch.sheets.map((s) => (
          <label key={s.name} className={`flex items-center gap-3 rounded-[6px] border px-3 py-2 ${sheet === s.name ? "border-primary bg-primary-subtle" : "border-border"}`}>
            <input type="radio" name="sheet" checked={sheet === s.name} onChange={() => setSheet(s.name)} />
            <span className="flex-1 t-body-strong text-text">{s.name}</span>
            <span className="t-small text-text-muted tabular-nums">{s.rows.toLocaleString("en-US")} rows</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-6 flex justify-between">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button loading={busy} onClick={choose} disabled={!sheet}>
          Continue
        </Button>
      </div>
    </Card>
  );
}
