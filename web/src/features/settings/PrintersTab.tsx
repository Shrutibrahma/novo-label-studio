import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Card, Mono, StatusDot } from "../../components/Display";
import { Field, Input, Select } from "../../components/Form";
import { ConfirmDialog, Dialog } from "../../components/Overlay";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { formatDateTime, formatRelative, sizeText } from "../../lib/format";
import { qk, usePrinters, useSizes } from "../../lib/queries";
import { effectivePrinterStatus, PRINTER_STATUS_TONE, PRINTER_STATUS_WORD } from "../../lib/status";
import type { Printer } from "../../lib/types";
import { TestLabelButton } from "../print/TestLabelButton";

export function PrintersTab() {
  const printers = usePrinters();
  return (
    <div className="flex flex-col gap-4">
      {(printers.data ?? []).map((p) => (
        <PrinterCard key={p.id} printer={p} />
      ))}
    </div>
  );
}

function numOrEmpty(n: number | null): string {
  return n === null ? "" : String(n);
}

function PrinterCard({ printer }: { printer: Printer }) {
  const qc = useQueryClient();
  const toast = useToast();
  const sizes = useSizes();
  const init = {
    loaded: printer.loaded_label_size?.id ?? "",
    darkness: numOrEmpty(printer.darkness),
    speed: numOrEmpty(printer.speed_ips),
    x: String(printer.offset_x_dots),
    y: String(printer.offset_y_dots),
  };
  const [form, setForm] = useState(init);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmToken, setConfirmToken] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => setForm(init), [printer.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = JSON.stringify(form) !== JSON.stringify(init);
  const status = effectivePrinterStatus(printer);

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {};
      if (form.loaded !== init.loaded) Object.assign(body, form.loaded ? { loaded_label_size_id: form.loaded } : { clear_loaded_label_size: true });
      if (form.darkness !== init.darkness) Object.assign(body, form.darkness === "" ? { clear_darkness: true } : { darkness: Number(form.darkness) });
      if (form.speed !== init.speed) Object.assign(body, form.speed === "" ? { clear_speed: true } : { speed_ips: Number(form.speed) });
      if (form.x !== init.x) body.offset_x_dots = Number(form.x);
      if (form.y !== init.y) body.offset_y_dots = Number(form.y);
      return api<Printer>(`/printers/${printer.id}`, { method: "PATCH", body, headers: { "If-Match": printer.updated_at } });
    },
    onSuccess: () => {
      setErrors({});
      void qc.invalidateQueries({ queryKey: qk.printers });
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.fields).length) setErrors(e.fields);
      else toast.error(e instanceof ApiError ? e.message : String(e));
    },
  });
  const rotate = useMutation({
    mutationFn: () => api<{ agent_token: string }>(`/printers/${printer.id}/agent-token`, { method: "POST" }),
    onSuccess: (r) => {
      setConfirmToken(false);
      setToken(r.agent_token);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });

  const sizeOptions = [{ value: "", label: "—" }, ...(sizes.data ?? []).filter((s) => s.active).map((s) => ({ value: s.id, label: `${s.name} · ${sizeText(s)}` }))];

  return (
    <Card className="max-w-[720px]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="t-h3 text-text">{printer.name}</h3>
          <p className="t-small text-text-secondary">{printer.model}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="inline-flex items-center gap-2 t-body-strong">
            <StatusDot tone={PRINTER_STATUS_TONE[status]} />
            {PRINTER_STATUS_WORD[status]}
          </span>
          <span className="t-small text-text-muted" title={formatDateTime(printer.agent_last_seen_at)}>
            Last seen {formatRelative(printer.agent_last_seen_at)}
          </span>
        </div>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4">
        <Field label="Loaded labels" htmlFor={`pr-size-${printer.id}`} className="col-span-2">
          <Select id={`pr-size-${printer.id}`} value={form.loaded} options={sizeOptions} onChange={(e) => setForm({ ...form, loaded: e.target.value })} />
        </Field>
        <Field label="Darkness" htmlFor={`pr-dark-${printer.id}`} error={errors.darkness} helper="0–30. Empty = printer default.">
          <Input id={`pr-dark-${printer.id}`} type="number" min={0} max={30} value={form.darkness} error={errors.darkness} onChange={(e) => setForm({ ...form, darkness: e.target.value })} />
        </Field>
        <Field label="Speed" htmlFor={`pr-speed-${printer.id}`} error={errors.speed_ips} helper="ips. Empty = printer default.">
          <Input id={`pr-speed-${printer.id}`} type="number" min={1} max={14} value={form.speed} error={errors.speed_ips} onChange={(e) => setForm({ ...form, speed: e.target.value })} />
        </Field>
        <Field label="X offset" htmlFor={`pr-x-${printer.id}`} error={errors.offset_x_dots} helper="dots, −200 to 200">
          <Input id={`pr-x-${printer.id}`} type="number" min={-200} max={200} value={form.x} error={errors.offset_x_dots} onChange={(e) => setForm({ ...form, x: e.target.value })} />
        </Field>
        <Field label="Y offset" htmlFor={`pr-y-${printer.id}`} error={errors.offset_y_dots} helper="dots, −200 to 200">
          <Input id={`pr-y-${printer.id}`} type="number" min={-200} max={200} value={form.y} error={errors.offset_y_dots} onChange={(e) => setForm({ ...form, y: e.target.value })} />
        </Field>
      </div>
      <div className="mt-5 flex items-center gap-2">
        <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
        <TestLabelButton printer={printer} />
        <Button variant="secondary" size="sm" onClick={() => setConfirmToken(true)}>
          New agent token
        </Button>
      </div>
      <ConfirmDialog
        open={confirmToken}
        title="New agent token"
        body="The old token stops working immediately."
        confirmLabel="New agent token"
        loading={rotate.isPending}
        onCancel={() => setConfirmToken(false)}
        onConfirm={() => rotate.mutate()}
      />
      <Dialog open={token !== null} onClose={() => setToken(null)} title="New agent token" footer={<Button onClick={() => setToken(null)}>Done</Button>}>
        <div className="flex items-center gap-2 rounded-[6px] border border-border bg-surface-subtle px-3 py-2">
          <Mono className="flex-1 break-all text-text">{token}</Mono>
          <Button variant="secondary" size="sm" icon={Copy} onClick={() => token && void navigator.clipboard.writeText(token)}>
            Copy
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
