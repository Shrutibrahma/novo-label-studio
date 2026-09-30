import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "../../lib/api";
import type { ImportBatch } from "./types";

const ACCEPT = ".csv,.xlsx,.xls";

/** Step 1 hero (12.10): dark gradient, 720 px column, 720 × 240 drop zone. */
export function Hero({ parsing, error, onUploaded }: { parsing: string | null; error: string | null; onUploaded: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const busyName = uploading ?? parsing;

  const send = async (file: File) => {
    setUploading(file.name);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const batch = await api<ImportBatch>("/imports", { method: "POST", form });
      onUploaded(batch.id);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setUploading(null);
    }
  };

  const shownError = uploadError ?? error;
  return (
    <div className="flex min-h-[calc(100vh-56px)] justify-center bg-hero-bg-from bg-cover bg-center px-8 py-20" style={{ backgroundImage: "linear-gradient(rgba(23, 33, 15, 0.55), rgba(23, 33, 15, 0.55)), url(/art/backdrop.svg)" }}>
      <div className="flex w-[720px] flex-col items-center text-center">
        <h2 className="t-display text-hero-text">Give us your parts list</h2>
        <p className="mt-3 t-body text-hero-text-muted">Upload a CSV or Excel file. We'll match the columns and show you every change before anything is saved.</p>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            const f = e.dataTransfer.files[0];
            if (f && !busyName) void send(f);
          }}
          className={`mt-10 flex h-[240px] w-[720px] flex-col items-center justify-center gap-3 rounded-[16px] border-2 border-dashed transition-colors duration-150 ${over ? "border-primary bg-hero-drop-bg-hover" : "border-hero-drop-border bg-hero-drop-bg"}`}
          data-testid="drop-zone"
        >
          {busyName ? (
            <span className="inline-flex items-center gap-3 text-white" role="status">
              <span className="spinner" aria-hidden />
              <span className="t-body">Reading {busyName}…</span>
            </span>
          ) : (
            <>
              <Upload size={40} strokeWidth={1.75} className="text-white" aria-hidden />
              <span className="text-[16px] leading-6 font-semibold text-white">Drop your file here</span>
              <span className="t-small text-hero-text-muted">or</span>
              <button
                type="button"
                onClick={() => input.current?.click()}
                className="inline-flex h-9 items-center rounded-[6px] bg-surface px-4 t-button text-text hover:bg-hover-fill"
              >
                Choose file
              </button>
              <input
                ref={input}
                type="file"
                accept={ACCEPT}
                hidden
                aria-label="Choose file"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void send(f);
                  e.target.value = "";
                }}
              />
            </>
          )}
        </div>
        <p className="mt-3 t-caption text-hero-text-muted">CSV · XLSX · XLS · up to 20 MB</p>
        {shownError && (
          <p role="alert" className="mt-4 rounded-[6px] bg-danger-bg px-3 py-2 t-body text-danger">
            {shownError}
          </p>
        )}
      </div>
    </div>
  );
}
