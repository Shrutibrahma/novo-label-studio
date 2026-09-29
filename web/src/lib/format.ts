/** Formatters. Section 5 invariant 5: local time, format `Sep 29, 2026, 9:34 AM`. */

const dateTime = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const dateOnly = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateTime.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateOnly.format(new Date(iso));
}

const relative = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });

export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return relative.format(Math.round(diff), "second");
  if (abs < 45 * 60) return relative.format(Math.round(diff / 60), "minute");
  if (abs < 22 * 3600) return relative.format(Math.round(diff / 3600), "hour");
  if (abs < 26 * 86400) return relative.format(Math.round(diff / 86400), "day");
  if (abs < 320 * 86400) return relative.format(Math.round(diff / (30 * 86400)), "month");
  return relative.format(Math.round(diff / (365 * 86400)), "year");
}

/** 4.000 -> "4", 2.500 -> "2.5". */
export function inches(n: number): string {
  return String(Number(n.toFixed(2)));
}

/** Label size as shown in tables: "4 × 2 in" (section 12.4). */
export function sizeText(size: { width_in: number; height_in: number } | null | undefined): string {
  if (!size) return "—";
  return `${inches(size.width_in)} × ${inches(size.height_in)} in`;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

export function thousands(n: number): string {
  return n.toLocaleString("en-US");
}
