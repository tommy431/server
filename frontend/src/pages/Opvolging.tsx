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

export default function Opvolging() {
  const id = Number(useParams().id);
  const [klant, setKlant] = useState<Klant | null>(null);
  const [o, setO] = useState<OpvolgingT | null>(null);
  const [instrumenten, setInstrumenten] = useState<Instrument[]>([]);
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezitFormulier, setBezitFormulier] = useState(false);
  const [regels, setRegels] = useState<Regel[]>([]);
  const [kas, setKas] = useState("0");
  const [peildatum, setPeildatum] = useState(vandaag());

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
    setKas(String(o?.bezit?.kas_eur ?? 0));
    setPeildatum(vandaag());
    setBezitFormulier(true);
  }

  async function bewaarBezit(e: FormEvent) {
    e.preventDefault();
    const posities = regels
      .filter((r) => r.isin && r.aantal.trim() !== "")
      .map((r) => ({ isin: r.isin, aantal: Number(r.aantal.replace(",", ".")) }))
      .filter((r) => r.aantal !== 0);
    try {
      await api(`/klanten/${id}/bezit`, {
        methode: "POST",
        body: { peildatum, posities, kas_eur: Number(kas.replace(",", ".")) || 0 },
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

  const w = o.waardering;
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
              <button onClick={openBezit}>{o.bezit ? "Nieuwe opgave" : "Bezit vastleggen"}</button>
            )}
          </div>

          {bezitFormulier && (
            <form onSubmit={bewaarBezit} aria-label="Bezit vastleggen">
              <p className="zacht">
                Neem de aantallen over van het meest recente depotoverzicht van de klant. De waarde wordt berekend met
                de laatst bekende slotkoers.
              </p>
              <label className="smal-veld">
                Peildatum
                <input type="date" value={peildatum} max={vandaag()} onChange={(e) => setPeildatum(e.target.value)} required />
              </label>
              <table className="compact">
                <thead>
                  <tr>
                    <th>Fonds</th>
                    <th>Aantal stukken</th>
                    <th />
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
                    {h.transacties.map((t) => (
                      <tr key={t.isin + t.actie}>
                        <td>{t.actie === "koop" ? "Kopen" : "Verkopen"}</td>
                        <td>{t.naam}</td>
                        <td className="getal">{stuks(t.aantal)}</td>
                        <td className="getal">{euro(t.bedrag)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
