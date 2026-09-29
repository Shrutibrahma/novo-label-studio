import { ChevronDown, type LucideIcon } from "lucide-react";
import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Tooltip } from "./Tooltip";

const CONTROL =
  "w-full rounded-[6px] border bg-surface px-3 text-text placeholder:text-text-muted transition-colors duration-150 ease-out " +
  "focus:border-primary focus:outline-2 focus:outline-offset-2 focus:outline-focus-ring " +
  "disabled:bg-surface-subtle disabled:text-text-secondary read-only:bg-surface-subtle";

function borderFor(error?: string | null): string {
  return error ? "border-danger" : "border-border-strong";
}

export interface FieldProps {
  label?: ReactNode;
  required?: boolean;
  error?: string | null;
  helper?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}

/** Label + control + 13 px danger message below (11.4 Input). */
export function Field({ label, required, error, helper, htmlFor, children, className = "" }: FieldProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label !== undefined && (
        <label htmlFor={htmlFor} className="t-body-strong text-text">
          {label}
          {required && <span className="ml-0.5 text-danger">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="t-small text-danger" role="alert">
          {error}
        </p>
      ) : helper ? (
        <p className="t-small text-text-muted">{helper}</p>
      ) : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string | null;
  icon?: LucideIcon;
  heightClass?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { error, icon: Icon, className = "", heightClass = "h-9", ...rest },
  ref,
) {
  if (!Icon) {
    return (
      <input ref={ref} aria-invalid={!!error || undefined} className={`${CONTROL} ${heightClass} ${borderFor(error)} ${className}`} {...rest} />
    );
  }
  return (
    <div className={`relative ${className}`}>
      <Icon size={16} strokeWidth={1.75} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-text-muted" aria-hidden />
      <input ref={ref} aria-invalid={!!error || undefined} className={`${CONTROL} ${heightClass} ${borderFor(error)} pl-9`} {...rest} />
    </div>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: string | null;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({ error, className = "", ...rest }, ref) {
  return <textarea ref={ref} className={`${CONTROL} py-2 ${borderFor(error)} ${className}`} {...rest} />;
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  error?: string | null;
  options: { value: string; label: string; disabled?: boolean }[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ error, options, className = "", ...rest }, ref) {
  return (
    <div className={`relative ${className}`}>
      <select ref={ref} className={`${CONTROL} h-9 appearance-none pr-9 ${borderFor(error)}`} {...rest}>
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown size={16} strokeWidth={1.75} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-text-muted" aria-hidden />
    </div>
  );
});

export function Checkbox({
  label,
  checked,
  onChange,
  disabled,
  tooltip,
  id,
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  tooltip?: string | null;
  id?: string;
}) {
  const auto = useId();
  const cid = id ?? auto;
  const box = (
    <label htmlFor={cid} className={`inline-flex items-center gap-2 t-body ${disabled ? "text-text-muted" : "text-text"}`}>
      <input id={cid} type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
  return tooltip ? <Tooltip content={tooltip}>{box}</Tooltip> : box;
}

/** 36 × 20 switch, checked --primary. */
export function Switch({
  checked,
  onChange,
  label,
  disabled,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
  description?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-60 ${checked ? "bg-primary" : "bg-border-strong"}`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-surface shadow-dropdown transition-transform duration-150 ease-out ${checked ? "translate-x-4" : ""}`}
        />
      </button>
      <label htmlFor={id} className="flex flex-col">
        <span className="t-body text-text">{label}</span>
        {description && <span className="t-small text-text-muted">{description}</span>}
      </label>
    </div>
  );
}

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  tooltip?: string;
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: T;
  onChange: (v: T) => void;
  options: SegmentOption<T>[];
  ariaLabel: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-[6px] border border-border-strong bg-surface p-0.5">
      {options.map((o) => {
        const selected = o.value === value;
        const btn = (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={`h-8 rounded-[4px] px-3 t-button transition-colors duration-150 ease-out disabled:cursor-not-allowed disabled:text-text-muted ${selected ? "bg-primary-subtle text-primary" : "text-text-secondary hover:bg-hover-fill"}`}
          >
            {o.label}
          </button>
        );
        return o.tooltip ? (
          <Tooltip key={o.value} content={o.tooltip}>
            {btn}
          </Tooltip>
        ) : (
          btn
        );
      })}
    </div>
  );
}

/** Number stepper: − / input / +, clamped to [min, max]. */
export function NumberStepper({
  value,
  onChange,
  min,
  max,
  label,
  id,
  error,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  label: string;
  id?: string;
  error?: string | null;
}) {
  const clamp = (n: number) => Math.min(max, Math.max(min, Math.round(n)));
  return (
    <div className={`inline-flex h-9 items-stretch overflow-hidden rounded-[6px] border ${borderFor(error)} bg-surface`}>
      <button type="button" aria-label={`Decrease ${label}`} disabled={value <= min} onClick={() => onChange(clamp(value - 1))} className="w-9 t-button text-text-secondary hover:bg-hover-fill disabled:text-text-muted disabled:hover:bg-surface">
        −
      </button>
      <input
        id={id}
        aria-label={label}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (e.target.value !== "" && Number.isFinite(n)) onChange(clamp(n));
        }}
        className="w-16 border-x border-border px-2 text-center tabular-nums focus:outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
      />
      <button type="button" aria-label={`Increase ${label}`} disabled={value >= max} onClick={() => onChange(clamp(value + 1))} className="w-9 t-button text-text-secondary hover:bg-hover-fill disabled:text-text-muted disabled:hover:bg-surface">
        +
      </button>
    </div>
  );
}
