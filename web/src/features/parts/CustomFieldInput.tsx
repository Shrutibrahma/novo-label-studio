import { Field, Input, Select } from "../../components/Form";
import type { CustomField } from "../../lib/parts";

/** Input for one admin-defined field, by type. Values travel as strings; the API canonicalizes them. */
export function CustomFieldInput({
  field,
  value,
  onChange,
  error,
  readOnly,
}: {
  field: CustomField;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  readOnly?: boolean;
}) {
  const id = `cf-${field.key}`;
  let control;
  if (field.data_type === "choice") {
    control = (
      <Select
        id={id}
        value={value}
        disabled={readOnly}
        error={error}
        onChange={(e) => onChange(e.target.value)}
        options={[{ value: "", label: "—" }, ...(field.choices ?? []).map((c) => ({ value: c, label: c }))]}
      />
    );
  } else {
    control = (
      <Input
        id={id}
        type={field.data_type === "date" ? "date" : "text"}
        inputMode={field.data_type === "number" ? "decimal" : undefined}
        value={value}
        readOnly={readOnly}
        error={error}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <Field label={field.label} required={field.required && !readOnly} htmlFor={id} error={error}>
      {control}
    </Field>
  );
}

export function customValue(v: string | number | undefined): string {
  return v === undefined || v === null ? "" : String(v);
}
