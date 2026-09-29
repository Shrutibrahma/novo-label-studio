import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { AppSettings, LabelSize, Printer, User } from "./types";

export const qk = {
  me: ["me"] as const,
  setupStatus: ["setup-status"] as const,
  printers: ["printers"] as const,
  settings: ["settings"] as const,
  sizes: ["sizes"] as const,
  users: ["users"] as const,
  parts: (params: Record<string, unknown>) => ["parts", params] as const,
  part: (id: string) => ["part", id] as const,
  customFields: ["custom-fields"] as const,
  configs: ["configs"] as const,
  config: (key: string) => ["config", key] as const,
  imports: (id: string) => ["import", id] as const,
  history: (params: Record<string, unknown>) => ["history", params] as const,
  label: (id: string) => ["label", id] as const,
};

export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => {
      try {
        return await api<User>("/auth/me", { quiet401: true });
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useSetupStatus() {
  return useQuery({
    queryKey: qk.setupStatus,
    queryFn: () => api<{ needs_setup: boolean }>("/setup/status"),
    staleTime: Infinity,
    retry: false,
  });
}

export function usePrinters(enabled = true) {
  return useQuery({
    queryKey: qk.printers,
    queryFn: () => api<Printer[]>("/printers"),
    refetchInterval: 5000,
    enabled,
  });
}

export function useDefaultPrinter(enabled = true) {
  const q = usePrinters(enabled);
  return { ...q, printer: q.data?.find((p) => p.is_default) ?? q.data?.[0] };
}

export function useSettings(enabled = true) {
  return useQuery({ queryKey: qk.settings, queryFn: () => api<AppSettings>("/settings"), enabled, staleTime: 30_000 });
}

export function useSizes() {
  return useQuery({ queryKey: qk.sizes, queryFn: () => api<LabelSize[]>("/sizes"), staleTime: 30_000 });
}
