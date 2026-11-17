import { expect, test } from "@playwright/test";

import { BEHEERDER_1, inloggen, totpCode, uitloggen } from "./hulp";

test("nieuwe adviseur: tijdelijk wachtwoord, eigen wachtwoord kiezen en tweestapsverificatie", async ({ page }) => {
  test.setTimeout(90_000);
  const email = `nieuw${Date.now()}@voorbeeld.nl`;
  const eigen = "mijn-eigen-sterke-wachtwoord";

  // Beheerder maakt het account aan; het tijdelijke wachtwoord wordt één keer getoond.
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Gebruikers" }).click();
  await page.getByLabel("Naam", { exact: true }).fill("Nieuwe Adviseur");
  await page.getByLabel("E-mailadres").fill(email);
  await page.getByRole("button", { name: "Account aanmaken" }).click();
  const tijdelijk = await page.getByTestId("tijdelijk-wachtwoord").innerText();
  expect(tijdelijk).toHaveLength(16);
  await expect(page.getByRole("row", { name: /Nieuwe Adviseur/ })).toContainText("tijdelijk wachtwoord");
  await uitloggen(page);

  // Eerste keer inloggen: eerst een eigen wachtwoord kiezen.
  await page.getByLabel("E-mailadres").fill(email);
  await page.getByLabel("Wachtwoord").fill(tijdelijk);
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page.getByRole("heading", { name: "Kies een eigen wachtwoord" })).toBeVisible();
  await page.getByLabel("Tijdelijk wachtwoord").fill(tijdelijk);
  await page.getByLabel("Nieuw wachtwoord (minimaal 12 tekens)").fill(eigen);
  await page.getByLabel("Herhaal nieuw wachtwoord").fill(eigen);
  await page.getByRole("button", { name: "Wachtwoord opslaan" }).click();
  await expect(page.getByRole("heading", { name: "Klanten" })).toBeVisible();

  // Tweestapsverificatie aanzetten.
  await page.getByRole("link", { name: "Mijn account" }).click();
  await page.getByRole("button", { name: "Tweestapsverificatie aanzetten" }).click();
  await expect(page.locator(".qr svg")).toBeVisible();
  const geheim = await page.getByTestId("totp-geheim").innerText();
  await page.getByLabel("Code uit de app").fill("000000");
  await page.getByRole("button", { name: "Bevestigen" }).click();
  await expect(page.getByRole("alert")).toHaveText("Onjuiste code");
  await page.getByLabel("Code uit de app").fill(totpCode(geheim));
  await page.getByRole("button", { name: "Bevestigen" }).click();
  await expect(page.getByText("Tweestapsverificatie staat aan.")).toBeVisible();
  await uitloggen(page);

  // Inloggen vraagt nu ook een code; een gebruikte code werkt geen tweede keer.
  await page.getByLabel("E-mailadres").fill(email);
  await page.getByLabel("Wachtwoord").fill(eigen);
  await page.getByRole("button", { name: "Inloggen" }).click();
  const codeVeld = page.getByLabel("Code uit uw authenticator-app");
  await expect(codeVeld).toBeVisible();
  await codeVeld.fill(totpCode(geheim, 1));
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page.getByRole("heading", { name: "Klanten" })).toBeVisible();
});

test("beheerder maken gaat via een voorstel", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Gebruikers" }).click();
  const rij = page.getByRole("row", { name: /Anna Adviseur/ });
  await rij.getByRole("button", { name: "Beheerder maken" }).click();
  await expect(page.getByText("Voorstel ingediend; een tweede beheerder moet het goedkeuren.")).toBeVisible();
  const wacht = page.locator("section", { has: page.getByRole("heading", { name: "Wacht op goedkeuring" }) });
  await expect(wacht.getByText("Account adviseur@voorbeeld.nl")).toBeVisible();
  await expect(wacht.getByText("Rol: adviseur → beheerder")).toBeVisible();
  await expect(rij).toContainText("Adviseur");
  // Intrekken, zodat de andere tests met een gewone adviseur blijven werken.
  page.once("dialog", (d) => d.accept("Toch niet"));
  await wacht.getByRole("button", { name: "Intrekken" }).click();
  await expect(page.getByRole("heading", { name: "Wacht op goedkeuring" })).toHaveCount(0);
});
