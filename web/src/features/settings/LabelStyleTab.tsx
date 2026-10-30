import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Display";
import { Checkbox, SegmentedControl } from "../../components/Form";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { useLabelTypes, type LabelType } from "../../lib/labelTypes";
import type { PartList } from "../../lib/parts";
import { useSettings } from "../../lib/queries";
import type { HouseStyle } from "../../lib/types";

const FONT_NAMES: Record<HouseStyle["font"], string> = { inter: "Inter", roboto_condensed: "Roboto Condensed", atkinson: "Atkinson Hyperlegible" };
const labelStyleKey = ["label-style"] as const;

/** The part the family preview shows: the most recently printed part, or the first part alphabetically. */
function useSamplePart() {
  return useQuery({
    queryKey: ["label-style", "sample-part"],
    queryFn: async () => {
      const last = await api<{ items: { part_id: string }[] }>("/history?limit=1");
      if (last.items[0]) return last.items[0].part_id;
      const first = await api<PartList>("/parts?limit=1&status=active");
      return first.items[0]?.id ?? null;
    },
    staleTime: 60_000,
  });
}

/** 4.5 Settings → Label style: one font, frame, title band and footer for every label type. */
export function LabelStyleTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const settings = useSettings();
  const saved = useQuery({ queryKey: labelStyleKey, queryFn: () => api<HouseStyle>("/settings/label-style") });
  const [draft, setDraft] = useState<HouseStyle | null>(null);
  useEffect(() => {
    if (saved.data) setDraft(saved.data);
  }, [saved.data]);
  const save = useMutation({
    mutationFn: (body: HouseStyle) => api<HouseStyle>("/settings/label-style", { method: "PUT", body }),
    onSuccess: (s) => {
      qc.setQueryData(labelStyleKey, s);
      void qc.invalidateQueries({ queryKey: ["preview"] });
      toast.show("Label style saved.", "success");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });
  const types = useLabelTypes();
  const sample = useSamplePart();
  if (!draft) return null;
  const fonts = (settings.data?.fonts_allowed ?? Object.keys(FONT_NAMES)) as HouseStyle["font"][];
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.data);
  const set = (patch: Partial<HouseStyle>) => setDraft({ ...draft, ...patch });

  return (
    <div className="flex flex-col gap-6">
      <Card className="w-full max-w-[720px]">
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="t-body-strong text-text">Font</span>
            <SegmentedControl ariaLabel="Font" value={draft.font} onChange={(font) => set({ font })} options={fonts.map((f) => ({ value: f, label: FONT_NAMES[f] }))} />
          </div>
          <div className="flex flex-col gap-2.5">
            <Checkbox label="Frame around every label" checked={draft.frame} onChange={(frame) => set({ frame })} />
            <Checkbox label="Title band at the top" checked={draft.title_band} onChange={(title_band) => set({ title_band })} />
            <Checkbox label="Company name in the title band" checked={draft.company_in_band} disabled={!draft.title_band} onChange={(company_in_band) => set({ company_in_band })} />
            <Checkbox label="Footer with serial number and date" checked={draft.footer} onChange={(footer) => set({ footer })} />
            <p className="t-small text-text-muted">Labels under 1.5 in tall show the frame only.</p>
          </div>
          <div className="flex gap-2">
            <Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate(draft)}>
              Save
            </Button>
            <Button variant="secondary" disabled={!dirty} onClick={() => saved.data && setDraft(saved.data)}>
              Discard changes
            </Button>
          </div>
        </div>
      </Card>
      <div className="flex flex-col gap-3">
        <span className="t-caption text-text-muted uppercase">Every label type with this style</span>
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {sample.data && (types.data ?? []).map((t) => <FamilyPreview key={t.id} type={t} partId={sample.data!} style={draft} />)}
        </div>
        {sample.data === null && <p className="t-small text-text-muted">Add a part to see the labels here.</p>}
      </div>
    </div>
  );
}

function FamilyPreview({ type, partId, style }: { type: LabelType; partId: string; style: HouseStyle }) {
  const preview = usePreview({ part_id: partId, config_id: type.default_config_id, label_type_id: type.id, house_style: style }, 250);
  return (
    <figure className="flex flex-col gap-2 rounded-[12px] border border-border bg-surface p-3 shadow-card">
      <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={260} showActualSizeToggle={false} padding={12} />
      <figcaption className="t-small text-text-secondary">
        {type.name} · {type.size.name}
      </figcaption>
    </figure>
  );
}
