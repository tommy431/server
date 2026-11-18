import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Klant, api, datum, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

export default function Klanten() {
  const [klanten, setKlanten] = useState<Klant[] | null>(null);
  const [archief, setArchief] = useState(false);
  const [nieuweNaam, setNieuweNaam] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);
  const navigeer = useNavigate();

  const laad = useCallback(async () => {
    try {
      setKlanten(await api<Klant[]>(`/klanten?gearchiveerd=${archief}`));
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }, [archief]);

  useEffect(() => {
    void laad();
  }, [laad]);

  async function maakAan(e: FormEvent) {
    e.preventDefault();
    try {
      const klant = await api<Klant>("/klanten", { methode: "POST", body: { naam: nieuweNaam } });
      navigeer(`/klanten/${klant.id}`);
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  return (
    <>
      <div className="kop">
        <h1>{archief ? "Gearchiveerde klanten" : "Klanten"}</h1>
        <button className="tekstknop" onClick={() => setArchief(!archief)}>
          {archief ? "Toon actieve klanten" : "Toon archief"}
        </button>
      </div>
      <Fouten meldingen={fouten} />

      {!archief && (
        <form className="rij" onSubmit={maakAan}>
          <input
            aria-label="Naam nieuwe klant"
            placeholder="Naam nieuwe klant"
            value={nieuweNaam}
            onChange={(e) => setNieuweNaam(e.target.value)}
            required
          />
          <button>Klant toevoegen</button>
        </form>
      )}

      {klanten === null ? (
        <p className="zacht">Laden…</p>
      ) : klanten.length === 0 ? (
        <p className="zacht">{archief ? "Het archief is leeg." : "Nog geen klanten. Voeg hierboven de eerste toe."}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Naam</th>
              <th>Risicoprofiel</th>
              <th>Horizon</th>
              <th>Profiel vastgelegd</th>
            </tr>
          </thead>
          <tbody>
            {klanten.map((k) => (
              <tr key={k.id}>
                <td>
                  <Link to={`/klanten/${k.id}`}>{k.naam}</Link>
                </td>
                {k.huidig_profiel ? (
                  <>
                    <td>{naam(k.huidig_profiel.risicoprofiel)}</td>
                    <td>{k.huidig_profiel.horizon_jaren} jaar</td>
                    <td className="datumcel">{datum(k.huidig_profiel.vastgelegd_op)}</td>
                  </>
                ) : (
                  <td colSpan={3} className="zacht">
                    Nog geen profiel
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
