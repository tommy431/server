import { useEffect, useState } from "react";

import { AllocatieRegel, Risicoprofiel, api, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

function Profielkaart({ profiel }: { profiel: Risicoprofiel }) {
  const [regels, setRegels] = useState<AllocatieRegel[]>(profiel.allocatie);
  const [opgeslagen, setOpgeslagen] = useState<AllocatieRegel[]>(profiel.allocatie);
  const [fouten, setFouten] = useState<string[]>([]);
  const [gelukt, setGelukt] = useState(false);

  const totaal = regels.reduce((som, r) => som + r.streef, 0);
  const gewijzigd = JSON.stringify(regels) !== JSON.stringify(opgeslagen);

  function wijzig(categorie: string, veld: "streef" | "minimum" | "maximum", waarde: string) {
    setGelukt(false);
    setRegels(regels.map((r) => (r.categorie === categorie ? { ...r, [veld]: Number(waarde) || 0 } : r)));
  }

  async function bewaar() {
    setFouten([]);
    try {
      const nieuw = await api<Risicoprofiel>(`/risicoprofielen/${profiel.code}/allocatie`, {
        methode: "PUT",
        body: regels,
      });
      setRegels(nieuw.allocatie);
      setOpgeslagen(nieuw.allocatie);
      setGelukt(true);
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
        <button onClick={bewaar} disabled={!gewijzigd || totaal !== 100}>
          Opslaan
        </button>
        {gewijzigd && (
          <button className="tekstknop" onClick={() => setRegels(opgeslagen)}>
            Herstellen
          </button>
        )}
        {gelukt && !gewijzigd && <span className="zacht">Opgeslagen</span>}
      </div>
    </section>
  );
}

export default function Modelallocaties() {
  const [profielen, setProfielen] = useState<Risicoprofiel[] | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);

  useEffect(() => {
    api<Risicoprofiel[]>("/risicoprofielen")
      .then(setProfielen)
      .catch((fout) => setFouten(meldingenVan(fout)));
  }, []);

  return (
    <>
      <h1>Modelallocaties</h1>
      <p className="zacht">
        De strategische asset allocatie per risicoprofiel. Een wijziging geldt voor alle adviseurs en voor nieuwe
        portefeuilles; elke wijziging wordt vastgelegd in het logboek.
      </p>
      <Fouten meldingen={fouten} />
      {profielen?.map((p) => <Profielkaart key={p.code} profiel={p} />)}
    </>
  );
}
