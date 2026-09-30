import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Badge, Banner, Mono } from "../../components/Display";
import { Input, Select, Switch } from "../../components/Form";
import { SearchInput } from "../../components/PartBits";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { useDebounced } from "../../lib/parts";
import { JOB_STATUS_TONE, JOB_STATUS_WORD } from "../../lib/status";
import { useSentinel } from "../parts/usePartsQuery";
import { HistoryDrawer } from "./HistoryDrawer";
import { ReprintDialog } from "./ReprintDialogs";
import type { HistoryRow, SerialInfo } from "./types";

type Range = "all" | "today" | "7" | "30" | "custom";

function rangeParams(range: Range, from: string, to: string): Record<string, string> {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const daysAgo = (n: number) => new Date(startOfToday.getTime() - (n - 1) * 86_400_000).toISOString();
  if (range === "today") return { from: startOfToday.toISOString() };
  if (range === "7") return { from: daysAgo(7) };
  if (range === "30") return { from: daysAgo(30) };
  if (range === "custom") {
    const out: Record<string, string> = {};
    if (from) out.from = new Date(`${from}T00:00:00`).toISOString();
    if (to) out.to = new Date(new Date(`${to}T00:00:00`).getTime() + 86_400_000).toISOString();
    return out;
  }
  return {};
}

/** 12.12 History. */
export function HistoryPage() {
  usePage("History");
  const [search, setSearch] = useSearchParams();
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim(), 200);
  const [range, setRange] = useState<Range>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [user, setUser] = useState("");
  const [reprintsOnly, setReprintsOnly] = useState(false);
  const [reprintFor, setReprintFor] = useState<HistoryRow | null>(null);
  const openId = search.get("label");
  const open = (id: string | null) => {
    const next = new URLSearchParams(search);
    if (id) next.set("label", id);
    else next.delete("label");
    setSearch(next, { replace: true });
  };

  const people = useQuery({ queryKey: ["history-people"], queryFn: () => api<{ id: string; display_name: string }[]>("/history/people") });
  const params = useMemo(() => {
    const p: Record<string, string> = { limit: "50", ...rangeParams(range, from, to) };
    if (dq) p.q = dq;
    if (user) p.user_id = user;
    if (reprintsOnly) p.reprints_only = "true";
    return p;
  }, [dq, range, from, to, user, reprintsOnly]);

  const rows = useInfiniteQuery({
    queryKey: ["history", params],
    queryFn: ({ pageParam, signal }) =>
      api<{ items: HistoryRow[]; next_cursor: string | null }>(`/history?${new URLSearchParams({ ...params, ...(pageParam ? { cursor: pageParam } : {}) })}`, { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const list = rows.data?.pages.flatMap((p) => p.items) ?? [];
  const sentinel = useSentinel(() => rows.hasNextPage && !rows.isFetchingNextPage && void rows.fetchNextPage(), !!rows.hasNextPage);

  // An exact serial typed in the search opens its drawer directly (the original print of that serial).
  useEffect(() => {
    if (!dq) return;
    const ctl = new AbortController();
    api<{ serial: SerialInfo; labels: HistoryRow[] }>(`/serials/${encodeURIComponent(dq)}`, { signal: ctl.signal })
      .then((r) => {
        const original = r.labels.find((l) => !l.reprint_of) ?? r.labels[0];
        if (original) open(original.id);
      })
      .catch(() => undefined);
    return () => ctl.abort();
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Page>
      <SearchInput placeholder="Search serial, part number or label name" aria-label="Search serial, part number or label name" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Select
          aria-label="Date range"
          className="w-40"
          value={range}
          onChange={(e) => setRange(e.target.value as Range)}
          options={[
            { value: "all", label: "All" },
            { value: "today", label: "Today" },
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "custom", label: "Custom" },
          ]}
        />
        {range === "custom" && (
          <>
            <Input aria-label="From" type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
            <Input aria-label="To" type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
        <Select
          aria-label="Printed by"
          className="w-48"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          options={[{ value: "", label: "Printed by" }, ...(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))]}
        />
        <Switch label="Reprints only" checked={reprintsOnly} onChange={setReprintsOnly} />
      </div>

      <div className="mt-6">
        {rows.error ? (
          <Banner tone="danger">{rows.error instanceof ApiError ? rows.error.message : String(rows.error)}</Banner>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Label</Th>
                <Th>Serial</Th>
                <Th>Box</Th>
                <Th>Size</Th>
                <Th>Copies</Th>
                <Th>By</Th>
                <Th>Status</Th>
                <Th className="w-32">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.isPending ? (
                <SkeletonRows columns={9} />
              ) : (
                list.map((r) => (
                  <Tr key={r.id} onClick={() => open(r.id)} selected={r.id === openId}>
                    <Td className="whitespace-nowrap">{formatDateTime(r.created_at)}</Td>
                    <Td>
                      <div className="t-body-strong text-text">{r.label_name ?? r.part_name}</div>
                      <Mono className="t-small">{r.part_number}</Mono>
                    </Td>
                    <Td>{r.serial ? <Mono className="text-text">{r.serial}</Mono> : "—"}</Td>
                    <Td className="tabular-nums">{r.box ?? "—"}</Td>
                    <Td>{r.size}</Td>
                    <Td className="tabular-nums">{r.copies}</Td>
                    <Td>{r.by}</Td>
                    <Td>
                      <Badge tone={JOB_STATUS_TONE[r.status]}>{JOB_STATUS_WORD[r.status]}</Badge>
                    </Td>
                    <Td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="sm" icon={RotateCcw} onClick={() => setReprintFor(r)}>
                        Reprint
                      </Button>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </Table>
        )}
        <div ref={sentinel} />
      </div>
      <HistoryDrawer labelId={openId} onClose={() => open(null)} onOpen={open} />
      <ReprintDialog labelId={reprintFor?.id ?? null} dpi={null} onClose={() => setReprintFor(null)} />
    </Page>
  );
}
