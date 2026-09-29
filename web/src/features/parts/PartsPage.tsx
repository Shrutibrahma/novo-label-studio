import { FileSpreadsheet, Plus, Tag, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Page } from "../../app/Shell";
import { useIsAdmin } from "../../app/auth";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner, EmptyState, Mono } from "../../components/Display";
import { Select } from "../../components/Form";
import { PartStatusBadge, PartThumb, SearchInput } from "../../components/PartBits";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { Tooltip } from "../../components/Tooltip";
import { ApiError, SERVER_UNREACHABLE } from "../../lib/api";
import { formatDateTime, formatRelative } from "../../lib/format";
import { useDebounced } from "../../lib/parts";
import { AddPartDialog } from "./AddPartDialog";
import { PartDrawer } from "./PartDrawer";
import { usePartsQuery, useSentinel, type PartsParams } from "./usePartsQuery";

type StatusFilter = NonNullable<PartsParams["status"]>;

/** 12.7 Parts. */
export function PartsPage() {
  usePage("Parts");
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q.trim(), 200);
  const [status, setStatus] = useState<StatusFilter>("active");
  const [adding, setAdding] = useState(false);
  const openId = search.get("part");
  const openPart = (id: string | null) => {
    const next = new URLSearchParams(search);
    if (id) next.set("part", id);
    else next.delete("part");
    setSearch(next, { replace: true });
  };

  const params = useMemo<PartsParams>(() => ({ q: debouncedQ || undefined, status }), [debouncedQ, status]);
  const query = usePartsQuery(params);
  const rows = query.data?.pages.flatMap((p) => p.items) ?? [];
  const sentinel = useSentinel(() => query.hasNextPage && !query.isFetchingNextPage && void query.fetchNextPage(), !!query.hasNextPage);
  const emptyCatalogue = !query.isPending && rows.length === 0 && !debouncedQ && status === "active";
  const errorMessage = query.error ? (query.error instanceof ApiError ? query.error.message : SERVER_UNREACHABLE) : null;

  return (
    <Page>
      <div className="flex items-center gap-3">
        <SearchInput
          className="max-w-[480px]"
          placeholder="Search part number, label name or description"
          aria-label="Search part number, label name or description"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          aria-label="Status"
          className="w-40"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusFilter)}
          options={[
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
            { value: "archived", label: "Archived" },
            { value: "all", label: "All" },
          ]}
        />
        {isAdmin && (
          <div className="ml-auto flex gap-2">
            <Button variant="secondary" icon={Upload} onClick={() => navigate("/parts/import")}>
              Import
            </Button>
            <Button icon={Plus} onClick={() => setAdding(true)}>
              Add part
            </Button>
          </div>
        )}
      </div>

      <div className="mt-6">
        {errorMessage ? (
          <Banner tone="danger">{errorMessage}</Banner>
        ) : emptyCatalogue ? (
          <div className="rounded-[8px] border border-border bg-surface">
            <EmptyState
              icon={FileSpreadsheet}
              title="Your parts list is empty"
              body="Import a CSV or Excel file, or add parts one at a time."
              action={
                isAdmin ? (
                  <>
                    <Button onClick={() => navigate("/parts/import")}>Import parts</Button>
                    <Button variant="ghost" onClick={() => setAdding(true)}>
                      Add part
                    </Button>
                  </>
                ) : undefined
              }
            />
          </div>
        ) : !query.isPending && rows.length === 0 && debouncedQ ? (
          <div className="rounded-[8px] border border-border bg-surface px-6 py-16 text-center t-body text-text-secondary">No parts match "{debouncedQ}"</div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-16">Image</Th>
                <Th>Part number</Th>
                <Th>Part name</Th>
                <Th>Label name</Th>
                <Th>Revision</Th>
                <Th>Status</Th>
                <Th>Updated</Th>
              </tr>
            </thead>
            <tbody>
              {query.isPending ? (
                <SkeletonRows columns={7} tall />
              ) : (
                rows.map((p) => (
                  <Tr key={p.id} tall onClick={() => openPart(p.id)} selected={p.id === openId}>
                    <Td className="py-2">
                      <PartThumb part={p} />
                    </Td>
                    <Td>
                      <Mono className="text-text">{p.part_number}</Mono>
                    </Td>
                    <Td className="text-text">{p.part_name}</Td>
                    <Td>
                      {p.label_name ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Tag size={14} strokeWidth={1.75} aria-hidden />
                          {p.label_name}
                        </span>
                      ) : (
                        "—"
                      )}
                    </Td>
                    <Td>{p.revision ?? "—"}</Td>
                    <Td>
                      <PartStatusBadge status={p.status} />
                    </Td>
                    <Td>
                      <Tooltip content={formatDateTime(p.updated_at)}>
                        <span>{formatRelative(p.updated_at)}</span>
                      </Tooltip>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </Table>
        )}
        <div ref={sentinel} />
      </div>

      <PartDrawer partId={openId} onClose={() => openPart(null)} />
      <AddPartDialog open={adding} onClose={() => setAdding(false)} onOpenExisting={(id) => openPart(id)} />
    </Page>
  );
}
