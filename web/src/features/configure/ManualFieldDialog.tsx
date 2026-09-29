import { useState } from "react";
import { Button } from "../../components/Button";
import { Field, Input, Select, Switch, Textarea } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import type { ManualField } from "../../lib/parts";

type Kind = ManualField["type"];
const KINDS: { value: Kind; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "choice", label: "Choice" },
  { value: "box_sequence", label: "Box sequence" },
];

function keyFromName(name: string): string {
  const k = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  if (!k) return "";
  return (/^[a-z]/.test(k) ? k : `f_${k}`).slice(0, 63);
}

interface Form {
  label: string;
  type: Kind;
  required: boolean;
  max_length: string;
  min: string;
  max: string;
  integer: boolean;
  choices: string;
  noun: string;
}

function toForm(m: ManualField | null): Form {
  const base: Form = { label: "", type: "text", required: false, max_length: "30", min: "", max: "", integer: false, choices: "", noun: "BOX" };
  if (!m) return base;
  const f = { ...base, label: m.label, type: m.type, required: m.required };
  if (m.type === "text") f.max_length = String(m.max_length);
  if (m.type === "number") Object.assign(f, { min: m.min === null ? "" : String(m.min), max: m.max === null ? "" : String(m.max), integer: m.integer });
  if (m.type === "choice") f.choices = m.choices.join("\n");
  if (m.type === "box_sequence") f.noun = m.noun;
  return f;
}

/** "Add print-time field" dialog: Name (key auto from name), Type, type options, Required (12.11). */
export function ManualFieldDialog({
  open,
  editing,
  existing,
  onClose,
  onSave,
}: {
  open: boolean;
  editing: ManualField | null;
  existing: ManualField[];
  onClose: () => void;
  onSave: (m: ManualField) => void;
}) {
  const [form, setForm] = useState<Form>(toForm(editing));
  const [openedFor, setOpenedFor] = useState<{ open: boolean; editing: ManualField | null }>({ open: false, editing: null });
  const [errors, setErrors] = useState<Record<string, string>>({});
  if (open !== openedFor.open || editing !== openedFor.editing) {
    setOpenedFor({ open, editing });
    setForm(toForm(editing));
    setErrors({});
  }
  const key = editing?.key ?? keyFromName(form.label);
  const others = existing.filter((m) => m.key !== editing?.key);
  const hasBox = others.some((m) => m.type === "box_sequence");

  const save = () => {
    const e: Record<string, string> = {};
    if (!form.label.trim()) e.label = "Name is required.";
    else if (!key || others.some((m) => m.key === key)) e.label = "A field with this key already exists.";
    let field: ManualField | null = null;
    if (form.type === "text") {
      const n = Number(form.max_length);
      if (!Number.isInteger(n) || n < 1 || n > 60) e.max_length = "Max length must be between 1 and 60.";
      field = { key, label: form.label.trim(), type: "text", required: form.required, max_length: n };
    } else if (form.type === "number") {
      const min = form.min.trim() === "" ? null : Number(form.min);
      const max = form.max.trim() === "" ? null : Number(form.max);
      if ((min !== null && Number.isNaN(min)) || (max !== null && Number.isNaN(max))) e.min = "Min must be a number.";
      else if (min !== null && max !== null && min > max) e.min = `Min must be between −∞ and ${max}.`;
      field = { key, label: form.label.trim(), type: "number", required: form.required, min, max, integer: form.integer };
    } else if (form.type === "choice") {
      const choices = [...new Set(form.choices.split("\n").map((c) => c.trim()).filter(Boolean))];
      if (choices.length < 1 || choices.length > 20) e.choices = "Choices must be between 1 and 20.";
      field = { key, label: form.label.trim(), type: "choice", required: form.required, choices };
    } else {
      const noun = form.noun.trim().toUpperCase();
      if (!/^[A-Z]{1,16}$/.test(noun)) e.noun = "Noun can use 1–16 capital letters.";
      field = { key, label: form.label.trim(), type: "box_sequence", required: form.required, noun };
    }
    setErrors(e);
    if (Object.keys(e).length === 0 && field) onSave(field);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? editing.label : "Add print-time field"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save}>{editing ? "Save" : "Add print-time field"}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="mf-name" error={errors.label} helper={key ? <span className="t-mono">{key}</span> : undefined}>
          <Input id="mf-name" data-autofocus value={form.label} error={errors.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        </Field>
        <Field label="Type" htmlFor="mf-type">
          <Select
            id="mf-type"
            value={form.type}
            disabled={!!editing}
            onChange={(e) => setForm({ ...form, type: e.target.value as Kind })}
            options={KINDS.map((k) => ({ ...k, disabled: k.value === "box_sequence" && hasBox }))}
          />
        </Field>
        {form.type === "text" && (
          <Field label="Max length" htmlFor="mf-maxlen" error={errors.max_length}>
            <Input id="mf-maxlen" type="number" min={1} max={60} value={form.max_length} error={errors.max_length} onChange={(e) => setForm({ ...form, max_length: e.target.value })} />
          </Field>
        )}
        {form.type === "number" && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Min" htmlFor="mf-min" error={errors.min}>
                <Input id="mf-min" type="number" value={form.min} error={errors.min} onChange={(e) => setForm({ ...form, min: e.target.value })} />
              </Field>
              <Field label="Max" htmlFor="mf-max">
                <Input id="mf-max" type="number" value={form.max} onChange={(e) => setForm({ ...form, max: e.target.value })} />
              </Field>
            </div>
            <Switch label="Whole numbers" checked={form.integer} onChange={(v) => setForm({ ...form, integer: v })} />
          </>
        )}
        {form.type === "choice" && (
          <Field label="Choices" htmlFor="mf-choices" error={errors.choices} helper="One per line.">
            <Textarea id="mf-choices" rows={4} value={form.choices} error={errors.choices} onChange={(e) => setForm({ ...form, choices: e.target.value })} />
          </Field>
        )}
        {form.type === "box_sequence" && (
          <Field label="Noun" htmlFor="mf-noun" error={errors.noun}>
            <Input id="mf-noun" className="t-mono" value={form.noun} error={errors.noun} onChange={(e) => setForm({ ...form, noun: e.target.value.toUpperCase() })} />
          </Field>
        )}
        <Switch label="Required" checked={form.required} onChange={(v) => setForm({ ...form, required: v })} />
      </div>
    </Dialog>
  );
}
