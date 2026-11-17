import { useEffect, useState } from "react";

import { Adviseur, AllocatieRegel, Risicoprofiel, Voorstel, api, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import { Voorstellen } from "../Voorstellen";

function Profielkaart({
  profiel,
  magWijzigen,
  naVoorstel,
}: {
  profiel: Risicoprofiel;
  magWijzigen: boolean;
  naVoorstel: () => void;
}) {
  const [regels, setRegels] = useState<AllocatieRegel[]>(profiel.allocatie);
  const [opgeslagen, setOpgeslagen] = useState<AllocatieRegel[]>(profiel.allocatie);
  const [fouten, setFouten] = useState<string[]>([]);
  const [gelukt, setGelukt] = useState<string | null>(null);

  const totaal = regels.reduce((som, r) => som + r.streef, 0);
  const gewijzigd = JSON.stringify(regels) !== JSON.stringify(opgeslagen);

  function wijzig(categorie: string, veld: "streef" | "minimum" | "maximum", waarde: string) {
    setGelukt(null);
    setRegels(regels.map((r) => (r.categorie === categorie ? { ...r, [veld]: Number(waarde) || 0 } : r)));
  }

  async function bewaar() {
    setFouten([]);
    try {
      const voorstel = await api<Voorstel>(`/risicoprofielen/${profiel.code}/allocatie`, {
        methode: "PUT",
        body: regels,
      });
      if (voorstel.status === "doorgevoerd") {
        setOpgeslagen(regels);
        setGelukt("Opgeslagen");
      } else {
        // Nog niet van kracht: de huidige allocatie blijft staan tot een tweede beheerder akkoord geeft.
        setRegels(opgeslagen);
        setGelukt("Voorstel ingediend; een tweede beheerder moet het goedkeuren.");
      }
      naVoorstel();
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  return (
    <section className="kaart">
      <h2>{profiel.naam}</h2>
      <table className="compact">
        <thead>
          <tr>
            <th>Categorie</th>
            <th className="getal">Min. %</th>
            <th className="getal">Streef %</th>
            <th className="getal">Max. %</th>
          </tr>
        </thead>
        <tbody>
          {regels.map((r) => (
            <tr key={r.categorie}>
              <td>{naam(r.categorie)}</td>
              {(["minimum", "streef", "maximum"] as const).map((veld) => (
                <td className="getal" key={veld}>
                  <input
                    className="klein"
                    type="number"
                    min={0}
                    max={100}
                    step={1}
                    aria-label={`${naam(r.categorie)} ${veld}`}
                    value={r[veld]}
                    disabled={!magWijzigen}
                    onChange={(e) => wijzig(r.categorie, veld, e.target.value)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>Totaal streefgewicht</td>
            <td />
            <td className={`getal ${totaal === 100 ? "" : "rood"}`}>{totaal}%</td>
            <td />
          </tr>
        </tfoot>
      </table>
      <Fouten meldingen={fouten} />
      <div className="rij">
        {magWijzigen && (
          <button onClick={bewaar} disabled={!gewijzigd || totaal !== 100}>
            Wijziging voorstellen
          </button>
        )}
        {gewijzigd && (
          <button className="tekstknop" onClick={() => setRegels(opgeslagen)}>
            Herstellen
          </button>
        )}
        {gelukt && !gewijzigd && <span className="zacht">{gelukt}</span>}
      </div>
    </section>
  );
}

export default function Modelallocaties({ adviseur }: { adviseur: Adviseur }) {
  const [profielen, setProfielen] = useState<Risicoprofiel[] | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);

  const [verversing, setVersversing] = useState(0);
  useEffect(() => {
    api<Risicoprofiel[]>("/risicoprofielen")
      .then(setProfielen)
      .catch((fout) => setFouten(meldingenVan(fout)));
  }, [verversing]);
  const magWijzigen = adviseur.rol === "beheerder";

  return (
    <>
      <h1>Modelallocaties</h1>
      <p className="zacht">
        De strategische asset allocatie per risicoprofiel. Een wijziging geldt voor alle adviseurs en voor nieuwe
        portefeuilles; elke wijziging wordt vastgelegd in het logboek.{" "}
        {magWijzigen
          ? "Een wijziging wordt van kracht nadat een tweede beheerder haar heeft goedgekeurd."
          : "Alleen een beheerder kan de modelallocaties wijzigen."}
      </p>
      <Fouten meldingen={fouten} />
      <Voorstellen
        soort="modelallocatie"
        adviseur={adviseur}
        verversing={verversing}
        naWijziging={() => setVersversing((v) => v + 1)}
      />
      {profielen?.map((p) => (
        <Profielkaart
          key={`${p.code}-${JSON.stringify(p.allocatie)}`}
          profiel={p}
          magWijzigen={magWijzigen}
          naVoorstel={() => setVersversing((v) => v + 1)}
        />
      ))}
    </>
  );
}
