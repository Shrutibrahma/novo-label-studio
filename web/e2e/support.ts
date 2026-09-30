import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ADMIN = { display_name: "Ada Admin", username: "ada", password: "correct-horse-battery" };
export const OPERATOR = { display_name: "Olive Operator", username: "olive", password: "correct-horse-battery" };

const here = dirname(fileURLToPath(import.meta.url));
const STATE = join(here, "..", "test-results", "e2e-state.json");

/** State shared between spec files (they run in order, one worker). */
export interface E2EState {
  agentToken?: string;
  printerId?: string;
}

export function saveState(patch: E2EState): void {
  mkdirSync(dirname(STATE), { recursive: true });
  writeFileSync(STATE, JSON.stringify({ ...loadState(), ...patch }, null, 2));
}

export function loadState(): E2EState {
  try {
    return JSON.parse(readFileSync(STATE, "utf8")) as E2EState;
  } catch {
    return {};
  }
}

export async function signIn(page: Page, user: { username: string; password: string }): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/print$/);
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: /Ada Admin|Olive Operator/ }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

// ---------------------------------------------------------------- the print agent, simulated mode
export const REPO_ROOT = process.env.E2E_REPO_ROOT ?? resolve(here, "..", "..");
export const AGENT_OUTPUT = join(REPO_ROOT, "agent-output", "e2e");
export const SIM_CONTROL_PORT = 9182;
const agentKey = Symbol.for("labelstudio.e2e.agent");
type WithAgent = typeof globalThis & { [agentKey]?: ChildProcess };

/** Starts the real agent (AGENT_PRINTER_MODE=simulated) against the e2e stack; it lives for the whole run. */
export function startAgent(token: string): void {
  const g = globalThis as WithAgent;
  if (g[agentKey]) return;
  mkdirSync(AGENT_OUTPUT, { recursive: true });
  const base = process.env.E2E_BASE_URL ?? "https://localhost:9443";
  const cert = join(REPO_ROOT, "deploy", "certs", "labelstudio.crt");
  const child = spawn("uv", ["run", "--quiet", "labelstudio-agent", "run"], {
    cwd: join(REPO_ROOT, "agent"),
    env: {
      ...process.env,
      AGENT_TOKEN: token,
      API_BASE_URL: `${base}/api`,
      AGENT_PRINTER_MODE: "simulated",
      AGENT_OUTPUT_DIR: AGENT_OUTPUT,
      AGENT_LOG_DIR: join(AGENT_OUTPUT, "logs"),
      AGENT_SIM_CONTROL_PORT: String(SIM_CONTROL_PORT),
      AGENT_POLL_SECONDS: "0.5",
      ...(existsSync(cert) ? { AGENT_CA_BUNDLE: cert } : {}),
    },
    stdio: "ignore",
  });
  g[agentKey] = child;
  process.on("exit", () => child.kill());
}

/** Forces the simulated printer's status through the agent's local control endpoint. */
export async function simStatus(status: string): Promise<void> {
  const res = await fetch(`http://127.0.0.1:${SIM_CONTROL_PORT}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  expect(res.ok).toBeTruthy();
}

export function agentJobFiles(): string[] {
  return existsSync(AGENT_OUTPUT) ? readdirSync(AGENT_OUTPUT).filter((f) => f.endsWith(".zpl")) : [];
}

/** An API context signed in as `user` (for arranging data without clicking through the UI). */
export async function apiAs(request: APIRequestContext, user: { username: string; password: string }): Promise<APIRequestContext> {
  const res = await request.post("/api/v1/auth/login", { data: { username: user.username, password: user.password } });
  expect(res.ok()).toBeTruthy();
  return request;
}
