export type Adviseur = { id: number; email: string; naam: string };

export type Profiel = {
  id: number;
  versie: number;
  vastgelegd_op: string;
  doel: string;
  horizon_jaren: number;
  inleg_eur: number;
  storting_per_maand_eur: number;
  doelvermogen_eur: number | null;
  antwoorden: Record<string, number>;
  score_bereidheid: number;
  score_capaciteit: number;
  score_kennis: number;
  lage_kennis: boolean;
  duurzaamheid: string;
  uitsluitingen: string[];
  duurzaamheid_toelichting: string | null;
  afgeleid_risicoprofiel: string;
  bepalende_factor: string;
  risicoprofiel: string;
  afwijking_toelichting: string | null;
};

export type Klant = {
  id: number;
  naam: string;
  email: string | null;
  geboortedatum: string | null;
  gearchiveerd: boolean;
  aangemaakt_op: string;
  huidig_profiel: Profiel | null;
};

export type AllocatieRegel = { categorie: string; streef: number; minimum: number; maximum: number };
export type Risicoprofiel = { code: string; naam: string; niveau: number; allocatie: AllocatieRegel[] };

export type Vraag = { code: string; dimensie: string; tekst: string; antwoorden: string[] };
export type Vragenlijst = {
  versie: number;
  dimensies: Record<string, string>;
  vragen: Vraag[];
  uitsluitingen: string[];
};

export type Uitkomst = {
  score_bereidheid: number;
  score_capaciteit: number;
  score_kennis: number;
  lage_kennis: boolean;
  risicoprofiel: string;
  bepalende_factor: string;
};

export type Bevinding = { ernst: string; code: string; melding: string };
export type DataStatus = {
  instrument_id: number;
  isin: string;
  naam: string;
  aantal_koersen: number;
  eerste_koers: string | null;
  laatste_koers: string | null;
  bron: string | null;
  bevindingen: Bevinding[];
};
export type VerversResultaat = { onderdeel: string; opgeslagen: number; fout: string | null };

const SLEUTEL = "token";
let bijUitloggen: () => void = () => {};

export const token = {
  lees: () => sessionStorage.getItem(SLEUTEL),
  zet: (waarde: string) => sessionStorage.setItem(SLEUTEL, waarde),
  wis: () => sessionStorage.removeItem(SLEUTEL),
};

export function registreerUitloggen(fn: () => void) {
  bijUitloggen = fn;
}

export class ApiFout extends Error {
  constructor(
    public status: number,
    public meldingen: string[],
  ) {
    super(meldingen.join(" "));
  }
}

function leesMeldingen(inhoud: unknown, status: number): string[] {
  const detail = (inhoud as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    return detail.map((d) =>
      typeof d === "string" ? d : `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? "ongeldig"}`,
    );
  }
  return [`Er ging iets mis (foutcode ${status}).`];
}

export async function api<T>(pad: string, opties: { methode?: string; body?: unknown } = {}): Promise<T> {
  const koppen: Record<string, string> = {};
  const huidig = token.lees();
  if (huidig) koppen.Authorization = `Bearer ${huidig}`;
  if (opties.body !== undefined) koppen["Content-Type"] = "application/json";

  let antwoord: Response;
  try {
    antwoord = await fetch(`/api${pad}`, {
      method: opties.methode ?? "GET",
      headers: koppen,
      body: opties.body === undefined ? undefined : JSON.stringify(opties.body),
    });
  } catch {
    throw new ApiFout(0, ["De server is niet bereikbaar."]);
  }
  const inhoud = await antwoord.json().catch(() => null);
  if (!antwoord.ok) {
    // Een verlopen sessie: terug naar het inlogscherm. Niet bij het inloggen zelf.
    if (antwoord.status === 401 && pad !== "/auth/login") bijUitloggen();
    throw new ApiFout(antwoord.status, leesMeldingen(inhoud, antwoord.status));
  }
  return inhoud as T;
}

export const euro = (bedrag: number) =>
  new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(
    bedrag,
  );

export const datum = (iso: string) =>
  new Intl.DateTimeFormat("nl-NL", { day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));

export const NAMEN: Record<string, string> = {
  "zeer-defensief": "Zeer defensief",
  defensief: "Defensief",
  neutraal: "Neutraal",
  offensief: "Offensief",
  "zeer-offensief": "Zeer offensief",
  bereidheid: "risicobereidheid",
  capaciteit: "risicocapaciteit",
  horizon: "beleggingshorizon",
  aandelen: "Aandelen",
  obligaties: "Obligaties",
  vastgoed: "Vastgoed",
  grondstoffen: "Grondstoffen",
  liquiditeiten: "Liquiditeiten",
  geen: "Geen voorkeur",
  enigszins: "Enige voorkeur",
  sterk: "Sterke voorkeur",
  wapens: "Wapens",
  tabak: "Tabak",
  "fossiele-brandstoffen": "Fossiele brandstoffen",
  gokken: "Gokken",
  alcohol: "Alcohol",
  kernenergie: "Kernenergie",
};
export const naam = (code: string) => NAMEN[code] ?? code;
