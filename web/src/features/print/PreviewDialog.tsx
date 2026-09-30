import { Button } from "../../components/Button";
import { Banner, Mono } from "../../components/Display";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { Dialog } from "../../components/Overlay";
import { sizeText } from "../../lib/format";
import { usePart, type PartListItem } from "../../lib/parts";

const QR_WORD = { none: "None", part: "Part", serial: "Serial" } as const;

/** 12.5 Preview dialog: read-only, width 720. */
export function PreviewDialog({ part, onClose, onPrint }: { part: PartListItem; onClose: () => void; onPrint: () => void }) {
  const detail = usePart(part.id);
  const preview = usePreview({ part_id: part.id }, 0);
  const cfg = detail.data?.config;
  const warnings = preview.data?.warnings ?? [];
  return (
    <Dialog
      open
      onClose={onClose}
      width={720}
      title={part.label_name ?? part.part_name}
      subtitle={<Mono>{part.part_number}</Mono>}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button onClick={onPrint}>Print</Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <LabelPreview result={preview.data} loading={preview.isFetching} maxHeight={420} />
        {cfg && (
          <div className="flex flex-wrap items-center gap-3 t-small text-text-secondary">
            <span>
              {cfg.size.name} · {sizeText(cfg.size)}
            </span>
            <span>·</span>
            <span>Config v{cfg.version}</span>
            <span>·</span>
            <span>QR: {QR_WORD[cfg.qr_mode]}</span>
            {cfg.serial_mode === "required" && (
              <span className="inline-flex h-[22px] items-center rounded-full bg-info-bg px-2 t-caption text-info">Serial assigned at print</span>
            )}
          </div>
        )}
        {warnings.length > 0 && (
          <Banner tone="warning">
            {warnings.map((w, i) => (
              <p key={i}>{w.message}</p>
            ))}
          </Banner>
        )}
      </div>
    </Dialog>
  );
}
