import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { usePage } from "../../app/page";
import { Banner } from "../../components/Display";
import { api, ApiError } from "../../lib/api";
import { qk } from "../../lib/queries";
import { DoneStep } from "./DoneStep";
import { Hero } from "./Hero";
import { MatchStep } from "./MatchStep";
import { ReviewStep } from "./ReviewStep";
import { SheetStep } from "./SheetStep";
import type { CommitResult, ImportBatch } from "./types";

const STEPS = ["Upload", "Match columns", "Review", "Done"] as const;

export function Stepper({ step }: { step: 0 | 1 | 2 | 3 }) {
  return (
    <ol className="flex items-center gap-3" aria-label="Import steps">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === step ? "step" : undefined} className="flex items-center gap-3">
          <span className={`inline-flex items-center gap-2 t-small ${i === step ? "text-primary" : i < step ? "text-text" : "text-text-muted"}`}>
            <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full t-caption ${i <= step ? "bg-primary text-white" : "bg-neutral-bg text-neutral-text"}`}>{i + 1}</span>
            {s}
          </span>
          {i < STEPS.length - 1 && <span aria-hidden className="h-px w-8 bg-border-strong" />}
        </li>
      ))}
    </ol>
  );
}

/** 12.10 Import: dark hero for step 1, light layout with a stepper for steps 2–5. */
export function ImportPage() {
  usePage("Import");
  const qc = useQueryClient();
  const [search, setSearch] = useSearchParams();
  const batchId = search.get("batch");
  const [result, setResult] = useState<CommitResult | null>(null);
  const [editingMapping, setEditingMapping] = useState(false);

  const setBatchId = (id: string | null) => {
    const next = new URLSearchParams(search);
    if (id) next.set("batch", id);
    else next.delete("batch");
    setSearch(next, { replace: true });
    setResult(null);
    setEditingMapping(false);
  };

  const batch = useQuery({
    queryKey: qk.imports(batchId ?? ""),
    queryFn: () => api<ImportBatch>(`/imports/${batchId}`),
    enabled: !!batchId,
    refetchInterval: (q) => (q.state.data && ["parsing", "validating"].includes(q.state.data.status) ? 400 : false),
  });
  const b = batch.data;
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.imports(batchId ?? "") });

  if (!batchId || (b && (b.status === "discarded" || b.status === "parsing" || b.status === "failed")) || (batch.error && !b)) {
    const expired = batch.error instanceof ApiError ? batch.error.message : null;
    return (
      <Hero
        parsing={b?.status === "parsing" ? b.file_name : null}
        error={b?.status === "failed" ? (b.error?.message ?? null) : expired}
        onUploaded={(id) => setBatchId(id)}
      />
    );
  }
  if (!b) return null;

  let body;
  let step: 0 | 1 | 2 | 3 = 0;
  if (result || b.status === "committed") {
    step = 3;
    body = <DoneStep result={result} batch={b} />;
  } else if (b.status === "needs_sheet") {
    step = 0;
    body = <SheetStep batch={b} onBack={() => setBatchId(null)} onChosen={refresh} />;
  } else if (b.status === "mapping" || editingMapping) {
    step = 1;
    body = (
      <MatchStep
        batch={b}
        onBack={() => (editingMapping ? setEditingMapping(false) : setBatchId(null))}
        onConfirmed={() => {
          setEditingMapping(false);
          refresh();
        }}
      />
    );
  } else if (b.status === "validating") {
    step = 1;
    const pct = b.progress_total ? Math.round((b.progress_done / b.progress_total) * 100) : 0;
    body = (
      <div className="flex max-w-[560px] flex-col gap-3 rounded-[8px] border border-border bg-surface shadow-card p-6" role="status">
        <p className="t-body text-text">
          Checking rows… {b.progress_done.toLocaleString("en-US")} of {b.progress_total.toLocaleString("en-US")}
        </p>
        <div className="h-2 overflow-hidden rounded-full bg-neutral-bg">
          <div className="h-full rounded-full bg-primary transition-[width] duration-150" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  } else {
    step = 2;
    body = <ReviewStep batch={b} onBack={() => setEditingMapping(true)} onDiscarded={() => setBatchId(null)} onCommitted={setResult} onChanged={refresh} />;
  }

  return (
    <div className="max-w-[1440px] p-8">
      <Stepper step={step} />
      <div className="mt-6">{batch.error && <Banner tone="danger">{batch.error.message}</Banner>}</div>
      {body}
    </div>
  );
}
