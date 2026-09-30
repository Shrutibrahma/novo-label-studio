import { expect, test } from "@playwright/test";
import { agentJobFiles, loadState, OPERATOR, simStatus, signIn, startAgent } from "./support";

const search = (page: import("@playwright/test").Page) => page.getByPlaceholder("Search part number, label name or description");

test.beforeAll(() => {
  const { agentToken } = loadState();
  if (agentToken) startAgent(agentToken); // already running when 01 ran in this worker
});

/** Flows 13.5 (print one label, operator), 13.6 (box set), 13.7 (batch), 13.10 (printer problem). */
test("print, box set, batch and printer problems", async ({ page }) => {
  await signIn(page, OPERATOR);
  await expect(page.getByRole("button", { name: /ZQ630 Plus/ })).toContainText("Ready", { timeout: 30_000 });

  // 13.5: search → row → Print. The first print asks to confirm the loaded size.
  await search(page).fill("Imported part 2");
  const row = page.getByRole("row", { name: /IM-002/ });
  await row.getByRole("button", { name: "Print" }).click();
  const dialog = page.getByRole("dialog", { name: "Print" });
  await expect(dialog.getByTestId("label-preview").getByRole("img")).toBeVisible();
  const printBtn = dialog.getByRole("button", { name: /^Print/ }).last();
  await expect(dialog.getByText(/The printer has .* labels loaded\. This label is Medium\./)).toBeVisible();
  await expect(printBtn).toBeDisabled();
  await dialog.getByRole("button", { name: "I've loaded Medium labels" }).click();
  await expect(printBtn).toBeEnabled();
  const before = agentJobFiles().length;
  await printBtn.click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(before + 1);
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(row).toContainText("Current");

  // 13.6: NP-10421 has a Box sequence + serial (from 04). "Print all 3 boxes" → 3 labels, 3 serials.
  await search(page).fill("NP-10421");
  await page.getByRole("row", { name: /NP-10421/ }).getByRole("button", { name: "Print" }).click();
  await expect(dialog.getByText("Print all 1 boxes")).toBeVisible();
  await dialog.getByRole("button", { name: "Increase Total boxes" }).click();
  await dialog.getByRole("button", { name: "Increase Total boxes" }).click();
  await expect(dialog.getByText("Print all 3 boxes")).toBeVisible();
  await expect(dialog.getByText("3 labels · 3 serials")).toBeVisible();
  await dialog.getByRole("button", { name: "Print 3 labels" }).click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await expect(dialog.locator(".t-mono").filter({ hasText: /^NOVO-\d{8}$/ })).toHaveCount(3);

  // Alternative: one box at a time → "Print box 2 of 3" → "Print box 3 of 3".
  await dialog.getByRole("button", { name: "Print another" }).click();
  await dialog.getByLabel("Print one box").check();
  await dialog.getByRole("button", { name: "Print", exact: true }).click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await dialog.getByRole("button", { name: "Print box 2 of 3" }).click();
  await expect(dialog.getByRole("button", { name: "Print box 3 of 3" })).toBeVisible();
  await dialog.getByRole("button", { name: "Print box 3 of 3" }).click();
  await expect(dialog.getByRole("button", { name: /Print box \d of 3/ })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Done" }).click();

  // 13.7: tick rows → "Print selected" → one job.
  await search(page).fill("Imported part");
  for (const n of ["IM-003", "IM-004", "IM-005"]) await page.getByLabel(`Select ${n}`).check();
  await expect(page.getByText("3 selected")).toBeVisible();
  await page.getByRole("button", { name: "Print selected" }).click();
  await expect(dialog.getByText("1 of 3")).toBeVisible();
  await dialog.getByRole("button", { name: "Next label" }).click();
  await expect(dialog.getByText("2 of 3")).toBeVisible();
  const beforeBatch = agentJobFiles().length;
  await dialog.getByRole("button", { name: "Print 3 labels" }).click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(beforeBatch + 1);
  await dialog.getByRole("button", { name: "Done" }).click();

  // 13.10: printer runs out of labels → red "Out of labels", Print disabled with the 14.2 message.
  await simStatus("out_of_media");
  const status = page.getByRole("button", { name: /ZQ630 Plus/ });
  await expect(status).toContainText("Out of labels", { timeout: 20_000 });
  await search(page).fill("IM-006");
  const blocked = page.getByRole("row", { name: /IM-006/ }).getByRole("button", { name: "Print" });
  await expect(blocked).toBeDisabled();
  // Wait for the search results to settle (IM-006 ranked first) so the row doesn't move out from under the mouse.
  await expect(page.getByRole("row").nth(1)).toContainText("IM-006");
  await blocked.locator("..").hover();
  await expect(page.getByRole("tooltip")).toHaveText("The printer is out of labels.");
  await simStatus("ready");
  await expect(status).toContainText("Ready", { timeout: 20_000 });
  await expect(blocked).toBeEnabled();
});
