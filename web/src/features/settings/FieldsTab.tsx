import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Banner, Mono } from "../../components/Display";
import { Field, Input, Select, Switch, Textarea } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { api, ApiError } from "../../lib/api";
import { qk } from "../../lib/queries";
import { useCustomFields, type CustomField, type FieldType } from "../../lib/parts";

const TYPE_LABEL: Record<FieldType, string> = { text: "Text", number: "Number", date: "Date", choice: "Choice" };

function keyFromName(name: string): string {
  const k = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/_+/g, "_");
  if (!k) return "";
  return /^[a-z]/.test(k) ? k.slice(0, 63) : `f_${k}`.slice(0, 63);
}

export function FieldsTab() {
  const fields = useCustomFields();
  const [editing, setEditing] = useState<CustomField | "new" | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Button icon={Plus} onClick={() => setEditing("new")}>
          Add field
        </Button>
      </div>
      {fields.error && <Banner tone="danger">{fields.error.message}</Banner>}
      <Table>
        <thead>
          <tr>
            <Th>Name</Th>
            <Th>Key</Th>
            <Th>Type</Th>
            <Th>Required</Th>
            <Th>Searchable</Th>
            <Th>Printable</Th>
          </tr>
        </thead>
        <tbody>
          {fields.isPending ? (
            <SkeletonRows columns={6} />
          ) : (
            (fields.data ?? []).map((f) => (
              <Tr key={f.key} onClick={() => setEditing(f)}>
                <Td className="t-body-strong text-text">{f.label}</Td>
                <Td>
                  <Mono>{f.key}</Mono>
                </Td>
                <Td>{TYPE_LABEL[f.data_type]}</Td>
                <Td>{f.required ? "Yes" : "No"}</Td>
                <Td>{f.searchable ? "Yes" : "No"}</Td>
                <Td>{f.printable ? "Yes" : "No"}</Td>
              </Tr>
            ))
          )}
        </tbody>
      </Table>
      <FieldDialog field={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

export function FieldDialog({
  field,
  onClose,
  initialName = "",
  onCreated,
}: {
  field: CustomField | "new" | null;
  onClose: () => void;
  initialName?: string;
  onCreated?: (f: CustomField) => void;
}) {
  const qc = useQueryClient();
  const existing = field && field !== "new" ? field : null;
  const blank = { label: initialName, key: keyFromName(initialName), keyTouched: false, data_type: "text" as FieldType, choices: "", required: false, searchable: false, printable: true };
  const [form, setForm] = useState(blank);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    setErrors({});
    setForm(
      existing
        ? { label: existing.label, key: existing.key, keyTouched: true, data_type: existing.data_type, choices: (existing.choices ?? []).join("\n"), required: existing.required, searchable: existing.searchable, printable: existing.printable }
        : { ...blank, label: initialName, key: keyFromName(initialName) },
    );
  }, [field, initialName]); // eslint-disable-line react-hooks/exhaustive-deps

  const choices = form.choices.split("\n").map((c) => c.trim()).filter(Boolean);
  const save = useMutation({
    mutationFn: () => {
      const base = { label: form.label, required: form.required, searchable: form.searchable, printable: form.printable };
      const withChoices = form.data_type === "choice" ? { ...base, choices } : base;
      return existing
        ? api<CustomField>(`/custom-fields/${existing.key}`, { method: "PATCH", body: withChoices })
        : api<CustomField>("/custom-fields", { body: { ...withChoices, key: form.key, data_type: form.data_type } });
    },
    onSuccess: (f) => {
      void qc.invalidateQueries({ queryKey: qk.customFields });
      onCreated?.(f);
      onClose();
    },
    onError: (e) => setErrors(e instanceof ApiError ? (Object.keys(e.fields).length ? e.fields : { form: e.message }) : { form: String(e) }),
  });

  return (
    <Dialog
      open={field !== null}
      onClose={onClose}
      title={existing ? existing.label : "Add field"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {existing ? "Save" : "Add field"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="cf-name" error={errors.label}>
          <Input
            id="cf-name"
            data-autofocus
            value={form.label}
            error={errors.label}
            onChange={(e) => setForm({ ...form, label: e.target.value, key: form.keyTouched ? form.key : keyFromName(e.target.value) })}
          />
        </Field>
        <Field label="Key" htmlFor="cf-key" error={errors.key}>
          <Input id="cf-key" className="t-mono" readOnly={!!existing} value={form.key} error={errors.key} onChange={(e) => setForm({ ...form, key: e.target.value, keyTouched: true })} />
        </Field>
        <Field label="Type" htmlFor="cf-type">
          <Select
            id="cf-type"
            disabled={!!existing}
            value={form.data_type}
            onChange={(e) => setForm({ ...form, data_type: e.target.value as FieldType })}
            options={(Object.keys(TYPE_LABEL) as FieldType[]).map((t) => ({ value: t, label: TYPE_LABEL[t] }))}
          />
        </Field>
        {form.data_type === "choice" && (
          <Field label="Choices" htmlFor="cf-choices" error={errors.choices} helper="One per line.">
            <Textarea id="cf-choices" rows={4} value={form.choices} error={errors.choices} onChange={(e) => setForm({ ...form, choices: e.target.value })} />
          </Field>
        )}
        <Switch label="Required" checked={form.required} onChange={(v) => setForm({ ...form, required: v })} />
        <Switch label="Searchable" checked={form.searchable} onChange={(v) => setForm({ ...form, searchable: v })} />
        <Switch label="Printable" checked={form.printable} onChange={(v) => setForm({ ...form, printable: v })} />
        {errors.form && <p role="alert" className="t-small text-danger">{errors.form}</p>}
      </div>
    </Dialog>
  );
}
