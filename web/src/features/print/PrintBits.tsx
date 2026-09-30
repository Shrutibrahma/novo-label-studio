import { CircleCheck, CircleX } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Banner, Mono, StatusDot } from "../../components/Display";
import { Field, Input, SegmentedControl, Select } from "../../components/Form";
import { api, ApiError, newIdempotencyKey } from "../../lib/api";
import type { ManualField } from "../../lib/parts";
import { effectivePrinterStatus, JOB_STATUS_WORD, PRINTER_STATUS_TONE, PRINTER_STATUS_WORD } from "../../lib/status";
import type { Printer } from "../../lib/types";
import { waitForJobs, type Job } from "./jobs";

export interface PrintItem {
  part_id: string;
  copies: number;
  quantity: number;
  manual_values: Record<string, unknown>;
  group?: { total: number; start_index: number; count: number; group_id?: string | null };
}

export interface PrintResponse {
  request_id: string;
  jobs: Job[];
  group_ids: (string | null)[];
  serials: string[];
}

export type Outcome =
  | { kind: "sent"; jobs: Job[]; serials: string[]; groupIds: (string | null)[] }
  | { kind: "failed"; error: string };

/** POST /print with a fresh Idempotency-Key, then wait for the agent (8.3). */
export function usePrintRunner() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (items: PrintItem[], loadedSizeConfirmed: boolean): Promise<Outcome | null> => {
    setBusy(true);
    setError(null);
    try {
      const res = await api<PrintResponse>("/print", {
        body: { items, loaded_size_confirmed: loadedSizeConfirmed },
        headers: { "Idempotency-Key": newIdempotencyKey() },
      });
      const jobs = await waitForJobs(res.jobs.map((j) => j.id), () => undefined);
      const failed = jobs.find((j) => j.status === "failed" || j.status === "cancelled");
      if (failed) return { kind: "failed", error: failed.error ?? JOB_STATUS_WORD[failed.status] };
      return { kind: "sent", jobs, serials: res.serials, groupIds: res.group_ids };
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  };
  return { run, busy, error, setError };
}

/** Printer line: status dot + "{printer name} · {status}" (12.6 step 5). */
export function PrinterLine({ printer }: { printer: Printer | undefined }) {
  if (!printer) return null;
  const status = effectivePrinterStatus(printer);
  return (
    <p className="inline-flex items-center gap-2 t-body text-text-secondary">
      <StatusDot tone={PRINTER_STATUS_TONE[status]} />
      {printer.name} · {PRINTER_STATUS_WORD[status]}
    </p>
  );
}

/** Size check (12.6 step 6). */
export function SizeBanner({ loaded, size, onConfirm }: { loaded: string | null; size: string; onConfirm: () => void }) {
  return (
    <Banner
      tone="warning"
      action={
        <Button variant="secondary" size="sm" onClick={onConfirm}>
          I've loaded {size} labels
        </Button>
      }
    >
      The printer has {loaded ?? "—"} labels loaded. This label is {size}.
    </Banner>
  );
}

/** Print-time fields in config order: text → input; number → numeric input; choice → segmented if ≤ 4, else select. */
export function ManualInputs({
  fields,
  values,
  onChange,
  errors,
  compact,
}: {
  fields: ManualField[];
  values: Record<string, unknown>;
  onChange: (key: string, v: string) => void;
  errors?: Record<string, string>;
  compact?: boolean;
}) {
  return (
    <>
      {fields
        .filter((m) => m.type !== "box_sequence")
        .map((m) => {
          const id = `mv-${m.key}`;
          const value = values[m.key] === undefined ? "" : String(values[m.key]);
          const error = errors?.[`manual_values.${m.key}`];
          let control;
          if (m.type === "choice") {
            control =
              m.choices.length <= 4 ? (
                <SegmentedControl ariaLabel={m.label} value={value} onChange={(v) => onChange(m.key, v)} options={m.choices.map((c) => ({ value: c, label: c }))} />
              ) : (
                <Select id={id} aria-label={m.label} value={value} onChange={(e) => onChange(m.key, e.target.value)} options={[{ value: "", label: "—" }, ...m.choices.map((c) => ({ value: c, label: c }))]} />
              );
          } else if (m.type === "number") {
            control = (
              <Input id={id} aria-label={m.label} type="number" min={m.min ?? undefined} max={m.max ?? undefined} step={m.integer ? 1 : "any"} value={value} error={error} onChange={(e) => onChange(m.key, e.target.value)} />
            );
          } else {
            control = <Input id={id} aria-label={m.label} maxLength={m.max_length} value={value} error={error} onChange={(e) => onChange(m.key, e.target.value)} />;
          }
          return (
            <Field key={m.key} label={compact ? undefined : m.label} required={m.required} htmlFor={id} error={error}>
              {control}
            </Field>
          );
        })}
    </>
  );
}

/** After submit: "Sent to printer" with the serials (max 5 then "+{n} more"), or "Print failed" with the error. */
export function ResultPanel({
  outcome,
  nextBox,
  onNextBox,
  onAnother,
  onDone,
  onRetry,
  busy,
  saved,
}: {
  outcome: Outcome;
  nextBox: { n: number; total: number } | null;
  onNextBox: () => void;
  onAnother: () => void;
  onDone: () => void;
  onRetry: () => void;
  busy: boolean;
  saved: boolean;
}) {
  if (outcome.kind === "failed") {
    return (
      <div className="flex flex-col items-start gap-3" role="alert">
        <CircleX size={32} strokeWidth={1.75} className="text-danger" aria-hidden />
        <h3 className="t-h3 text-text">Print failed</h3>
        <p className="t-body text-text-secondary">{outcome.error}</p>
        <Button loading={busy} onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }
  const confirmed = outcome.jobs.every((j) => j.status === "confirmed");
  const shown = outcome.serials.slice(0, 5);
  return (
    <div className="flex flex-col items-start gap-3" role="status">
      <CircleCheck size={32} strokeWidth={1.75} className="text-success" aria-hidden />
      <h3 className="t-h3 text-text">{confirmed ? JOB_STATUS_WORD.confirmed : JOB_STATUS_WORD.sent}</h3>
      {saved && <p className="t-small text-text-secondary">Saved for this part</p>}
      {shown.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {shown.map((s) => (
            <li key={s}>
              <Mono className="text-text">{s}</Mono>
            </li>
          ))}
          {outcome.serials.length > 5 && <li className="t-small text-text-secondary">+{outcome.serials.length - 5} more</li>}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {nextBox && (
          <Button loading={busy} onClick={onNextBox}>
            Print box {nextBox.n} of {nextBox.total}
          </Button>
        )}
        <Button variant="secondary" onClick={onAnother}>
          Print another
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}
