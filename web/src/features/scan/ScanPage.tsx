import { useQuery } from "@tanstack/react-query";
import { ImageOff, Package, ScanLine } from "lucide-react";
import { useEffect } from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router";
import { useDocumentTitle } from "../../app/page";
import { BrandLogo } from "../../app/Shell";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";

interface ScanResult {
  company: string;
  part_number: string;
  part_name: string;
  label_name: string | null;
  description: string | null;
  revision: string | null;
  status: string;
  fields: { label: string; value: string }[];
  aliases: string[];
  image_url: string | null;
  last_printed_at: string | null;
  serial: { value: string; status: string; printed_at: string | null } | null;
  part_id: string | null;
}

const SERIAL_WORD: Record<string, string> = { allocated: "Valid", printed: "Valid", voided: "Voided — don't use this label" };

/** The app is laid out for a 1280 px desktop (index.html); the scan page and its sign-in are for phones. */
export function useDeviceViewport(on = true) {
  useEffect(() => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
    if (!meta || !on) return;
    const before = meta.content;
    meta.content = "width=device-width, initial-scale=1";
    return () => {
      meta.content = before;
    };
  }, [on]);
}

/** What a label's QR code opens: /P/{part number}, or /S/{serial} on serial labels (capitals keep the QR code
 * small; the lookups ignore case). /p/{part number}?sn={serial} works too. Read-only, made for a phone. */
export function ScanPage() {
  useDeviceViewport();
  const location = useLocation();
  const [params] = useSearchParams();
  // The raw path keeps an encoded "/" inside a part number intact.
  const bySerial = /^\/s\//i.test(location.pathname);
  const partNumber = decodeURIComponent(location.pathname.replace(/^\/[ps]\//i, ""));
  const sn = bySerial ? partNumber : params.get("sn");
  const path = bySerial
    ? `/scan/serial/${encodeURIComponent(partNumber)}`
    : `/scan/${encodeURIComponent(partNumber)}${sn ? `?sn=${encodeURIComponent(sn)}` : ""}`;
  const query = useQuery({
    queryKey: ["scan", path],
    queryFn: () => api<ScanResult>(path, { quiet401: true }),
    retry: false,
  });
  const part = query.data;
  useDocumentTitle(part ? `${part.part_number} · ${part.part_name}` : partNumber);

  if (query.error instanceof ApiError && query.error.status === 401) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return (
    <div className="min-h-full bg-bg">
      <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3">
        <BrandLogo className="h-8" />
        {part?.company && <span className="ml-auto t-caption text-text-muted uppercase">{part.company}</span>}
      </header>
      <main className="mx-auto flex w-full max-w-[640px] flex-col gap-4 p-4">
        {query.isPending && <div className="skeleton h-64 w-full" />}
        {query.error && !(query.error instanceof ApiError && query.error.status === 401) && (
          <div className="flex flex-col items-center gap-2 rounded-[12px] border border-border bg-surface px-6 py-12 text-center shadow-card">
            <ScanLine size={40} strokeWidth={1.75} className="text-text-muted" aria-hidden />
            <p className="t-h3 text-text">{bySerial ? "Serial not found" : "Part not found"}</p>
            <p className="t-body text-text-secondary">
              {bySerial ? `No label with serial ${partNumber} here.` : `No part ${partNumber} here. It may have been renamed or archived.`}
            </p>
          </div>
        )}
        {part && (
          <>
            {part.serial && (
              <div className={`rounded-[12px] px-4 py-3 ${part.serial.status === "voided" ? "bg-danger-bg text-danger" : "bg-success-bg text-success"}`}>
                <p className="t-body-strong">
                  Serial {part.serial.value} · {SERIAL_WORD[part.serial.status] ?? part.serial.status}
                </p>
                {part.serial.printed_at && <p className="t-small">Printed {formatDateTime(part.serial.printed_at)}</p>}
              </div>
            )}
            <section className="overflow-hidden rounded-[12px] border border-border bg-surface shadow-card">
              {part.image_url ? (
                <img src={part.image_url} alt={part.part_name} className="block max-h-[360px] w-full bg-surface-subtle object-contain" />
              ) : (
                <div className="flex h-32 items-center justify-center gap-2 bg-surface-subtle text-text-muted">
                  <ImageOff size={20} strokeWidth={1.75} aria-hidden />
                  <span className="t-small">No picture yet</span>
                </div>
              )}
              <div className="flex flex-col gap-1 p-4">
                <span className="t-mono text-[22px] leading-7 text-text">{part.part_number}</span>
                <span className="t-h2 text-text">{part.label_name ?? part.part_name}</span>
                {part.label_name && <span className="t-body text-text-secondary">{part.part_name}</span>}
                {part.status !== "active" && <span className="t-small font-semibold text-warning">This part is archived.</span>}
              </div>
            </section>
            <section className="rounded-[12px] border border-border bg-surface shadow-card">
              <dl className="divide-y divide-border">
                {part.description && <Row label="Description" value={part.description} />}
                {part.revision && <Row label="Revision" value={part.revision} />}
                {part.fields.map((f) => (
                  <Row key={f.label} label={f.label} value={f.value} />
                ))}
                {part.aliases.length > 0 && <Row label="Also known as" value={part.aliases.join(", ")} />}
                <Row label="Last label printed" value={part.last_printed_at ? formatDateTime(part.last_printed_at) : "Never"} />
              </dl>
            </section>
            {part.part_id && (
              <Link to={`/parts?part=${part.part_id}`} className="inline-flex h-11 items-center justify-center gap-2 rounded-[8px] border border-border bg-surface t-button text-text shadow-card">
                <Package size={18} strokeWidth={1.75} aria-hidden />
                Open in Novo Smart Labels
              </Link>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-4 py-3">
      <dt className="t-caption text-text-muted uppercase">{label}</dt>
      <dd className="t-body whitespace-pre-wrap text-text">{value}</dd>
    </div>
  );
}
