import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

import { ADVISEUR, inloggen, klantMetProfiel } from "./hulp";

test("van klant tot adviesrapport", async ({ page }) => {
  test.setTimeout(120_000);
  await inloggen(page, ADVISEUR);
  const naam = `Klant ${Date.now()}`;
  await klantMetProfiel(page, naam, { doel: "200000", koopkracht: true });

  // Startvoorstel past binnen het profiel.
  await page.getByRole("link", { name: "Portefeuille samenstellen" }).click();
  await expect(page.getByTestId("totaal")).toHaveText("100%");
  await expect(page.getByText("past binnen het risicoprofiel")).toBeVisible();

  // Historische analyse en scenario's worden berekend.
  const historie = page.locator("section", { has: page.getByRole("heading", { name: "Historische analyse" }) });
  await expect(historie.getByText("In het verleden behaalde resultaten")).toBeVisible();
  await expect(historie.getByText("Stresstest: de huidige samenstelling")).toBeVisible();
  const toekomst = page.locator("section", { has: page.getByRole("heading", { name: "Verwacht rendement" }) });
  await expect(toekomst.getByText("zoals afgesproken in het klantprofiel")).toBeVisible();
  await expect(toekomst.getByText("Zware crisis", { exact: true })).toBeVisible();

  // Een afwijking van het profiel vraagt om een toelichting.
  const totaalAandelen = await page.getByLabel("Gewicht iShares Core MSCI World UCITS ETF (Acc)").inputValue();
  await page.getByLabel("Gewicht iShares Core MSCI World UCITS ETF (Acc)").fill(String(Number(totaalAandelen) + 20));
  await expect(page.getByText(/De gewichten tellen op tot 120%/)).toBeVisible();
  const vastleggen = page.getByRole("button", { name: "Portefeuille vastleggen" });
  await expect(vastleggen).toBeDisabled();
  await page.getByRole("button", { name: "Nieuw startvoorstel" }).click();
  await expect(page.getByText("past binnen het risicoprofiel")).toBeVisible();

  // Vastleggen en rapport opstellen.
  await page.getByLabel("Overige kosten % per jaar (advies, beheer, bewaring)").fill("0,5");
  await expect(vastleggen).toBeEnabled();
  await vastleggen.click();
  await expect(page.getByText("Versie 1 is vastgelegd.")).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Rapport (PDF)" }).click(),
  ]);
  const pdf = await readFile(await download.path());
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(download.suggestedFilename()).toBe("adviesrapport-versie-1-1.pdf");

  // Het rapport staat bij de klant, als concept met de redenen.
  await page.getByRole("link", { name: `← ${naam}` }).click();
  const rapporten = page.locator("section", { has: page.getByRole("heading", { name: "Adviesrapporten" }) });
  await expect(rapporten.getByText("Concept: niet aan de klant geven")).toBeVisible();
  await expect(rapporten.getByText(/voorbeeldaannames/)).toBeVisible();
});

test("een defensiever profiel kiezen vraagt een toelichting en blijft bij herzien staan", async ({ page }) => {
  await inloggen(page, ADVISEUR);
  const naam = `Voorzichtig ${Date.now()}`;
  await page.getByLabel("Naam nieuwe klant").fill(naam);
  await page.getByRole("button", { name: "Klant toevoegen" }).click();
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  await page.getByLabel("Beleggingsdoel").fill("Vermogensopbouw");
  await page.getByLabel("Horizon (jaren)").fill("20");
  await page.getByLabel("Inleg (€)").fill("50000");
  const { vragenlijstInvullen } = await import("./hulp");
  await vragenlijstInvullen(page, 2);
  await expect(page.getByText("Afgeleid profiel: Offensief")).toBeVisible();
  await page.getByLabel("Werken met een defensiever profiel (optioneel)").selectOption("neutraal");
  // Zonder toelichting houdt de browser het verzenden tegen: het veld is verplicht.
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  const toelichting = page.getByLabel("Waarom wordt afgeweken?");
  expect(await toelichting.evaluate((el) => (el as HTMLTextAreaElement).validity.valueMissing)).toBe(true);
  await expect(page.getByText(/versie 1, vastgelegd op/)).toHaveCount(0);
  await page.getByLabel("Waarom wordt afgeweken?").fill("Klant wil minder schommelingen");
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  await expect(page.getByText("Afgeleid profiel was Offensief")).toBeVisible();

  await page.getByRole("button", { name: "Profiel herzien" }).click();
  await expect(page.getByLabel("Werken met een defensiever profiel (optioneel)")).toHaveValue("neutraal");
  await expect(page.getByLabel("Waarom wordt afgeweken?")).toHaveValue("Klant wil minder schommelingen");
});

test("duurzaamheidswensen: toets bevestigen haalt dat conceptpunt weg", async ({ page }) => {
  test.setTimeout(120_000);
  await inloggen(page, ADVISEUR);
  const naam = `Duurzaam ${Date.now()}`;
  await klantMetProfiel(page, naam);
  await page.getByRole("button", { name: "Profiel herzien" }).click();
  await page.getByLabel("Voorkeur voor duurzaam beleggen").selectOption("sterk");
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  await expect(page.getByText(/versie 2, vastgelegd op/)).toBeVisible();

  await page.getByRole("link", { name: "Portefeuille samenstellen" }).click();
  await expect(page.getByText("past binnen het risicoprofiel")).toBeVisible();
  const toets = page.getByLabel(/Getoetst aan de duurzaamheidswensen/);
  await toets.fill("Alle fondsen hebben een SFDR artikel 8-label volgens het EID");
  await page.getByRole("button", { name: "Portefeuille vastleggen" }).click();
  await expect(page.getByText("Versie 1 is vastgelegd.")).toBeVisible();
  await page.getByRole("button", { name: "Rapport (PDF)" }).click();
  await page.getByRole("link", { name: `← ${naam}` }).click();
  const rapporten = page.locator("section", { has: page.getByRole("heading", { name: "Adviesrapporten" }) });
  await expect(rapporten.getByText(/voorbeeldaannames/)).toBeVisible();
  await expect(rapporten.getByText(/duurzaamheidswensen/)).toHaveCount(0);
});
