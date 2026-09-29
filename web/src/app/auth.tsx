import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { onSessionExpired } from "../lib/api";
import { qk, useMe, useSetupStatus } from "../lib/queries";
import type { Role, User } from "../lib/types";

/** Sends the browser to /login whenever any request reports SESSION_EXPIRED. */
export function SessionWatcher() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    onSessionExpired(() => {
      qc.setQueryData(qk.me, null);
      navigate("/login", { replace: true, state: { from: window.location.pathname + window.location.search } });
    });
  }, [navigate, qc]);
  return null;
}

export function RequireAuth({ children, role }: { children: ReactNode; role?: Role }) {
  const setup = useSetupStatus();
  const me = useMe();
  const location = useLocation();
  if (setup.isPending || me.isPending) return null;
  if (setup.data?.needs_setup) return <Navigate to="/setup" replace />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (role && me.data.role !== role) return <Navigate to="/print" replace />;
  return <>{children}</>;
}

export function useUser(): User {
  const me = useMe();
  if (!me.data) throw new Error("useUser outside RequireAuth");
  return me.data;
}

export function useIsAdmin(): boolean {
  return useMe().data?.role === "admin";
}
