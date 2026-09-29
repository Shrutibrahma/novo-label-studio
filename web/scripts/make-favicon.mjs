// Renders the product mark (11.6: Tag icon, white, in a #2563EB rounded-6 square) as the 32 px favicon.
// Run once with `node scripts/make-favicon.mjs`; the PNG is committed to public/.
import { chromium } from "@playwright/test";
import { Tag } from "lucide-react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";

const SCALE = 32 / 28; // the 28 px mark scaled to a 32 px favicon
const svg = renderToStaticMarkup(createElement(Tag, { size: 20 * SCALE, color: "#FFFFFF", strokeWidth: 1.75 }));
const html = `<html><body style="margin:0;background:transparent">
<div id="mark" style="width:32px;height:32px;border-radius:${6 * SCALE}px;background:#2563EB;display:flex;align-items:center;justify-content:center">${svg}</div>
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });
await page.setContent(html);
await page.locator("#mark").screenshot({ path: fileURLToPath(new URL("../public/favicon.png", import.meta.url)), omitBackground: true });
await browser.close();
