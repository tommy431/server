import { FormEvent, useEffect, useState } from "react";

import { Adviseur, Voorstel, api } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import { ONDERNEMINGSVELDEN, Voorstellen } from "../Voorstellen";

type Gegevens = Record<string, string>;

export default function Onderneming({ adviseur }: { adviseur: Adviseur }) {
  const magWijzigen = adviseur.rol === "beheerder";
  const [gegevens, setGegevens] = useState<Gegevens | null>(null);
  const [ontbrekend, setOntbrekend] = useState<string[]>([]);
  const [verversing, setVerversing] = useState(0);
  const [fouten, setFouten] = useState<string[]>([]);
  const [melding, setMelding] = useState<string | null>(null);

  useEffect(() => {
    api<Record<string, string> & { ontbrekend: string[] }>("/onderneming")
      .then(({ ontbrekend: o, ...g }) => {
        setGegevens(Object.fromEntries(Object.keys(ONDERNEMINGSVELDEN).map((k) => [k, String(g[k] ?? "")])));
        setOntbrekend(o);
      })
      .catch((f) => setFouten(meldingenVan(f)));
  }, [verversing]);

  async function bewaar(e: FormEvent) {
    e.preventDefault();
    setFouten([]);
    try {
      const v = await api<Voorstel>("/onderneming", {
        methode: "PUT",
        body: { ...gegevens, email: gegevens?.email || null },
      });
      setMelding(
        v.status === "doorgevoerd"
          ? "Opgeslagen."
          : "Voorstel ingediend; de gegevens gelden pas nadat een tweede beheerder ze heeft goedgekeurd.",
      );
      setVerversing((x) => x + 1);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  if (!gegevens) return <Fouten meldingen={fouten} />;
  return (
    <>
      <h1>Onderneming</h1>
      <p className="zacht">
        Deze gegevens staan in elk adviesrapport. Zolang verplichte gegevens ontbreken, is een rapport een concept.{" "}
        {magWijzigen
          ? "Een wijziging wordt van kracht nadat een tweede beheerder haar heeft goedgekeurd."
          : "Alleen een beheerder kan deze gegevens wijzigen."}
      </p>
      {ontbrekend.length > 0 && (
        <div className="melding let-op">Nog niet ingevuld: {ontbrekend.join(", ")}.</div>
      )}
      <Voorstellen
        soort="onderneming"
        adviseur={adviseur}
        verversing={verversing}
        naWijziging={() => setVerversing((x) => x + 1)}
      />
      <form className="kaart" onSubmit={bewaar}>
        <fieldset className="kaal" disabled={!magWijzigen}>
          <div className="kolommen">
            {Object.entries(ONDERNEMINGSVELDEN)
              .filter(([k]) => k !== "klachtenregeling")
              .map(([k, label]) => (
                <label key={k}>
                  {label}
                  <input
                    value={gegevens[k]}
                    type={k === "email" ? "email" : "text"}
                    onChange={(e) => {
                      setMelding(null);
                      setGegevens({ ...gegevens, [k]: e.target.value });
                    }}
                  />
                </label>
              ))}
          </div>
          <label>
            Klachtenregeling (zoals in het rapport)
            <textarea
              value={gegevens.klachtenregeling}
              maxLength={2000}
              onChange={(e) => setGegevens({ ...gegevens, klachtenregeling: e.target.value })}
            />
          </label>
          <Fouten meldingen={fouten} />
          {melding && <div className="melding goed">{melding}</div>}
          {magWijzigen && <button>Wijziging voorstellen</button>}
        </fieldset>
      </form>
    </>
  );
}
