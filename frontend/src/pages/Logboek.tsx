import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

type Regel = {
  id: number;
  tijdstip: string;
  door: string | null;
  actie: string;
  entiteit: string | null;
  entiteit_id: string | null;
  details: Record<string, unknown> | null;
};
type Controle = { in_orde: boolean; aantal: number; laatste_hash: string; fout_bij: number | null; fout: string | null };

const tijd = (iso: string) =>
  new Intl.DateTimeFormat("nl-NL", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(iso));
const leesbaar = (actie: string) => actie.replace(/_/g, " ");

export default function Logboek() {
  const [regels, setRegels] = useState<Regel[]>([]);
  const [controle, setControle] = useState<Controle | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);
  const [meer, setMeer] = useState(true);

  const laad = useCallback(async (voor?: number) => {
    try {
      const nieuw = await api<Regel[]>(`/logboek?aantal=100${voor ? `&voor_id=${voor}` : ""}`);
      setRegels((oud) => (voor ? [...oud, ...nieuw] : nieuw));
      setMeer(nieuw.length === 100);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }, []);

  useEffect(() => {
    void laad();
  }, [laad]);

  async function controleer() {
    try {
      setControle(await api<Controle>("/logboek/controle"));
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  return (
    <>
      <div className="kop">
        <h1>Logboek</h1>
        <button onClick={controleer}>Keten controleren</button>
      </div>
      <p className="zacht">
        Elke regel bevat een vingerafdruk van zichzelf en van de vorige regel. Wie achteraf iets wijzigt of verwijdert,
        verbreekt de keten.
      </p>
      {controle &&
        (controle.in_orde ? (
          <div className="melding goed" role="status">
            Het logboek is ongewijzigd: {controle.aantal} regels.
            <div className="klein-tekst">
              Laatste vingerafdruk: <code>{controle.laatste_hash}</code>. Bewaar deze buiten het systeem, bijvoorbeeld
              in een maandelijkse e-mail, als extra bewijs.
            </div>
          </div>
        ) : (
          <div className="melding fout" role="alert">
            Het logboek is niet in orde bij regel {controle.fout_bij}: {controle.fout}
          </div>
        ))}
      <Fouten meldingen={fouten} />
      <div className="schuifvlak">
        <table>
          <thead>
            <tr>
              <th>Tijdstip</th>
              <th>Door</th>
              <th>Actie</th>
              <th>Betreft</th>
            </tr>
          </thead>
          <tbody>
            {regels.map((r) => (
              <tr key={r.id}>
                <td className="klein-tekst">{tijd(r.tijdstip)}</td>
                <td>{r.door ?? <span className="zacht">systeem</span>}</td>
                <td>{leesbaar(r.actie)}</td>
                <td className="klein-tekst">
                  {[r.entiteit, r.entiteit_id].filter(Boolean).join(" ")}
                  {r.details && <div className="zacht">{JSON.stringify(r.details).slice(0, 160)}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {meer && regels.length > 0 && (
        <button className="tekstknop" onClick={() => laad(regels[regels.length - 1].id)}>
          Oudere regels tonen
        </button>
      )}
    </>
  );
}
