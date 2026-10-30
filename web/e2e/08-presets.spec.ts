import { expect, test } from "@playwright/test";
import { ADMIN, signIn } from "./support";

const PRESETS = ["Part label", "Bin label", "Kanban card", "Rack location", "Quality tag", "Box label"];

/** Flow 13.12 (v1.1 U3): create a label type from each preset and open its design: no warnings. */
test("label types from the industrial presets", async ({ page }) => {
  await signIn(page, ADMIN);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Configure" }).click();
  for (const name of PRESETS) {
    await page.getByRole("button", { name: "New type" }).click();
    const dialog = page.getByRole("dialog", { name: "New label type" });
    const start = dialog.getByLabel("Start from");
    const value = await start.locator("option", { hasText: `${name} (` }).first().getAttribute("value");
    await start.selectOption(value ?? "");
    await expect(dialog.getByLabel("Name")).toHaveValue(name);
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText(`Label type ${name} created`)).toBeVisible();
    await expect(page.getByRole("tab", { name: new RegExp(`^${name}`) })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("button", { name: "Edit default label" }).click();
    await expect(page.getByText("Ready to publish")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page).toHaveURL(/\/configure$/);
  }
});
