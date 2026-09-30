import { expect, test } from "@playwright/test";
import { ADMIN, agentJobFiles, OPERATOR, saveState, signIn, signOut, startAgent } from "./support";

/** Flow 13.1 (first install) with the agent in simulated mode, plus sign-in errors and operator navigation. */
test("first install: setup wizard, sign-in errors, roles", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await expect(page).toHaveTitle("Setup · Novo Smart Labels");

  await expect(page.getByRole("heading", { name: "Create the admin account" })).toBeVisible();
  await page.getByLabel("Display name").fill(ADMIN.display_name);
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password", { exact: true }).fill("short");
  await page.getByLabel("Confirm password").fill("short");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Password must be at least 12 characters.")).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill(ADMIN.password);
  await page.getByLabel("Confirm password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Your company" })).toBeVisible();
  await expect(page.getByLabel("Company name")).toHaveValue("Novo");
  await expect(page.getByText("First serial: NOVO-00000001")).toBeVisible();
  await page.getByLabel("Digits").fill("6");
  await expect(page.getByText("First serial: NOVO-000001")).toBeVisible();
  await page.getByLabel("Digits").fill("8");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Connect the printer" })).toBeVisible();
  await expect(page.getByText("Install the Smart Labels Agent on the laptop connected to the ZQ630 Plus, then paste this token when asked.")).toBeVisible();
  await expect(page.getByText("Waiting for the agent…")).toBeVisible();
  const token = (await page.getByTestId("agent-token").textContent())?.trim() ?? "";
  expect(token.length).toBeGreaterThan(40);
  await expect(page.getByRole("button", { name: "Print test label" })).toBeDisabled();
  const printers = await (await page.request.get("/api/v1/printers")).json();
  saveState({ agentToken: token, printerId: printers[0].id });

  // 13.1 step 3–4: install the agent with that token → "Agent connected" → "Print test label".
  const before = agentJobFiles().length;
  startAgent(token);
  await expect(page.getByText("Agent connected. Printer: Ready")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "Print test label" }).click();
  await expect(page.getByText("Sent to printer")).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(before + 1);
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/parts$/);
  await expect(page.getByText("Your parts list is empty")).toBeVisible();

  // Shell: brand, company name, admin navigation, tab title.
  await expect(page.getByText("Novo Smart Labels").first()).toBeVisible();
  for (const item of ["Print Labels", "Parts", "Configure", "History", "Settings"]) {
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: item })).toBeVisible();
  }
  await expect(page.getByText("ZQ630 Plus")).toBeVisible();

  // Setup can't be run again.
  await page.goto("/setup");
  await expect(page).not.toHaveURL(/\/setup$/);

  await signOut(page);
  await page.getByLabel("Username").fill(ADMIN.username);
  await page.getByLabel("Password").fill("wrong-password-1");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Username or password is incorrect.")).toBeVisible();
  await signIn(page, ADMIN);
  await expect(page).toHaveTitle("Print Labels · Novo Smart Labels");
  await expect(page.getByRole("heading", { level: 1, name: "Print Labels" })).toBeVisible();

  // Create an operator and check the operator's navigation (12.1).
  const created = await page.request.post("/api/v1/users", { data: { ...OPERATOR, role: "operator" } });
  expect(created.status()).toBe(201);
  await signOut(page);
  await signIn(page, OPERATOR);
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Print Labels" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Parts" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "History" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Configure" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0);
  const forbidden = await page.request.get("/api/v1/users");
  expect(forbidden.status()).toBe(403);
  await page.getByRole("button", { name: OPERATOR.display_name }).click();
  await expect(page.getByText("Operator", { exact: true })).toBeVisible();
});
