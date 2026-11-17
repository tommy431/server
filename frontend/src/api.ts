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

export type Instrument = {
  id: number;
  isin: string;
  naam: string;
  categorie: string;
  regio: string;
  sector: string;
  lopende_kosten: number;
  kosten_geverifieerd: boolean;
  actief: boolean;
};
export type Positie = { isin: string; gewicht: number };
export type Uitsluiting = { soort: "instrument" | "sector" | "regio"; waarde: string; reden: string };
export type Doorrekening = {
  totaal: number;
  per_categorie: Record<string, number>;
  per_regio: Record<string, number>;
  per_sector: Record<string, number>;
  zakelijke_waarden: number;
  grootste_positie: number;
  aantal_instrumenten: number;
  kosten_pct: number;
  kosten_per_positie: Record<string, number>;
  kosten_eur_per_jaar: number;
  bevindingen: Bevinding[];
};
export type Resultaat = {
  risicoprofiel: string;
  klantprofiel_versie: number;
  banden: Record<string, { streef: number; minimum: number; maximum: number }>;
  beperkingen: Record<string, number>;
  posities: Positie[];
  uitsluitingen: Uitsluiting[];
  doorrekening: Doorrekening;
};
export type Versie = Resultaat & { id: number; versie: number; vastgelegd_op: string; toelichting: string | null };

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
  wereld: "Wereldwijd gespreid",
  "noord-amerika": "Noord-Amerika",
  europa: "Europa",
  "opkomende-markten": "Opkomende markten",
  "azie-pacific": "Azië-Pacific",
  breed: "Breed gespreid",
  energie: "Energie",
  materialen: "Materialen",
  industrie: "Industrie",
  "duurzame-consumptiegoederen": "Duurzame consumptiegoederen",
  "dagelijkse-consumptiegoederen": "Dagelijkse consumptiegoederen",
  gezondheidszorg: "Gezondheidszorg",
  "financiele-dienstverlening": "Financiële dienstverlening",
  informatietechnologie: "Informatietechnologie",
  communicatiediensten: "Communicatiediensten",
  nutsbedrijven: "Nutsbedrijven",
};
export const naam = (code: string) => NAMEN[code] ?? code;

/** Basispunten als percentage met Nederlandse komma: 6630 → "66,3%". */
export const pct = (bp: number) =>
  `${new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 1 }).format(bp / 100)}%`;
export const pctKosten = (p: number) =>
  `${new Intl.NumberFormat("nl-NL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(p)}%`;

export type Kengetallen = {
  rendement_cumulatief: number;
  rendement_per_jaar: number;
  volatiliteit: number;
  max_daling: number;
  max_daling_top: string;
  max_daling_dal: string;
  sharpe: number | null;
};
export type AnalysePeriode = {
  code: string;
  jaren: number | null;
  beschikbaar: boolean;
  reden: string | null;
  van: string | null;
  tot: string | null;
  portefeuille: Kengetallen | null;
  benchmark: Kengetallen | null;
  risicovrij_per_jaar: number | null;
};
export type AnalyseUitkomst = {
  analyse: {
    peildatum: string | null;
    perioden: AnalysePeriode[];
    kalenderjaren: { jaar: number; portefeuille: number; benchmark: number | null }[];
    instrumenten: { isin: string; naam: string; eerste_koers: string; bruikbaar_vanaf: string; ingekort: boolean }[];
    waardeverloop: [string, number, number | null][];
    waarschuwingen: string[];
  };
  benchmark: { categorie: string; naam: string; gewicht: number }[];
  risicovrij: string | null;
};

/** Fractie als percentage met teken: 0.0453 → "+4,5%". */
export const rendement = (fractie: number, decimalen = 1) =>
  `${new Intl.NumberFormat("nl-NL", {
    minimumFractionDigits: decimalen,
    maximumFractionDigits: decimalen,
    signDisplay: "exceptZero",
  }).format(fractie * 100)}%`;
export const procent = (fractie: number) =>
  `${new Intl.NumberFormat("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(fractie * 100)}%`;
export const maand = (iso: string) =>
  new Intl.DateTimeFormat("nl-NL", { month: "short", year: "numeric" }).format(new Date(iso));

export type Jaarpunt = {
  jaar: number;
  ingelegd: number;
  ingelegd_reeel: number;
  nominaal: [number, number, number];
  reeel: [number, number, number];
};
export type ScenarioUitkomst = {
  scenario: {
    paden: number;
    horizon_jaren: number;
    inleg: number;
    storting_per_maand: number;
    doelvermogen: number | null;
    kosten_pct: number;
    verwacht_rendement: number;
    verwachte_volatiliteit: number;
    jaren: Jaarpunt[];
    kans_doel_nominaal: number | null;
    kans_doel_reeel: number | null;
    kans_minder_dan_ingelegd: number;
    mediaan_zonder_kosten: number;
    kosten_effect_mediaan: number;
    inflatie_effect_mediaan: number;
  } | null;
  reden: string | null;
  lopende_kosten_pct: number;
  overige_kosten_pct: number;
  gewichten: Record<string, number>;
  aannames: AannameSet & { id: number };
};
export type AannameSet = {
  bron: string;
  peildatum: string;
  categorieen: Record<string, { rendement: number; volatiliteit: number }>;
  correlaties: Record<string, Record<string, number>>;
  inflatie: number;
};
export type AannamesUit = AannameSet & { id: number; vastgelegd_op: string };
