import type { LabelSpec, ManualField, SizeBrief, SpecField } from "../../lib/parts";

export interface ConfigOut {
  id: string;
  config_key: string;
  version: number;
  scope: "default" | "part";
  part_id: string | null;
  size: SizeBrief;
  spec: LabelSpec;
  qr_mode: "none" | "part" | "serial";
  serial_mode: "none" | "required";
  is_current: boolean;
  created_at: string;
  created_by_name: string;
  next_version: number;
}

export interface OverrideRow {
  config_id: string;
  part_id: string;
  part_number: string;
  label_name: string | null;
  size: SizeBrief;
  version: number;
  created_at: string;
  created_by_name: string;
}

export interface Draft {
  label_size_id: string;
  spec: LabelSpec;
  qr_mode: "none" | "part" | "serial";
  serial_mode: "none" | "required";
}

export const ROLE_LABEL: Record<SpecField["role"], string> = { primary: "Main line", secondary: "Second line", detail: "Detail" };
export const ROLE_LIMIT: Record<SpecField["role"], number> = { primary: 1, secondary: 2, detail: 6 };

export const CORE_FIELD_LABELS: Record<string, string> = {
  label_name: "Label name",
  part_number: "Part number",
  part_name: "Part name",
  description: "Description",
  revision: "Revision",
  serial: "Serial number",
  print_date: "Print date",
};

export const PART_FIELD_KEYS = ["label_name", "part_number", "part_name", "description", "revision"] as const;
export const GENERATED_KEYS = ["serial", "print_date"] as const;

export function fieldName(key: string, custom: Record<string, string>, manual: ManualField[]): string {
  if (key.startsWith("manual.")) return manual.find((m) => m.key === key.slice(7))?.label ?? key.slice(7);
  return CORE_FIELD_LABELS[key] ?? custom[key] ?? key;
}

/** Role for a newly added field: main line if there is none, else a detail line, else a second line. */
export function defaultRole(fields: SpecField[]): SpecField["role"] | null {
  const count = (r: SpecField["role"]) => fields.filter((f) => f.role === r).length;
  if (count("primary") === 0) return "primary";
  if (count("detail") < ROLE_LIMIT.detail) return "detail";
  if (count("secondary") < ROLE_LIMIT.secondary) return "secondary";
  return null;
}

export function toDraft(c: ConfigOut): Draft {
  return { label_size_id: c.size.id, spec: structuredClone(c.spec), qr_mode: c.qr_mode, serial_mode: c.serial_mode };
}
