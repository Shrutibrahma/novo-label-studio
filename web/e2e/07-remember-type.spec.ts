import { expect, test, type Locator, type Page } from "@playwright/test";
import { ADMIN, agentJobFiles, loadState, OPERATOR, signIn, signOut, startAgent } from "./support";

const search = (page: Page) => page.getByPlaceholder("Search part number, label name or description");

test.beforeAll(() => {
  const { agentToken } = loadState();
  if (agentToken) startAgent(agentToken);
});

async function printIn(dialog: Locator): Promise<void> {
  const confirm = dialog.getByRole("button", { name: /^I've loaded/ });
  if (await confirm.isVisible()) await confirm.click();
  const before = agentJobFiles().length;
  await dialog.getByRole("button", { name: /^Print/ }).last().click();
  await expect(dialog.getByText("Sent to printer")).toBeVisible();
  await expect.poll(() => agentJobFiles().length).toBe(before + 1);
  await dialog.getByRole("button", { name: "Done" }).click();
}

/** Flow 13.11 (v1.1 U2): the part remembers its label type. */
test("a part remembers its label type", async ({ page }) => {
  await signIn(page, ADMIN);
  const created = await page.request.post("/api/v1/label-types", { data: { name: "Bin" } });
  expect(created.status()).toBe(201);
  await page.reload(); // the type list is cached for 30 s; Configure refreshes it, an API call doesn't

  // Admin: "Always print NP-10421 as Bin" in the Print dialog.
  await search(page).fill("NP-10421");
  await page.getByRole("row", { name: /NP-10421/ }).getByRole("button", { name: "Print" }).click();
  const dialog = page.getByRole("dialog", { name: "Print" });
  await dialog.getByRole("radiogroup", { name: "Label type" }).getByRole("radio", { name: "Bin" }).click();
  await dialog.getByLabel("Always print NP-10421 as Bin").check();
  await printIn(dialog);
  await signOut(page);

  // Operator: the row shows Bin; the dialog opens with Bin; History names the type.
  await signIn(page, OPERATOR);
  await expect(page.getByText("Print as (for parts without a saved type)")).toBeVisible();
  await search(page).fill("NP-10421");
  const row = page.getByRole("row", { name: /NP-10421/ });
  await expect(row.getByText("Bin", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Print" }).click();
  await expect(dialog.getByRole("radiogroup", { name: "Label type" }).getByRole("radio", { name: "Bin" })).toHaveAttribute("aria-checked", "true");
  await expect(dialog.getByLabel("Always print NP-10421 as Bin")).toHaveCount(0); // admins only
  await printIn(dialog);
  const history = await (await page.request.get("/api/v1/history?q=NP-10421&limit=1")).json();
  expect(history.items[0].label_type).toBe("Bin");
});
