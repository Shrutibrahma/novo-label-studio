import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Banner } from "../../components/Display";
import { Field, Textarea } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import { useToast } from "../../components/Toast";
import { api, ApiError, newIdempotencyKey } from "../../lib/api";
import { useDefaultPrinter } from "../../lib/queries";
import { JOB_STATUS_WORD, printerBlockMessage } from "../../lib/status";
import { waitForJobs, type Job } from "../print/jobs";
import { REASONS } from "./types";

/** "Reprint exact label" → reason (Damaged, Missing, Print issue, Other + optional note) → prints (12.12, 9.5). */
export function ReprintDialog({ labelId, dpi, onClose }: { labelId: string | null; dpi: number | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { printer } = useDefaultPrinter();
  const [reason, setReason] = useState<string>("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (labelId !== openFor) {
    setOpenFor(labelId);
    setReason("");
    setNote("");
    setError(null);
  }
  const blocked = printerBlockMessage(printer);
  const print = async () => {
    if (!labelId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ jobs: Job[] }>(`/labels/${labelId}/reprint`, {
        body: { reason, note: note.trim() || null },
        headers: { "Idempotency-Key": newIdempotencyKey() },
      });
      const jobs = await waitForJobs(res.jobs.map((j) => j.id), () => undefined);
      const job = jobs[0];
      if (job?.status === "failed") toast.error(`${JOB_STATUS_WORD.failed}: ${job.error ?? ""}`.trim());
      else if (job) toast.show(JOB_STATUS_WORD[job.status]);
      void qc.invalidateQueries({ queryKey: ["history"] });
      void qc.invalidateQueries({ queryKey: ["label"] });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={!!labelId}
      onClose={onClose}
      title="Reprint exact label"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={busy} disabled={!reason || !!blocked} tooltip={blocked} onClick={print}>
            {busy ? "Sending…" : "Print"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {printer && dpi !== null && printer.dpi !== dpi && (
          <Banner tone="warning">This printer has a different resolution. The label will be re-rendered from the original data.</Banner>
        )}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 t-body-strong text-text">
            Reason<span className="ml-0.5 text-danger">*</span>
          </legend>
          {REASONS.map((r) => (
            <label key={r.value} className="inline-flex items-center gap-2 t-body">
              <input type="radio" name="reprint-reason" checked={reason === r.value} onChange={() => setReason(r.value)} />
              {r.label}
            </label>
          ))}
        </fieldset>
        <Field label="Note" htmlFor="reprint-note">
          <Textarea id="reprint-note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {error && <Banner tone="danger">{error}</Banner>}
      </div>
    </Dialog>
  );
}

/** Admin: "Void serial" → dialog requiring a reason (min 5 chars). */
export function VoidDialog({ serial, onClose }: { serial: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openFor, setOpenFor] = useState<string | null>(null);
  if (serial !== openFor) {
    setOpenFor(serial);
    setReason("");
    setError(null);
  }
  const submit = async () => {
    if (!serial) return;
    setBusy(true);
    try {
      await api(`/serials/${encodeURIComponent(serial)}/void`, { body: { reason } });
      void qc.invalidateQueries({ queryKey: ["label"] });
      void qc.invalidateQueries({ queryKey: ["history"] });
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.reason ?? e.message) : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={!!serial}
      onClose={onClose}
      title="Void serial"
      subtitle={<span className="t-mono">{serial}</span>}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" loading={busy} disabled={reason.trim().length < 5} onClick={submit}>
            Void serial
          </Button>
        </>
      }
    >
      <Field label="Reason" required htmlFor="void-reason" error={error} helper="Minimum 5 characters.">
        <Textarea id="void-reason" data-autofocus rows={3} maxLength={500} value={reason} error={error} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Dialog>
  );
}
