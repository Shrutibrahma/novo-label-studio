/** API client: JSON over same-origin /api/v1, spec error envelope (section 6), reachability tracking. */

export const API = "/api/v1";

export interface ApiErrorBody {
  code: string;
  message: string;
  fields?: Record<string, string>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly fields: Record<string, string>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.code = body.code;
    this.status = status;
    this.fields = body.fields ?? {};
  }
}

/** Section 4: if the API is unreachable, printing is blocked and the UI says so. */
export const SERVER_UNREACHABLE = "Can't reach the server. Printing is paused.";

type Listener = (reachable: boolean) => void;
const reachabilityListeners = new Set<Listener>();
let reachable = true;

function setReachable(value: boolean): void {
  if (value === reachable) return;
  reachable = value;
  reachabilityListeners.forEach((l) => l(value));
}

export function isServerReachable(): boolean {
  return reachable;
}

export function onReachabilityChange(listener: Listener): () => void {
  reachabilityListeners.add(listener);
  return () => reachabilityListeners.delete(listener);
}

let sessionExpiredHandler: (() => void) | null = null;
export function onSessionExpired(handler: () => void): void {
  sessionExpiredHandler = handler;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Don't trigger the global "session expired" redirect (used by the login screen and /auth/me). */
  quiet401?: boolean;
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone;
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      credentials: "same-origin",
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name !== "AbortError") setReachable(false);
    throw err;
  }
  // 502/503/504 come from nginx when the API container is down.
  setReachable(!(res.status === 502 || res.status === 503 || res.status === 504));
  if (!res.ok) {
    let parsed: ApiErrorBody = { code: "INTERNAL", message: SERVER_UNREACHABLE };
    try {
      const json = (await res.json()) as { error?: ApiErrorBody };
      if (json.error) parsed = json.error;
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    const error = new ApiError(res.status, parsed);
    if (res.status === 401 && parsed.code === "SESSION_EXPIRED" && !opts.quiet401) sessionExpiredHandler?.();
    throw error;
  }
  return res;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function apiBlob(path: string, opts: RequestOptions = {}): Promise<{ blob: Blob; headers: Headers }> {
  const res = await send(path, opts);
  return { blob: await res.blob(), headers: res.headers };
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
