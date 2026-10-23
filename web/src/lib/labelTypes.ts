import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { api } from "./api";
import type { PartDetail, SizeBrief } from "./parts";
import { qk } from "./queries";

/** A saved label type (Label, Bin, Rack, Workstation, Kanban, ...) with its current default design. */
export interface LabelType {
  id: string;
  name: string;
  sort_order: number;
  size: SizeBrief;
  layout: "lines" | "grid" | "bin";
  version: number;
  default_config_id: string;
  override_count: number;
  created_at: string;
}

export const labelTypesKey = ["label-types"] as const;

export function useLabelTypes() {
  return useQuery({ queryKey: labelTypesKey, queryFn: () => api<LabelType[]>("/label-types"), staleTime: 30_000 });
}

export const LAYOUT_NAME: Record<LabelType["layout"], string> = { lines: "Lines", grid: "Rows & boxes", bin: "Bin card" };

// The type chosen on Print Labels, remembered per browser (a convenience; the server falls back to the first type).
const STORAGE_KEY = "nsl.labelType";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setCurrentLabelType(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // storage unavailable (private window): the choice lasts for this page only
    memory = id;
  }
  listeners.forEach((l) => l());
}

let memory: string | null = null;

/** The label type to print with: the remembered one if it still exists, else the first type. */
export function useCurrentLabelType(): LabelType | undefined {
  const types = useLabelTypes();
  const stored = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => read() ?? memory,
  );
  const list = types.data ?? [];
  return list.find((t) => t.id === stored) ?? list[0];
}

/** A part with its effective design for a label type (the first type when none is given). */
export function usePartForType(partId: string, typeId: string | undefined) {
  return useQuery({
    queryKey: [...qk.part(partId), typeId ?? "first"],
    queryFn: () => api<PartDetail>(`/parts/${partId}${typeId ? `?type_id=${typeId}` : ""}`),
  });
}
