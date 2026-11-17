import { expect, test } from "@playwright/test";

import { ADVISEUR, BEHEERDER_1, inloggen, uitloggen } from "./hulp";

test("verkeerd wachtwoord geeft een melding zonder te verraden of het adres bestaat", async ({ page }) => {
  await page.goto("/");
  for (const email of [ADVISEUR, "bestaat-niet@voorbeeld.nl"]) {
    await page.getByLabel("E-mailadres").fill(email);
    await page.getByLabel("Wachtwoord").fill("een-verkeerd-wachtwoord");
    await page.getByRole("button", { name: "Inloggen" }).click();
    await expect(page.getByRole("alert")).toHaveText("Onjuist e-mailadres of wachtwoord");
  }
});

test("inloggen, rol zien en uitloggen", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await expect(page.locator(".wie")).toContainText("Bea Beheer");
  await expect(page.locator(".wie")).toContainText("Beheerder");
  await uitloggen(page);

  await inloggen(page, ADVISEUR);
  await expect(page.locator(".wie")).toContainText("Anna Adviseur");
  await expect(page.locator(".wie")).not.toContainText("Beheerder");
});

test("sessie blijft na herladen bestaan", async ({ page }) => {
  await inloggen(page, ADVISEUR);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Klanten" })).toBeVisible();
});
