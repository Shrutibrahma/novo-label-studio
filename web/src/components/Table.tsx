import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { Skeleton } from "./Display";

/** Table: header --surface-subtle with Caption uppercase muted; rows 52 (64 with images); hover/selected fills (11.4). */
export function Table({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`overflow-hidden rounded-[8px] border border-border bg-surface ${className}`}>
      <table className="w-full border-collapse text-left">{children}</table>
    </div>
  );
}

export function Th({ children, className = "", ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={`h-10 border-b border-border bg-surface-subtle px-4 t-caption tracking-wide text-text-muted uppercase ${className}`} {...rest}>
      {children}
    </th>
  );
}

export function Td({ children, className = "", ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`border-b border-border px-4 py-3 t-body text-text-secondary ${className}`} {...rest}>
      {children}
    </td>
  );
}

export function Tr({
  children,
  selected,
  tall,
  onClick,
  className = "",
  ...rest
}: HTMLAttributes<HTMLTableRowElement> & { selected?: boolean; tall?: boolean }) {
  return (
    <tr
      onClick={onClick}
      className={`${tall ? "h-16" : "h-[52px]"} transition-colors duration-150 ${selected ? "bg-primary-subtle" : "hover:bg-row-hover"} ${onClick ? "cursor-pointer" : ""} ${className}`}
      {...rest}
    >
      {children}
    </tr>
  );
}

/** Loading state: skeleton rows × 8 (section 12). */
export function SkeletonRows({ columns, rows = 8, tall }: { columns: number; rows?: number; tall?: boolean }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className={tall ? "h-16" : "h-[52px]"}>
          {Array.from({ length: columns }, (_, c) => (
            <td key={c} className="border-b border-border px-4">
              <Skeleton className="h-4 w-full max-w-[160px]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
