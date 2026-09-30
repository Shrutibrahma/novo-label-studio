import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Copy } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { Button } from "../../components/Button";
import { Field, Input } from "../../components/Form";
import { Spinner } from "../../components/Display";
import { useDocumentTitle } from "../../app/page";
import { AuthBackdrop, BrandLogo } from "../../app/Shell";
import { api, ApiError } from "../../lib/api";
import { qk, useSetupStatus } from "../../lib/queries";
import { AGENT_STALE_MS, PRINTER_STATUS_WORD } from "../../lib/status";
import type { Printer, User } from "../../lib/types";
import { TestLabelButton } from "../print/TestLabelButton";

const STEPS = ["Create the admin account", "Your company", "Connect the printer"] as const;
const MIN_PASSWORD = 12;

interface SetupResult {
  user: User;
  agent_token: string;
  printer_id: string;
}

function formatSerial(prefix: string, digits: number, value: number): string {
  const d = Math.min(12, Math.max(4, digits || 0));
  return `${prefix}-${String(Math.max(1, value || 0)).padStart(d, "0")}`;
}

/** 12.3 First-run setup: 3-step wizard, card 640 px. */
export function SetupPage() {
  useDocumentTitle("Setup");
  const status = useSetupStatus();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [account, setAccount] = useState({ display_name: "", username: "", password: "", confirm_password: "" });
  const [company, setCompany] = useState({ company_name: "Novo", serial_prefix: "NOVO", starting_number: 1, digits: 8 });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SetupResult | null>(null);

  const printers = useQuery({
    queryKey: qk.printers,
    queryFn: () => api<Printer[]>("/printers"),
    enabled: result !== null,
    refetchInterval: 2000,
  });
  const printer = printers.data?.find((p) => p.id === result?.printer_id);
  // Connected = the agent has sent a heartbeat within the last 30 s (12.1 staleness rule).
  const connected = !!printer?.agent_last_seen_at && Date.now() - new Date(printer.agent_last_seen_at).getTime() <= AGENT_STALE_MS;

  if (status.data && !status.data.needs_setup && result === null) return <Navigate to="/login" replace />;

  const validateAccount = (): boolean => {
    const e: Record<string, string> = {};
    if (!account.display_name.trim()) e.display_name = "Display name is required.";
    if (!account.username.trim()) e.username = "Username is required.";
    if (account.password.length < MIN_PASSWORD) e.password = "Password must be at least 12 characters.";
    if (account.confirm_password !== account.password) e.confirm_password = "The passwords don't match.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    setBusy(true);
    setErrors({});
    try {
      const res = await api<SetupResult>("/setup", { body: { ...account, ...company } });
      setResult(res);
      qc.setQueryData(qk.me, res.user);
      qc.setQueryData(qk.setupStatus, { needs_setup: false });
      setStep(2);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(Object.keys(err.fields).length ? err.fields : { form: err.message });
        if (["username", "password", "confirm_password", "display_name"].some((k) => k in err.fields)) setStep(0);
      } else setErrors({ form: "Can't reach the server. Printing is paused." });
    } finally {
      setBusy(false);
    }
  };

  const finish = () => {
    qc.invalidateQueries();
    navigate("/parts", { replace: true });
  };

  const onContinue = () => {
    if (step === 0 && validateAccount()) setStep(1);
    else if (step === 1) void submit();
  };

  return (
    <AuthBackdrop>
      <div className="flex w-[640px] flex-col rounded-[12px] border border-border bg-surface shadow-dialog">
        <div className="flex items-center justify-between gap-3 border-b border-border px-6 py-4">
          <BrandLogo className="h-10" />
          <span className="t-h3 text-text">Novo Smart Labels</span>
        </div>
        <ol className="flex gap-6 border-b border-border px-6 py-3" aria-label="Setup steps">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined} className={`flex items-center gap-2 t-small ${i === step ? "text-primary" : i < step ? "text-text" : "text-text-muted"}`}>
              <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full t-caption ${i <= step ? "bg-primary text-white" : "bg-neutral-bg text-neutral-text"}`}>{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>

        <div className="flex flex-col gap-4 p-6">
          <h2 className="t-h2 text-text">{STEPS[step]}</h2>

          {step === 0 && (
            <>
              <Field label="Display name" htmlFor="display_name" error={errors.display_name}>
                <Input id="display_name" autoFocus value={account.display_name} error={errors.display_name} onChange={(e) => setAccount({ ...account, display_name: e.target.value })} />
              </Field>
              <Field label="Username" htmlFor="username" error={errors.username}>
                <Input id="username" autoComplete="username" value={account.username} error={errors.username} onChange={(e) => setAccount({ ...account, username: e.target.value })} />
              </Field>
              <Field label="Password" htmlFor="password" error={errors.password} helper="Minimum 12 characters.">
                <Input id="password" type="password" autoComplete="new-password" value={account.password} error={errors.password} onChange={(e) => setAccount({ ...account, password: e.target.value })} />
              </Field>
              <Field label="Confirm password" htmlFor="confirm_password" error={errors.confirm_password}>
                <Input id="confirm_password" type="password" autoComplete="new-password" value={account.confirm_password} error={errors.confirm_password} onChange={(e) => setAccount({ ...account, confirm_password: e.target.value })} />
              </Field>
            </>
          )}

          {step === 1 && (
            <>
              <Field label="Company name" htmlFor="company_name" error={errors.company_name}>
                <Input id="company_name" autoFocus value={company.company_name} error={errors.company_name} onChange={(e) => setCompany({ ...company, company_name: e.target.value })} />
              </Field>
              <div className="grid grid-cols-3 gap-4">
                <Field label="Serial prefix" htmlFor="serial_prefix" error={errors.serial_prefix}>
                  <Input id="serial_prefix" className="t-mono" value={company.serial_prefix} error={errors.serial_prefix} onChange={(e) => setCompany({ ...company, serial_prefix: e.target.value.toUpperCase() })} />
                </Field>
                <Field label="Starting number" htmlFor="starting_number" error={errors.starting_number}>
                  <Input id="starting_number" type="number" min={1} value={company.starting_number} error={errors.starting_number} onChange={(e) => setCompany({ ...company, starting_number: Number(e.target.value) })} />
                </Field>
                <Field label="Digits" htmlFor="digits" error={errors.digits}>
                  <Input id="digits" type="number" min={4} max={12} value={company.digits} error={errors.digits} onChange={(e) => setCompany({ ...company, digits: Number(e.target.value) })} />
                </Field>
              </div>
              <p className="t-body text-text-secondary">
                First serial: <span className="t-mono text-text">{formatSerial(company.serial_prefix, company.digits, company.starting_number)}</span>
              </p>
            </>
          )}

          {step === 2 && result && (
            <>
              <div className="flex items-center gap-2 rounded-[6px] border border-border bg-surface-subtle px-3 py-2">
                <code className="flex-1 t-mono break-all text-text" data-testid="agent-token">
                  {result.agent_token}
                </code>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Copy}
                  onClick={() => void navigator.clipboard.writeText(result.agent_token)}
                >
                  Copy
                </Button>
              </div>
              <p className="t-body text-text-secondary">Install the Smart Labels Agent on the laptop connected to the ZQ630 Plus, then paste this token when asked.</p>
              <div className="flex items-center justify-between gap-4">
                {connected && printer ? (
                  <span className="inline-flex items-center gap-2 t-body text-success">
                    <CircleCheck size={20} strokeWidth={1.75} aria-hidden />
                    Agent connected. Printer: {PRINTER_STATUS_WORD[printer.reported_status]}
                  </span>
                ) : (
                  <Spinner label="Waiting for the agent…" />
                )}
                {printer && <TestLabelButton printer={printer} disabled={!connected} />}
              </div>
            </>
          )}

          {errors.form && (
            <p role="alert" className="t-small text-danger">
              {errors.form}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border px-6 py-4">
          {step === 2 ? (
            <Button variant="ghost" onClick={finish}>
              Skip for now
            </Button>
          ) : (
            <Button variant="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
              Back
            </Button>
          )}
          {step < 2 ? (
            <Button loading={busy} onClick={onContinue}>
              Continue
            </Button>
          ) : (
            <Button onClick={finish}>Finish</Button>
          )}
        </div>
      </div>
    </AuthBackdrop>
  );
}
