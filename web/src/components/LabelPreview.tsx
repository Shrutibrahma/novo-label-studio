import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { HouseStyle } from "../lib/types";
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
  /** Where the design's rows and boxes are drawn: x, y, w, h in dots (inside the house frame, band and footer). */
  layout_box?: [number, number, number, number];
}

export interface PreviewRequest {
  /** Omitted for a quick label type. */
  part_id?: string;
  config_id?: string;
  label_type_id?: string;
  /** The browser's "Print as" choice, used when label_type_id is omitted (the server resolves the type). */
  print_as?: string;
  config?: { label_size_id: string; spec: unknown; qr_mode: string; serial_mode: string };
  manual_values?: Record<string, unknown>;
  /** An unsaved Settings → Label style draft (Admin only). */
  house_style?: HouseStyle;
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
  shrink: _shrink = false,
  overlay,
  roll,
}: {
  result: PreviewResult | undefined;
  loading?: boolean;
  maxHeight?: number;
  showActualSizeToggle?: boolean;
  padding?: number;
  /** Kept for callers; every preview now shrinks to fit its pane. */
  shrink?: boolean;
  /** Drawn over the label image at its size (e.g. clickable boxes in the Configure editor). */
  overlay?: ReactNode;
  /** The roll loaded in the printer, when it's bigger than the label: the label is shown centered on it, as printed. */
  roll?: { width_in: number; height_in: number; border: boolean } | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState({ w: 0, h: 0, dpr: 1 });
  const [actual, setActual] = useState(false);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    // Without a fixed height the pane grows with the image, so only the width limits the scale.
    // Windows display scaling and browser zoom change devicePixelRatio (and fire the observer via clientWidth).
    const measure = () =>
      setAvail({
        w: el.clientWidth - padding * 2,
        h: maxHeight ? maxHeight - padding * 2 : Number.POSITIVE_INFINITY,
        dpr: window.devicePixelRatio || 1,
      });
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
  let crisp = true;
  let scale = 1; // CSS px per printer dot
  // Same geometry as the API's frame_on_roll: the label centered on the roll, a 2-dot border 6 dots outside it.
  const rollW = result && roll ? Math.max(result.width_dots, Math.floor(roll.width_in * result.dpi)) : 0;
  const rollH = result && roll ? Math.max(result.height_dots, Math.floor(roll.height_in * result.dpi)) : 0;
  const onRoll = !!result && !!roll && (rollW > result.width_dots || rollH > result.height_dots);
  const frameW = onRoll ? rollW : (result?.width_dots ?? 0);
  const frameH = onRoll ? rollH : (result?.height_dots ?? 0);
  if (result) {
    if (actual) {
      scale = 96 / result.dpi;
      crisp = false;
    } else {
      // The integer multiple is in device pixels, not CSS pixels: at 125% scaling a 2× CSS scale is 2.5 device
      // pixels per dot, which makes dots uneven and text look distorted.
      const fit = Math.min(avail.w / frameW, avail.h / frameH) * avail.dpr;
      // Too big for the pane: shrink to fit (never cut the label off). Otherwise the largest whole multiple.
      scale = fit < 1 ? Math.max(fit, 0.05) / avail.dpr : Math.max(1, Math.floor(fit)) / avail.dpr;
      crisp = Number.isInteger(Math.round(scale * avail.dpr * 1000) / 1000);
    }
    width = result.width_dots * scale;
    height = result.height_dots * scale;
  }
  const gapX = onRoll && result ? Math.min(8, Math.floor((rollW - result.width_dots) / 2)) * scale : 0;
  const gapY = onRoll && result ? Math.min(8, Math.floor((rollH - result.height_dots) / 2)) * scale : 0;
  const image = src && result && (
    <div className="relative m-auto shrink-0" style={{ width, height }}>
      <img
        src={src}
        alt="Label preview"
        className={`${crisp ? "pixelated " : ""}block max-w-none bg-label-paper ${onRoll ? "" : "outline outline-1 outline-preview-edge"}`}
        style={{ width, height }}
        draggable={false}
      />
      {onRoll && roll?.border && (
        <span
          aria-hidden
          className="pointer-events-none absolute border-label-ink"
          style={{ left: -gapX, top: -gapY, right: -gapX, bottom: -gapY, borderWidth: Math.max(1, 2 * scale), borderStyle: "solid" }}
        />
      )}
      {overlay}
    </div>
  );

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={box}
        className="relative flex overflow-auto rounded-[8px] bg-preview-surround"
        style={{ padding, height: maxHeight, minHeight: 160 }}
        data-testid="label-preview"
      >
        {image && onRoll ? (
          <div
            className="m-auto flex shrink-0 rounded-[3px] bg-label-paper outline outline-1 outline-preview-edge"
            style={{ width: frameW * scale, height: frameH * scale }}
            title="The loaded roll: the label prints in its middle"
          >
            {image}
          </div>
        ) : (
          image
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
