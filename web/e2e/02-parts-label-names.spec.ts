import { expect, test } from "@playwright/test";
import { ADMIN, signIn } from "./support";

const DECOYS: [string, string][] = [
  ["NP-10422", "Bearing Cap"],
  ["NP-20432", "10-32 nut"],
  ["SC-1032", "Socket cap screw 10-32 x 3/4"],
  ["HW-2", "Washer"],
];

/** Add part (12.9), custom fields (12.13), and flow 13.4 "Give a part a label name" + A8 searches. */
test("parts, custom field, and label-name search", async ({ page }) => {
  await signIn(page, ADMIN);
  for (const [part_number, part_name] of DECOYS) {
    const r = await page.request.post("/api/v1/parts", { data: { part_number, part_name } });
    expect(r.status()).toBe(201);
  }

  // Settings → Custom fields → Add field.
  await page.goto("/settings/custom-fields");
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByLabel("Name").fill("Material");
  await expect(page.getByLabel("Key")).toHaveValue("material");
  await page.getByRole("dialog").getByRole("button", { name: "Add field" }).click();
  await expect(page.getByRole("cell", { name: "material", exact: true })).toBeVisible();

  // Parts → Add part.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Parts" }).click();
  await expect(page).toHaveTitle("Parts · Novo Label Studio");
  await page.getByRole("button", { name: "Add part" }).click();
  const dialog = page.getByRole("dialog", { name: "Add part" });
  await dialog.getByLabel("Part number").fill("NP-10421");
  await dialog.getByLabel("Part name").fill("Bearing Housing");
  await dialog.getByLabel("Revision").fill("C");
  await dialog.getByLabel("Material").fill("Cast iron");
  await dialog.getByRole("button", { name: "Add part" }).click();
  await expect(dialog).toHaveCount(0);

  // Duplicate part number → field error + "Open it".
  await page.getByRole("button", { name: "Add part" }).click();
  await dialog.getByLabel("Part number").fill("np-10421");
  await dialog.getByLabel("Part name").fill("Dup");
  await dialog.getByRole("button", { name: "Add part" }).click();
  await expect(dialog.getByText("A part with this number already exists.")).toBeVisible();
  await dialog.getByRole("button", { name: "Open it" }).click();
  const drawer = page.getByRole("dialog", { name: "Part" });
  await expect(drawer.getByRole("heading", { name: "Bearing Housing" })).toBeVisible();
  await page.keyboard.press("Escape");

  // 13.4: Parts → search "NP-10421" → drawer → Label names → add "10-32 x 1/2 16".
  await page.getByPlaceholder("Search part number, label name or description").fill("NP-10421");
  await page.getByRole("row", { name: /NP-10421/ }).click();
  await drawer.getByRole("tab", { name: "Label names" }).click();
  await expect(drawer.getByText("Searching any of these names finds this part.")).toBeVisible();
  await drawer.getByPlaceholder("e.g. 10-32 x 1/2 16").fill("10-32 x 1/2 16");
  await expect(drawer.getByLabel("Use as label name")).toBeChecked();
  await drawer.getByRole("button", { name: "Add", exact: true }).click();
  await expect(drawer.getByText("Label name", { exact: true })).toBeVisible();
  await expect(drawer.getByRole("heading", { name: "10-32 x 1/2 16" })).toBeVisible();

  // An alias that's another part's number is rejected with the 14.2 message.
  await drawer.getByPlaceholder("e.g. 10-32 x 1/2 16").fill("HW-2");
  await drawer.getByRole("button", { name: "Add", exact: true }).click();
  await expect(drawer.getByText("This name is another part's part number.")).toBeVisible();
  await page.keyboard.press("Escape");

  // A8: every alias form finds the part first on Print Labels.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Print Labels" }).click();
  const search = page.getByPlaceholder("Search part number, label name or description");
  for (const q of ["10-32", "10 32 x 1/2 16", "NP-104"]) {
    await search.fill(q);
    const first = page.locator("tbody tr").first();
    await expect(first).toContainText("NP-10421");
    await expect(first).toContainText("10-32 x 1/2 16");
    await expect(first).toContainText("Never printed");
  }
  await search.fill("zzz-nothing");
  await expect(page.getByText('No parts match "zzz-nothing"')).toBeVisible();

  // `/` focuses the page search.
  await search.fill("");
  await page.locator("body").click();
  await page.keyboard.press("/");
  await expect(search).toBeFocused();
});
