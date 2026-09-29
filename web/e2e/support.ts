import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
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

/** An API context signed in as `user` (for arranging data without clicking through the UI). */
export async function apiAs(request: APIRequestContext, user: { username: string; password: string }): Promise<APIRequestContext> {
  const res = await request.post("/api/v1/auth/login", { data: { username: user.username, password: user.password } });
  expect(res.ok()).toBeTruthy();
  return request;
}
