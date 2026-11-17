import { Page, expect } from "@playwright/test";

export const WACHTWOORD = "test-wachtwoord-e2e";
export const BEHEERDER_1 = "beheerder1@voorbeeld.nl";
export const BEHEERDER_2 = "beheerder2@voorbeeld.nl";
export const ADVISEUR = "adviseur@voorbeeld.nl";

export async function inloggen(page: Page, email: string) {
  await page.goto("/");
  await page.getByLabel("E-mailadres").fill(email);
  await page.getByLabel("Wachtwoord").fill(WACHTWOORD);
  await page.getByRole("button", { name: "Inloggen" }).click();
  await expect(page.getByRole("heading", { name: "Klanten" })).toBeVisible();
}

export async function uitloggen(page: Page) {
  await page.getByRole("button", { name: "Uitloggen" }).click();
  await expect(page.getByRole("button", { name: "Inloggen" })).toBeVisible();
}

/** Beantwoordt elke vraag met hetzelfde antwoord (0 t/m 3). */
export async function vragenlijstInvullen(page: Page, antwoord: number) {
  const vragen = page.getByRole("radiogroup").filter({ has: page.getByRole("radio").nth(3) });
  const aantal = await vragen.count();
  for (let i = 0; i < aantal; i++) await vragen.nth(i).getByRole("radio").nth(antwoord).check();
}

/** Maakt een klant aan met een vastgelegd profiel en opent het klantscherm. */
export async function klantMetProfiel(
  page: Page,
  naam: string,
  opties: { horizon?: string; doel?: string; koopkracht?: boolean } = {},
) {
  await page.getByLabel("Naam nieuwe klant").fill(naam);
  await page.getByRole("button", { name: "Klant toevoegen" }).click();
  await expect(page.getByRole("heading", { name: naam })).toBeVisible();
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  await page.getByLabel("Beleggingsdoel").fill("Aanvulling pensioen");
  await page.getByLabel("Horizon (jaren)").fill(opties.horizon ?? "15");
  await page.getByLabel("Inleg (€)").fill("100000");
  await page.getByLabel("Storting per maand (€)").fill("250");
  if (opties.doel) {
    await page.getByLabel("Doelvermogen (€, optioneel)").fill(opties.doel);
    if (opties.koopkracht) await page.getByLabel("in koopkracht van vandaag").check();
  }
  await vragenlijstInvullen(page, 1);
  await expect(page.getByText("Afgeleid profiel:")).toBeVisible();
  await page.getByRole("button", { name: "Profiel vastleggen" }).click();
  await expect(page.getByText(/versie 1, vastgelegd op/)).toBeVisible();
}

/** Controleert dat de pagina op de huidige breedte niet horizontaal schuift. */
export async function geenHorizontaleScroll(page: Page) {
  const overloop = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overloop).toBeLessThanOrEqual(0);
}
