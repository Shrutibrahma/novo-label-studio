import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useDebounced } from "../lib/parts";
import { Switch } from "./Form";

export interface PreviewWarning {
  code: string;
  field: string | null;
  message: string;
}

export interface PreviewResult {
  png_base64: string;
  fits: boolean;
  warnings: PreviewWarning[];
  width_dots: number;
  height_dots: number;
  dpi: number;
  family: string;
  serial_placeholder: boolean;
}

export interface PreviewRequest {
  part_id: string;
  config_id?: string;
  config?: { label_size_id: string; spec: unknown; qr_mode: string; serial_mode: string };
  manual_values?: Record<string, unknown>;
}

/** POST /render/preview, debounced (250 ms after the last change in the Print dialog, 12.6). */
export function usePreview(req: PreviewRequest | null, debounceMs = 250) {
  const key = req ? JSON.stringify(req) : null;
  const debounced = useDebounced(key, debounceMs);
  return useQuery({
    queryKey: ["preview", debounced],
    queryFn: ({ signal }) => api<PreviewResult>("/render/preview", { body: JSON.parse(debounced as string), signal }),
    enabled: !!debounced,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/**
 * 7.7: the rendered PNG, `image-rendering: pixelated`, scaled to the largest integer multiple that fits the pane
 * (minimum 1×), on the #E5E7EB surround with a 1 px #9CA3AF outline; "Actual size" uses 96 CSS px per inch.
 */
export function LabelPreview({
  result,
  loading,
  maxHeight,
  showActualSizeToggle = true,
  padding = 24,
  shrink = false,
}: {
  result: PreviewResult | undefined;
  loading?: boolean;
  maxHeight?: number;
  showActualSizeToggle?: boolean;
  padding?: number;
  /** Static thumbnails (Configure card, part drawer): scale below 1× when the label is wider than the pane. */
  shrink?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState({ w: 0, h: 0 });
  const [actual, setActual] = useState(false);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    // Without a fixed height the pane grows with the image, so only the width limits the scale.
    const measure = () => setAvail({ w: el.clientWidth - padding * 2, h: maxHeight ? maxHeight - padding * 2 : Number.POSITIVE_INFINITY });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [maxHeight, padding]);

  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    setSrc(result ? `data:image/png;base64,${result.png_base64}` : null);
  }, [result]);

  let width = 0;
  let height = 0;
  if (result) {
    if (actual) {
      width = (result.width_dots / result.dpi) * 96;
      height = (result.height_dots / result.dpi) * 96;
    } else {
      const fit = Math.min(avail.w / result.width_dots, avail.h / result.height_dots);
      const scale = shrink && fit < 1 ? Math.max(fit, 0.05) : Math.max(1, Math.floor(fit) || 1);
      width = result.width_dots * scale;
      height = result.height_dots * scale;
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={box}
        className="relative flex overflow-auto rounded-[8px] bg-preview-surround"
        style={{ padding, height: maxHeight, minHeight: 160 }}
        data-testid="label-preview"
      >
        {src && result && (
          <img
            src={src}
            alt="Label preview"
            className="pixelated m-auto block max-w-none shrink-0 bg-label-paper outline outline-1 outline-preview-edge"
            style={{ width, height }}
            draggable={false}
          />
        )}
        {result?.serial_placeholder && (
          <span className="absolute top-3 right-3 inline-flex h-[22px] items-center rounded-full bg-info-bg px-2 t-caption text-info">Serial assigned at print</span>
        )}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-preview-surround/60" aria-label="Rendering">
            <span className="spinner text-text-secondary" />
          </div>
        )}
      </div>
      {showActualSizeToggle && result && <Switch label="Actual size" checked={actual} onChange={setActual} />}
    </div>
  );
}
