import { AnalyseUitkomst, datum, naam, procent, rendement } from "./api";
import { Waardegrafiek } from "./Waardegrafiek";

const TITEL: Record<string, string> = { "1j": "1 jaar", "3j": "3 jaar", "5j": "5 jaar", "10j": "10 jaar" };

/** Historische analyse van een portefeuille tegen de benchmark van het risicoprofiel. */
export function Analyse({ uitkomst }: { uitkomst: AnalyseUitkomst }) {
  const a = uitkomst.analyse;
  if (!a.peildatum) {
    return (
      <div className="melding let-op">
        Geen historische analyse mogelijk. {a.waarschuwingen.join(" ")} Ververs de koersen in het scherm Data.
      </div>
    );
  }
  const jaren = a.kalenderjaren;
  const beste = jaren.length ? jaren.reduce((x, y) => (y.portefeuille > x.portefeuille ? y : x)) : null;
  const slechtste = jaren.length ? jaren.reduce((x, y) => (y.portefeuille < x.portefeuille ? y : x)) : null;
  const metBenchmark = uitkomst.benchmark.length > 0;

  return (
    <>
      <p className="zacht">
        Koersen tot en met {datum(a.peildatum)}. Totaalrendement in euro, inclusief dividend en na lopende fondskosten.
      </p>
      {a.waarschuwingen.length > 0 && (
        <div className="melding let-op">
          <ul>
            {a.waarschuwingen.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <table className="compact">
        <thead>
          <tr>
            <th>Periode</th>
            <th className="getal">Rendement per jaar</th>
            <th className="getal">Volatiliteit</th>
            <th className="getal">Grootste daling</th>
            <th className="getal">Sharpe-ratio</th>
            {metBenchmark && <th className="getal">Benchmark per jaar</th>}
            {metBenchmark && <th className="getal">Verschil</th>}
          </tr>
        </thead>
        <tbody>
          {a.perioden.map((p) => {
            const titel = p.code === "start" ? (p.van ? `Sinds ${datum(p.van)}` : "Sinds start") : TITEL[p.code];
            if (!p.beschikbaar || !p.portefeuille) {
              return (
                <tr key={p.code}>
                  <td>{titel}</td>
                  <td colSpan={metBenchmark ? 6 : 4} className="zacht">
                    Niet beschikbaar: {p.reden}
                  </td>
                </tr>
              );
            }
            const k = p.portefeuille;
            return (
              <tr key={p.code}>
                <td>{titel}</td>
                <td className="getal">{rendement(k.rendement_per_jaar)}</td>
                <td className="getal">{procent(k.volatiliteit)}</td>
                <td className="getal" title={`Van ${datum(k.max_daling_top)} tot ${datum(k.max_daling_dal)}`}>
                  {rendement(k.max_daling)}
                </td>
                <td className="getal">
                  {k.sharpe === null
                    ? "—"
                    : new Intl.NumberFormat("nl-NL", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(k.sharpe)}
                </td>
                {metBenchmark && (
                  <td className="getal">{p.benchmark ? rendement(p.benchmark.rendement_per_jaar) : "—"}</td>
                )}
                {metBenchmark && (
                  <td className="getal">
                    {p.benchmark ? rendement(k.rendement_per_jaar - p.benchmark.rendement_per_jaar) : "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>

      <Waardegrafiek punten={a.waardeverloop} />

      {jaren.length > 0 && beste && slechtste && (
        <>
          <h3>Kalenderjaren</h3>
          <p>
            Beste jaar: {beste.jaar} ({rendement(beste.portefeuille)}). Slechtste jaar: {slechtste.jaar} (
            {rendement(slechtste.portefeuille)}).
          </p>
          <table className="compact smal-tabel">
            <thead>
              <tr>
                <th>Jaar</th>
                <th className="getal">Portefeuille</th>
                {metBenchmark && <th className="getal">Benchmark</th>}
              </tr>
            </thead>
            <tbody>
              {[...jaren].reverse().map((j) => (
                <tr key={j.jaar}>
                  <td>{j.jaar}</td>
                  <td className="getal">{rendement(j.portefeuille)}</td>
                  {metBenchmark && <td className="getal">{j.benchmark === null ? "—" : rendement(j.benchmark)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Toelichting bij de berekening</h3>
      <ul className="zacht klein-tekst">
        <li>
          De portefeuille wordt op de eerste handelsdag van elk kalenderjaar teruggebracht naar de opgegeven gewichten.
        </li>
        <li>
          Lopende fondskosten zijn in de koersen verwerkt. Transactiekosten en kosten van adviseur of bank zijn niet
          meegerekend.
        </li>
        <li>Volatiliteit is de standaarddeviatie van dagrendementen, omgerekend naar jaarbasis.</li>
        <li>
          Grootste daling is de grootste daling van top tot dal binnen de periode. Bij een periode korter dan een jaar
          is het rendement niet naar jaarbasis omgerekend.
        </li>
        {uitkomst.risicovrij && (
          <li>De Sharpe-ratio gebruikt {uitkomst.risicovrij} als risicovrij rendement.</li>
        )}
        {metBenchmark && (
          <li>
            Benchmark: {uitkomst.benchmark.map((b) => `${b.gewicht}% ${b.naam} (${naam(b.categorie).toLowerCase()})`).join(", ")}
            . Dit zijn beleggingsfondsen na kosten, geen indices.
          </li>
        )}
      </ul>
      <p className="wettelijk">In het verleden behaalde resultaten bieden geen garantie voor de toekomst.</p>
    </>
  );
}
