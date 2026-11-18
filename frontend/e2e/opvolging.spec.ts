import { expect, test } from "@playwright/test";

import { ADVISEUR, geenHorizontaleScroll, inloggen, klantMetProfiel } from "./hulp";

test("bezit vastleggen, vergelijken met het advies en evalueren", async ({ page }) => {
  test.setTimeout(120_000);
  await inloggen(page, ADVISEUR);
  const naam = `Opvolging ${Date.now()}`;
  await klantMetProfiel(page, naam);

  // Zonder advies: alleen het signaal dat er nog geen portefeuille is.
  await page.getByRole("link", { name: "Opvolging" }).click();
  await expect(page.getByText("nog geen portefeuille geadviseerd")).toBeVisible();

  await page.getByRole("link", { name: `← ${naam}` }).click();
  await page.getByRole("link", { name: "Portefeuille samenstellen" }).click();
  await expect(page.getByText("past binnen het risicoprofiel")).toBeVisible();
  await page.getByLabel("Overige kosten % per jaar (advies, beheer, bewaring)").fill("0,5");
  await page.getByRole("button", { name: "Portefeuille vastleggen" }).click();
  await expect(page.getByText("Versie 1 is vastgelegd.")).toBeVisible();

  await page.getByRole("link", { name: `← ${naam}` }).click();
  await page.getByRole("link", { name: "Opvolging" }).click();
  await expect(page.getByText("Het werkelijke bezit is nog niet vastgelegd")).toBeVisible();

  // Alles in één aandelenfonds plus wat geld: buiten de bandbreedtes.
  await page.getByRole("button", { name: "Bezit vastleggen" }).click();
  await page.getByLabel("Aantal iShares Core MSCI World UCITS ETF (Acc)").fill("500");
  await page.getByLabel("Geldsaldo op de beleggingsrekening (€)").fill("1000");
  await page.getByRole("button", { name: "Opslaan" }).click();

  await expect(page.getByText(/Aandelen weegt .* valt buiten/)).toBeVisible();
  const voorstel = page.locator("section", { has: page.getByRole("heading", { name: "Herbalanceringsvoorstel" }) });
  await expect(voorstel.getByRole("cell", { name: "Verkopen" }).first()).toBeVisible();
  await expect(voorstel.getByRole("cell", { name: "Kopen" }).first()).toBeVisible();

  // Het signaal staat ook in het overzicht.
  await page.getByRole("link", { name: "Signalen" }).click();
  const kaart = page.locator("section", { has: page.getByRole("link", { name: naam }) });
  await expect(kaart.getByText(/valt buiten/).first()).toBeVisible();
  await kaart.getByRole("link", { name: naam }).click();

  // Evaluatie vastleggen.
  await page.getByLabel("Uitkomst").selectOption("herbalanceren");
  await page.getByLabel("Notitie (wat is besproken, wat is afgesproken)").fill("Klant akkoord met herbalanceren");
  await page.getByRole("button", { name: "Evaluatie vastleggen" }).click();
  await expect(page.getByRole("cell", { name: "Klant akkoord met herbalanceren" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Herbalanceren afgesproken" })).toBeVisible();

  if (process.env.SCHERMAFDRUK) await page.screenshot({ path: `${process.env.SCHERMAFDRUK}/opvolging.png`, fullPage: true });

  // Ook op een telefoon leesbaar zonder horizontaal te schuiven.
  await page.setViewportSize({ width: 375, height: 800 });
  await geenHorizontaleScroll(page);
  if (process.env.SCHERMAFDRUK) await page.screenshot({ path: `${process.env.SCHERMAFDRUK}/opvolging-telefoon.png`, fullPage: true });
});

test("bezit inlezen uit een depotoverzicht", async ({ page }) => {
  test.setTimeout(120_000);
  await inloggen(page, ADVISEUR);
  const naam = `Inlezen ${Date.now()}`;
  await klantMetProfiel(page, naam);
  await page.getByRole("link", { name: "Portefeuille samenstellen" }).click();
  await expect(page.getByText("past binnen het risicoprofiel")).toBeVisible();
  await page.getByLabel("Overige kosten % per jaar (advies, beheer, bewaring)").fill("0,5");
  await page.getByRole("button", { name: "Portefeuille vastleggen" }).click();
  await expect(page.getByText("Versie 1 is vastgelegd.")).toBeVisible();
  await page.getByRole("link", { name: `← ${naam}` }).click();
  await page.getByRole("link", { name: "Opvolging" }).click();

  await page.getByRole("button", { name: "Bezit vastleggen" }).click();
  const csv = "Product;ISIN;Aantal;Waarde\nWereld;IE00B4L5Y983;1.250;122.650,00\nApple;US0378331005;10;2.000,00\nTotaal;;;124.650,00\n";
  await page.getByLabel("Depotoverzicht inlezen (CSV, optioneel)").setInputFiles({
    name: "depot.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "latin1"),
  });
  await expect(page.getByText("2 positie(s) ingelezen uit depot.csv")).toBeVisible();
  await expect(page.getByText(/buiten de fondsenlijst zijn als overig bezit opgenomen/)).toBeVisible();
  await expect(page.getByLabel("Aantal iShares Core MSCI World UCITS ETF (Acc)")).toHaveValue("1250");

  // Apple staat niet in de fondsenlijst: overig bezit met de waarde uit de export.
  const apple = page.getByRole("group", { name: "Overig 1" });
  await expect(apple.getByLabel("Omschrijving")).toHaveValue("Apple");
  await expect(apple.getByLabel("ISIN (optioneel)")).toHaveValue("US0378331005");
  await expect(apple.getByLabel("Waarde (€)")).toHaveValue("2000");
  await apple.getByLabel("Categorie").selectOption("aandelen");
  await page.getByRole("button", { name: "Opslaan" }).click();

  await expect(page.getByRole("cell", { name: "1.250" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Apple \(overig, waarde opgegeven\)/ })).toBeVisible();
  await expect(page.getByText("Apple (overig bezit) zit niet in het advies")).toBeVisible();
  const voorstel = page.locator("section", { has: page.getByRole("heading", { name: "Herbalanceringsvoorstel" }) });
  await expect(voorstel.getByRole("row", { name: /Verkopen Apple alles ≈ € 2\.000/ })).toBeVisible();

  // Behouden: geen signaal en geen verkoop meer.
  await page.getByRole("button", { name: "Nieuwe opgave" }).click();
  await page.getByRole("group", { name: "Overig 1" }).getByLabel("Behouden").check();
  await page.getByRole("button", { name: "Opslaan" }).click();
  await expect(page.getByRole("cell", { name: /Apple \(overig, behouden/ })).toBeVisible();
  await expect(page.getByText("Apple (overig bezit) zit niet in het advies")).toHaveCount(0);
  await expect(voorstel.getByRole("row", { name: /Apple/ })).toHaveCount(0);
  if (process.env.SCHERMAFDRUK) {
    await page.screenshot({ path: `${process.env.SCHERMAFDRUK}/overig.png`, fullPage: true });
    await page.setViewportSize({ width: 375, height: 800 });
    await page.getByRole("button", { name: "Nieuwe opgave" }).click();
    await geenHorizontaleScroll(page);
    await page.screenshot({ path: `${process.env.SCHERMAFDRUK}/overig-formulier-telefoon.png`, fullPage: true });
  }
});
