import { expect, test } from "@playwright/test";
import { ADMIN, OPERATOR, saveState, signIn, signOut } from "./support";

/** Flow 13.1 steps 1–3 and 5 (the agent-connected part runs in 05-print once the simulated agent starts). */
test("first install: setup wizard, sign-in errors, roles", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await expect(page).toHaveTitle("Setup · Novo Label Studio");

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
  await expect(page.getByText("Install the Label Studio Agent on the laptop connected to the ZQ630 Plus, then paste this token when asked.")).toBeVisible();
  await expect(page.getByText("Waiting for the agent…")).toBeVisible();
  const token = (await page.getByTestId("agent-token").textContent())?.trim() ?? "";
  expect(token.length).toBeGreaterThan(40);
  await expect(page.getByRole("button", { name: "Print test label" })).toBeDisabled();
  const printers = await (await page.request.get("/api/v1/printers")).json();
  saveState({ agentToken: token, printerId: printers[0].id });
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/(parts|print)$/);

  // Shell: brand, company name, admin navigation, tab title.
  await expect(page.getByText("Novo Label Studio").first()).toBeVisible();
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
  await expect(page).toHaveTitle("Print Labels · Novo Label Studio");
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
