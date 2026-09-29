/** Status words and their colours (section 11.1 status mapping, 8.3 UI status words). */

import type { PrinterStatus } from "./types";

export type Tone = "success" | "info" | "warning" | "danger" | "neutral" | "archived";

export const PRINTER_STATUS_WORD: Record<PrinterStatus, string> = {
  ready: "Ready",
  printing: "Printing…",
  offline: "Offline",
  out_of_media: "Out of labels",
  head_open: "Head open",
  paused: "Paused",
  error: "Error",
  unknown: "Unknown",
};

export const PRINTER_STATUS_TONE: Record<PrinterStatus, Tone> = {
  ready: "success",
  printing: "info",
  offline: "danger",
  out_of_media: "danger",
  head_open: "danger",
  paused: "danger",
  error: "danger",
  unknown: "neutral",
};

/** Section 14.1 blocking statuses and their 14.2 messages. */
export const PRINTER_BLOCK_MESSAGE: Partial<Record<PrinterStatus, string>> = {
  offline: "The printer is offline. Check the USB cable and that the printer is on.",
  out_of_media: "The printer is out of labels.",
  head_open: "The printer cover is open.",
  paused: "The printer is paused. Press the pause button on the printer.",
  error: "The printer reported an error. Check it and try again.",
};

export const AGENT_UNREACHABLE = "The print agent on the laptop isn't responding.";
export const AGENT_STALE_MS = 30_000;

export type JobStatus = "created" | "rendered" | "queued" | "sending" | "sent" | "confirmed" | "failed" | "cancelled";

export const JOB_STATUS_WORD: Record<JobStatus, string> = {
  created: "Waiting for printer",
  rendered: "Waiting for printer",
  queued: "Waiting for printer",
  sending: "Printing…",
  sent: "Sent to printer",
  confirmed: "Printed",
  failed: "Print failed",
  cancelled: "Cancelled",
};

export const JOB_STATUS_TONE: Record<JobStatus, Tone> = {
  created: "info",
  rendered: "info",
  queued: "info",
  sending: "info",
  sent: "info",
  confirmed: "success",
  failed: "danger",
  cancelled: "neutral",
};

export type LabelState = "current" | "out_of_date" | "never_printed";

export const LABEL_STATE_WORD: Record<LabelState, string> = {
  current: "Current",
  out_of_date: "Out of date",
  never_printed: "Never printed",
};

export const LABEL_STATE_TONE: Record<LabelState, Tone> = {
  current: "success",
  out_of_date: "warning",
  never_printed: "neutral",
};

export type PartStatus = "active" | "inactive" | "archived";

export const PART_STATUS_WORD: Record<PartStatus, string> = {
  active: "Active",
  inactive: "Inactive",
  archived: "Archived",
};

export const PART_STATUS_TONE: Record<PartStatus, Tone> = {
  active: "success",
  inactive: "neutral",
  archived: "archived",
};

/**
 * Effective printer status: the API already reports "offline" when the agent is stale, but the UI also
 * checks agent_last_seen_at against the local clock so the dot turns red without waiting for a refetch.
 */
export function effectivePrinterStatus(p: { status: PrinterStatus; agent_last_seen_at: string | null }): PrinterStatus {
  if (!p.agent_last_seen_at || Date.now() - new Date(p.agent_last_seen_at).getTime() > AGENT_STALE_MS) {
    return "offline";
  }
  return p.status;
}

/** First matching 14.1 message, or null when the printer allows printing. */
export function printerBlockMessage(
  p: { reported_status: PrinterStatus; agent_last_seen_at: string | null } | undefined,
): string | null {
  if (!p) return AGENT_UNREACHABLE;
  const reported = PRINTER_BLOCK_MESSAGE[p.reported_status];
  if (reported) return reported;
  if (!p.agent_last_seen_at || Date.now() - new Date(p.agent_last_seen_at).getTime() > AGENT_STALE_MS) {
    return AGENT_UNREACHABLE;
  }
  return null;
}
