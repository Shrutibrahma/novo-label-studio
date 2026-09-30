import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { useIsAdmin } from "../../app/auth";
import { Button } from "../../components/Button";
import { Badge, Banner, Mono, Skeleton } from "../../components/Display";
import { LabelPreview } from "../../components/LabelPreview";
import { Drawer } from "../../components/Overlay";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { qk } from "../../lib/queries";
import { JOB_STATUS_TONE, JOB_STATUS_WORD, type JobStatus } from "../../lib/status";
import { ReprintDialog, VoidDialog } from "./ReprintDialogs";
import { SERIAL_TONE, SERIAL_WORD, type LabelDetail } from "./types";

const TIMELINE_WORD: Record<string, string> = { created: "Waiting for printer" };

/** History drawer (12.12): exact stored bitmap, snapshot, job info, reprints, serial status. */
export function HistoryDrawer({ labelId, onClose, onOpen }: { labelId: string | null; onClose: () => void; onOpen: (id: string) => void }) {
  const isAdmin = useIsAdmin();
  const detail = useQuery({ queryKey: qk.label(labelId ?? ""), queryFn: () => api<LabelDetail>(`/labels/${labelId}`), enabled: !!labelId });
  const [reprinting, setReprinting] = useState(false);
  const [voiding, setVoiding] = useState(false);
  const d = detail.data;
  const voided = d?.serial?.status === "voided";
  return (
    <Drawer
      open={!!labelId}
      onClose={onClose}
      label="Printed label"
      header={
        d ? (
          <div>
            <h2 className="t-h2 text-text">{d.row.label_name ?? d.row.part_name ?? d.row.part_number}</h2>
            <Mono className="t-body text-text-secondary">{d.row.part_number}</Mono>
            <div className="mt-2 flex gap-2">
              <Badge tone={JOB_STATUS_TONE[d.row.status]}>{JOB_STATUS_WORD[d.row.status]}</Badge>
            </div>
          </div>
        ) : (
          <Skeleton className="h-14 w-full" />
        )
      }
      footer={
        d && (
          <div className="flex items-center gap-2">
            <div className="flex-1">
              {isAdmin && d.serial && !voided && (
                <Button variant="danger-ghost" onClick={() => setVoiding(true)}>
                  Void serial
                </Button>
              )}
            </div>
            <Button icon={RotateCcw} disabled={voided} tooltip={voided ? "This serial was voided and can't be reprinted." : null} onClick={() => setReprinting(true)}>
              Reprint exact label
            </Button>
          </div>
        )
      }
    >
      {detail.error && (
        <div className="p-6">
          <Banner tone="danger">{detail.error.message}</Banner>
        </div>
      )}
      {d && (
        <div className="flex flex-col gap-6 p-6">
          <LabelPreview
            padding={12}
            shrink
            result={{ png_base64: d.bitmap_png_base64, width_dots: d.width_dots, height_dots: d.height_dots, dpi: d.dpi, fits: true, warnings: [], family: "", serial_placeholder: false }}
          />
          <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-2">
            {d.fields.map((f) => (
              <div key={f.key} className="contents">
                <dt className="t-small text-text-muted">{f.label}</dt>
                <dd className="t-body text-text">{f.key === "serial" || f.key === "part_number" ? <Mono>{f.value}</Mono> : f.value}</dd>
              </div>
            ))}
            <dt className="t-small text-text-muted">Time</dt>
            <dd className="t-body text-text">{formatDateTime(d.row.created_at)}</dd>
            <dt className="t-small text-text-muted">By</dt>
            <dd className="t-body text-text">{d.row.by}</dd>
            <dt className="t-small text-text-muted">Copies</dt>
            <dd className="t-body text-text tabular-nums">{d.row.copies}</dd>
          </dl>

          <section className="flex flex-col gap-2">
            <h3 className="t-h3 text-text">Job</h3>
            <p className="t-small text-text-secondary">
              <Mono className="text-text">{d.job.id}</Mono> · {d.job.printer}
            </p>
            <ol className="flex flex-col gap-1">
              {d.job.timeline.map((t, i) => (
                <li key={i} className="flex justify-between t-small">
                  <span className="text-text">{TIMELINE_WORD[t.status] ?? JOB_STATUS_WORD[t.status as JobStatus] ?? t.status}</span>
                  <span className="text-text-muted">{formatDateTime(t.at)}</span>
                </li>
              ))}
            </ol>
            {d.job.error && <p className="t-small text-danger">{d.job.error}</p>}
          </section>

          {d.serial && (
            <section className="flex flex-col gap-2">
              <h3 className="t-h3 text-text">Serial</h3>
              <div className="flex items-center gap-2">
                <Mono className="text-text">{d.serial.value}</Mono>
                <Badge tone={SERIAL_TONE[d.serial.status]}>{SERIAL_WORD[d.serial.status]}</Badge>
              </div>
              {d.serial.void_reason && <p className="t-small text-text-secondary">{d.serial.void_reason}</p>}
            </section>
          )}

          {d.reprints.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="t-h3 text-text">Reprints</h3>
              <ul className="flex flex-col divide-y divide-border rounded-[8px] border border-border">
                {d.reprints.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => onOpen(r.id)} className="flex w-full justify-between px-3 py-2 text-left t-small hover:bg-row-hover">
                      <span className="text-text">
                        {formatDateTime(r.created_at)} · {r.by}
                      </span>
                      <Badge tone={JOB_STATUS_TONE[r.status]}>{JOB_STATUS_WORD[r.status]}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
      <ReprintDialog labelId={reprinting && d ? d.row.id : null} dpi={d?.dpi ?? null} onClose={() => setReprinting(false)} />
      <VoidDialog serial={voiding && d?.serial ? d.serial.value : null} onClose={() => setVoiding(false)} />
    </Drawer>
  );
}
