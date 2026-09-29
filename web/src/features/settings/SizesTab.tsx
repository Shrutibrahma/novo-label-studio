import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Badge, Banner } from "../../components/Display";
import { Field, Input, Switch } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { api, ApiError } from "../../lib/api";
import { inches, plural } from "../../lib/format";
import { qk, useSizes } from "../../lib/queries";
import type { LabelSize } from "../../lib/types";

export function SizesTab() {
  const sizes = useSizes();
  const [editing, setEditing] = useState<LabelSize | "new" | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Button icon={Plus} onClick={() => setEditing("new")}>
          Add size
        </Button>
      </div>
      {sizes.error && <Banner tone="danger">{sizes.error.message}</Banner>}
      <Table>
        <thead>
          <tr>
            <Th>Name</Th>
            <Th>Width</Th>
            <Th>Height</Th>
            <Th>Status</Th>
            <Th>Used by</Th>
          </tr>
        </thead>
        <tbody>
          {sizes.isPending ? (
            <SkeletonRows columns={5} />
          ) : (
            (sizes.data ?? []).map((s) => (
              <Tr key={s.id} onClick={() => setEditing(s)}>
                <Td className="t-body-strong text-text">{s.name}</Td>
                <Td>{inches(s.width_in)} in</Td>
                <Td>{inches(s.height_in)} in</Td>
                <Td>{s.active ? <Badge tone="success">Active</Badge> : <Badge tone="neutral">Inactive</Badge>}</Td>
                <Td>{s.used_by ? `Used by ${s.used_by} ${plural(s.used_by, "label", "labels")}` : "—"}</Td>
              </Tr>
            ))
          )}
        </tbody>
      </Table>
      <SizeDialog size={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function SizeDialog({ size, onClose }: { size: LabelSize | "new" | null; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = size === "new";
  const existing = size && size !== "new" ? size : null;
  const [form, setForm] = useState({ name: "", width_in: "", height_in: "", active: true });
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    setErrors({});
    setForm(existing ? { name: existing.name, width_in: String(existing.width_in), height_in: String(existing.height_in), active: existing.active } : { name: "", width_in: "", height_in: "", active: true });
  }, [size]); // eslint-disable-line react-hooks/exhaustive-deps
  const inUse = !!existing && existing.used_by > 0;
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { name: form.name };
      if (!inUse) Object.assign(body, { width_in: form.width_in, height_in: form.height_in });
      if (existing) body.active = form.active;
      return existing ? api<LabelSize>(`/sizes/${existing.id}`, { method: "PATCH", body }) : api<LabelSize>("/sizes", { body });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.sizes });
      onClose();
    },
    onError: (e) => setErrors(e instanceof ApiError ? (Object.keys(e.fields).length ? e.fields : { form: e.message }) : { form: String(e) }),
  });
  return (
    <Dialog
      open={size !== null}
      onClose={onClose}
      title={isNew ? "Add size" : (existing?.name ?? "")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {isNew ? "Add size" : "Save"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="sz-name" error={errors.name}>
          <Input id="sz-name" data-autofocus value={form.name} error={errors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Width in" htmlFor="sz-w" error={errors.width_in} helper={inUse ? `Used by ${existing?.used_by} ${plural(existing?.used_by ?? 0, "label", "labels")}` : undefined}>
            <Input id="sz-w" type="number" step="0.01" min="2" max="4.4" readOnly={inUse} value={form.width_in} error={errors.width_in} onChange={(e) => setForm({ ...form, width_in: e.target.value })} />
          </Field>
          <Field label="Height in" htmlFor="sz-h" error={errors.height_in}>
            <Input id="sz-h" type="number" step="0.01" min="0.5" max="11" readOnly={inUse} value={form.height_in} error={errors.height_in} onChange={(e) => setForm({ ...form, height_in: e.target.value })} />
          </Field>
        </div>
        {existing && <Switch label="Active" checked={form.active} onChange={(v) => setForm({ ...form, active: v })} />}
        {errors.form && <p role="alert" className="t-small text-danger">{errors.form}</p>}
      </div>
    </Dialog>
  );
}
