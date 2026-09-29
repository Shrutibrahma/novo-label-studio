export interface ImportBatch {
  id: string;
  file_name: string;
  status: "parsing" | "needs_sheet" | "mapping" | "validating" | "staged" | "committed" | "discarded" | "failed";
  error: { code: string; message: string } | null;
  sheet_name: string | null;
  sheets: { name: string; rows: number }[];
  columns: { header: string; samples: string[] }[];
  mapping: Record<string, string | null>;
  saved_mapping_name: string | null;
  save_as_default: string;
  progress_done: number;
  progress_total: number;
  counts: { total_rows: number; new: number; updated: number; unchanged: number; invalid: number; missing: number };
  accepted_to_import: number;
  accepted_missing: number;
  created_at: string;
  committed_at: string | null;
}

export type RowAction = "new" | "update" | "unchanged" | "invalid" | "missing";

export interface ImportRow {
  id: number;
  source_row: number | null;
  action: RowAction;
  part_id: string | null;
  data: Record<string, string | number>;
  diff: Record<string, [unknown, unknown]> | null;
  errors: { field: string; msg: string }[] | null;
  accepted: boolean;
}

export interface CommitResult {
  new: number;
  updated: number;
  marked_inactive: number;
  skipped: number;
  batch: ImportBatch;
}
