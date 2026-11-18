import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Instrument, Klant, Opvolging as OpvolgingT, api, datum, euro, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import Signaallijst from "../Signaallijst";

const pct = (bp: number) => `${(bp / 100).toLocaleString("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
const stuks = (n: number) => n.toLocaleString("nl-NL", { maximumFractionDigits: 4 });
const koersEuro = (n: number) =>
  new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }).format(n);
const vandaag = () => new Date().toISOString().slice(0, 10);
const UITKOMSTEN: Record<string, string> = {
  ongewijzigd: "Advies ongewijzigd",
  herbalanceren: "Herbalanceren afgesproken",
  aangepast: "Advies aangepast",
};

type Regel = { isin: string; aantal: string };
type OverigRegel = {
  omschrijving: string;
  isin: string;
  categorie: string;
  aantal: string;
  waarde: string;
  behouden: boolean;
};
const CATEGORIEEN = ["aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten", "overig"];
const leegOverig = (): OverigRegel => ({
  omschrijving: "",
  isin: "",
  categorie: "",
  aantal: "",
  waarde: "",
  behouden: false,
});
const alsTekst = (n: number | null | undefined) => (n == null ? "" : String(n).replace(".", ","));
/** Leest "1.250", "1250,5" en "12.50" als 1250, 1250,5 en 12,5. */
function getal(tekst: string): number {
  const t = tekst.trim().replace(/[\s\u00a0]/g, "");
  if (t.includes(",")) return Number(t.replace(/\./g, "").replace(",", "."));
  // Zonder komma: een punt gevolgd door precies drie cijfers is een duizendtalscheiding.
  if (/^-?[1-9]\d{0,2}(\.\d{3})+$/.test(t)) return Number(t.replace(/\./g, ""));
  return Number(t);
}

export default function Opvolging() {
  const id = Number(useParams().id);
  const [klant, setKlant] = useState<Klant | null>(null);
  const [o, setO] = useState<OpvolgingT | null>(null);
  const [instrumenten, setInstrumenten] = useState<Instrument[]>([]);
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezitFormulier, setBezitFormulier] = useState(false);
  const [regels, setRegels] = useState<Regel[]>([]);
  const [overig, setOverig] = useState<OverigRegel[]>([]);
  const [bezig, setBezig] = useState(false);
  const [kas, setKas] = useState("0");
  const [peildatum, setPeildatum] = useState(vandaag());
  const [inleesMeldingen, setInleesMeldingen] = useState<string[]>([]);

  const laad = useCallback(async () => {
    try {
      const [k, op, ins] = await Promise.all([
        api<Klant>(`/klanten/${id}`),
        api<OpvolgingT>(`/klanten/${id}/opvolging`),
        api<Instrument[]>("/instrumenten"),
      ]);
      setKlant(k);
      setO(op);
      setInstrumenten(ins);
      setFouten([]);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }, [id]);

  useEffect(() => {
    void laad();
  }, [laad]);

  const perIsin = useMemo(() => Object.fromEntries(instrumenten.map((i) => [i.isin, i])), [instrumenten]);

  function openBezit() {
    // Begin bij de vorige opgave, of anders bij de fondsen uit het advies.
    const vorige = o?.bezit?.posities;
    const basis = vorige
      ? Object.entries(vorige).map(([isin, a]) => ({ isin, aantal: String(a) }))
      : Object.keys(o?.advies?.posities ?? {}).map((isin) => ({ isin, aantal: "" }));
    setRegels(basis.length ? basis : [{ isin: "", aantal: "" }]);
    setOverig(
      (o?.bezit?.overig ?? []).map((x) => ({
        omschrijving: x.omschrijving,
        isin: x.isin ?? "",
        categorie: x.categorie,
        aantal: alsTekst(x.aantal),
        waarde: alsTekst(x.waarde),
        behouden: x.behouden,
      })),
    );
    setKas(String(o?.bezit?.kas_eur ?? 0).replace(".", ","));
    setPeildatum(vandaag());
    setInleesMeldingen([]);
    setBezitFormulier(true);
  }

  async function leesBestand(bestand: File | undefined) {
    if (!bestand) return;
    const bytes = await bestand.arrayBuffer();
    // Exports uit Excel zijn vaak Windows-1252 in plaats van UTF-8.
    let tekst: string;
    try {
      tekst = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      tekst = new TextDecoder("windows-1252").decode(bytes);
    }
    try {
      const r = await api<{
        posities: { isin: string; aantal: number }[];
        overig: { isin: string; omschrijving: string; aantal: number; waarde_eur: number | null }[];
        meldingen: string[];
      }>(
        `/klanten/${id}/bezit/inlezen`,
        { methode: "POST", body: { tekst } },
      );
      if (r.posities.length || r.overig.length) {
        setRegels(r.posities.map((p) => ({ isin: p.isin, aantal: String(p.aantal).replace(".", ",") })));
        setOverig(
          r.overig.map((x) => ({
            ...leegOverig(),
            omschrijving: x.omschrijving,
            isin: x.isin,
            aantal: alsTekst(x.aantal),
            waarde: alsTekst(x.waarde_eur),
          })),
        );
      }
      setInleesMeldingen([
        r.posities.length || r.overig.length
          ? `${r.posities.length + r.overig.length} positie(s) ingelezen uit ${bestand.name}. Controleer de aantallen en vul het geldsaldo in.`
          : `Uit ${bestand.name} zijn geen fondsen overgenomen.`,
        ...r.meldingen,
      ]);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  async function koersenOphalen() {
    setBezig(true);
    try {
      const r = await api<{ opgehaald: number; fouten: string[] }>(`/klanten/${id}/koersen`, { methode: "POST" });
      await laad();
      setFouten(r.fouten.map((f) => `Koers niet opgehaald: ${f}`));
    } catch (f) {
      setFouten(meldingenVan(f));
    } finally {
      setBezig(false);
    }
  }

  async function bewaarBezit(e: FormEvent) {
    e.preventDefault();
    const posities = regels
      .filter((r) => r.isin && r.aantal.trim() !== "")
      .map((r) => ({ isin: r.isin, aantal: getal(r.aantal) }))
      .filter((r) => r.aantal !== 0);
    const overigInvoer = overig
      .filter((x) => x.omschrijving.trim() || x.waarde.trim())
      .map((x) => ({
        omschrijving: x.omschrijving.trim(),
        isin: x.isin.trim().toUpperCase() || null,
        categorie: x.categorie,
        aantal: x.aantal.trim() ? getal(x.aantal) : null,
        waarde_eur: x.waarde.trim() ? getal(x.waarde) : null,
        behouden: x.behouden,
      }));
    try {
      await api(`/klanten/${id}/bezit`, {
        methode: "POST",
        body: { peildatum, posities, overig: overigInvoer, kas_eur: getal(kas) || 0 },
      });
      setBezitFormulier(false);
      await laad();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  async function bewaarEvaluatie(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const formulier = e.currentTarget;
    const v = new FormData(formulier);
    try {
      await api(`/klanten/${id}/evaluaties`, {
        methode: "POST",
        body: { datum: v.get("datum"), uitkomst: v.get("uitkomst"), notitie: v.get("notitie") || null },
      });
      formulier.reset();
      await laad();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  if (!klant || !o) {
    return (
      <>
        <Fouten meldingen={fouten} />
        {fouten.length === 0 && <p className="zacht">Laden…</p>}
      </>
    );
  }

  const w = o.waardering && {
    ...o.waardering,
    behouden: o.waardering.overig.filter((x) => x.behouden).reduce((t, x) => t + x.waarde, 0),
  };
  const h = o.herbalancering;
  const actief = !klant.gearchiveerd;

  return (
    <>
      <p>
        <Link to={`/klanten/${id}`}>← {klant.naam}</Link>
      </p>
      <h1>Opvolging</h1>
      <Fouten meldingen={fouten} />

      <section className="kaart">
        <h2>Aandachtspunten</h2>
        <Signaallijst signalen={o.signalen} />
        {o.advies && (
          <p className="zacht">
            Laatste advies: versie {o.advies.versie} van {datum(o.advies.datum)}, risicoprofiel{" "}
            {naam(o.advies.risicoprofiel)}.
            {o.volgende_evaluatie && <> Volgende evaluatie: {datum(o.volgende_evaluatie)}.</>}
          </p>
        )}
      </section>

      {o.advies && (
        <section className="kaart">
          <div className="kop">
            <h2>Werkelijk bezit</h2>
            {actief && !bezitFormulier && (
              <div className="rij">
                {o.bezit?.overig.some((x) => x.isin && x.aantal) && (
                  <button className="tweede" onClick={() => void koersenOphalen()} disabled={bezig}>
                    {bezig ? "Koersen ophalen…" : "Koersen ophalen"}
                  </button>
                )}
                <button onClick={openBezit}>{o.bezit ? "Nieuwe opgave" : "Bezit vastleggen"}</button>
              </div>
            )}
          </div>

          {bezitFormulier && (
            <form onSubmit={bewaarBezit} aria-label="Bezit vastleggen">
              <p className="zacht">
                Neem de aantallen over van het meest recente depotoverzicht van de klant. De waarde wordt berekend met
                de laatst bekende slotkoers.
              </p>
              <label className="smal-veld">
                Depotoverzicht inlezen (CSV, optioneel)
                <input type="file" accept=".csv,.txt,text/csv" onChange={(e) => void leesBestand(e.target.files?.[0])} />
              </label>
              <p className="zacht">
                Een export van de bank of broker met een kolom met het ISIN en een kolom &lsquo;Aantal&rsquo; (of
                &lsquo;Stukken&rsquo;, &lsquo;Quantity&rsquo;). Er wordt pas iets opgeslagen als u op Opslaan klikt.
              </p>
              {inleesMeldingen.length > 0 && (
                <div className="melding let-op">
                  <ul>
                    {inleesMeldingen.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                </div>
              )}
              <label className="smal-veld">
                Peildatum
                <input type="date" value={peildatum} max={vandaag()} onChange={(e) => setPeildatum(e.target.value)} required />
              </label>
              <table className="compact bezit-tabel">
                <thead>
                  <tr>
                    <th>Fonds</th>
                    <th className="aantal-kolom">Aantal</th>
                    <th className="verwijder-kolom" />
                  </tr>
                </thead>
                <tbody>
                  {regels.map((r, i) => (
                    <tr key={i}>
                      <td>
                        <select
                          aria-label={`Fonds regel ${i + 1}`}
                          value={r.isin}
                          onChange={(e) => setRegels(regels.map((x, j) => (j === i ? { ...x, isin: e.target.value } : x)))}
                        >
                          <option value="">Kies een fonds…</option>
                          {instrumenten.map((ins) => (
                            <option key={ins.isin} value={ins.isin}>
                              {ins.naam}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          aria-label={`Aantal ${perIsin[r.isin]?.naam ?? `regel ${i + 1}`}`}
                          inputMode="decimal"
                          className="klein"
                          value={r.aantal}
                          onChange={(e) => setRegels(regels.map((x, j) => (j === i ? { ...x, aantal: e.target.value } : x)))}
                        />
                      </td>
                      <td>
                        <button type="button" className="tekstknop" onClick={() => setRegels(regels.filter((_, j) => j !== i))}>
                          Verwijder
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                <button type="button" className="tekstknop" onClick={() => setRegels([...regels, { isin: "", aantal: "" }])}>
                  + Fonds toevoegen
                </button>
              </p>
              <h3>Overig bezit</h3>
              <p className="zacht">
                Beleggingen die niet in de fondsenlijst staan, zoals losse aandelen of andere fondsen. Met ISIN en
                aantal wordt de actuele koers opgehaald; lukt dat niet, dan geldt de opgegeven waarde. Ze tellen mee in
                het vermogen en de verdeling. Wil de klant iets houden, vink
                dan &lsquo;Behouden&rsquo; aan: het blijft dan buiten het herbalanceren.
              </p>
              {overig.map((x, i) => {
                const zet = (deel: Partial<OverigRegel>) => setOverig(overig.map((y, j) => (j === i ? { ...y, ...deel } : y)));
                return (
                  <fieldset className="overig-regel" key={i}>
                    <legend className="zacht">Overig {i + 1}</legend>
                    <label>
                      Omschrijving
                      <input value={x.omschrijving} maxLength={200} required onChange={(e) => zet({ omschrijving: e.target.value })} />
                    </label>
                    <label>
                      ISIN (optioneel)
                      <input value={x.isin} maxLength={12} className="isin" onChange={(e) => zet({ isin: e.target.value })} />
                    </label>
                    <label>
                      Categorie
                      <select value={x.categorie} required onChange={(e) => zet({ categorie: e.target.value })}>
                        <option value="">Kies…</option>
                        {CATEGORIEEN.map((c) => (
                          <option key={c} value={c}>
                            {naam(c)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Aantal (optioneel)
                      <input inputMode="decimal" className="klein-bedrag" value={x.aantal} onChange={(e) => zet({ aantal: e.target.value })} />
                    </label>
                    <label>
                      Waarde (€)
                      <input
                        inputMode="decimal"
                        className="klein-bedrag"
                        value={x.waarde}
                        required={!(x.isin.trim() && x.aantal.trim())}
                        onChange={(e) => zet({ waarde: e.target.value })}
                      />
                    </label>
                    <label className="vinkje">
                      <input type="checkbox" checked={x.behouden} onChange={(e) => zet({ behouden: e.target.checked })} />
                      Behouden
                    </label>
                    <button type="button" className="tekstknop" onClick={() => setOverig(overig.filter((_, j) => j !== i))}>
                      Verwijder
                    </button>
                  </fieldset>
                );
              })}
              <p>
                <button type="button" className="tekstknop" onClick={() => setOverig([...overig, leegOverig()])}>
                  + Overig bezit toevoegen
                </button>
              </p>
              <label className="smal-veld">
                Geldsaldo op de beleggingsrekening (€)
                <input inputMode="decimal" value={kas} onChange={(e) => setKas(e.target.value)} />
              </label>
              <div className="rij">
                <button>Opslaan</button>
                <button type="button" className="tweede" onClick={() => setBezitFormulier(false)}>
                  Annuleren
                </button>
              </div>
            </form>
          )}

          {!o.bezit && !bezitFormulier && <p className="zacht">Nog geen bezit vastgelegd.</p>}

          {w && o.bezit && (
            <>
              <p className="uitkomst">
                {euro(w.totaal)} <span className="zacht">per {datum(o.bezit.peildatum)}</span>
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Fonds</th>
                    <th className="getal alleen-breed">Stukken</th>
                    <th className="getal alleen-breed">Koers</th>
                    <th className="getal">Waarde</th>
                    <th className="getal">Werkelijk</th>
                    <th className="getal">Advies</th>
                  </tr>
                </thead>
                <tbody>
                  {w.posities.map((p) => (
                    <tr key={p.isin}>
                      <td>{p.naam}</td>
                      <td className="getal alleen-breed">{stuks(p.aantal)}</td>
                      <td className="getal alleen-breed">
                        {p.koers === null ? <span className="zacht">onbekend</span> : koersEuro(p.koers)}
                      </td>
                      <td className="getal">{euro(p.waarde)}</td>
                      <td className="getal">{pct(p.gewicht)}</td>
                      <td className="getal">{pct(p.advies)}</td>
                    </tr>
                  ))}
                  {w.overig.map((x, i) => (
                    <tr key={`overig-${i}`}>
                      <td>
                        {x.omschrijving}{" "}
                        <span className="zacht">
                          (overig{x.behouden ? ", behouden" : ""},{" "}
                          {x.bron === "koers"
                            ? `koers van ${datum(x.koersdatum!)}`
                            : x.bron === "opgegeven"
                              ? "waarde opgegeven"
                              : "geen koers en geen waarde"}
                          )
                        </span>
                      </td>
                      <td className="getal alleen-breed">{x.aantal === null ? "" : stuks(x.aantal)}</td>
                      <td className="getal alleen-breed">{x.koers === null ? "" : koersEuro(x.koers)}</td>
                      <td className="getal">{euro(x.waarde)}</td>
                      <td className="getal">{pct(x.gewicht)}</td>
                      <td className="getal">{x.behouden ? <span className="zacht">—</span> : pct(0)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>Geldsaldo</td>
                    <td className="alleen-breed" />
                    <td className="alleen-breed" />
                    <td className="getal">{euro(w.kas)}</td>
                    <td className="getal">{pct(w.totaal ? Math.round((10000 * w.kas) / w.totaal) : 0)}</td>
                    <td />
                  </tr>
                </tbody>
              </table>

              <h3>Verdeling naar beleggingscategorie</h3>
              <table className="compact">
                <thead>
                  <tr>
                    <th>Categorie</th>
                    <th className="getal">Werkelijk</th>
                    <th className="getal">Bandbreedte</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(o.advies.banden).map(([c, b]) => {
                    const g = w.per_categorie[c] ?? 0;
                    const buiten = g < b.minimum * 100 || g > b.maximum * 100;
                    return (
                      <tr key={c}>
                        <td>{naam(c)}</td>
                        <td className={`getal${buiten ? " rood" : ""}`}>{pct(g)}</td>
                        <td className="getal">
                          {b.minimum}–{b.maximum}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      {w && (
        <section className="kaart">
          <h2>Herbalanceringsvoorstel</h2>
          {o.herbalancering_fout ? (
            <p className="melding let-op">Geen voorstel mogelijk: {o.herbalancering_fout}.</p>
          ) : h && h.transacties.length === 0 ? (
            <p className="melding goed">Het bezit ligt dicht genoeg bij het advies; herbalanceren is niet nodig.</p>
          ) : (
            h && (
              <>
                <p className="zacht">
                  Terug naar de gewichten van het advies, in hele stukken tegen de laatste slotkoers. Eerst verkopen,
                  dan kopen. Transactiekosten en spreads zijn niet meegerekend; controleer de koersen bij het opgeven
                  van de orders.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Actie</th>
                      <th>Fonds</th>
                      <th className="getal">Stukken</th>
                      <th className="getal">Bedrag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {h.transacties.map((t, i) => (
                      <tr key={`${t.isin ?? t.naam}-${t.actie}-${i}`}>
                        <td>{t.actie === "koop" ? "Kopen" : "Verkopen"}</td>
                        <td>{t.naam}</td>
                        <td className="getal">{t.aantal === null ? "alles" : stuks(t.aantal)}</td>
                        <td className="getal">{t.geschat ? `≈ ${euro(t.bedrag)}` : euro(t.bedrag)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {h.transacties.some((t) => t.geschat) && (
                  <p className="melding let-op">
                    ≈ Overig bezit is gerekend met de opgegeven waarde; de werkelijke opbrengst kan afwijken. Leg na de
                    verkoop een nieuwe opgave vast voordat u de aankopen doet.
                  </p>
                )}
                {w.behouden > 0 && (
                  <p className="zacht">
                    Behouden bezit ({euro(w.behouden)}) blijft staan; de gewichten van het advies gelden voor de rest
                    van het vermogen.
                  </p>
                )}
                <p className="zacht">Geldsaldo na uitvoering: {euro(h.kas_na)}.</p>
              </>
            )
          )}
        </section>
      )}

      {o.advies && (
        <section className="kaart">
          <h2>Evaluaties</h2>
          {o.evaluaties.length === 0 ? (
            <p className="zacht">Nog geen evaluatie vastgelegd.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Datum</th>
                  <th>Uitkomst</th>
                  <th>Notitie</th>
                  <th>Door</th>
                </tr>
              </thead>
              <tbody>
                {o.evaluaties.map((e) => (
                  <tr key={e.id}>
                    <td>{datum(e.datum)}</td>
                    <td>{UITKOMSTEN[e.uitkomst] ?? e.uitkomst}</td>
                    <td>{e.notitie ?? <span className="zacht">—</span>}</td>
                    <td>{e.door}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {actief && (
            <form onSubmit={bewaarEvaluatie} aria-label="Evaluatie vastleggen">
              <h3>Evaluatie vastleggen</h3>
              <div className="rij">
                <label>
                  Datum
                  <input type="date" name="datum" defaultValue={vandaag()} max={vandaag()} required />
                </label>
                <label>
                  Uitkomst
                  <select name="uitkomst" defaultValue="ongewijzigd">
                    {Object.entries(UITKOMSTEN).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                Notitie (wat is besproken, wat is afgesproken)
                <textarea name="notitie" rows={3} maxLength={4000} />
              </label>
              <button>Evaluatie vastleggen</button>
            </form>
          )}
        </section>
      )}
    </>
  );
}
