import { formatDate } from "../../lib/format";
import type { PartDetail } from "../../lib/parts";

/** 12.8 "Label" tab: effective config and last print. The preview and editor links arrive with M4. */
export function PartLabelTab({ part }: { part: PartDetail }) {
  return (
    <div className="flex flex-col gap-3 p-6">
      <p className="t-body-strong text-text">{part.has_override ? `Custom label for this part · v${part.config.version}` : "Uses the default label"}</p>
      <p className="t-body text-text-secondary">{part.last_printed_at ? `Last printed ${formatDate(part.last_printed_at)}` : "Never printed"}</p>
    </div>
  );
}
