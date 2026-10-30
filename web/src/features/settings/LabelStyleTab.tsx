import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { Banner, Card } from "../../components/Display";
import { Checkbox, Field, Input, SegmentedControl, Switch } from "../../components/Form";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { useLabelTypes, type LabelType } from "../../lib/labelTypes";
import type { PartList } from "../../lib/parts";
import { useSettings } from "../../lib/queries";
import type { HouseStyle } from "../../lib/types";
import { useSaveSettings } from "./GeneralTabs";

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
            <Checkbox
              label="Label type name in the title band (LABEL, KANBAN, ...)"
              checked={draft.title_in_band}
              disabled={!draft.title_band}
              onChange={(title_in_band) => set({ title_in_band })}
            />
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
      <CompanyCard />
      <QrCard />
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
  // Quick labels have no part: their print-time fields show their own names as sample values.
  const quickSample = useQuery({
    queryKey: ["config", "quick-sample", type.default_config_id],
    queryFn: () => api<{ spec: { manual_fields: { key: string; label: string; type: string }[] } }>(`/configs/default?type_id=${type.id}`),
    enabled: type.kind === "quick",
    select: (c) => Object.fromEntries(c.spec.manual_fields.filter((m) => m.type !== "box_sequence").map((m) => [m.key, m.label])),
  });
  const preview = usePreview(
    type.kind === "quick"
      ? quickSample.data ? { config_id: type.default_config_id, label_type_id: type.id, house_style: style, manual_values: quickSample.data } : null
      : { part_id: partId, config_id: type.default_config_id, label_type_id: type.id, house_style: style },
    250,
  );
  return (
    <figure className="flex flex-col gap-2 rounded-[12px] border border-border bg-surface p-3 shadow-card">
      <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={260} showActualSizeToggle={false} padding={12} />
      <figcaption className="t-small text-text-secondary">
        {type.name} · {type.size.name}
      </figcaption>
    </figure>
  );
}

/** The company name printed in the title band (the same setting as Settings → General). */
function CompanyCard() {
  const qc = useQueryClient();
  const settings = useSettings();
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => setName(settings.data?.company_name ?? ""), [settings.data?.company_name]);
  const save = useSaveSettings(setErrors);
  return (
    <Card className="w-full max-w-[720px]">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ company_name: name.trim() }, { onSuccess: () => void qc.invalidateQueries({ queryKey: ["preview"] }) });
        }}
      >
        <Field label="Company name on the label" htmlFor="ls-company" error={errors.company_name} helper="Printed in the title band, in capitals.">
          <Input id="ls-company" maxLength={120} value={name} error={errors.company_name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div>
          <Button type="submit" loading={save.isPending} disabled={!name.trim() || name.trim() === settings.data?.company_name}>
            Save
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** What a label's QR code does when someone scans it. */
function QrCard() {
  const settings = useSettings();
  const qr = settings.data?.qr;
  const [base, setBase] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => setBase(qr?.link_base ?? ""), [qr?.link_base]);
  const save = useSaveSettings(setErrors);
  if (!qr) return null;
  const localhost = /\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(qr.link_base);
  return (
    <Card className="w-full max-w-[720px]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <span className="t-h3 text-text">QR codes</span>
          <span className="t-small text-text-muted">Scanning a label with a phone opens the part's page: its details, picture and serial.</span>
        </div>
        <Switch label="QR codes open the part page" checked={qr.link} onChange={(link) => save.mutate({ qr_link: link })} />
        {qr.link && (
          <>
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                save.mutate({ qr_link_base: base });
              }}
            >
              <Field
                label="Address phones open"
                htmlFor="qr-base"
                error={errors.qr_link_base}
                helper="This computer's address on your network (or your server's), e.g. https://192.168.1.20:8443."
              >
                <Input id="qr-base" maxLength={200} value={base} error={errors.qr_link_base} onChange={(e) => setBase(e.target.value)} />
              </Field>
              <div>
                <Button type="submit" variant="secondary" loading={save.isPending} disabled={!base.trim() || base.trim() === qr.link_base}>
                  Save address
                </Button>
              </div>
            </form>
            {localhost && (
              <Banner tone="warning">"localhost" only works on this computer. Phones need this computer's network address instead.</Banner>
            )}
            <Checkbox
              label="Anyone who scans can open it (no sign-in)"
              checked={qr.scan_public}
              onChange={(scan_public) => save.mutate({ scan_public })}
            />
            <p className="t-small text-text-muted">
              Labels already printed keep the QR code they were printed with. Off: the QR code holds the part number as text.
            </p>
          </>
        )}
      </div>
    </Card>
  );
}
