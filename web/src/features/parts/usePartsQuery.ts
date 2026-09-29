import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../../lib/api";
import type { PartList } from "../../lib/parts";

export interface PartsParams {
  q?: string;
  status?: "active" | "inactive" | "archived" | "all";
  label_state?: "current" | "out_of_date" | "never_printed";
  printed_within_days?: number;
}

function toSearch(params: PartsParams, cursor: string | null): string {
  const s = new URLSearchParams({ limit: "50" });
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") s.set(k, String(v));
  if (cursor) s.set("cursor", cursor);
  return s.toString();
}

/** 50 rows per page, infinite scroll (12.4). */
export function usePartsQuery(params: PartsParams) {
  return useInfiniteQuery({
    queryKey: ["parts", params],
    queryFn: ({ pageParam, signal }) => api<PartList>(`/parts?${toSearch(params, pageParam)}`, { signal }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

/** Calls `onVisible` when the sentinel scrolls into view. */
export function useSentinel(onVisible: () => void, enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const cb = useRef(onVisible);
  cb.current = onVisible;
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && cb.current(), { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [enabled]);
  return ref;
}
