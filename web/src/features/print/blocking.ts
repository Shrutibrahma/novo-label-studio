import { isServerReachable, SERVER_UNREACHABLE } from "../../lib/api";
import { printerBlockMessage } from "../../lib/status";
import type { Printer } from "../../lib/types";
import type { PreviewResult } from "../../components/LabelPreview";

export interface Block {
  blocked: boolean;
  /** The first matching 14.2 message, shown as the disabled Print button's tooltip (null while loading). */
  reason: string | null;
}

/** 14.1: why printing is disabled, checked in the order of the 14.2 table. */
export function printBlock(opts: {
  previews: (PreviewResult | undefined)[];
  printer: Printer | undefined;
  sizeMismatch: string | null; // size name to load, when loaded size ≠ label size and not yet confirmed
}): Block {
  if (!isServerReachable()) return { blocked: true, reason: SERVER_UNREACHABLE };
  for (const p of opts.previews) {
    if (!p) return { blocked: true, reason: null };
    const w = p.warnings[0];
    if (w) return { blocked: true, reason: w.message };
  }
  const printer = printerBlockMessage(opts.printer);
  if (printer) return { blocked: true, reason: printer };
  if (opts.sizeMismatch) return { blocked: true, reason: `Load ${opts.sizeMismatch} labels in the printer, then confirm.` };
  return { blocked: false, reason: null };
}
