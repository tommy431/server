import { expect, test } from "@playwright/test";

import { ADVISEUR, geenHorizontaleScroll, inloggen, klantMetProfiel } from "./hulp";

test.use({ viewport: { width: 375, height: 800 } });

test("schermen passen op een telefoon", async ({ page }) => {
  test.setTimeout(90_000);
  await inloggen(page, ADVISEUR);
  await geenHorizontaleScroll(page);
  await klantMetProfiel(page, `Telefoon ${Date.now()}`, { doel: "150000" });
  await geenHorizontaleScroll(page);
  await page.getByRole("link", { name: "Portefeuille samenstellen" }).click();
  await expect(page.getByText("In het verleden behaalde resultaten")).toBeVisible();
  await expect(page.getByText("zoals afgesproken in het klantprofiel")).toBeVisible();
  await geenHorizontaleScroll(page);
  for (const pad of ["/modelallocaties", "/aannames", "/data"]) {
    await page.goto(pad);
    await page.waitForLoadState("networkidle");
    await geenHorizontaleScroll(page);
  }
});
