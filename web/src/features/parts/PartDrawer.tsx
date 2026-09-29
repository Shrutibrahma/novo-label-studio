import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ChevronDown, ImagePlus, Tag } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useIsAdmin } from "../../app/auth";
import { Button } from "../../components/Button";
import { Banner, Mono, PrimaryBadge, Skeleton } from "../../components/Display";
import { Checkbox, Field, Input, Textarea } from "../../components/Form";
import { Menu, Tabs } from "../../components/Menu";
import { ConfirmDialog, Dialog, Drawer } from "../../components/Overlay";
import { FreshnessBadge, PartStatusBadge, PartThumb } from "../../components/PartBits";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { qk } from "../../lib/queries";
import { useCustomFields, usePart, type Alias, type PartDetail } from "../../lib/parts";
import { CustomFieldInput, customValue } from "./CustomFieldInput";
import { PartLabelTab } from "./PartLabelTab";

type Tab = "details" | "names" | "label";

export function PartDrawer({ partId, onClose, initialTab = "details" }: { partId: string | null; onClose: () => void; initialTab?: Tab }) {
  const part = usePart(partId);
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(() => setTab(initialTab), [partId, initialTab]);
  const p = part.data;
  return (
    <Drawer
      open={!!partId}
      onClose={onClose}
      label="Part"
      header={p ? <DrawerHeader part={p} /> : <Skeleton className="h-16 w-full" />}
    >
      {p && (
        <>
          <Tabs<Tab>
            label="Part"
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "details", label: "Details" },
              { value: "names", label: "Label names" },
              { value: "label", label: "Label" },
            ]}
          />
          {tab === "details" && <DetailsTab key={p.id + p.updated_at} part={p} onArchived={onClose} />}
          {tab === "names" && <LabelNamesTab part={p} />}
          {tab === "label" && <PartLabelTab part={p} />}
        </>
      )}
      {part.error && (
        <div className="p-6">
          <Banner tone="danger">{part.error instanceof ApiError ? part.error.message : String(part.error)}</Banner>
        </div>
      )}
    </Drawer>
  );
}

function useInvalidatePart(id: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: qk.part(id) });
    void qc.invalidateQueries({ queryKey: ["parts"] });
  };
}

function DrawerHeader({ part }: { part: PartDetail }) {
  const isAdmin = useIsAdmin();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const invalidate = useInvalidatePart(part.id);
  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api<PartDetail>(`/parts/${part.id}/image`, { method: "PUT", form });
    },
    onSuccess: invalidate,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });
  return (
    <div className="flex items-start gap-4">
      {isAdmin ? (
        <button type="button" aria-label="Change image" title="Change image" onClick={() => file.current?.click()} className="group relative shrink-0 rounded-[6px]">
          <PartThumb part={part} size={64} />
          <span className="absolute inset-0 hidden items-center justify-center rounded-[6px] bg-text/50 text-white group-hover:flex">
            {upload.isPending ? <span className="spinner" /> : <ImagePlus size={20} strokeWidth={1.75} aria-hidden />}
          </span>
          <input
            ref={file}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = "";
            }}
          />
        </button>
      ) : (
        <PartThumb part={part} size={64} />
      )}
      <div className="min-w-0">
        <h2 className="t-h2 text-text">{part.label_name ?? part.part_name}</h2>
        <Mono className="t-body text-text-secondary">{part.part_number}</Mono>
        <div className="mt-2 flex gap-2">
          <PartStatusBadge status={part.status} />
          <FreshnessBadge state={part.label_state} />
        </div>
      </div>
    </div>
  );
}

function DetailsTab({ part, onArchived }: { part: PartDetail; onArchived: () => void }) {
  const isAdmin = useIsAdmin();
  const fields = useCustomFields();
  const invalidate = useInvalidatePart(part.id);
  const toast = useToast();
  const initial = {
    part_number: part.part_number,
    part_name: part.part_name,
    description: part.description ?? "",
    revision: part.revision ?? "",
  };
  const initialCustom = Object.fromEntries((fields.data ?? []).map((f) => [f.key, customValue(part.custom_data[f.key])]));
  const [form, setForm] = useState(initial);
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmArchive, setConfirmArchive] = useState(false);

  const customMerged = { ...initialCustom, ...custom };
  const dirtyCore = (Object.keys(initial) as (keyof typeof initial)[]).filter((k) => form[k] !== initial[k]);
  const dirtyCustom = Object.keys(custom).filter((k) => custom[k] !== initialCustom[k]);
  const dirty = dirtyCore.length > 0 || dirtyCustom.length > 0;

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { clear: [] as string[] };
      for (const k of dirtyCore) {
        const v = form[k].trim();
        if ((k === "description" || k === "revision") && v === "") (body.clear as string[]).push(k);
        else body[k] = form[k];
      }
      if (dirtyCustom.length) body.custom_data = Object.fromEntries(dirtyCustom.map((k) => [k, custom[k]]));
      return api<PartDetail>(`/parts/${part.id}`, { method: "PATCH", body, headers: { "If-Match": part.updated_at } });
    },
    onSuccess: () => {
      setErrors({});
      setCustom({});
      invalidate();
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.fields).length) setErrors(e.fields);
      else toast.error(e instanceof ApiError ? e.message : String(e));
    },
  });

  const statusChange = useMutation({
    mutationFn: (action: "archive" | "restore") => api<PartDetail>(`/parts/${part.id}/${action}`, { method: "POST" }),
    onSuccess: (_, action) => {
      invalidate();
      setConfirmArchive(false);
      if (action === "archive") onArchived();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });

  const readOnly = !isAdmin;
  const set = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="flex flex-col">
      <div className="flex flex-col gap-4 p-6">
        <Field label="Part number" htmlFor="pd-number" error={errors.part_number}>
          <Input id="pd-number" className="t-mono" readOnly={readOnly} value={form.part_number} error={errors.part_number} onChange={set("part_number")} />
        </Field>
        <Field label="Part name" htmlFor="pd-name" error={errors.part_name}>
          <Input id="pd-name" readOnly={readOnly} value={form.part_name} error={errors.part_name} onChange={set("part_name")} />
        </Field>
        <Field label="Description" htmlFor="pd-desc" error={errors.description}>
          <Textarea id="pd-desc" rows={4} readOnly={readOnly} value={form.description} error={errors.description} onChange={set("description")} />
        </Field>
        <Field label="Revision" htmlFor="pd-rev" error={errors.revision}>
          <Input id="pd-rev" readOnly={readOnly} value={form.revision} error={errors.revision} onChange={set("revision")} />
        </Field>
        {(fields.data ?? []).map((f) => (
          <CustomFieldInput
            key={f.key}
            field={f}
            readOnly={readOnly}
            value={customMerged[f.key] ?? ""}
            error={errors[`custom_data.${f.key}`]}
            onChange={(v) => setCustom({ ...custom, [f.key]: v })}
          />
        ))}
      </div>
      {isAdmin && (
        <div className="sticky bottom-0 flex items-center gap-2 border-t border-border bg-surface px-6 py-4">
          <div className="flex-1">
            {part.status === "archived" ? (
              <Button variant="ghost" icon={ArchiveRestore} loading={statusChange.isPending} onClick={() => statusChange.mutate("restore")}>
                Restore
              </Button>
            ) : (
              <Button variant="danger-ghost" icon={Archive} onClick={() => setConfirmArchive(true)}>
                Archive part
              </Button>
            )}
          </div>
          <Button
            variant="secondary"
            disabled={!dirty}
            onClick={() => {
              setForm(initial);
              setCustom({});
              setErrors({});
            }}
          >
            Cancel
          </Button>
          <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirmArchive}
        title={`Archive ${part.part_number}?`}
        body="It will disappear from Print Labels. Print history is kept."
        confirmLabel="Archive"
        danger
        loading={statusChange.isPending}
        onCancel={() => setConfirmArchive(false)}
        onConfirm={() => statusChange.mutate("archive")}
      />
    </div>
  );
}

function LabelNamesTab({ part }: { part: PartDetail }) {
  const isAdmin = useIsAdmin();
  const invalidate = useInvalidatePart(part.id);
  const toast = useToast();
  const [text, setText] = useState("");
  const [asLabel, setAsLabel] = useState(part.label_name === null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<Alias | null>(null);
  useEffect(() => setAsLabel(part.label_name === null), [part.label_name]);

  const add = useMutation({
    mutationFn: () => api<Alias>(`/parts/${part.id}/aliases`, { body: { alias: text, is_label_name: asLabel } }),
    onSuccess: () => {
      setText("");
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? (e.fields.alias ?? e.message) : String(e)),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { alias?: string; is_label_name?: boolean } }) => api<Alias>(`/aliases/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      setRenaming(null);
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/aliases/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });

  return (
    <div className="flex flex-col gap-4 p-6">
      <ul className="flex flex-col divide-y divide-border rounded-[8px] border border-border">
        {part.aliases.map((a) => (
          <li key={a.id} className="flex items-center gap-3 px-4 py-3">
            <Tag size={16} strokeWidth={1.75} className="text-text-muted" aria-hidden />
            <span className="flex-1 t-body text-text">{a.alias}</span>
            {a.is_label_name && <PrimaryBadge>Label name</PrimaryBadge>}
            {isAdmin && (
              <Menu
                label={`Actions for ${a.alias}`}
                items={[
                  { label: "Use as label name", disabled: a.is_label_name, onSelect: () => patch.mutate({ id: a.id, body: { is_label_name: true } }) },
                  { label: "Rename", onSelect: () => setRenaming(a) },
                  { label: "Remove", danger: true, onSelect: () => remove.mutate(a.id) },
                ]}
                trigger={(p) => (
                  <button type="button" {...p} aria-label={`Actions for ${a.alias}`} className="rounded-[6px] p-1 text-text-secondary hover:bg-hover-fill">
                    <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
                  </button>
                )}
              />
            )}
          </li>
        ))}
      </ul>
      {isAdmin && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) add.mutate();
          }}
        >
          <div className="flex gap-2">
            <Input aria-label="Label name" placeholder="e.g. 10-32 x 1/2 16" value={text} error={error} onChange={(e) => setText(e.target.value)} />
            <Button type="submit" variant="secondary" loading={add.isPending} disabled={!text.trim()}>
              Add
            </Button>
          </div>
          {error && <p role="alert" className="-mt-1 t-small text-danger">{error}</p>}
          <Checkbox label="Use as label name" checked={asLabel} onChange={setAsLabel} />
        </form>
      )}
      <p className="t-small text-text-muted">Searching any of these names finds this part.</p>
      <RenameDialog alias={renaming} onClose={() => setRenaming(null)} onSave={(v) => (renaming ? patch.mutateAsync({ id: renaming.id, body: { alias: v } }) : undefined)} />
    </div>
  );
}

function RenameDialog({ alias, onClose, onSave }: { alias: Alias | null; onClose: () => void; onSave: (v: string) => Promise<unknown> | undefined }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setValue(alias?.alias ?? "");
    setError(null);
  }, [alias]);
  const submit = async () => {
    setBusy(true);
    try {
      await onSave(value);
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.alias ?? e.message) : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={!!alias}
      onClose={onClose}
      title="Rename"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={busy} onClick={submit}>
            Save
          </Button>
        </>
      }
    >
      <Field label="Label name" htmlFor="rename-alias" error={error}>
        <Input id="rename-alias" data-autofocus value={value} error={error} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void submit()} />
      </Field>
    </Dialog>
  );
}
