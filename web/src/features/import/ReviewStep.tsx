import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Plus, RefreshCw, TriangleAlert, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Banner, Mono } from "../../components/Display";
import { Field, Input } from "../../components/Form";
import { Dialog } from "../../components/Overlay";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { thousands } from "../../lib/format";
import { useCustomFields } from "../../lib/parts";
import { useSentinel } from "../parts/usePartsQuery";
import type { CommitResult, ImportBatch, ImportRow, RowAction } from "./types";

type Filter = RowAction | null;

const IMAGE = "image";

/** A picture staged from the spreadsheet (asset id), as a small thumbnail. */
function Thumb({ id, label }: { id: unknown; label: string }) {
  if (typeof id !== "string") return <span className="text-text-muted">none</span>;
  return <img src={`/api/v1/assets/${id}`} alt={label} className="inline-block h-8 w-8 rounded-[4px] border border-border bg-surface object-contain" />;
}

function show(v: unknown): string {
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

function SummaryCard({ label, count, icon: Icon, active, muted, onClick, tone }: {
  label: string;
  count: number;
  icon?: LucideIcon;
  active: boolean;
  muted?: boolean;
  tone: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`flex flex-1 flex-col gap-2 rounded-[8px] border p-6 text-left transition-colors duration-150 ${active ? "border-primary bg-primary-subtle" : muted ? "border-border bg-surface-subtle" : "border-border bg-surface hover:bg-row-hover"}`}
    >
      <span className="flex items-center gap-2 t-body-strong text-text-secondary">
        {Icon && <Icon size={20} strokeWidth={1.75} className={tone} aria-hidden />}
        {label}
      </span>
      <span className="text-[32px] leading-10 font-bold text-text tabular-nums">{thousands(count)}</span>
    </button>
  );
}

/** 12.10 "Review". */
export function ReviewStep({ batch, onBack, onDiscarded, onCommitted, onChanged }: {
  batch: ImportBatch;
  onBack: () => void;
  onDiscarded: () => void;
  onCommitted: (r: CommitResult) => void;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>(null);
  const [fixing, setFixing] = useState<ImportRow | null>(null);
  const [committing, setCommitting] = useState(false);

  const rows = useInfiniteQuery({
    queryKey: ["import-rows", batch.id, filter],
    queryFn: ({ pageParam }) =>
      api<{ items: ImportRow[]; next_cursor: string | null }>(`/imports/${batch.id}/rows?limit=100${filter ? `&action=${filter}` : ""}${pageParam ? `&cursor=${pageParam}` : ""}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const list = rows.data?.pages.flatMap((p) => p.items) ?? [];
  const sentinel = useSentinel(() => rows.hasNextPage && !rows.isFetchingNextPage && void rows.fetchNextPage(), !!rows.hasNextPage);
  const reload = () => {
    void qc.invalidateQueries({ queryKey: ["import-rows", batch.id] });
    onChanged();
  };

  const toggle = async (row: ImportRow, accepted: boolean) => {
    try {
      await api<ImportRow>(`/imports/${batch.id}/rows/${row.id}`, { method: "PATCH", body: { accepted } });
      reload();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    }
  };

  const commit = async () => {
    setCommitting(true);
    try {
      const r = await api<CommitResult>(`/imports/${batch.id}/commit`, { method: "POST" });
      void qc.invalidateQueries({ queryKey: ["parts"] });
      onCommitted(r);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCommitting(false);
    }
  };
  const discard = async () => {
    await api<ImportBatch>(`/imports/${batch.id}/discard`, { method: "POST" });
    onDiscarded();
  };

  const pick = (f: RowAction) => setFilter(filter === f ? null : f);
  const c = batch.counts;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex gap-4">
        <SummaryCard label="New" count={c.new} icon={Plus} tone="text-primary" active={filter === "new"} onClick={() => pick("new")} />
        <SummaryCard label="Updated" count={c.updated} icon={RefreshCw} tone="text-info" active={filter === "update"} onClick={() => pick("update")} />
        <SummaryCard label="Unchanged" count={c.unchanged} icon={CircleCheck} tone="text-success" active={filter === "unchanged"} onClick={() => pick("unchanged")} />
        <SummaryCard label="Need attention" count={c.invalid} icon={TriangleAlert} tone="text-warning" active={filter === "invalid"} onClick={() => pick("invalid")} />
        {c.missing > 0 && <SummaryCard label="Missing from file" count={c.missing} muted tone="" active={filter === "missing"} onClick={() => pick("missing")} />}
      </div>

      <Table>
        <thead>
          <tr>
            <Th className="w-12">
              <span className="sr-only">Accept</span>
            </Th>
            <Th className="w-20">Row</Th>
            <Th>Part number</Th>
            <Th>Part name</Th>
            <Th>Changes</Th>
            <Th>Problem</Th>
          </tr>
        </thead>
        <tbody>
          {rows.isPending ? (
            <SkeletonRows columns={6} />
          ) : (
            list.map((r) => (
              <Tr key={r.id}>
                <Td className="px-3">
                  {r.action === "missing" ? (
                    <label className="inline-flex items-center gap-2 whitespace-nowrap t-small text-text-secondary">
                      <input type="checkbox" checked={r.accepted} onChange={(e) => void toggle(r, e.target.checked)} />
                      Mark as inactive
                    </label>
                  ) : (
                    <input
                      type="checkbox"
                      aria-label={`Accept row ${r.source_row}`}
                      checked={r.accepted && (r.action === "new" || r.action === "update")}
                      disabled={r.action === "invalid" || r.action === "unchanged"}
                      onChange={(e) => void toggle(r, e.target.checked)}
                    />
                  )}
                </Td>
                <Td className="tabular-nums">{r.source_row ?? "—"}</Td>
                <Td>
                  <Mono className="text-text">{show(r.data.part_number)}</Mono>
                </Td>
                <Td className="text-text">
                  <span className="inline-flex items-center gap-2">
                    {r.action === "new" && typeof r.data[IMAGE] === "string" && <Thumb id={r.data[IMAGE]} label="Image" />}
                    {show(r.data.part_name)}
                  </span>
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(r.diff ?? {}).map(([field, [oldV, newV]]) =>
                      field === "status" && oldV === "archived" ? (
                        <span key={field} className="rounded-[6px] bg-warning-bg px-2 py-0.5 t-caption text-warning">
                          Restore archived part
                        </span>
                      ) : field === IMAGE ? (
                        <span key={field} className="inline-flex items-center gap-1.5 rounded-[6px] bg-neutral-bg px-2 py-0.5 t-caption text-text">
                          image: <Thumb id={oldV} label="Current image" /> → <Thumb id={newV} label="New image" />
                        </span>
                      ) : (
                        <span key={field} className="rounded-[6px] bg-neutral-bg px-2 py-0.5 t-caption text-text">
                          {field}: <span className="text-text-muted line-through">{show(oldV)}</span> → {show(newV)}
                        </span>
                      ),
                    )}
                  </div>
                </Td>
                <Td>
                  {r.action === "invalid" && (
                    <div className="flex items-start justify-between gap-3">
                      <span className="t-small text-danger">{(r.errors ?? []).map((e) => e.msg).join(" ")}</span>
                      <Button variant="secondary" size="sm" onClick={() => setFixing(r)}>
                        Fix
                      </Button>
                    </div>
                  )}
                </Td>
              </Tr>
            ))
          )}
        </tbody>
      </Table>
      <div ref={sentinel} />

      <div className="flex items-center gap-2">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <div className="flex-1" />
        <Button variant="danger-ghost" onClick={() => void discard()}>
          Discard import
        </Button>
        <Button loading={committing} onClick={commit}>
          Import {thousands(batch.accepted_to_import)} parts
        </Button>
      </div>

      <FixDialog batch={batch} row={fixing} onClose={() => setFixing(null)} onSaved={reload} />

    </div>
  );
}

const CORE_LABEL: Record<string, string> = { part_number: "Part number", part_name: "Part name", description: "Description", revision: "Revision", image: "Image" };

function FixDialog({ batch, row, onClose, onSaved }: { batch: ImportBatch; row: ImportRow | null; onClose: () => void; onSaved: () => void }) {
  const fields = useCustomFields();
  const targets = [...new Set(Object.values(batch.mapping).filter(Boolean) as string[])].filter((t) => t !== IMAGE);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedFor, setOpenedFor] = useState<number | null>(null);
  if (row && row.id !== openedFor) {
    setOpenedFor(row.id);
    setError(null);
    setValues(Object.fromEntries(targets.map((t) => [t, row.data[t] === undefined ? "" : String(row.data[t])])));
  }
  const label = (t: string) => CORE_LABEL[t] ?? fields.data?.find((f) => f.key === t)?.label ?? t;
  const save = async () => {
    if (!row) return;
    setBusy(true);
    try {
      const updated = await api<ImportRow>(`/imports/${batch.id}/rows/${row.id}`, { method: "PATCH", body: { data: values } });
      onSaved();
      if (updated.action === "invalid") setError((updated.errors ?? []).map((e) => e.msg).join(" "));
      else onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={!!row}
      onClose={onClose}
      title={`Row ${row?.source_row ?? ""}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={busy} onClick={save}>
            Save
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {error && <Banner tone="danger">{error}</Banner>}
        {targets.map((t) => (
          <Field key={t} label={label(t)} htmlFor={`fix-${t}`}>
            <Input id={`fix-${t}`} value={values[t] ?? ""} onChange={(e) => setValues({ ...values, [t]: e.target.value })} />
          </Field>
        ))}
      </div>
    </Dialog>
  );
}
