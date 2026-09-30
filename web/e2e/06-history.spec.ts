import { expect, test } from "@playwright/test";
import { ADMIN, agentJobFiles, loadState, signIn, startAgent } from "./support";

test.beforeAll(() => {
  const { agentToken } = loadState();
  if (agentToken) startAgent(agentToken);
});

/** Flow 13.8 "Reprint a damaged label" (A4 in the UI) and History filters. */
test("reprint a damaged label from History", async ({ page }) => {
  await signIn(page, ADMIN);
  const res = await page.request.get("/api/v1/history?q=NP-10421");
  const serial: string = (await res.json()).items.find((r: { serial: string | null }) => r.serial).serial;

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  await expect(page).toHaveTitle("History · Novo Label Studio");
  await page.getByPlaceholder("Search serial, part number or label name").fill(serial);
  const drawer = page.getByRole("dialog", { name: "Printed label" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(serial).first()).toBeVisible();
  await expect(drawer.getByRole("img", { name: "Label preview" })).toBeVisible();

  const before = agentJobFiles().length;
  await drawer.getByRole("button", { name: "Reprint exact label" }).click();
  const dialog = page.getByRole("dialog", { name: "Reprint exact label" });
  await expect(dialog.getByRole("button", { name: "Print" })).toBeDisabled(); // reason is required
  await dialog.getByLabel("Damaged").check();
  await dialog.getByRole("button", { name: "Print" }).click();
  await expect(page.getByText("Sent to printer").first()).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(before + 1);
  await expect(drawer.getByRole("heading", { name: "Reprints" })).toBeVisible();

  await page.keyboard.press("Escape");
  await page.getByPlaceholder("Search serial, part number or label name").fill("");
  await page.getByRole("switch", { name: "Reprints only" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr").first()).toContainText(serial);
});
