import { useState } from "react";
import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { JOB_STATUS_WORD } from "../../lib/status";
import type { Printer } from "../../lib/types";
import { waitForJobs, type Job } from "./jobs";

/** "Print test label" (12.1 popover, 12.3 setup step 3, 12.13 Printers). */
export function TestLabelButton({ printer, disabled, variant = "secondary" }: { printer: Printer; disabled?: boolean; variant?: "primary" | "secondary" }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const job = await api<Job>(`/printers/${printer.id}/test`, { method: "POST" });
      const [done] = await waitForJobs([job.id], () => undefined);
      if (done?.status === "failed") toast.error(`${JOB_STATUS_WORD.failed}: ${done.error ?? ""}`.trim());
      else if (done) toast.show(JOB_STATUS_WORD[done.status]);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button variant={variant} size="sm" loading={busy} disabled={disabled} onClick={run}>
      Print test label
    </Button>
  );
}
