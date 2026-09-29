import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner, Card, Mono } from "../../components/Display";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { api } from "../../lib/api";
import { formatDate, sizeText } from "../../lib/format";
import { qk } from "../../lib/queries";
import { useCustomFields, type PartList } from "../../lib/parts";
import { fieldName, type ConfigOut, type OverrideRow } from "./types";

export function useFirstActivePart() {
  return useQuery({
    queryKey: ["parts", { first: true }],
    queryFn: () => api<PartList>("/parts?limit=1&status=active"),
    staleTime: 60_000,
    select: (d) => d.items[0] ?? null,
  });
}

/** 12.11 Configure list page. */
export function ConfigureListPage() {
  usePage("Configure");
  const navigate = useNavigate();
  const configs = useQuery({ queryKey: qk.configs, queryFn: () => api<{ default: ConfigOut; overrides: OverrideRow[] }>("/configs") });
  const first = useFirstActivePart();
  const custom = useCustomFields();
  const def = configs.data?.default;
  const preview = usePreview(def && first.data ? { part_id: first.data.id, config_id: def.id } : null, 0);
  const customLabels = Object.fromEntries((custom.data ?? []).map((f) => [f.key, f.label]));

  return (
    <Page>
      {configs.error && <Banner tone="danger">{configs.error.message}</Banner>}
      <Card className="flex gap-6">
        <div className="w-[280px] shrink-0">
          <LabelPreview result={preview.data} loading={preview.isFetching} padding={12} shrink showActualSizeToggle={false} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <h2 className="t-h2 text-text">Default label</h2>
          {def && (
            <>
              <p className="t-body text-text">
                {def.size.name} · {sizeText(def.size)}
              </p>
              <p className="t-body text-text-secondary">{def.spec.fields.map((f) => fieldName(f.key, customLabels, def.spec.manual_fields)).join(" · ") || "—"}</p>
              <p className="t-small text-text-muted">
                Version {def.version} · published {formatDate(def.created_at)} by {def.created_by_name}
              </p>
              <div className="mt-2">
                <Button onClick={() => navigate("/configure/default")}>Edit default label</Button>
              </div>
            </>
          )}
        </div>
      </Card>

      <h2 className="mt-8 mb-4 t-h2 text-text">Custom labels for specific parts</h2>
      {configs.data && configs.data.overrides.length === 0 ? (
        <p className="t-body text-text-secondary">All parts use the default label.</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Part number</Th>
              <Th>Label name</Th>
              <Th>Size</Th>
              <Th>Version</Th>
              <Th>Published</Th>
            </tr>
          </thead>
          <tbody>
            {configs.isPending ? (
              <SkeletonRows columns={5} />
            ) : (
              configs.data?.overrides.map((o) => (
                <Tr key={o.config_id} onClick={() => navigate(`/configure/part/${o.part_id}`)}>
                  <Td>
                    <Mono className="text-text">{o.part_number}</Mono>
                  </Td>
                  <Td>{o.label_name ?? "—"}</Td>
                  <Td>{sizeText(o.size)}</Td>
                  <Td className="tabular-nums">v{o.version}</Td>
                  <Td>
                    {formatDate(o.created_at)} · {o.created_by_name}
                  </Td>
                </Tr>
              ))
            )}
          </tbody>
        </Table>
      )}
    </Page>
  );
}
