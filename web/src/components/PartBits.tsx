import { ImageOff, Search } from "lucide-react";
import { forwardRef, type InputHTMLAttributes } from "react";
import { partImageUrl } from "../lib/parts";
import { LABEL_STATE_TONE, LABEL_STATE_WORD, PART_STATUS_TONE, PART_STATUS_WORD, type LabelState, type PartStatus } from "../lib/status";
import { Badge } from "./Display";

/** 48 × 48 thumb, radius 6, ImageOff on the neutral fill when none (12.4). */
export function PartThumb({ part, size = 48 }: { part: { id: string; image_version: string | null }; size?: number }) {
  const url = partImageUrl(part);
  return url ? (
    <img src={url} alt="" width={size} height={size} className="shrink-0 rounded-[6px] border border-border bg-surface object-cover" style={{ width: size, height: size }} />
  ) : (
    <span className="inline-flex shrink-0 items-center justify-center rounded-[6px] bg-neutral-bg text-text-muted" style={{ width: size, height: size }}>
      <ImageOff size={size > 48 ? 20 : 16} strokeWidth={1.75} aria-hidden />
    </span>
  );
}

export function FreshnessBadge({ state }: { state: LabelState }) {
  return <Badge tone={LABEL_STATE_TONE[state]}>{LABEL_STATE_WORD[state]}</Badge>;
}

export function PartStatusBadge({ status }: { status: PartStatus }) {
  return <Badge tone={PART_STATUS_TONE[status]}>{PART_STATUS_WORD[status]}</Badge>;
}

/** Page search: h 44, Search icon, `/` focuses it (12.1, 12.4). */
export const SearchInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function SearchInput({ className = "", ...rest }, ref) {
  return (
    <div className={`relative w-full max-w-[720px] ${className}`}>
      <Search size={20} strokeWidth={1.75} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-text-muted" aria-hidden />
      <input
        ref={ref}
        type="search"
        data-page-search
        className="h-11 w-full rounded-[6px] border border-border-strong bg-surface pr-3 pl-10 text-text placeholder:text-text-muted focus:border-primary focus:outline-2 focus:outline-offset-2 focus:outline-focus-ring"
        {...rest}
      />
    </div>
  );
});
