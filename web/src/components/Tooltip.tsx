import { useId, useState, type ReactElement, type ReactNode } from "react";

/** Hover/focus tooltip. Wraps a single element. */
export function Tooltip({ content, children, side = "top" }: { content: ReactNode; children: ReactElement; side?: "top" | "bottom" }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (content === null || content === undefined || content === "") return children;
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      aria-describedby={open ? id : undefined}
    >
      {children}
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`pointer-events-none absolute left-1/2 z-50 w-max max-w-[280px] -translate-x-1/2 rounded-[6px] bg-text px-2 py-1 t-caption text-white shadow-dropdown ${side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5"}`}
        >
          {content}
        </span>
      )}
    </span>
  );
}
