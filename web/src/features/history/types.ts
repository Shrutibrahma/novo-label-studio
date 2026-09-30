import type { JobStatus } from "../../lib/status";

export interface HistoryRow {
  id: string;
  created_at: string;
  part_id: string;
  part_number: string;
  label_name: string | null;
  part_name: string | null;
  serial: string | null;
  box: string | null;
  size: string;
  size_name: string;
  copies: number;
  by: string;
  status: JobStatus;
  kind: "print" | "reprint";
  reprint_of: string | null;
}

export interface SerialInfo {
  value: string;
  status: "allocated" | "printed" | "unconfirmed" | "voided";
  void_reason: string | null;
  allocated_at: string;
  status_changed_at: string;
}

export interface LabelDetail {
  row: HistoryRow;
  bitmap_png_base64: string;
  width_dots: number;
  height_dots: number;
  dpi: number;
  printer_dpi: number;
  config_version: number;
  qr_payload: string | null;
  fields: { key: string; label: string; value: string }[];
  job: { id: string; printer: string; status: JobStatus; error: string | null; reprint_reason: string | null; timeline: { status: string; at: string }[] };
  reprints: HistoryRow[];
  serial: SerialInfo | null;
}

export const SERIAL_WORD: Record<SerialInfo["status"], string> = {
  allocated: "Allocated",
  printed: "Printed",
  unconfirmed: "Unconfirmed",
  voided: "Voided",
};

export const SERIAL_TONE = { allocated: "neutral", printed: "success", unconfirmed: "warning", voided: "danger" } as const;

export const REASONS = [
  { value: "damaged", label: "Damaged" },
  { value: "missing", label: "Missing" },
  { value: "print_issue", label: "Print issue" },
  { value: "other", label: "Other" },
] as const;
