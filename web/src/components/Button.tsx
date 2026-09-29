import type { LucideIcon } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Tooltip } from "./Tooltip";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "danger-ghost";
export type ButtonSize = "md" | "sm" | "big";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-white hover:bg-primary-hover active:bg-primary-pressed disabled:bg-primary-disabled disabled:hover:bg-primary-disabled",
  secondary:
    "bg-surface text-text border border-border-strong hover:bg-hover-fill disabled:text-text-muted disabled:hover:bg-surface",
  ghost: "bg-transparent text-text-secondary hover:bg-hover-fill disabled:text-text-muted disabled:hover:bg-transparent",
  danger: "bg-danger text-white hover:bg-danger-hover disabled:bg-danger-bg disabled:text-danger",
  "danger-ghost": "bg-transparent text-danger hover:bg-danger-bg disabled:opacity-50",
};

const SIZE: Record<ButtonSize, string> = {
  md: "h-9 px-4 t-button gap-2",
  sm: "h-8 px-3 t-button gap-1.5",
  big: "h-12 px-6 text-[16px] leading-6 font-semibold gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  loading?: boolean;
  /** Tooltip shown (also while disabled) — used for the 14.1 "why is Print disabled" message. */
  tooltip?: string | null;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", icon: Icon, loading, tooltip, className = "", children, disabled, type, ...rest },
  ref,
) {
  const iconSize = size === "big" ? 20 : size === "sm" ? 16 : 20;
  const btn = (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center rounded-[6px] whitespace-nowrap transition-colors duration-150 ease-out disabled:cursor-not-allowed ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {loading ? <span className="spinner" aria-hidden /> : Icon ? <Icon size={iconSize} strokeWidth={1.75} aria-hidden /> : null}
      {children}
    </button>
  );
  if (!tooltip) return btn;
  return (
    <Tooltip content={tooltip}>
      <span className="inline-flex" tabIndex={disabled ? 0 : -1}>
        {btn}
      </span>
    </Tooltip>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  label: string;
  iconSize?: number;
}

/** Ghost icon button; `label` is both the accessible name and the tooltip. */
export function IconButton({ icon: Icon, label, iconSize = 20, className = "", ...rest }: IconButtonProps) {
  return (
    <Tooltip content={label}>
      <button
        type="button"
        aria-label={label}
        className={`inline-flex h-8 w-8 items-center justify-center rounded-[6px] text-text-secondary transition-colors duration-150 ease-out hover:bg-hover-fill disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
        {...rest}
      >
        <Icon size={iconSize} strokeWidth={1.75} aria-hidden />
      </button>
    </Tooltip>
  );
}
