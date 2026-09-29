import { expect, test, type Page } from "@playwright/test";
import { ADMIN, signIn } from "./support";

function csv(rows: string[][]): Buffer {
  return Buffer.from(rows.map((r) => r.join(",")).join("\r\n") + "\r\n", "utf8");
}

async function uploadFile(page: Page, name: string, body: Buffer) {
  await page.goto("/parts/import");
  await expect(page.getByRole("heading", { name: "Give us your parts list" })).toBeVisible();
  await expect(page.getByText("CSV · XLSX · XLS · up to 20 MB")).toBeVisible();
  await page.getByLabel("Choose file").setInputFiles({ name, mimeType: "text/csv", buffer: body });
}

/** Flows 13.2 (first import) and 13.3 (re-import after a revision change). */
test("first import then re-import", async ({ page }) => {
  await signIn(page, ADMIN);

  const first = [["PART_NO", "Name", "Description", "Rev", "Material"]];
  for (let i = 1; i <= 40; i++) first.push([`IM-${String(i).padStart(3, "0")}`, `Imported part ${i}`, `Batch one ${i}`, "C", "Steel"]);
  first.push(["", "No number", "", "A", ""]); // row 42: invalid, fixed below
  first.push(["IM-900", "", "Missing name", "A", ""]); // row 43: invalid, left skipped
  await uploadFile(page, "NovoParts.csv", csv(first));

  // Match columns: synonyms suggested; name the mapping.
  await expect(page.getByRole("columnheader", { name: "Column in your file" })).toBeVisible();
  await expect(page.getByLabel("Maps to for PART_NO")).toHaveValue("part_number");
  await expect(page.getByLabel("Maps to for Name")).toHaveValue("part_name");
  await expect(page.getByLabel("Maps to for Material")).toHaveValue("material");
  await page.getByLabel("Maps to for Name").selectOption("");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Map a column to Part Number and Part Name to continue.")).toBeVisible();
  await page.getByLabel("Maps to for Name").selectOption("part_name");
  await expect(page.getByLabel("Save this mapping as")).toHaveValue("NovoParts");
  await page.getByLabel("Save this mapping as").fill("Novo master list");
  await page.getByRole("button", { name: "Continue" }).click();

  // Review: 40 new, 2 need attention.
  await expect(page.getByRole("button", { name: /New\s*40/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Need attention\s*2/ })).toBeVisible();
  await page.getByRole("button", { name: /Need attention/ }).click();
  await expect(page.getByText("Part number is missing.")).toBeVisible();
  await expect(page.getByText("Part name is missing.")).toBeVisible();
  const fixRow = page.getByRole("row", { name: /Part number is missing/ });
  await fixRow.getByRole("button", { name: "Fix" }).click();
  await page.getByRole("dialog").getByLabel("Part number").fill("IM-041");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: /Need attention\s*1/ })).toBeVisible();
  await page.getByRole("button", { name: "Import 41 parts" }).click();

  await expect(page.getByRole("heading", { name: "Import complete" })).toBeVisible();
  await expect(page.getByText("41 new · 0 updated · 0 marked inactive")).toBeVisible();
  await expect(page.getByText("1 rows skipped because of errors.")).toBeVisible();
  await page.getByRole("button", { name: "View parts" }).click();
  await expect(page).toHaveURL(/\/parts$/);
  await expect(page.getByRole("row", { name: /IM-001/ })).toBeVisible();

  // 13.3: the saved mapping applies automatically; one revision change and missing parts unticked.
  const second = [["PART_NO", "Name", "Description", "Rev", "Material"]];
  for (let i = 1; i <= 38; i++) second.push([`IM-${String(i).padStart(3, "0")}`, `Imported part ${i}`, "", i === 1 ? "D" : "C", ""]);
  await uploadFile(page, "NovoParts.csv", csv(second));
  await expect(page.getByText("Using saved mapping: Novo master list")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("button", { name: /Updated\s*1/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Missing from file\s*\d+/ })).toBeVisible();
  await page.getByRole("button", { name: /Updated/ }).click();
  await expect(page.getByText(/revision:\s*C\s*→\s*D/)).toBeVisible();
  await page.getByRole("button", { name: /Missing from file/ }).click();
  const markInactive = page.getByLabel("Mark as inactive").first();
  await expect(markInactive).not.toBeChecked();
  await page.getByRole("button", { name: "Import 1 parts" }).click();
  await expect(page.getByText("0 new · 1 updated · 0 marked inactive")).toBeVisible();
  await page.getByRole("button", { name: "Print out-of-date labels" }).click();
  await expect(page).toHaveURL(/\/print\?filter=out_of_date$/);
  await expect(page.getByRole("radio", { name: "Out of date" })).toHaveAttribute("aria-checked", "true");
});
