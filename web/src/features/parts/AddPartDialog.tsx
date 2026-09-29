import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Field, Input, Textarea } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import { api, ApiError } from "../../lib/api";
import { useCustomFields, type PartDetail, type PartList } from "../../lib/parts";
import { CustomFieldInput } from "./CustomFieldInput";

const EMPTY = { part_number: "", part_name: "", label_name: "", description: "", revision: "" };

/** 12.9 Add part dialog (width 560). */
export function AddPartDialog({ open, onClose, onOpenExisting }: {
  open: boolean;
  onClose: () => void;
  onOpenExisting: (id: string) => void;
}) {
  const qc = useQueryClient();
  const fields = useCustomFields();
  const [form, setForm] = useState(EMPTY);
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [duplicateId, setDuplicateId] = useState<string | null>(null);

  const close = () => {
    setForm(EMPTY);
    setCustom({});
    setErrors({});
    setDuplicateId(null);
    onClose();
  };

  const create = useMutation({
    mutationFn: () =>
      api<PartDetail>("/parts", {
        body: {
          ...form,
          label_name: form.label_name.trim() || null,
          description: form.description.trim() || null,
          revision: form.revision.trim() || null,
          custom_data: Object.fromEntries(Object.entries(custom).filter(([, v]) => v.trim() !== "")),
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["parts"] });
      close();
    },
    onError: async (e) => {
      if (!(e instanceof ApiError)) return setErrors({ form: String(e) });
      setErrors(Object.keys(e.fields).length ? { ...e.fields, alias: e.fields.alias ?? "" } : { form: e.message });
      if (e.code === "PART_NUMBER_TAKEN") {
        const found = await api<PartList>(`/parts?status=all&limit=5&q=${encodeURIComponent(form.part_number.trim())}`);
        const match = found.items.find((p) => p.part_number.trim().toUpperCase() === form.part_number.trim().toUpperCase());
        setDuplicateId(match?.id ?? null);
      }
    },
  });

  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Add part"
      footer={
        <Button loading={create.isPending} onClick={() => create.mutate()}>
          Add part
        </Button>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Part number" required htmlFor="ap-number" error={errors.part_number}>
          <Input id="ap-number" data-autofocus className="t-mono" value={form.part_number} error={errors.part_number} onChange={set("part_number")} />
        </Field>
        {duplicateId && (
          <button type="button" className="-mt-2 self-start t-small text-primary hover:underline" onClick={() => { close(); onOpenExisting(duplicateId); }}>
            Open it
          </button>
        )}
        <Field label="Part name" required htmlFor="ap-name" error={errors.part_name}>
          <Input id="ap-name" value={form.part_name} error={errors.part_name} onChange={set("part_name")} />
        </Field>
        <Field label="Label name" htmlFor="ap-label" error={errors.alias || errors.label_name}>
          <Input id="ap-label" value={form.label_name} error={errors.alias || errors.label_name} onChange={set("label_name")} />
        </Field>
        <Field label="Description" htmlFor="ap-desc" error={errors.description}>
          <Textarea id="ap-desc" rows={4} value={form.description} error={errors.description} onChange={set("description")} />
        </Field>
        <Field label="Revision" htmlFor="ap-rev" error={errors.revision}>
          <Input id="ap-rev" value={form.revision} error={errors.revision} onChange={set("revision")} />
        </Field>
        {(fields.data ?? []).map((f) => (
          <CustomFieldInput
            key={f.key}
            field={f}
            value={custom[f.key] ?? ""}
            error={errors[`custom_data.${f.key}`]}
            onChange={(v) => setCustom({ ...custom, [f.key]: v })}
          />
        ))}
        {errors.form && <p role="alert" className="t-small text-danger">{errors.form}</p>}
        <button type="submit" hidden />
      </form>
    </Dialog>
  );
}
