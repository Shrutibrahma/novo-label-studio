import { expect, test } from "@playwright/test";
import { ADMIN, signIn } from "./support";

/** Flow 13.9 "Customize the label for one part", plus the default label editor (12.11). */
test("configure default label and a per-part override", async ({ page }) => {
  await signIn(page, ADMIN);

  // Default label: list card, editor, leave guard, publish v2.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Configure" }).click();
  await expect(page.getByRole("heading", { name: "Default label" })).toBeVisible();
  await expect(page.getByText(/Version 1 · published .* by Ada Admin/)).toBeVisible();
  await expect(page.getByText("All parts use the default label.")).toBeVisible();
  await page.getByRole("button", { name: "Edit default label" }).click();
  const publish = page.getByRole("button", { name: "Publish version 2" });
  await expect(publish).toBeDisabled(); // nothing changed yet
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByRole("menuitem", { name: "Revision" }).click();
  await expect(page.getByText("Fits")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("heading", { name: "Discard your changes?" })).toBeVisible();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page).toHaveURL(/\/configure\/default$/);
  await page.getByRole("radio", { name: "Medium 3 × 2 in" }).click();
  await expect(publish).toBeEnabled();
  await publish.click();
  await expect(page).toHaveURL(/\/configure$/);
  await expect(page.getByText(/Version 2 · published/)).toBeVisible();

  // 13.9: Part drawer → Label → "Customize for this part".
  await page.goto("/parts");
  await page.getByPlaceholder("Search part number, label name or description").fill("NP-10421");
  await page.getByRole("row", { name: /NP-10421/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Part" });
  await drawer.getByRole("tab", { name: "Label", exact: true }).click();
  await expect(drawer.getByText("Uses the default label")).toBeVisible();
  await expect(drawer.locator("p", { hasText: "Never printed" })).toBeVisible();
  await drawer.getByRole("button", { name: "Customize for this part" }).click();
  await expect(page).toHaveURL(/\/configure\/part\//);
  await expect(page.getByRole("heading", { name: "Custom label for NP-10421" })).toBeVisible();
  await expect(page.getByLabel("Preview with part")).toHaveAttribute("placeholder", /NP-10421/);

  // Add a Box sequence print-time field and put it on the label.
  await page.getByRole("button", { name: "Add print-time field" }).click();
  const dlg = page.getByRole("dialog", { name: "Add print-time field" });
  await dlg.getByLabel("Name").fill("Box");
  await dlg.getByLabel("Type").selectOption("box_sequence");
  await expect(dlg.getByLabel("Noun")).toHaveValue("BOX");
  await dlg.getByRole("button", { name: "Add print-time field" }).click();
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByRole("menuitem", { name: "Box" }).click();

  // Serial on, QR Serial (disabled until serial is on).
  const serialQr = page.getByRole("radio", { name: "Serial" });
  await expect(serialQr).toBeDisabled();
  await page.getByRole("switch", { name: "Serial number" }).click();
  await expect(serialQr).toBeEnabled();
  await serialQr.click();
  await expect(page.getByText("Serial assigned at print")).toBeVisible();
  await expect(page.getByText("Fits")).toBeVisible();
  await page.getByRole("button", { name: "Publish version 1" }).click();
  await expect(page).toHaveURL(/\/configure$/);
  await expect(page.getByRole("row", { name: /NP-10421/ })).toContainText("v1");

  // The part now shows its override; "Use default label" removes it.
  await page.goto("/parts");
  await page.getByPlaceholder("Search part number, label name or description").fill("NP-10421");
  await page.getByRole("row", { name: /NP-10421/ }).first().click();
  await drawer.getByRole("tab", { name: "Label", exact: true }).click();
  await expect(drawer.getByText("Custom label for this part · v1")).toBeVisible();
  await drawer.getByRole("button", { name: "Use default label" }).click();
  await expect(drawer.getByText("Uses the default label")).toBeVisible();

  // Put the override back for the print flows (box set in 05).
  await drawer.getByRole("button", { name: "Customize for this part" }).click();
  await page.getByRole("button", { name: "Add print-time field" }).click();
  await dlg.getByLabel("Name").fill("Box");
  await dlg.getByLabel("Type").selectOption("box_sequence");
  await dlg.getByRole("button", { name: "Add print-time field" }).click();
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByRole("menuitem", { name: "Box" }).click();
  await page.getByRole("switch", { name: "Serial number" }).click();
  await page.getByRole("radio", { name: "Serial" }).click();
  await page.getByRole("button", { name: "Publish version 2" }).click();
  await expect(page).toHaveURL(/\/configure$/);
});
