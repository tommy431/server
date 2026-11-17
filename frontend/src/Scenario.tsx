import { useState } from "react";
import { Link } from "react-router-dom";

import { ScenarioUitkomst, datum, euro, naam, procent } from "./api";
import { Scenariografiek } from "./Scenariografiek";

const kans = (k: number) => `${Math.round(k * 100)}%`;

export function Scenario({ uitkomst }: { uitkomst: ScenarioUitkomst }) {
  const [reeel, setReeel] = useState(false);
  const s = uitkomst.scenario;
  if (!s) return <p className="zacht">{uitkomst.reden}</p>;
  const eind = s.jaren[s.jaren.length - 1];
  const w = reeel ? eind.reeel : eind.nominaal;
  const ingelegd = reeel ? eind.ingelegd_reeel : eind.ingelegd;
  const a = uitkomst.aannames;

  return (
    <>
      <div className="keuzerij" role="radiogroup" aria-label="Bedragen">
        <span>Bedragen:</span>
        <label className="keuze">
          <input type="radio" checked={!reeel} onChange={() => setReeel(false)} />
          Nominaal
        </label>
        <label className="keuze">
          <input type="radio" checked={reeel} onChange={() => setReeel(true)} />
          In koopkracht van vandaag ({procent(a.inflatie)} inflatie per jaar)
        </label>
      </div>

      <table className="compact">
        <thead>
          <tr>
            <th>Na {s.horizon_jaren} jaar</th>
            <th className="getal">Vermogen</th>
            <th className="getal">t.o.v. ingelegd</th>
          </tr>
        </thead>
        <tbody>
          {(
            [
              ["Goed scenario", w[2]],
              ["Verwacht scenario", w[1]],
              ["Slecht scenario", w[0]],
            ] as const
          ).map(([titel, bedrag]) => (
            <tr key={titel}>
              <td>{titel}</td>
              <td className="getal">{euro(bedrag)}</td>
              <td className="getal">{euro(bedrag - ingelegd)}</td>
            </tr>
          ))}
          <tr>
            <td className="zacht">Totaal ingelegd{reeel && " (in koopkracht van vandaag)"}</td>
            <td className="getal zacht">{euro(ingelegd)}</td>
            <td />
          </tr>
        </tbody>
      </table>

      <Scenariografiek jaren={s.jaren} reeel={reeel} doel={s.doelvermogen} />

      <dl>
        {s.doelvermogen && s.kans_doel_nominaal !== null && s.kans_doel_reeel !== null && (
          <>
            <dt>Kans op doelvermogen</dt>
            <dd>
              {kans(s.kans_doel_nominaal)} dat {euro(s.doelvermogen)} wordt gehaald. Gemeten in koopkracht van vandaag is
              die kans {kans(s.kans_doel_reeel)}.
            </dd>
          </>
        )}
        <dt>Kans op minder dan ingelegd</dt>
        <dd>{kans(s.kans_minder_dan_ingelegd)} (nominaal, na {s.horizon_jaren} jaar)</dd>
        <dt>Effect van kosten</dt>
        <dd>
          {procent(s.kosten_pct / 100)} per jaar ({procent(uitkomst.lopende_kosten_pct / 100)} fondskosten
          {uitkomst.overige_kosten_pct > 0 && ` + ${procent(uitkomst.overige_kosten_pct / 100)} overige kosten`}) verlaagt
          het verwachte eindvermogen met circa {euro(s.kosten_effect_mediaan)}.
        </dd>
        <dt>Effect van inflatie</dt>
        <dd>
          Het verwachte eindvermogen is in koopkracht van vandaag circa {euro(s.inflatie_effect_mediaan)} minder waard.
        </dd>
        <dt>Uitgangspunten mix</dt>
        <dd>
          Verwacht rendement {procent(s.verwacht_rendement)} per jaar vóór kosten, volatiliteit{" "}
          {procent(s.verwachte_volatiliteit)}.{" "}
          {Object.entries(uitkomst.gewichten)
            .map(([c, g]) => `${naam(c)} ${Math.round(g * 1000) / 10}%`)
            .join(", ")
            .replace(/\./g, ",")}
          .
        </dd>
      </dl>

      <div className={a.bron.startsWith("Voorbeeldwaarden") ? "melding let-op" : "melding"}>
        Aannames van {datum(a.peildatum)}. Bron: {a.bron} <Link to="/aannames">Aannames bekijken</Link>
      </div>

      <h3>Toelichting bij de berekening</h3>
      <ul className="zacht klein-tekst">
        <li>
          {new Intl.NumberFormat("nl-NL").format(s.paden)} gesimuleerde verlopen met maandelijkse rendementen per
          beleggingscategorie, op basis van de aannames voor rendement, volatiliteit en correlaties.
        </li>
        <li>
          De inleg wordt direct belegd en de storting van {euro(s.storting_per_maand)} aan het eind van elke maand. De
          portefeuille wordt maandelijks teruggebracht naar de verdeling per categorie.
        </li>
        <li>
          Het model gaat uit van normaal verdeelde (log)rendementen. Extreme dalingen komen in werkelijkheid vaker voor
          dan het model aanneemt; het slechte scenario is geen ondergrens.
        </li>
        <li>Belastingen zijn niet meegerekend.</li>
      </ul>
      <p className="wettelijk">
        Dit zijn scenario's op basis van aannames, geen voorspelling. De werkelijke uitkomst kan hoger of lager zijn,
        ook lager dan het slechte scenario.
      </p>
    </>
  );
}
