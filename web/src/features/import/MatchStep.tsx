import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { Banner } from "../../components/Display";
import { Field, Input, Select } from "../../components/Form";
import { Table, Td, Th, Tr } from "../../components/Table";
import { api, ApiError } from "../../lib/api";
import { qk } from "../../lib/queries";
import { useCustomFields } from "../../lib/parts";
import { FieldDialog } from "../settings/FieldsTab";
import type { ImportBatch } from "./types";

const NEW_FIELD = "__new__";
const CORE = [
  { value: "part_number", label: "Part number" },
  { value: "part_name", label: "Part name" },
  { value: "description", label: "Description" },
  { value: "revision", label: "Revision" },
];

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** 12.10 "Match columns". */
export function MatchStep({ batch, onBack, onConfirmed }: { batch: ImportBatch; onBack: () => void; onConfirmed: () => void }) {
  const qc = useQueryClient();
  const fields = useCustomFields();
  const [mapping, setMapping] = useState<Record<string, string | null>>(batch.mapping);
  const [saveAs, setSaveAs] = useState(batch.saved_mapping_name ?? batch.save_as_default);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newFieldFor, setNewFieldFor] = useState<string | null>(null);
  useEffect(() => setMapping(batch.mapping), [batch.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const used = useMemo(() => new Set(Object.values(mapping).filter(Boolean) as string[]), [mapping]);
  const options = (header: string) => {
    const mine = mapping[header];
    const all = [...CORE, ...(fields.data ?? []).map((f) => ({ value: f.key, label: f.label }))];
    return [
      { value: "", label: "Ignore" },
      ...all.map((o) => ({ ...o, disabled: used.has(o.value) && mine !== o.value })),
      { value: NEW_FIELD, label: "+ New custom field…" },
    ];
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api<ImportBatch>(`/imports/${batch.id}/mapping`, { method: "PUT", body: { mapping, save_as: saveAs } });
      onConfirmed();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {batch.saved_mapping_name && <Banner tone="info">Using saved mapping: {batch.saved_mapping_name}</Banner>}
      <Table>
        <thead>
          <tr>
            <Th>Column in your file</Th>
            <Th>Sample values</Th>
            <Th className="w-[280px]">Maps to</Th>
          </tr>
        </thead>
        <tbody>
          {batch.columns.map((c) => (
            <Tr key={c.header}>
              <Td>
                <span className="t-mono text-text">{c.header}</span>
              </Td>
              <Td className="text-text-muted">{truncate(c.samples.join(", "), 60)}</Td>
              <Td>
                <Select
                  aria-label={`Maps to for ${c.header}`}
                  value={mapping[c.header] ?? ""}
                  options={options(c.header)}
                  onChange={(e) => {
                    if (e.target.value === NEW_FIELD) setNewFieldFor(c.header);
                    else setMapping({ ...mapping, [c.header]: e.target.value || null });
                  }}
                />
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <Field label="Save this mapping as" htmlFor="save-as" className="max-w-[400px]">
        <Input id="save-as" value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />
      </Field>
      {error && <Banner tone="danger">{error}</Banner>}
      <div className="flex justify-between">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button loading={busy} onClick={submit}>
          Continue
        </Button>
      </div>
      <FieldDialog
        field={newFieldFor ? "new" : null}
        initialName={newFieldFor ?? ""}
        onClose={() => setNewFieldFor(null)}
        onCreated={(f) => {
          if (newFieldFor) setMapping((m) => ({ ...m, [newFieldFor]: f.key }));
          void qc.invalidateQueries({ queryKey: qk.customFields });
        }}
      />
    </div>
  );
}
