import { expect, test } from "@playwright/test";
import { ADMIN, agentJobFiles, loadState, signIn, startAgent } from "./support";

test.beforeAll(() => {
  const { agentToken } = loadState();
  if (agentToken) startAgent(agentToken);
});

/** Flow 13.13 (v1.1 U4): create the Workstation sign quick label, print "CELL 4", reprint it from History. */
test("quick label: workstation sign", async ({ page }) => {
  await signIn(page, ADMIN);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Configure" }).click();
  await page.getByRole("button", { name: "New type" }).click();
  const create = page.getByRole("dialog", { name: "New label type" });
  await create.getByRole("radio", { name: "Quick label (no part)" }).click();
  const start = create.getByLabel("Start from");
  await start.selectOption((await start.locator("option", { hasText: "Workstation sign (" }).first().getAttribute("value")) ?? "");
  await expect(create.getByLabel("Name")).toHaveValue("Workstation sign");
  await create.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Label type Workstation sign created")).toBeVisible();
  await expect(page.getByText("Quick labels", { exact: true })).toBeVisible();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Print Labels" }).click();
  await page.getByRole("button", { name: "Quick label" }).click();
  const dialog = page.getByRole("dialog", { name: "Quick label" });
  await dialog.getByLabel("Station").fill("CELL 4");
  await expect(dialog.getByTestId("label-preview").getByRole("img")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: /^I've loaded/ });
  if (await confirm.isVisible()) await confirm.click();
  const before = agentJobFiles().length;
  await dialog.getByRole("button", { name: "Print", exact: true }).click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(before + 1);
  await dialog.getByRole("button", { name: "Done" }).click();

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "History" }).click();
  await page.getByRole("switch", { name: "Quick labels" }).click();
  const row = page.locator("tbody tr").first();
  await expect(row).toContainText("Quick label · Workstation sign");
  await row.click();
  const drawer = page.getByRole("dialog", { name: "Printed label" });
  await expect(drawer.getByText("CELL 4")).toBeVisible();
  const beforeReprint = agentJobFiles().length;
  await drawer.getByRole("button", { name: "Reprint exact label" }).click();
  const reprint = page.getByRole("dialog", { name: "Reprint exact label" });
  await reprint.getByLabel("Damaged").check();
  await reprint.getByRole("button", { name: "Print" }).click();
  await expect(page.getByText("Sent to printer").first()).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(beforeReprint + 1);
});
