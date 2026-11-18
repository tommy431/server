import { FormEvent, useCallback, useEffect, useState } from "react";

import { Adviseur, DataStatus, VerversResultaat, api, datum } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

export default function Data({ adviseur }: { adviseur: Adviseur }) {
  const [status, setStatus] = useState<DataStatus[] | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezig, setBezig] = useState(false);
  const [resultaat, setResultaat] = useState<string | null>(null);
  const [controle, setControle] = useState<number | null>(null);
  const beheerder = adviseur.rol === "beheerder";

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

  async function bewaarKosten(e: FormEvent<HTMLFormElement>, s: DataStatus) {
    e.preventDefault();
    const v = new FormData(e.currentTarget);
    try {
      await api(`/instrumenten/${s.instrument_id}/kosten`, {
        methode: "PUT",
        body: {
          lopende_kosten: Number(String(v.get("kosten")).replace(",", ".")),
          bron: v.get("bron"),
        },
      });
      setControle(null);
      setResultaat(`Kosten van ${s.naam} vastgelegd als gecontroleerd.`);
      await laad();
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  const ongecontroleerd = status?.filter((s) => !s.kosten_geverifieerd).length ?? 0;
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
          {ongecontroleerd > 0 && (
            <div className="melding let-op">
              Van {ongecontroleerd} fonds(en) zijn de lopende kosten nog niet gecontroleerd tegen het actuele
              essentiële-informatiedocument (EID). Een adviesrapport met zo&apos;n fonds blijft een concept.
              {beheerder ? " Controleer ze hieronder." : " Een beheerder kan ze controleren."}
            </div>
          )}
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Koersen vanaf</th>
                <th>Laatste koers</th>
                <th>Lopende kosten</th>
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
                    {s.lopende_kosten.toLocaleString("nl-NL", { minimumFractionDigits: 2 })}%
                    <div className="zacht klein-tekst">
                      {s.kosten_geverifieerd
                        ? s.kosten_gecontroleerd_op
                          ? `Gecontroleerd ${datum(s.kosten_gecontroleerd_op)}${s.kosten_bron ? ` (${s.kosten_bron})` : ""}`
                          : "Gecontroleerd"
                        : "Niet gecontroleerd"}
                    </div>
                    {beheerder && controle !== s.instrument_id && (
                      <button className="tekstknop" onClick={() => setControle(s.instrument_id)}>
                        Controleren
                      </button>
                    )}
                    {controle === s.instrument_id && (
                      <form onSubmit={(e) => void bewaarKosten(e, s)} aria-label={`Kosten controleren ${s.naam}`}>
                        <label>
                          Lopende kosten volgens EID (%)
                          <input
                            name="kosten"
                            inputMode="decimal"
                            className="klein-bedrag"
                            defaultValue={String(s.lopende_kosten).replace(".", ",")}
                            required
                          />
                        </label>
                        <label>
                          Bron
                          <input name="bron" placeholder="Bijv. EID van maart 2026" minLength={3} required />
                        </label>
                        <div className="rij">
                          <button>Vastleggen</button>
                          <button type="button" className="tweede" onClick={() => setControle(null)}>
                            Annuleren
                          </button>
                        </div>
                      </form>
                    )}
                  </td>
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
