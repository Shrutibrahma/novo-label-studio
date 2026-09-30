import { Eye, Printer as PrinterIcon } from "lucide-react";
import { Button, IconButton } from "../../components/Button";
import { Skeleton } from "../../components/Display";
import { Dialog } from "../../components/Overlay";
import { useDefaultPrinter } from "../../lib/queries";
import { printerBlockMessage } from "../../lib/status";
import { usePart, type PartListItem } from "../../lib/parts";
import { BatchPrint } from "./BatchPrint";
import { PreviewDialog } from "./PreviewDialog";
import { SinglePrint } from "./SinglePrint";

export type PrintLaunch = { mode: "preview"; parts: [PartListItem] } | { mode: "print"; parts: PartListItem[] };

/** Row actions on Print Labels: ghost Eye (tooltip "Preview") + primary small "Print" (12.4). */
export function PrintRowActions({ part, onLaunch }: { part: PartListItem; onLaunch: (l: PrintLaunch) => void }) {
  const { printer } = useDefaultPrinter();
  const blocked = printerBlockMessage(printer);
  return (
    <div className="flex items-center justify-end gap-1">
      <IconButton icon={Eye} label="Preview" onClick={() => onLaunch({ mode: "preview", parts: [part] })} />
      <Button size="sm" icon={PrinterIcon} tooltip={blocked} disabled={!!blocked} onClick={() => onLaunch({ mode: "print", parts: [part] })}>
        Print
      </Button>
    </div>
  );
}

function SingleHost({ part, onClose }: { part: PartListItem; onClose: () => void }) {
  const detail = usePart(part.id);
  return detail.data ? <SinglePrint part={detail.data} onClose={onClose} /> : <Skeleton className="h-[460px] w-full" />;
}

export function PrintLaunchHost({ launch, onClose, onSwitch }: { launch: PrintLaunch | null; onClose: () => void; onSwitch: (l: PrintLaunch) => void }) {
  if (!launch) return null;
  if (launch.mode === "preview") {
    return <PreviewDialog part={launch.parts[0]} onClose={onClose} onPrint={() => onSwitch({ mode: "print", parts: launch.parts })} />;
  }
  const single = launch.parts.length === 1 ? launch.parts[0] : null;
  return (
    <Dialog open onClose={onClose} width={960} title="Print">
      {single ? <SingleHost part={single} onClose={onClose} /> : <BatchPrint parts={launch.parts} onClose={onClose} />}
    </Dialog>
  );
}
