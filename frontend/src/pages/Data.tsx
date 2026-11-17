import { useCallback, useEffect, useState } from "react";

import { Adviseur, DataStatus, VerversResultaat, api, datum } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

export default function Data({ adviseur }: { adviseur: Adviseur }) {
  const [status, setStatus] = useState<DataStatus[] | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezig, setBezig] = useState(false);
  const [resultaat, setResultaat] = useState<string | null>(null);

  const laad = useCallback(async () => {
    try {
      setStatus(await api<DataStatus[]>("/data/status"));
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }, []);

  useEffect(() => {
    void laad();
  }, [laad]);

  async function ververs() {
    setBezig(true);
    setFouten([]);
    setResultaat(null);
    try {
      const uit = await api<VerversResultaat[]>("/data/verversen", { methode: "POST" });
      const mislukt = uit.filter((r) => r.fout);
      setResultaat(`${uit.length - mislukt.length} van ${uit.length} onderdelen bijgewerkt.`);
      setFouten(mislukt.map((r) => `${r.onderdeel}: ${r.fout}`));
      await laad();
    } catch (fout) {
      setFouten(meldingenVan(fout));
    } finally {
      setBezig(false);
    }
  }

  const metBevinding = status?.filter((s) => s.bevindingen.length > 0).length ?? 0;

  return (
    <>
      <div className="kop">
        <h1>Koersdata</h1>
        {adviseur.rol === "beheerder" && (
          <button onClick={ververs} disabled={bezig}>
            {bezig ? "Bezig met ophalen…" : "Koersen verversen"}
          </button>
        )}
      </div>
      <p className="zacht">
        Bron: Yahoo Finance (dagkoersen, gecorrigeerd voor dividend). Dit is een onofficiële bron voor het prototype;
        niet geschikt voor commercieel gebruik.
      </p>
      {resultaat && <div className="melding">{resultaat}</div>}
      <Fouten meldingen={fouten} />
      {status === null ? (
        <p className="zacht">Laden…</p>
      ) : status.length === 0 ? (
        <p className="zacht">Er zijn nog geen instrumenten geladen.</p>
      ) : (
        <>
          <p>
            {status.length} instrumenten, waarvan {metBevinding} met een bevinding.
          </p>
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Koersen vanaf</th>
                <th>Laatste koers</th>
                <th>Bevindingen</th>
              </tr>
            </thead>
            <tbody>
              {status.map((s) => (
                <tr key={s.isin}>
                  <td>
                    {s.naam}
                    <div className="zacht klein-tekst">{s.isin}</div>
                  </td>
                  <td>{s.eerste_koers ? datum(s.eerste_koers) : "—"}</td>
                  <td>{s.laatste_koers ? datum(s.laatste_koers) : "—"}</td>
                  <td>
                    {s.bevindingen.length === 0
                      ? "Geen"
                      : s.bevindingen.map((b) => (
                          <div key={b.code} className={b.ernst === "fout" ? "rood" : "oranje"}>
                            {b.melding}
                          </div>
                        ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}
