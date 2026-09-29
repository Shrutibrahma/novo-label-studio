import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { qk } from "./queries";
import type { LabelState, PartStatus } from "./status";

export interface SizeBrief {
  id: string;
  name: string;
  width_in: number;
  height_in: number;
}

export interface PartListItem {
  id: string;
  part_number: string;
  part_name: string;
  description: string | null;
  revision: string | null;
  status: PartStatus;
  label_name: string | null;
  has_image: boolean;
  image_version: string | null;
  label_state: LabelState;
  last_printed_at: string | null;
  size: SizeBrief | null;
  config_version: number | null;
  has_override: boolean;
  updated_at: string;
  score: number | null;
}

export interface PartList {
  items: PartListItem[];
  next_cursor: string | null;
}

export interface Alias {
  id: string;
  alias: string;
  is_label_name: boolean;
  created_at: string;
}

export interface ConfigBrief {
  id: string;
  version: number;
  scope: "default" | "part";
  size: SizeBrief;
  qr_mode: "none" | "part" | "serial";
  serial_mode: "none" | "required";
  spec: LabelSpec;
  created_at: string;
  created_by_name: string;
}

export interface PartDetail {
  id: string;
  part_number: string;
  part_name: string;
  description: string | null;
  revision: string | null;
  custom_data: Record<string, string | number>;
  status: PartStatus;
  source: string;
  label_name: string | null;
  has_image: boolean;
  image_version: string | null;
  aliases: Alias[];
  config: ConfigBrief;
  has_override: boolean;
  label_state: LabelState;
  last_printed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type FieldType = "text" | "number" | "date" | "choice";

export interface CustomField {
  key: string;
  label: string;
  data_type: FieldType;
  choices: string[] | null;
  required: boolean;
  searchable: boolean;
  printable: boolean;
  sort_order: number;
}

export type Role3 = "primary" | "secondary" | "detail";

export interface SpecField {
  key: string;
  role: Role3;
  uppercase: boolean;
  caption: string | null;
}

export type ManualField =
  | { key: string; label: string; type: "text"; required: boolean; max_length: number }
  | { key: string; label: string; type: "number"; required: boolean; min: number | null; max: number | null; integer: boolean }
  | { key: string; label: string; type: "choice"; required: boolean; choices: string[] }
  | { key: string; label: string; type: "box_sequence"; required: boolean; noun: string };

export interface LabelStyle {
  font: "inter" | "roboto_condensed" | "atkinson";
  primary_weight: "regular" | "bold" | "extra_bold";
  alignment: "left" | "center";
  emphasis: "small" | "medium" | "large";
  spacing: "compact" | "standard" | "spacious";
  qr_position: "left" | "right";
}

export interface LabelSpec {
  fields: SpecField[];
  manual_fields: ManualField[];
  style: LabelStyle;
}

export function partImageUrl(p: { id: string; image_version: string | null }): string | null {
  return p.image_version ? `/api/v1/parts/${p.id}/image?v=${p.image_version}` : null;
}

export function usePart(id: string | null) {
  return useQuery({
    queryKey: qk.part(id ?? ""),
    queryFn: () => api<PartDetail>(`/parts/${id}`),
    enabled: !!id,
  });
}

export function useCustomFields() {
  return useQuery({ queryKey: qk.customFields, queryFn: () => api<CustomField[]>("/custom-fields"), staleTime: 30_000 });
}

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** The line shown in bold in part tables: label name, else part name (12.4). */
export function displayName(p: { label_name: string | null; part_name: string }): string {
  return p.label_name ?? p.part_name;
}
