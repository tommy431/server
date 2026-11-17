import { expect, test } from "@playwright/test";

import { ADVISEUR, BEHEERDER_1, BEHEERDER_2, inloggen, uitloggen } from "./hulp";

// Werkt met het profiel "zeer offensief", zodat de andere tests er geen last van hebben.
const KAART = { name: "Zeer offensief", exact: true };

test("adviseur ziet modelallocaties en aannames alleen-lezen", async ({ page }) => {
  await inloggen(page, ADVISEUR);
  await page.getByRole("link", { name: "Modelallocaties" }).click();
  await expect(page.getByText("Alleen een beheerder kan de modelallocaties wijzigen.")).toBeVisible();
  await expect(page.getByLabel("Aandelen streef").first()).toBeDisabled();
  await expect(page.getByRole("button", { name: "Wijziging voorstellen" })).toHaveCount(0);

  await page.getByRole("link", { name: "Aannames" }).click();
  await expect(page.getByText("Alleen een beheerder kan de aannames wijzigen.")).toBeVisible();
  await expect(page.getByLabel("Aandelen rendement")).toBeDisabled();
  await expect(page.getByRole("button", { name: "Nieuwe versie voorstellen" })).toHaveCount(0);
});

test("vier ogen: wijziging pas van kracht na goedkeuring door een tweede beheerder", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Modelallocaties" }).click();
  const kaart = page.locator("section", { has: page.getByRole("heading", KAART) });
  await kaart.getByLabel("Aandelen streef").fill("80");
  await kaart.getByLabel("Obligaties streef").fill("10");
  await kaart.getByRole("button", { name: "Wijziging voorstellen" }).click();
  await expect(kaart.getByText("Voorstel ingediend; een tweede beheerder moet het goedkeuren.")).toBeVisible();
  await expect(kaart.getByLabel("Aandelen streef")).toHaveValue("85"); // nog de oude waarde

  const wacht = page.locator("section", { has: page.getByRole("heading", { name: "Wacht op goedkeuring" }) });
  await expect(wacht.getByText("Aandelen: 85% (75–95%) → 80% (75–95%)")).toBeVisible();
  await expect(wacht.getByRole("button", { name: "Goedkeuren" })).toBeDisabled();
  await uitloggen(page);

  await inloggen(page, ADVISEUR);
  await page.getByRole("link", { name: "Modelallocaties" }).click();
  await expect(page.getByRole("heading", { name: "Wacht op goedkeuring" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Goedkeuren" })).toHaveCount(0);
  await uitloggen(page);

  await inloggen(page, BEHEERDER_2);
  await page.getByRole("link", { name: "Modelallocaties" }).click();
  await page.getByRole("button", { name: "Goedkeuren" }).click();
  await expect(page.getByRole("heading", { name: "Wacht op goedkeuring" })).toHaveCount(0);
  const kaart2 = page.locator("section", { has: page.getByRole("heading", KAART) });
  await expect(kaart2.getByLabel("Aandelen streef")).toHaveValue("80");
});

test("aannames: voorstel afwijzen met reden", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Aannames" }).click();
  await page.getByLabel("Aandelen rendement").fill("6");
  await page.getByLabel("Bron").fill("Testbron voor afwijzing");
  await page.getByRole("button", { name: "Nieuwe versie voorstellen" }).click();
  await expect(page.getByText(/Voorstel ingediend; de aannames gelden pas/)).toBeVisible();
  await uitloggen(page);

  await inloggen(page, BEHEERDER_2);
  await page.getByRole("link", { name: "Aannames" }).click();
  const wacht = page.locator("section", { has: page.getByRole("heading", { name: "Wacht op goedkeuring" }) });
  await expect(wacht.getByText("Aandelen rendement: 6,5% → 6%")).toBeVisible();
  page.once("dialog", (d) => d.accept("Bron is niet erkend"));
  await wacht.getByRole("button", { name: "Afwijzen" }).click();
  await expect(page.getByRole("heading", { name: "Wacht op goedkeuring" })).toHaveCount(0);
  await expect(page.getByLabel("Aandelen rendement")).toHaveValue("6,5");
});

test("bedrijfsgegevens invullen en laten goedkeuren", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Onderneming" }).click();
  await expect(page.getByText(/Nog niet ingevuld: naam van de onderneming/)).toBeVisible();
  const velden: Record<string, string> = {
    Naam: "Voorbeeld Vermogensadvies B.V.",
    Adres: "Damrak 1",
    "Postcode en plaats": "1012 LG Amsterdam",
    Telefoon: "020 123 45 67",
    "E-mailadres": "info@voorbeeld.nl",
    "KvK-nummer": "12345678",
    "AFM-vergunningnummer": "12000001",
    "Kifid-aansluitnummer": "300.000001",
    "Klachtenregeling (zoals in het rapport)": "Een klacht kunt u schriftelijk indienen.",
  };
  for (const [label, waarde] of Object.entries(velden)) await page.getByLabel(label, { exact: true }).fill(waarde);
  await page.getByRole("button", { name: "Wijziging voorstellen" }).click();
  await expect(page.getByText(/Voorstel ingediend; de gegevens gelden pas/)).toBeVisible();
  await expect(page.getByText("Naam: — → Voorbeeld Vermogensadvies B.V.")).toBeVisible();
  await uitloggen(page);

  await inloggen(page, BEHEERDER_2);
  await page.getByRole("link", { name: "Onderneming" }).click();
  await page.getByRole("button", { name: "Goedkeuren" }).click();
  await expect(page.getByText(/Nog niet ingevuld/)).toHaveCount(0);
  await expect(page.getByLabel("Naam", { exact: true })).toHaveValue("Voorbeeld Vermogensadvies B.V.");
  await uitloggen(page);

  await inloggen(page, ADVISEUR);
  await page.getByRole("link", { name: "Onderneming" }).click();
  await expect(page.getByLabel("Naam", { exact: true })).toBeDisabled();
});

test("logboek tonen en de keten controleren", async ({ page }) => {
  await inloggen(page, BEHEERDER_1);
  await page.getByRole("link", { name: "Logboek" }).click();
  await expect(page.getByRole("cell", { name: "login", exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Keten controleren" }).click();
  await expect(page.getByRole("status")).toContainText("Het logboek is ongewijzigd");
  await uitloggen(page);
  await inloggen(page, ADVISEUR);
  await expect(page.getByRole("link", { name: "Logboek" })).toHaveCount(0);
});
