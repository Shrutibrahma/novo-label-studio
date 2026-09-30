import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Lock, Tag } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Display";
import { Field, Input, Select } from "../../components/Form";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { qk, useSettings } from "../../lib/queries";
import type { AppSettings } from "../../lib/types";

function useSaveSettings(onFieldErrors: (f: Record<string, string>) => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api<AppSettings>("/settings", { method: "PATCH", body }),
    onSuccess: (s) => {
      qc.setQueryData(qk.settings, s);
      onFieldErrors({});
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.fields).length) onFieldErrors(e.fields);
      else toast.error(e instanceof ApiError ? e.message : String(e));
    },
  });
}

export function GeneralTab() {
  const settings = useSettings();
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => setName(settings.data?.company_name ?? ""), [settings.data?.company_name]);
  const save = useSaveSettings(setErrors);
  return (
    <div className="flex flex-wrap items-start gap-6">
    <Card className="w-full max-w-[560px]">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ company_name: name });
        }}
      >
        <Field label="Company name" htmlFor="company" error={errors.company_name}>
          <Input id="company" value={name} error={errors.company_name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div>
          <Button type="submit" loading={save.isPending} disabled={!name.trim() || name === settings.data?.company_name}>
            Save
          </Button>
        </div>
      </form>
    </Card>
    <SidebarPreview name={name} />
    </div>
  );
}

/** How the company name appears at the top of the sidebar, updating as you type. */
function SidebarPreview({ name }: { name: string }) {
  return (
    <div className="flex w-[260px] flex-col gap-2">
      <span className="t-caption text-text-muted uppercase">Preview</span>
      <div className="flex flex-col gap-3 rounded-[12px] bg-nav-bg bg-[length:280px_280px] p-4 shadow-card" style={{ backgroundImage: "url(/art/pattern.svg)" }} aria-hidden>
        <div className="rounded-[8px] bg-surface px-3 py-2">
          <img src="/brand/novo-lean-solutions.svg" alt="" className="block h-9 w-auto" />
        </div>
        <div className="flex items-center gap-2 px-1">
          <Tag size={16} strokeWidth={1.75} className="shrink-0 text-nav-text" />
          <div className="flex min-w-0 flex-col">
            <span className="text-[15px] leading-5 font-semibold text-white">Novo Label Studio</span>
            <span className="truncate t-caption text-nav-text">{name.trim() || "Your company"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

const SEPARATORS = [
  { value: "-", label: "Dash" },
  { value: "_", label: "Underscore" },
  { value: "", label: "None" },
];

export function SerialTab() {
  const settings = useSettings();
  const serial = settings.data?.serial;
  const [form, setForm] = useState({ prefix: "", separator: "-", digits: 8, next_value: 1 });
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (serial) setForm({ prefix: serial.prefix, separator: serial.separator, digits: serial.digits, next_value: serial.next_value });
  }, [serial]);
  const save = useSaveSettings(setErrors);
  if (!serial) return null;
  const locked = serial.locked;
  const example = `${form.prefix}${form.separator}${String(Math.max(1, form.next_value || 1)).padStart(Math.min(12, Math.max(4, form.digits || 4)), "0")}`;
  const dirty = form.prefix !== serial.prefix || form.separator !== serial.separator || form.digits !== serial.digits || form.next_value !== serial.next_value;
  const submit = () => {
    const body: Record<string, unknown> = {};
    if (!locked) {
      if (form.prefix !== serial.prefix) body.serial_prefix = form.prefix;
      if (form.separator !== serial.separator) body.serial_separator = form.separator;
      if (form.digits !== serial.digits) body.serial_digits = form.digits;
    }
    if (form.next_value !== serial.next_value) body.serial_next_value = form.next_value;
    save.mutate(body);
  };
  return (
    <Card className="max-w-[560px]">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {locked && (
          <p className="inline-flex items-center gap-2 t-body text-text-secondary">
            <Lock size={16} strokeWidth={1.75} aria-hidden />
            Locked after the first serial is issued.
          </p>
        )}
        <div className="grid grid-cols-3 gap-4">
          <Field label="Prefix" htmlFor="s-prefix" error={errors.serial_prefix}>
            <Input id="s-prefix" className="t-mono" readOnly={locked} value={form.prefix} error={errors.serial_prefix} onChange={(e) => setForm({ ...form, prefix: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Separator" htmlFor="s-sep">
            <Select id="s-sep" disabled={locked} value={form.separator} options={SEPARATORS} onChange={(e) => setForm({ ...form, separator: e.target.value })} />
          </Field>
          <Field label="Digits" htmlFor="s-digits" error={errors.serial_digits}>
            <Input id="s-digits" type="number" min={4} max={12} readOnly={locked} value={form.digits} error={errors.serial_digits} onChange={(e) => setForm({ ...form, digits: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Next number" htmlFor="s-next" error={errors.serial_next_value}>
          <Input id="s-next" type="number" min={serial.next_value} value={form.next_value} error={errors.serial_next_value} onChange={(e) => setForm({ ...form, next_value: Number(e.target.value) })} />
        </Field>
        <p className="t-body text-text-secondary">
          <span className="t-mono text-text">{example}</span>
        </p>
        <div>
          <Button type="submit" loading={save.isPending} disabled={!dirty}>
            Save
          </Button>
        </div>
      </form>
    </Card>
  );
}
