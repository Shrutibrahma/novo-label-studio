import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner, Card, Mono } from "../../components/Display";
import { Field, Input, Select } from "../../components/Form";
import { ConfirmDialog, Dialog } from "../../components/Overlay";
import { useToast } from "../../components/Toast";
import { LAYOUT_NAME, labelTypesKey, setCurrentLabelType, useLabelTypes, type LabelType } from "../../lib/labelTypes";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { api, ApiError } from "../../lib/api";
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
  const qc = useQueryClient();
  const toast = useToast();
  const types = useLabelTypes();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"new" | "rename" | "archive" | null>(null);
  const selected: LabelType | undefined = (types.data ?? []).find((t) => t.id === selectedId) ?? types.data?.[0];
  const isFirst = selected?.id === types.data?.[0]?.id;
  const configs = useQuery({
    queryKey: [...qk.configs, selected?.id ?? "first"],
    queryFn: () => api<{ default: ConfigOut; overrides: OverrideRow[] }>(`/configs${selected ? `?type_id=${selected.id}` : ""}`),
    enabled: !types.isPending,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: labelTypesKey });
    void qc.invalidateQueries({ queryKey: qk.configs });
  };
  const editPath = isFirst || !selected ? "/configure/default" : `/configure/type/${selected.id}`;
  const first = useFirstActivePart();
  const custom = useCustomFields();
  const def = configs.data?.default;
  const preview = usePreview(def && first.data ? { part_id: first.data.id, config_id: def.id } : null, 0);
  const customLabels = Object.fromEntries((custom.data ?? []).map((f) => [f.key, f.label]));

  return (
    <Page>
      {configs.error && <Banner tone="danger">{configs.error.message}</Banner>}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="mr-1 t-body-strong text-text">Label types</span>
        <div role="tablist" aria-label="Label types" className="flex flex-wrap gap-1.5">
          {(types.data ?? []).map((t) => {
            const on = t.id === selected?.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setSelectedId(t.id)}
                className={`inline-flex h-9 items-center gap-2 rounded-full border px-3.5 t-button transition-colors duration-150 ${on ? "border-primary bg-primary text-white shadow-card" : "border-border-strong bg-surface text-text hover:bg-hover-fill"}`}
              >
                {t.name}
                <span className={`t-caption ${on ? "text-white/80" : "text-text-muted"}`}>
                  {sizeText(t.size)} · {LAYOUT_NAME[t.layout]}
                </span>
              </button>
            );
          })}
        </div>
        <Button variant="secondary" size="sm" icon={Plus} onClick={() => setDialog("new")}>
          New type
        </Button>
        <span className="flex-1" />
        {selected && (
          <>
            <Button variant="ghost" size="sm" icon={Pencil} onClick={() => setDialog("rename")}>
              Rename
            </Button>
            <Button variant="ghost" size="sm" icon={Archive} disabled={(types.data?.length ?? 0) < 2} tooltip={(types.data?.length ?? 0) < 2 ? "Keep at least one label type" : undefined} onClick={() => setDialog("archive")}>
              Archive
            </Button>
          </>
        )}
      </div>
      <Card className="flex gap-6">
        <div className="w-[280px] shrink-0">
          <LabelPreview result={preview.data} loading={preview.isFetching} padding={12} shrink showActualSizeToggle={false} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <h2 className="inline-flex items-center gap-2 t-h2 text-text">
            Default label
            {(types.data?.length ?? 0) > 1 && selected && (
              <span className="inline-flex h-6 items-center rounded-full bg-primary-subtle px-2.5 t-caption text-primary">{selected.name}</span>
            )}
          </h2>
          {def && (
            <>
              <p className="t-body text-text">
                {def.size.name} · {sizeText(def.size)}
              </p>
              <p className="t-body text-text-secondary">
                {def.spec.style.layout === "grid" || def.spec.style.layout === "bin"
                  ? `${LAYOUT_NAME[def.spec.style.layout]} layout`
                  : def.spec.fields.map((f) => fieldName(f.key, customLabels, def.spec.manual_fields)).join(" · ") || "—"}
              </p>
              <p className="t-small text-text-muted">
                Version {def.version} · published {formatDate(def.created_at)} by {def.created_by_name}
              </p>
              <div className="mt-2">
                <Button onClick={() => navigate(editPath)}>Edit default label</Button>
              </div>
            </>
          )}
        </div>
      </Card>

      <h2 className="mt-8 mb-4 t-h2 text-text">Custom labels for specific parts</h2>
      {configs.data && configs.data.overrides.length === 0 ? (
        <p className="t-body text-text-secondary">All parts use the default{(types.data?.length ?? 0) > 1 && selected ? ` ${selected.name}` : ""} label.</p>
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
                <Tr key={o.config_id} onClick={() => navigate(`/configure/part/${o.part_id}${isFirst || !selected ? "" : `?type=${selected.id}`}`)}>
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

      <TypeDialog
        open={dialog === "new" || dialog === "rename"}
        mode={dialog === "rename" ? "rename" : "new"}
        types={types.data ?? []}
        current={selected}
        onClose={() => setDialog(null)}
        onSaved={(t) => {
          refresh();
          setSelectedId(t.id);
          setDialog(null);
          toast.show(dialog === "rename" ? `Renamed to ${t.name}` : `Label type ${t.name} created`, "success");
        }}
      />
      <ConfirmDialog
        open={dialog === "archive"}
        title={`Archive ${selected?.name ?? ""}?`}
        body="It disappears from Configure and Print Labels. Labels already printed with it stay in History and can still be reprinted exactly."
        confirmLabel="Archive"
        danger
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          if (!selected) return;
          try {
            await api(`/label-types/${selected.id}/archive`, { method: "POST" });
            setSelectedId(null);
            refresh();
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : String(e));
          }
          setDialog(null);
        }}
      />
    </Page>
  );
}

/** New label type (starts as a copy of another type's design) or rename the selected one. */
function TypeDialog({ open, mode, types, current, onClose, onSaved }: {
  open: boolean;
  mode: "new" | "rename";
  types: LabelType[];
  current: LabelType | undefined;
  onClose: () => void;
  onSaved: (t: LabelType) => void;
}) {
  const [name, setName] = useState("");
  const [copyFrom, setCopyFrom] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedFor, setOpenedFor] = useState<string | null>(null);
  const key = open ? `${mode}:${current?.id ?? ""}` : null;
  if (key !== openedFor) {
    setOpenedFor(key);
    setName(mode === "rename" ? (current?.name ?? "") : "");
    setCopyFrom(current?.id ?? types[0]?.id ?? "");
    setError(null);
  }
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const t =
        mode === "rename" && current
          ? await api<LabelType>(`/label-types/${current.id}`, { method: "PATCH", body: { name } })
          : await api<LabelType>("/label-types", { body: { name, copy_from_type_id: copyFrom || null } });
      if (mode === "new") setCurrentLabelType(t.id);
      onSaved(t);
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.name ?? e.message) : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={mode === "rename" ? "Rename label type" : "New label type"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={busy} disabled={!name.trim()} onClick={save}>
            {mode === "rename" ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Name" htmlFor="type-name" error={error} helper={mode === "new" ? "For example Bin, Rack, Workstation, Kanban, Front, Back." : undefined}>
          <Input id="type-name" autoFocus maxLength={40} value={name} error={error} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && void save()} />
        </Field>
        {mode === "new" && (
          <Field label="Start from the design of" htmlFor="type-copy">
            <Select id="type-copy" value={copyFrom} options={types.map((t) => ({ value: t.id, label: `${t.name} (${sizeText(t.size)})` }))} onChange={(e) => setCopyFrom(e.target.value)} />
          </Field>
        )}
      </div>
    </Dialog>
  );
}
