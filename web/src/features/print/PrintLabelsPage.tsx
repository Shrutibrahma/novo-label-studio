import { Package } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Page } from "../../app/Shell";
import { useIsAdmin } from "../../app/auth";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner, EmptyState, Mono } from "../../components/Display";
import { FreshnessBadge, PartThumb, SearchInput } from "../../components/PartBits";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { ApiError, SERVER_UNREACHABLE } from "../../lib/api";
import { sizeText } from "../../lib/format";
import { useDebounced, type PartListItem } from "../../lib/parts";
import { usePartsQuery, useSentinel, type PartsParams } from "../parts/usePartsQuery";
import { PrintLaunchHost, PrintRowActions, type PrintLaunch } from "./PrintLaunch";

type Chip = "all" | "recent" | "out_of_date" | "never_printed";

const CHIPS: { value: Chip; label: string }[] = [
  { value: "all", label: "All" },
  { value: "recent", label: "Recently printed" },
  { value: "out_of_date", label: "Out of date" },
  { value: "never_printed", label: "Never printed" },
];

function chipParams(chip: Chip): PartsParams {
  if (chip === "recent") return { printed_within_days: 7 };
  if (chip === "out_of_date") return { label_state: "out_of_date" };
  if (chip === "never_printed") return { label_state: "never_printed" };
  return {};
}

/** 12.4 Print Labels. */
export function PrintLabelsPage() {
  usePage("Print Labels");
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const initialChip = (search.get("filter") as Chip | null) ?? "all";
  const [chip, setChip] = useState<Chip>(CHIPS.some((c) => c.value === initialChip) ? initialChip : "all");
  const [q, setQ] = useState(search.get("q") ?? "");
  const debouncedQ = useDebounced(q.trim(), 200);
  const [selected, setSelected] = useState<Map<string, PartListItem>>(new Map());
  const [launch, setLaunch] = useState<PrintLaunch | null>(null);

  const params = useMemo<PartsParams>(() => ({ q: debouncedQ || undefined, status: "active", ...chipParams(chip) }), [debouncedQ, chip]);
  const query = usePartsQuery(params);
  const rows = query.data?.pages.flatMap((p) => p.items) ?? [];
  const sentinel = useSentinel(() => query.hasNextPage && !query.isFetchingNextPage && void query.fetchNextPage(), !!query.hasNextPage);
  const isEmptyCatalogue = !query.isPending && rows.length === 0 && !debouncedQ && chip === "all";

  const setChipAndUrl = (c: Chip) => {
    setChip(c);
    const next = new URLSearchParams(search);
    if (c === "all") next.delete("filter");
    else next.set("filter", c);
    setSearch(next, { replace: true });
  };

  const toggle = (p: PartListItem) =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(p.id)) next.delete(p.id);
      else next.set(p.id, p);
      return next;
    });
  const allVisibleSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const toggleAll = () =>
    setSelected((prev) => {
      const next = new Map(prev);
      if (allVisibleSelected) rows.forEach((r) => next.delete(r.id));
      else rows.forEach((r) => next.set(r.id, r));
      return next;
    });

  // Enter in the search with exactly one result opens its Print dialog (12.4).
  const onSearchKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && rows.length === 1 && rows[0] && debouncedQ === q.trim()) {
      e.preventDefault();
      setLaunch({ mode: "print", parts: [rows[0]] });
    }
  };

  const errorMessage = query.error ? (query.error instanceof ApiError ? query.error.message : SERVER_UNREACHABLE) : null;

  return (
    <Page className="pb-28">
      <SearchInput
        autoFocus
        placeholder="Search part number, label name or description"
        aria-label="Search part number, label name or description"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onSearchKey}
      />
      <div className="mt-4 flex gap-2" role="radiogroup" aria-label="Filter">
        {CHIPS.map((c) => (
          <button
            key={c.value}
            type="button"
            role="radio"
            aria-checked={chip === c.value}
            onClick={() => setChipAndUrl(c.value)}
            className={`h-8 rounded-full border px-3 t-button transition-colors duration-150 ${chip === c.value ? "border-primary-subtle bg-primary-subtle text-primary" : "border-border-strong bg-surface text-text-secondary hover:bg-hover-fill"}`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {errorMessage ? (
          <Banner tone="danger">{errorMessage}</Banner>
        ) : isEmptyCatalogue ? (
          <div className="rounded-[8px] border border-border bg-surface">
            <EmptyState
              icon={Package}
              title="No parts yet"
              body={isAdmin ? "Import your parts list to start printing." : "Ask an admin to import parts."}
              action={isAdmin ? <Button onClick={() => navigate("/parts/import")}>Import parts</Button> : undefined}
            />
          </div>
        ) : !query.isPending && rows.length === 0 && debouncedQ ? (
          <div className="rounded-[8px] border border-border bg-surface px-6 py-16 text-center t-body text-text-secondary">No parts match "{debouncedQ}"</div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-10 px-3">
                  <input type="checkbox" aria-label="Select all" checked={allVisibleSelected} onChange={toggleAll} />
                </Th>
                <Th className="w-16">Image</Th>
                <Th>Label name</Th>
                <Th>Part number</Th>
                <Th>Size</Th>
                <Th>Label</Th>
                <Th className="w-40">
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {query.isPending ? (
                <SkeletonRows columns={7} tall />
              ) : (
                rows.map((p) => (
                  <Tr key={p.id} tall selected={selected.has(p.id)}>
                    <Td className="px-3">
                      <input type="checkbox" aria-label={`Select ${p.part_number}`} checked={selected.has(p.id)} onChange={() => toggle(p)} />
                    </Td>
                    <Td className="py-2">
                      <PartThumb part={p} />
                    </Td>
                    <Td>
                      <div className="t-body-strong text-text">{p.label_name ?? p.part_name}</div>
                      {p.label_name && <div className="t-small text-text-secondary">{p.part_name}</div>}
                    </Td>
                    <Td>
                      <Mono className="text-text">{p.part_number}</Mono>
                    </Td>
                    <Td>{sizeText(p.size)}</Td>
                    <Td>
                      <FreshnessBadge state={p.label_state} />
                    </Td>
                    <Td className="text-right">
                      <PrintRowActions part={p} onLaunch={setLaunch} />
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </Table>
        )}
        <div ref={sentinel} />
        {query.isFetchingNextPage && <div className="py-4 text-center t-small text-text-muted"><span className="spinner" aria-hidden /></div>}
      </div>

      {selected.size > 0 && (
        <div className="fixed right-0 bottom-0 left-60 z-10 border-t border-border bg-surface px-8 py-3 shadow-dropdown">
          <div className="flex max-w-[1440px] items-center gap-4">
            <span className="t-body-strong text-text">{selected.size} selected</span>
            <Button onClick={() => setLaunch({ mode: "print", parts: [...selected.values()] })}>Print selected</Button>

            <Button variant="ghost" onClick={() => setSelected(new Map())}>
              Clear
            </Button>
          </div>
        </div>
      )}

      <PrintLaunchHost launch={launch} onClose={() => setLaunch(null)} onSwitch={setLaunch} />
    </Page>
  );
}

