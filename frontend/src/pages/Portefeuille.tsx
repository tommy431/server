import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Analyse } from "../Analyse";
import { Scenario } from "../Scenario";
import {
  AnalyseUitkomst,
  ScenarioUitkomst,
  Instrument,
  Klant,
  Resultaat,
  Uitsluiting,
  Versie,
  api,
  datum,
  euro,
  naam,
  pct,
  pctKosten,
} from "../api";
import { Fouten, meldingenVan } from "../Fouten";

const CATEGORIEEN = ["aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten"];
const REGIOS = ["noord-amerika", "europa", "opkomende-markten", "azie-pacific"];
const SECTOREN = [
  "energie",
  "materialen",
  "industrie",
  "duurzame-consumptiegoederen",
  "dagelijkse-consumptiegoederen",
  "gezondheidszorg",
  "financiele-dienstverlening",
  "informatietechnologie",
  "communicatiediensten",
  "nutsbedrijven",
  "vastgoed",
];

type Gewichten = Record<string, number>;

function isUitgesloten(i: Instrument, uitsluitingen: Uitsluiting[]) {
  return uitsluitingen.some(
    (u) =>
      (u.soort === "instrument" && u.waarde === i.isin) ||
      (u.soort === "sector" && u.waarde === i.sector) ||
      (u.soort === "regio" && u.waarde === i.regio),
  );
}

/** Balk met het toegestane bereik (band) en de plek van het huidige gewicht. */
function Bandbalk({ gewicht, band }: { gewicht: number; band: { minimum: number; maximum: number } }) {
  const buiten = gewicht < band.minimum * 100 || gewicht > band.maximum * 100;
  return (
    <div className="bandbalk" aria-hidden="true">
      <span className="band" style={{ left: `${band.minimum}%`, width: `${band.maximum - band.minimum}%` }} />
      <span className={`wijzer ${buiten ? "buiten" : ""}`} style={{ left: `${Math.min(gewicht / 100, 100)}%` }} />
    </div>
  );
}

export default function Portefeuille() {
  const id = Number(useParams().id);
  const [klant, setKlant] = useState<Klant | null>(null);
  const [instrumenten, setInstrumenten] = useState<Instrument[]>([]);
  const [versies, setVersies] = useState<Versie[]>([]);
  const [gewichten, setGewichten] = useState<Gewichten>({});
  const [uitsluitingen, setUitsluitingen] = useState<Uitsluiting[]>([]);
  const [resultaat, setResultaat] = useState<Resultaat | null>(null);
  const [toelichting, setToelichting] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);
  const [opgeslagen, setOpgeslagen] = useState<string | null>(null);
  const [klaar, setKlaar] = useState(false);
  const [bezig, setBezig] = useState(false);
  const [analyse, setAnalyse] = useState<AnalyseUitkomst | null>(null);
  const [analyseBezig, setAnalyseBezig] = useState(false);
  const [scenario, setScenario] = useState<ScenarioUitkomst | null>(null);
  const [overigeKosten, setOverigeKosten] = useState("0");

  const [filter, setFilter] = useState({ categorie: "aandelen", regio: "", sector: "" });
  const [gekozen, setGekozen] = useState("");
  const [nieuweUitsluiting, setNieuweUitsluiting] = useState<Uitsluiting>({
    soort: "sector",
    waarde: SECTOREN[0],
    reden: "",
  });

  const perIsin = useMemo(() => Object.fromEntries(instrumenten.map((i) => [i.isin, i])), [instrumenten]);

  const neemOver = (r: Resultaat) => {
    setGewichten(Object.fromEntries(r.posities.map((p) => [p.isin, p.gewicht])));
    setUitsluitingen(r.uitsluitingen);
    setResultaat(r);
  };

  const vraagVoorstel = useCallback(
    async (uit: Uitsluiting[]) => {
      const r = await api<Resultaat>(`/klanten/${id}/portefeuille/voorstel`, {
        methode: "POST",
        body: { uitsluitingen: uit },
      });
      neemOver(r);
    },
    [id],
  );

  // Eerste keer: de laatst vastgelegde versie, of anders een startvoorstel.
  useEffect(() => {
    (async () => {
      try {
        const [k, lijst, v] = await Promise.all([
          api<Klant>(`/klanten/${id}`),
          api<Instrument[]>("/instrumenten"),
          api<Versie[]>(`/klanten/${id}/portefeuille/versies`),
        ]);
        setKlant(k);
        setInstrumenten(lijst);
        setVersies(v);
        if (v.length > 0) neemOver(v[0]);
        else await vraagVoorstel([]);
        setKlaar(true);
      } catch (fout) {
        setFouten(meldingenVan(fout));
      }
    })();
  }, [id, vraagVoorstel]);

  // Na elke wijziging opnieuw doorrekenen; alleen het laatste antwoord telt.
  const volgnummer = useRef(0);
  useEffect(() => {
    if (!klaar) return;
    const nummer = ++volgnummer.current;
    const timer = setTimeout(async () => {
      try {
        const r = await api<Resultaat>(`/klanten/${id}/portefeuille/doorrekenen`, {
          methode: "POST",
          body: {
            posities: Object.entries(gewichten).map(([isin, gewicht]) => ({ isin, gewicht })),
            uitsluitingen,
          },
        });
        if (nummer === volgnummer.current) {
          setResultaat(r);
          setFouten([]);
        }
      } catch (fout) {
        if (nummer === volgnummer.current) setFouten(meldingenVan(fout));
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [gewichten, uitsluitingen, klaar, id]);

  const overigeKostenPct = Math.min(5, Math.max(0, Number(overigeKosten.replace(",", ".")) || 0));
  // De historische analyse volgt de doorrekening, maar alleen als de gewichten op 100% uitkomen.
  const analyseNummer = useRef(0);
  const totaal = resultaat?.doorrekening.totaal;
  useEffect(() => {
    if (!klaar || totaal !== 10000) {
      setAnalyse(null);
      setScenario(null);
      return;
    }
    const nummer = ++analyseNummer.current;
    setAnalyseBezig(true);
    const timer = setTimeout(async () => {
      try {
        const uit = await api<AnalyseUitkomst>(`/klanten/${id}/portefeuille/analyse`, {
          methode: "POST",
          body: { posities: Object.entries(gewichten).map(([isin, gewicht]) => ({ isin, gewicht })), uitsluitingen },
        });
        if (nummer === analyseNummer.current) setAnalyse(uit);
      } catch {
        if (nummer === analyseNummer.current) setAnalyse(null);
      } finally {
        if (nummer === analyseNummer.current) setAnalyseBezig(false);
      }
    }, 600);
    const timerScenario = setTimeout(async () => {
      try {
        const uit = await api<ScenarioUitkomst>(`/klanten/${id}/portefeuille/scenario`, {
          methode: "POST",
          body: {
            posities: Object.entries(gewichten).map(([isin, gewicht]) => ({ isin, gewicht })),
            uitsluitingen,
            overige_kosten_pct: overigeKostenPct,
          },
        });
        if (nummer === analyseNummer.current) setScenario(uit);
      } catch {
        if (nummer === analyseNummer.current) setScenario(null);
      }
    }, 600);
    return () => {
      clearTimeout(timer);
      clearTimeout(timerScenario);
    };
    // De doorrekening bepaalt of de gewichten geldig zijn; daarna telt alleen de samenstelling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultaat, klaar, id, overigeKostenPct]);

  if (!klant || !resultaat) {
    return (
      <>
        <Fouten meldingen={fouten} />
        {fouten.length === 0 && <p className="zacht">Laden…</p>}
        <Link to={`/klanten/${id}`}>Terug naar de klant</Link>
      </>
    );
  }

  const d = resultaat.doorrekening;
  const blokkades = d.bevindingen.filter((b) => b.ernst === "fout");
  const afwijkingen = d.bevindingen.filter((b) => b.ernst === "afwijking");
  const aandachtspunten = d.bevindingen.filter((b) => b.ernst === "aandachtspunt");
  const profielHerzien = versies.length > 0 && versies[0].klantprofiel_versie < resultaat.klantprofiel_versie;

  const wijzig = (nieuw: Gewichten) => {
    setOpgeslagen(null);
    setGewichten(nieuw);
  };
  const zetGewicht = (isin: string, tekst: string) => {
    const bp = Math.round(Number(tekst.replace(",", ".")) * 100);
    wijzig({ ...gewichten, [isin]: Number.isFinite(bp) ? bp : 0 });
  };
  const verwijder = (isin: string) => {
    const { [isin]: _, ...rest } = gewichten;
    wijzig(rest);
  };

  const kandidaten = instrumenten.filter(
    (i) =>
      i.actief &&
      !(i.isin in gewichten) &&
      !isUitgesloten(i, uitsluitingen) &&
      i.categorie === filter.categorie &&
      (!filter.regio || i.regio === filter.regio) &&
      (!filter.sector || i.sector === filter.sector),
  );
  const keuze = kandidaten.some((k) => k.isin === gekozen) ? gekozen : (kandidaten[0]?.isin ?? "");

  const waardenVoor = (soort: Uitsluiting["soort"]) =>
    soort === "sector" ? SECTOREN : soort === "regio" ? REGIOS : instrumenten.map((i) => i.isin);
  const voegUitsluitingToe = () => {
    if (uitsluitingen.some((u) => u.soort === nieuweUitsluiting.soort && u.waarde === nieuweUitsluiting.waarde)) return;
    setOpgeslagen(null);
    setUitsluitingen([...uitsluitingen, nieuweUitsluiting]);
    setNieuweUitsluiting({ ...nieuweUitsluiting, reden: "" });
  };

  async function nieuwVoorstel() {
    setOpgeslagen(null);
    try {
      await vraagVoorstel(uitsluitingen);
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  async function legVast() {
    setBezig(true);
    setFouten([]);
    try {
      const v = await api<Versie>(`/klanten/${id}/portefeuille/versies`, {
        methode: "POST",
        body: {
          posities: Object.entries(gewichten).map(([isin, gewicht]) => ({ isin, gewicht })),
          uitsluitingen,
          overige_kosten_pct: overigeKostenPct,
          toelichting: toelichting || null,
        },
      });
      setVersies([v, ...versies]);
      setToelichting("");
      setOpgeslagen(`Versie ${v.versie} is vastgelegd.`);
    } catch (fout) {
      setFouten(meldingenVan(fout));
    } finally {
      setBezig(false);
    }
  }

  return (
    <>
      <p>
        <Link to={`/klanten/${id}`}>← {klant.naam}</Link>
      </p>
      <div className="kop">
        <h1>Portefeuille</h1>
        <span className="label">Risicoprofiel: {naam(resultaat.risicoprofiel)}</span>
      </div>
      {profielHerzien && (
        <div className="melding let-op">
          Het klantprofiel is herzien nadat de laatste portefeuille is vastgelegd. Beoordeel de portefeuille opnieuw en
          leg een nieuwe versie vast.
        </div>
      )}

      <section className="kaart">
        <div className="kop">
          <h2>Posities</h2>
          <button className="tweede" onClick={nieuwVoorstel}>
            Nieuw startvoorstel
          </button>
        </div>
        <table className="compact">
          <thead>
            <tr>
              <th>Instrument</th>
              <th className="getal">Kosten p.j.</th>
              <th className="getal">Gewicht %</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {CATEGORIEEN.flatMap((categorie) =>
              Object.keys(gewichten)
                .filter((isin) => (perIsin[isin]?.categorie ?? "") === categorie)
                .sort((a, b) => gewichten[b] - gewichten[a])
                .map((isin) => {
                  const i = perIsin[isin];
                  return (
                    <tr key={isin}>
                      <td>
                        <span className={`stip ${categorie}`} />
                        {i.naam}
                        <div className="zacht klein-tekst">
                          {naam(i.categorie)} · {naam(i.regio)}
                          {i.sector !== "breed" && i.sector !== "vastgoed" && ` · ${naam(i.sector)}`}
                        </div>
                      </td>
                      <td className="getal">
                        {pctKosten(i.lopende_kosten)}
                        {!i.kosten_geverifieerd && <span title="Niet gecontroleerd tegen de fondsdocumentatie"> *</span>}
                      </td>
                      <td className="getal">
                        <input
                          className="klein"
                          type="number"
                          min={0}
                          max={100}
                          step={0.1}
                          aria-label={`Gewicht ${i.naam}`}
                          value={gewichten[isin] / 100}
                          onChange={(e) => zetGewicht(isin, e.target.value)}
                        />
                      </td>
                      <td>
                        <button className="tekstknop" aria-label={`Verwijder ${i.naam}`} onClick={() => verwijder(isin)}>
                          Verwijderen
                        </button>
                      </td>
                    </tr>
                  );
                }),
            )}
          </tbody>
          <tfoot>
            <tr>
              <td>Totaal</td>
              <td className="getal">{pctKosten(d.kosten_pct)}</td>
              <td className={`getal ${d.totaal === 10000 ? "" : "rood"}`} data-testid="totaal">
                {pct(d.totaal)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
        <p className="zacht klein-tekst">* Lopende kosten nog niet gecontroleerd tegen de fondsdocumentatie.</p>

        <h3>Instrument toevoegen</h3>
        <div className="kolommen">
          <label>
            Categorie
            <select value={filter.categorie} onChange={(e) => setFilter({ ...filter, categorie: e.target.value })}>
              {CATEGORIEEN.map((c) => (
                <option key={c} value={c}>
                  {naam(c)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Regio
            <select value={filter.regio} onChange={(e) => setFilter({ ...filter, regio: e.target.value })}>
              <option value="">Alle regio's</option>
              {["wereld", ...REGIOS].map((r) => (
                <option key={r} value={r}>
                  {naam(r)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sector
            <select value={filter.sector} onChange={(e) => setFilter({ ...filter, sector: e.target.value })}>
              <option value="">Alle sectoren</option>
              {["breed", ...SECTOREN].map((s) => (
                <option key={s} value={s}>
                  {naam(s)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="rij">
          <select aria-label="Instrument" value={keuze} onChange={(e) => setGekozen(e.target.value)} disabled={!keuze}>
            {kandidaten.length === 0 && <option value="">Geen instrumenten met deze keuze</option>}
            {kandidaten.map((k) => (
              <option key={k.isin} value={k.isin}>
                {k.naam} ({pctKosten(k.lopende_kosten)})
              </option>
            ))}
          </select>
          <button className="tweede" disabled={!keuze} onClick={() => wijzig({ ...gewichten, [keuze]: 500 })}>
            Toevoegen met 5%
          </button>
        </div>
      </section>

      <section className="kaart">
        <h2>Uitsluitingen</h2>
        {uitsluitingen.length === 0 ? (
          <p className="zacht">Geen uitsluitingen.</p>
        ) : (
          <ul className="lijst">
            {uitsluitingen.map((u) => (
              <li key={u.soort + u.waarde}>
                <span>
                  {u.soort === "instrument" ? (perIsin[u.waarde]?.naam ?? u.waarde) : naam(u.waarde)}
                  {u.reden && <span className="zacht"> — {u.reden}</span>}
                </span>
                <button
                  className="tekstknop"
                  onClick={() => {
                    setOpgeslagen(null);
                    setUitsluitingen(uitsluitingen.filter((x) => x !== u));
                  }}
                >
                  Opheffen
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="kolommen">
          <label>
            Soort
            <select
              value={nieuweUitsluiting.soort}
              onChange={(e) => {
                const soort = e.target.value as Uitsluiting["soort"];
                setNieuweUitsluiting({ soort, waarde: waardenVoor(soort)[0] ?? "", reden: nieuweUitsluiting.reden });
              }}
            >
              <option value="sector">Sector</option>
              <option value="regio">Regio</option>
              <option value="instrument">Instrument</option>
            </select>
          </label>
          <label>
            Uitsluiten
            <select
              value={nieuweUitsluiting.waarde}
              onChange={(e) => setNieuweUitsluiting({ ...nieuweUitsluiting, waarde: e.target.value })}
            >
              {waardenVoor(nieuweUitsluiting.soort).map((w) => (
                <option key={w} value={w}>
                  {nieuweUitsluiting.soort === "instrument" ? perIsin[w]?.naam : naam(w)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Reden (optioneel)
            <input
              value={nieuweUitsluiting.reden}
              maxLength={300}
              onChange={(e) => setNieuweUitsluiting({ ...nieuweUitsluiting, reden: e.target.value })}
            />
          </label>
        </div>
        <button className="tweede" onClick={voegUitsluitingToe}>
          Uitsluiting toevoegen
        </button>
      </section>

      <section className="kaart">
        <h2>Verdeling en toetsing</h2>
        <table className="compact">
          <thead>
            <tr>
              <th>Categorie</th>
              <th className="getal">Gewicht</th>
              <th className="getal">Toegestaan</th>
              <th className="breed-kolom">Positie binnen de bandbreedte</th>
            </tr>
          </thead>
          <tbody>
            {CATEGORIEEN.filter((c) => resultaat.banden[c]).map((c) => {
              const band = resultaat.banden[c];
              const gewicht = d.per_categorie[c] ?? 0;
              const buiten = gewicht < band.minimum * 100 || gewicht > band.maximum * 100;
              return (
                <tr key={c}>
                  <td>
                    <span className={`stip ${c}`} />
                    {naam(c)}
                  </td>
                  <td className={`getal ${buiten ? "rood" : ""}`}>{pct(gewicht)}</td>
                  <td className="getal">
                    {band.minimum}–{band.maximum}%
                  </td>
                  <td className="breed-kolom">
                    <Bandbalk gewicht={gewicht} band={band} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="kolommen ruim">
          <div>
            <h3>Naar regio</h3>
            <table className="compact">
              <tbody>
                {Object.entries(d.per_regio).map(([r, g]) => (
                  <tr key={r}>
                    <td>{naam(r)}</td>
                    <td className="getal">{pct(g)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h3>Naar sector</h3>
            <table className="compact">
              <tbody>
                {Object.entries(d.per_sector).map(([s, g]) => (
                  <tr key={s}>
                    <td>{naam(s)}</td>
                    <td className="getal">{pct(g)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h3>Kenmerken</h3>
            <dl className="smal">
              <dt>Zakelijke waarden</dt>
              <dd>{pct(d.zakelijke_waarden)}</dd>
              <dt>Grootste positie</dt>
              <dd>{pct(d.grootste_positie)}</dd>
              <dt>Instrumenten</dt>
              <dd>{d.aantal_instrumenten}</dd>
              <dt>Lopende kosten</dt>
              <dd>
                {pctKosten(d.kosten_pct)} per jaar
                {klant.huidig_profiel && klant.huidig_profiel.inleg_eur > 0 && (
                  <>
                    , circa {euro(d.kosten_eur_per_jaar)} op de inleg van {euro(klant.huidig_profiel.inleg_eur)}
                  </>
                )}
              </dd>
            </dl>
          </div>
        </div>
        <p className="zacht klein-tekst">
          Regio en sector zijn de labels van het instrument. Van breed gespreide fondsen is de onderliggende verdeling
          niet bekend; die staan onder "Wereldwijd gespreid" en "Breed gespreid". Transactiekosten en kosten van de
          adviseur of bank zijn niet meegerekend.
        </p>
      </section>

      <section className="kaart">
        <h2>Historische analyse</h2>
        {analyse ? (
          <div className={analyseBezig ? "verouderd" : ""}>
            <Analyse uitkomst={analyse} />
          </div>
        ) : (
          <p className="zacht">
            {totaal === 10000 ? "Bezig met berekenen…" : "Beschikbaar zodra de gewichten optellen tot 100%."}
          </p>
        )}
      </section>

      <section className="kaart">
        <h2>Verwacht rendement</h2>
        <label className="smal-veld">
          Overige kosten % per jaar (advies, beheer, bewaring)
          <input inputMode="decimal" value={overigeKosten} onChange={(e) => setOverigeKosten(e.target.value)} />
        </label>
        {scenario ? (
          <div className={analyseBezig ? "verouderd" : ""}>
            <Scenario uitkomst={scenario} />
          </div>
        ) : (
          <p className="zacht">
            {totaal === 10000 ? "Bezig met berekenen…" : "Beschikbaar zodra de gewichten optellen tot 100%."}
          </p>
        )}
      </section>

      <section className="kaart">
        <h2>Beoordeling en vastleggen</h2>
        {blokkades.length > 0 && (
          <div className="melding fout" role="alert">
            <strong>Kan niet worden vastgelegd:</strong>
            <ul>
              {blokkades.map((b) => (
                <li key={b.melding}>{b.melding}</li>
              ))}
            </ul>
          </div>
        )}
        {afwijkingen.length > 0 && (
          <div className="melding let-op" role="alert">
            <strong>Buiten het risicoprofiel of de beperkingen; toelichting verplicht:</strong>
            <ul>
              {afwijkingen.map((b) => (
                <li key={b.melding}>{b.melding}</li>
              ))}
            </ul>
          </div>
        )}
        {blokkades.length === 0 && afwijkingen.length === 0 && (
          <div className="melding goed">De portefeuille past binnen het risicoprofiel en de beperkingen.</div>
        )}
        {aandachtspunten.length > 0 && (
          <div className="melding">
            <strong>Aandachtspunten:</strong>
            <ul>
              {aandachtspunten.map((b) => (
                <li key={b.melding}>{b.melding}</li>
              ))}
            </ul>
          </div>
        )}
        <label>
          Toelichting {afwijkingen.length > 0 ? "(verplicht)" : "(optioneel)"}
          <textarea value={toelichting} maxLength={2000} onChange={(e) => setToelichting(e.target.value)} />
        </label>
        <Fouten meldingen={fouten} />
        {opgeslagen && <div className="melding goed">{opgeslagen}</div>}
        <button
          onClick={legVast}
          disabled={
            bezig || klant.gearchiveerd || blokkades.length > 0 || (afwijkingen.length > 0 && !toelichting.trim())
          }
        >
          {bezig ? "Bezig…" : "Portefeuille vastleggen"}
        </button>
      </section>

      {versies.length > 0 && (
        <section className="kaart">
          <h2>Vastgelegde versies</h2>
          <table className="compact">
            <thead>
              <tr>
                <th>Versie</th>
                <th>Vastgelegd</th>
                <th>Risicoprofiel</th>
                <th className="getal">Zakelijke waarden</th>
                <th className="getal">Kosten</th>
                <th>Toelichting</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {versies.map((v) => (
                <tr key={v.id}>
                  <td>{v.versie}</td>
                  <td>{datum(v.vastgelegd_op)}</td>
                  <td>{naam(v.risicoprofiel)}</td>
                  <td className="getal">{pct(v.doorrekening.zakelijke_waarden)}</td>
                  <td className="getal">{pctKosten(v.doorrekening.kosten_pct)}</td>
                  <td>{v.toelichting ?? "—"}</td>
                  <td>
                    <button
                      className="tekstknop"
                      onClick={() => {
                        setOpgeslagen(null);
                        setGewichten(Object.fromEntries(v.posities.map((p) => [p.isin, p.gewicht])));
                        setUitsluitingen(v.uitsluitingen);
                      }}
                    >
                      Overnemen
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
