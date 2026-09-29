import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { Button } from "../../components/Button";
import { Field, Input } from "../../components/Form";
import { useDocumentTitle } from "../../app/page";
import { BrandMark } from "../../app/Shell";
import { api, ApiError } from "../../lib/api";
import { qk, useMe, useSetupStatus } from "../../lib/queries";
import type { User } from "../../lib/types";

/** 12.2 Login. */
export function LoginPage() {
  useDocumentTitle("Sign in");
  const setup = useSetupStatus();
  const me = useMe();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (setup.data?.needs_setup) return <Navigate to="/setup" replace />;
  if (me.data) return <Navigate to="/print" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api<User>("/auth/login", { body: { username, password }, quiet401: true });
      qc.setQueryData(qk.me, user);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== "/login" ? from : "/print", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Can't reach the server. Printing is paused.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-bg p-6">
      <form onSubmit={submit} className="flex w-[400px] flex-col gap-5 rounded-[8px] border border-border bg-surface p-6" noValidate>
        <BrandMark />
        <h2 className="t-h2 text-text">Sign in</h2>
        <Field label="Username" htmlFor="username">
          <Input id="username" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {error && (
          <p role="alert" className="t-small text-danger">
            {error}
          </p>
        )}
        <Button type="submit" loading={busy} className="w-full">
          Sign in
        </Button>
      </form>
    </div>
  );
}
