import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useBlocker, useNavigate, useParams } from "react-router";
import { usePage } from "../../app/page";
import { Button } from "../../components/Button";
import { Banner } from "../../components/Display";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { ConfirmDialog } from "../../components/Overlay";
import { api, ApiError } from "../../lib/api";
import { qk, useSettings, useSizes } from "../../lib/queries";
import { useCustomFields, usePart, type LabelStyle } from "../../lib/parts";
import { FieldsSection, ManualSection, QrSection, Section, SizeSection, StyleSection } from "./EditorSections";
import { PartPicker, type PickedPart } from "./PartPicker";
import { useFirstActivePart } from "./ConfigureListPage";
import { toDraft, type ConfigOut, type Draft } from "./types";

/** A required print-time value can't exist yet while editing, so it doesn't make the draft "not fit". */
const EDITOR_IGNORED = new Set(["REQUIRED_VALUE_MISSING"]);

/** 12.11 editor: /configure/default and /configure/part/:id. */
export function ConfigEditorPage() {
  usePage("Configure");
  const { partId } = useParams();
  const scope: "default" | "part" = partId ? "part" : "default";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const sizes = useSizes();
  const custom = useCustomFields();
  const settings = useSettings();
  const part = usePart(partId ?? null);
  const first = useFirstActivePart();

  const base = useQuery({
    queryKey: qk.config(partId ? `part-${partId}` : "default"),
    queryFn: () => api<ConfigOut>(partId ? `/parts/${partId}/config` : "/configs/default"),
    staleTime: 0,
  });

  const [draft, setDraft] = useState<Draft | null>(null);
  const [initial, setInitial] = useState<string>("");
  const [previewPart, setPreviewPart] = useState<PickedPart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(false);
  // Read by the leave guard: set synchronously on publish so the redirect that follows is never blocked.
  const allowLeave = useRef(false);

  // "Customize for this part": the editor starts from the part's current effective config (the default if none).
  useEffect(() => {
    if (base.data && draft === null) {
      const d = toDraft(base.data);
      setDraft(d);
      setInitial(JSON.stringify(d));
    }
  }, [base.data, draft]);

  useEffect(() => {
    if (previewPart) return;
    if (part.data) {
      const p = part.data;
      setPreviewPart({ id: p.id, part_number: p.part_number, part_name: p.part_name, label_name: p.label_name });
    } else if (!partId && first.data) setPreviewPart(first.data);
  }, [part.data, first.data, partId, previewPart]);

  useEffect(() => {
    if (published) navigate("/configure");
  }, [published, navigate]);

  const dirty = draft !== null && JSON.stringify(draft) !== initial;
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !allowLeave.current && currentLocation.pathname !== nextLocation.pathname);

  const preview = usePreview(draft && previewPart ? { part_id: previewPart.id, config: draft } : null, 250);
  const shownWarnings = useMemo(() => (preview.data?.warnings ?? []).filter((w) => !EDITOR_IGNORED.has(w.code)), [preview.data]);
  const fits = preview.data !== undefined && shownWarnings.length === 0;

  if (!draft || !base.data) return <div className="p-8">{base.error && <Banner tone="danger">{base.error.message}</Banner>}</div>;

  const setStyle = (s: Partial<LabelStyle>) => setDraft({ ...draft, spec: { ...draft.spec, style: { ...draft.spec.style, ...s } } });
  const nextVersion = base.data.next_version;

  const publish = async () => {
    setPublishing(true);
    setError(null);
    try {
      await api<ConfigOut>("/configs", {
        body: { scope, part_id: partId ?? null, ...draft, base_config_id: base.data.id },
      });
      allowLeave.current = true;
      setPublished(true);
      void qc.invalidateQueries({ queryKey: qk.configs });
      void qc.invalidateQueries({ queryKey: ["config"] });
      void qc.invalidateQueries({ queryKey: ["parts"] });
      if (partId) void qc.invalidateQueries({ queryKey: qk.part(partId) });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPublishing(false);
    }
  };
  const title = partId ? `Custom label for ${part.data?.part_number ?? ""}` : "Default label";
  return (
    <div className="flex max-w-[1440px] flex-col">
      <div className="flex items-center gap-3 border-b border-border bg-surface px-8 py-4">
        <h2 className="flex-1 t-h2 text-text">{title}</h2>
        <Button variant="ghost" onClick={() => navigate("/configure")}>
          Cancel
        </Button>
        <Button loading={publishing} disabled={!dirty || !fits} onClick={publish}>
          Publish version {nextVersion}
        </Button>
      </div>
      {error && (
        <div className="px-8 pt-4">
          <Banner tone="danger">{error}</Banner>
        </div>
      )}
      <div className="flex items-start">
        <div className="w-[440px] shrink-0 overflow-y-auto border-r border-border bg-surface" style={{ maxHeight: "calc(100vh - 56px - 69px)" }}>
          <Section title="Size">
            <SizeSection sizes={(sizes.data ?? []).filter((s) => s.active)} value={draft.label_size_id} onChange={(id) => setDraft({ ...draft, label_size_id: id })} />
          </Section>
          <Section title="What's on the label">
            <FieldsSection draft={draft} custom={custom.data ?? []} onFields={(fields) => setDraft({ ...draft, spec: { ...draft.spec, fields } })} />
          </Section>
          <Section title="Print-time fields">
            <ManualSection draft={draft} onChange={(manual_fields, fields) => setDraft({ ...draft, spec: { ...draft.spec, manual_fields, fields } })} />
          </Section>
          <Section title="QR code & serial">
            <QrSection
              draft={draft}
              onChange={(patch, style) => setDraft({ ...draft, ...patch, spec: style ? { ...draft.spec, style: { ...draft.spec.style, ...style } } : draft.spec })}
            />
          </Section>
          <Section title="Style">
            <StyleSection style={draft.spec.style} fonts={settings.data?.fonts_allowed ?? ["inter", "roboto_condensed", "atkinson"]} onChange={setStyle} />
          </Section>
        </div>
        <div className="sticky top-14 flex min-w-0 flex-1 flex-col gap-4 p-8">
          <PartPicker value={previewPart} onChange={setPreviewPart} />
          <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={520} />
          {preview.error ? (
            <Banner tone="danger">{preview.error instanceof ApiError ? preview.error.message : String(preview.error)}</Banner>
          ) : fits ? (
            <p className="inline-flex items-center gap-2 t-body text-success">
              <CircleCheck size={16} strokeWidth={1.75} aria-hidden />
              Fits
            </p>
          ) : shownWarnings.length ? (
            <div role="alert" className="flex flex-col gap-1 rounded-[8px] bg-warning-bg px-4 py-3">
              {shownWarnings.map((w, i) => (
                <p key={i} className="inline-flex items-start gap-2 t-body text-warning">
                  <TriangleAlert size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden />
                  {w.message}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title="Discard your changes?"
        cancelLabel="Keep editing"
        confirmLabel="Discard"
        danger
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      />
    </div>
  );
}
