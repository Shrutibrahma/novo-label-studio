import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner, Card, Mono } from "../../components/Display";
import { Field, Input, SegmentedControl, Select } from "../../components/Form";
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
  const quick = selected?.kind === "quick";
  const preview = usePreview(
    def && quick ? { config_id: def.id, label_type_id: selected?.id } : def && first.data ? { part_id: first.data.id, config_id: def.id, label_type_id: selected?.id } : null,
    0,
  );
  const customLabels = Object.fromEntries((custom.data ?? []).map((f) => [f.key, f.label]));

  return (
    <Page>
      {configs.error && <Banner tone="danger">{configs.error.message}</Banner>}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="mr-1 t-body-strong text-text">Label types</span>
        <div role="tablist" aria-label="Label types" className="flex flex-wrap items-center gap-1.5">
          {[...(types.data ?? []).filter((t) => t.kind === "part"), ...(types.data ?? []).filter((t) => t.kind === "quick")].map((t, i, all) => {
            const on = t.id === selected?.id;
            const firstQuick = t.kind === "quick" && all[i - 1]?.kind !== "quick";
            return (
              <span key={t.id} className="contents">
              {firstQuick && <span className="ml-3 mr-1 t-body-strong text-text">Quick labels</span>}
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
              </span>
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
          <h2 className="t-h2 text-text">{(types.data?.length ?? 0) > 1 && selected ? `${selected.name} label` : "Default label"}</h2>
          <p className="t-small text-text-muted">{quick ? "Printed without a part, from Print Labels → Quick label." : "Used for every part unless a part has its own version (below)."}</p>
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

      {!quick && (<>
      <h2 className="mt-8 mb-4 t-h2 text-text">Parts with their own version</h2>
      {configs.data && configs.data.overrides.length === 0 ? (
        <p className="t-body text-text-secondary">No part has its own version yet. Every part prints with the design above.</p>
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
      </>)}

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

interface Preset {
  key: string;
  name: string;
  size_name: string;
  kind: "part" | "quick";
}

/** New label type (from an industrial preset, or a copy of another type's design) or rename the selected one. */
function TypeDialog({ open, mode, types, current, onClose, onSaved }: {
  open: boolean;
  mode: "new" | "rename";
  types: LabelType[];
  current: LabelType | undefined;
  onClose: () => void;
  onSaved: (t: LabelType) => void;
}) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<"part" | "quick">("part");
  const [copyFrom, setCopyFrom] = useState("");
  const presets = useQuery({ queryKey: ["label-type-presets"], queryFn: () => api<Preset[]>("/label-types/presets"), enabled: open && mode === "new", staleTime: Infinity });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedFor, setOpenedFor] = useState<string | null>(null);
  const key = open ? `${mode}:${current?.id ?? ""}` : null;
  if (key !== openedFor) {
    setOpenedFor(key);
    setName(mode === "rename" ? (current?.name ?? "") : "");
    setTitle(mode === "rename" ? (current?.title ?? "") : "");
    setKind("part");
    setCopyFrom(current?.id ?? types[0]?.id ?? "");
    setError(null);
  }
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const t =
        mode === "rename" && current
          ? await api<LabelType>(`/label-types/${current.id}`, { method: "PATCH", body: { name, title: title.trim() || null } })
          : await api<LabelType>("/label-types", {
              body: copyFrom.startsWith("preset:")
                ? { name, kind, title: title.trim() || null, preset: copyFrom.slice(7) }
                : { name, kind, title: title.trim() || null, copy_from_type_id: copyFrom || null },
            });
      if (mode === "new") setCurrentLabelType(t.id);
      onSaved(t);
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.name ?? e.fields.title ?? e.message) : String(e));
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
        <Field label="Title on label" htmlFor="type-title" helper="Printed in the black band at the top of the label.">
          <Input id="type-title" maxLength={24} placeholder={name.trim().toUpperCase()} className="uppercase" value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        {mode === "new" && (
          <div className="flex flex-col gap-1.5">
            <span className="t-body-strong text-text">Kind</span>
            <SegmentedControl
              ariaLabel="Kind"
              value={kind}
              onChange={(k: "part" | "quick") => {
                setKind(k);
                const firstOfKind = (presets.data ?? []).find((p) => p.kind === k);
                if (k === "quick" && firstOfKind && !name.trim()) setName(firstOfKind.name);
                setCopyFrom(k === "quick" ? (firstOfKind ? `preset:${firstOfKind.key}` : "") : (current?.kind === "part" ? current.id : types.find((t) => t.kind === "part")?.id ?? ""));
              }}
              options={[
                { value: "part", label: "Part label" },
                { value: "quick", label: "Quick label (no part)" },
              ]}
            />
            <span className="t-caption text-text-muted">Chosen once: a type can't change kind later.</span>
          </div>
        )}
        {mode === "new" && (
          <Field label="Start from" htmlFor="type-copy">
            <Select
              id="type-copy"
              value={copyFrom}
              options={[]}
              groups={[
                { label: "Presets", options: (presets.data ?? []).filter((p) => p.kind === kind).map((p) => ({ value: `preset:${p.key}`, label: `${p.name} (${p.size_name})` })) },
                { label: "Copy an existing type", options: types.filter((t) => t.kind === kind).map((t) => ({ value: t.id, label: `${t.name} (${sizeText(t.size)})` })) },
              ]}
              onChange={(e) => {
                const v = e.target.value;
                // A preset names the new type, unless a name was already typed.
                const p = (presets.data ?? []).find((x) => `preset:${x.key}` === v);
                if (p && !name.trim()) setName(p.name);
                setCopyFrom(v);
              }}
            />
          </Field>
        )}
      </div>
    </Dialog>
  );
}
