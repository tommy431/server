import { useEffect, useState } from "react";

import { AannamesUit, api, datum, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

const CATEGORIEEN = ["aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten"];
type Invoer = { rendement: string; volatiliteit: string };
const alsTekst = (f: number) => String(Math.round(f * 10000) / 100).replace(".", ",");
const alsFractie = (t: string) => Number(t.replace(",", ".")) / 100;
const correlatieTekst = (f: number) => String(f).replace(".", ",");

export default function Aannames() {
  const [geschiedenis, setGeschiedenis] = useState<AannamesUit[]>([]);
  const [waarden, setWaarden] = useState<Record<string, Invoer>>({});
  const [correlaties, setCorrelaties] = useState<Record<string, Record<string, string>>>({});
  const [inflatie, setInflatie] = useState("");
  const [stress, setStress] = useState<Record<string, string>>({});
  const [bron, setBron] = useState("");
  const [peildatum, setPeildatum] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);
  const [gelukt, setGelukt] = useState(false);

  function neemOver(a: AannamesUit) {
    setWaarden(
      Object.fromEntries(
        CATEGORIEEN.map((c) => [
          c,
          { rendement: alsTekst(a.categorieen[c].rendement), volatiliteit: alsTekst(a.categorieen[c].volatiliteit) },
        ]),
      ),
    );
    setCorrelaties(
      Object.fromEntries(
        CATEGORIEEN.map((r) => [r, Object.fromEntries(CATEGORIEEN.map((k) => [k, correlatieTekst(a.correlaties[r][k])]))]),
      ),
    );
    setInflatie(alsTekst(a.inflatie));
    setStress(Object.fromEntries(CATEGORIEEN.map((c) => [c, alsTekst(a.stress?.[c] ?? 0)])));
    setBron(a.bron);
    setPeildatum(a.peildatum);
  }

  useEffect(() => {
    api<AannamesUit[]>("/aannames/geschiedenis")
      .then((g) => {
        setGeschiedenis(g);
        if (g[0]) neemOver(g[0]);
      })
      .catch((f) => setFouten(meldingenVan(f)));
  }, []);

  function zetCorrelatie(r: string, k: string, tekst: string) {
    setGelukt(false);
    setCorrelaties({ ...correlaties, [r]: { ...correlaties[r], [k]: tekst }, [k]: { ...correlaties[k], [r]: tekst } });
  }

  async function bewaar() {
    setFouten([]);
    try {
      const nieuw = await api<AannamesUit>("/aannames", {
        methode: "POST",
        body: {
          bron,
          peildatum,
          inflatie: alsFractie(inflatie),
          stress: Object.fromEntries(CATEGORIEEN.map((c) => [c, alsFractie(stress[c] ?? "0")])),
          categorieen: Object.fromEntries(
            CATEGORIEEN.map((c) => [
              c,
              { rendement: alsFractie(waarden[c].rendement), volatiliteit: alsFractie(waarden[c].volatiliteit) },
            ]),
          ),
          correlaties: Object.fromEntries(
            CATEGORIEEN.map((r) => [r, Object.fromEntries(CATEGORIEEN.map((k) => [k, Number(correlaties[r][k].replace(",", "."))]))]),
          ),
        },
      });
      setGeschiedenis([nieuw, ...geschiedenis]);
      neemOver(nieuw);
      setGelukt(true);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  if (!geschiedenis.length) return <Fouten meldingen={fouten} />;
  const huidig = geschiedenis[0];

  return (
    <>
      <h1>Aannames voor verwacht rendement</h1>
      <p className="zacht">
        Deze aannames bepalen de scenario's bij elke portefeuille. Een wijziging wordt een nieuwe versie, geldt voor alle
        adviseurs en wordt vastgelegd in het logboek. Al vastgelegde portefeuilles houden de aannames van dat moment.
      </p>
      {huidig.bron.startsWith("Voorbeeldwaarden") && (
        <div className="melding let-op">
          De huidige aannames zijn voorbeeldwaarden zonder gepubliceerde bron. Vervang ze door aannames uit een erkende
          bron voordat de scenario's in een advies worden gebruikt.
        </div>
      )}

      <section className="kaart">
        <h2>Per beleggingscategorie</h2>
        <table className="compact">
          <thead>
            <tr>
              <th>Categorie</th>
              <th className="getal">Verwacht rendement % per jaar</th>
              <th className="getal">Volatiliteit % per jaar</th>
            </tr>
          </thead>
          <tbody>
            {CATEGORIEEN.map((c) => (
              <tr key={c}>
                <td>{naam(c)}</td>
                {(["rendement", "volatiliteit"] as const).map((veld) => (
                  <td className="getal" key={veld}>
                    <input
                      className="klein"
                      inputMode="decimal"
                      aria-label={`${naam(c)} ${veld}`}
                      value={waarden[c]?.[veld] ?? ""}
                      onChange={(e) => {
                        setGelukt(false);
                        setWaarden({ ...waarden, [c]: { ...waarden[c], [veld]: e.target.value } });
                      }}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="zacht klein-tekst">
          Nominaal en vóór kosten. Rendement is het rekenkundig gemiddelde per jaar; het samengestelde rendement ligt
          lager naarmate de volatiliteit hoger is.
        </p>

        <h3>Correlaties</h3>
        <div className="schuifvlak">
          <table className="compact">
            <thead>
              <tr>
                <th />
                {CATEGORIEEN.map((c) => (
                  <th key={c} className="getal">
                    {naam(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CATEGORIEEN.map((r, i) => (
                <tr key={r}>
                  <td>{naam(r)}</td>
                  {CATEGORIEEN.map((k, j) => (
                    <td key={k} className="getal">
                      {j === i ? (
                        "1"
                      ) : j < i ? (
                        <span className="zacht">{correlaties[r]?.[k]}</span>
                      ) : (
                        <input
                          className="klein"
                          inputMode="decimal"
                          aria-label={`Correlatie ${naam(r)} en ${naam(k)}`}
                          value={correlaties[r]?.[k] ?? ""}
                          onChange={(e) => zetCorrelatie(r, k, e.target.value)}
                        />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>Zware crisis</h3>
        <p className="zacht klein-tekst">
          Directe waardeverandering per categorie in een hypothetische zware crisis, in procenten. Wordt bij elke
          portefeuille getoond naast de scenario's.
        </p>
        <div className="kolommen">
          {CATEGORIEEN.map((c) => (
            <label key={c}>
              {naam(c)} %
              <input
                inputMode="decimal"
                aria-label={`Crisis ${naam(c)}`}
                value={stress[c] ?? ""}
                onChange={(e) => {
                  setGelukt(false);
                  setStress({ ...stress, [c]: e.target.value });
                }}
              />
            </label>
          ))}
        </div>

        <div className="kolommen">
          <label>
            Inflatie % per jaar
            <input inputMode="decimal" value={inflatie} onChange={(e) => setInflatie(e.target.value)} />
          </label>
          <label>
            Peildatum
            <input type="date" value={peildatum} onChange={(e) => setPeildatum(e.target.value)} />
          </label>
        </div>
        <label>
          Bron
          <textarea value={bron} maxLength={500} onChange={(e) => setBron(e.target.value)} />
        </label>
        <Fouten meldingen={fouten} />
        {gelukt && <div className="melding goed">Nieuwe versie vastgelegd.</div>}
        <button onClick={bewaar}>Nieuwe versie vastleggen</button>
      </section>

      <section className="kaart">
        <h2>Eerdere versies</h2>
        <table className="compact">
          <thead>
            <tr>
              <th>Vastgelegd</th>
              <th>Peildatum</th>
              <th className="getal">Aandelen</th>
              <th className="getal">Obligaties</th>
              <th>Bron</th>
            </tr>
          </thead>
          <tbody>
            {geschiedenis.map((g) => (
              <tr key={g.id}>
                <td>{datum(g.vastgelegd_op)}</td>
                <td>{datum(g.peildatum)}</td>
                <td className="getal">{alsTekst(g.categorieen.aandelen.rendement)}%</td>
                <td className="getal">{alsTekst(g.categorieen.obligaties.rendement)}%</td>
                <td>{g.bron}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
