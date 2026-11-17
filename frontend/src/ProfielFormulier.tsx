import { FormEvent, useEffect, useState } from "react";

import { Profiel, Risicoprofiel, Uitkomst, Vragenlijst, api, naam } from "./api";
import { Fouten, meldingenVan } from "./Fouten";

type Props = {
  klantId: number;
  vorige: Profiel | null;
  vragenlijst: Vragenlijst;
  risicoprofielen: Risicoprofiel[];
  naOpslaan: () => void;
  annuleer: () => void;
};

const getal = (tekst: string) => (tekst.trim() === "" ? null : Number(tekst));

export default function ProfielFormulier({
  klantId,
  vorige,
  vragenlijst,
  risicoprofielen,
  naOpslaan,
  annuleer,
}: Props) {
  const [doel, setDoel] = useState(vorige?.doel ?? "");
  const [horizon, setHorizon] = useState(String(vorige?.horizon_jaren ?? ""));
  const [inleg, setInleg] = useState(String(vorige?.inleg_eur ?? ""));
  const [storting, setStorting] = useState(String(vorige?.storting_per_maand_eur ?? "0"));
  const [doelvermogen, setDoelvermogen] = useState(String(vorige?.doelvermogen_eur ?? ""));
  const [antwoorden, setAntwoorden] = useState<Record<string, number>>(vorige?.antwoorden ?? {});
  const [duurzaamheid, setDuurzaamheid] = useState(vorige?.duurzaamheid ?? "geen");
  const [uitsluitingen, setUitsluitingen] = useState<string[]>(vorige?.uitsluitingen ?? []);
  const [duurzaamToelichting, setDuurzaamToelichting] = useState(vorige?.duurzaamheid_toelichting ?? "");
  // Een eerder gekozen defensiever profiel en de toelichting worden overgenomen.
  const eerderAfgeweken = vorige !== null && vorige.risicoprofiel !== vorige.afgeleid_risicoprofiel;
  const [gekozen, setGekozen] = useState(eerderAfgeweken ? vorige.risicoprofiel : "");
  const [afwijking, setAfwijking] = useState(eerderAfgeweken ? (vorige.afwijking_toelichting ?? "") : "");
  const [uitkomst, setUitkomst] = useState<Uitkomst | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezig, setBezig] = useState(false);

  const compleet = vragenlijst.vragen.every((v) => antwoorden[v.code] !== undefined);
  const horizonJaren = getal(horizon);

  // Toon het afgeleide profiel zodra alle vragen en de horizon zijn ingevuld.
  useEffect(() => {
    if (!compleet || !horizonJaren || horizonJaren < 1 || horizonJaren > 60) {
      setUitkomst(null);
      return;
    }
    let actueel = true;
    api<Uitkomst>("/vragenlijst/uitkomst", {
      methode: "POST",
      body: { antwoorden, horizon_jaren: horizonJaren },
    })
      .then((u) => actueel && setUitkomst(u))
      .catch(() => actueel && setUitkomst(null));
    return () => {
      actueel = false;
    };
  }, [antwoorden, compleet, horizonJaren]);

  const afgeleid = risicoprofielen.find((p) => p.code === uitkomst?.risicoprofiel);
  const defensiever = afgeleid ? risicoprofielen.filter((p) => p.niveau < afgeleid.niveau) : [];

  // Een eerder gekozen profiel dat niet langer defensiever is dan het afgeleide vervalt.
  useEffect(() => {
    if (afgeleid && gekozen && !defensiever.some((p) => p.code === gekozen)) setGekozen("");
  }, [afgeleid, defensiever, gekozen]);

  async function verstuur(e: FormEvent) {
    e.preventDefault();
    if (!compleet) {
      setFouten(["Beantwoord alle vragen van de vragenlijst."]);
      return;
    }
    setBezig(true);
    setFouten([]);
    try {
      await api(`/klanten/${klantId}/profielen`, {
        methode: "POST",
        body: {
          doel,
          horizon_jaren: horizonJaren,
          inleg_eur: getal(inleg) ?? 0,
          storting_per_maand_eur: getal(storting) ?? 0,
          doelvermogen_eur: getal(doelvermogen),
          antwoorden,
          duurzaamheid,
          uitsluitingen,
          duurzaamheid_toelichting: duurzaamToelichting || null,
          gekozen_risicoprofiel: gekozen || null,
          afwijking_toelichting: gekozen ? afwijking : null,
        },
      });
      naOpslaan();
    } catch (fout) {
      setFouten(meldingenVan(fout));
      setBezig(false);
    }
  }

  return (
    <form className="kaart" onSubmit={verstuur}>
      <h2>{vorige ? "Profiel herzien" : "Profiel vastleggen"}</h2>
      {vorige && (
        <p className="zacht">
          De vorige versie blijft bewaard. De velden zijn vooringevuld met versie {vorige.versie}.
        </p>
      )}

      <fieldset>
        <legend>Doel en vermogen</legend>
        <label>
          Beleggingsdoel
          <input value={doel} onChange={(e) => setDoel(e.target.value)} maxLength={500} required />
        </label>
        <div className="kolommen">
          <label>
            Horizon (jaren)
            <input type="number" min={1} max={60} value={horizon} onChange={(e) => setHorizon(e.target.value)} required />
          </label>
          <label>
            Inleg (€)
            <input type="number" min={0} step={1} value={inleg} onChange={(e) => setInleg(e.target.value)} required />
          </label>
          <label>
            Storting per maand (€)
            <input type="number" min={0} step={1} value={storting} onChange={(e) => setStorting(e.target.value)} required />
          </label>
          <label>
            Doelvermogen (€, optioneel)
            <input type="number" min={1} step={1} value={doelvermogen} onChange={(e) => setDoelvermogen(e.target.value)} />
          </label>
        </div>
      </fieldset>

      {Object.entries(vragenlijst.dimensies).map(([dimensie, titel]) => (
        <fieldset key={dimensie}>
          <legend>{titel}</legend>
          {vragenlijst.vragen
            .filter((v) => v.dimensie === dimensie)
            .map((v) => (
              <div className="vraag" key={v.code} role="radiogroup" aria-label={v.tekst}>
                <p>{v.tekst}</p>
                {v.antwoorden.map((tekst, punten) => (
                  <label className="keuze" key={tekst}>
                    <input
                      type="radio"
                      name={v.code}
                      checked={antwoorden[v.code] === punten}
                      onChange={() => setAntwoorden({ ...antwoorden, [v.code]: punten })}
                    />
                    {tekst}
                  </label>
                ))}
              </div>
            ))}
        </fieldset>
      ))}

      <fieldset>
        <legend>Duurzaamheidsvoorkeuren</legend>
        <label>
          Voorkeur voor duurzaam beleggen
          <select value={duurzaamheid} onChange={(e) => setDuurzaamheid(e.target.value)}>
            {["geen", "enigszins", "sterk"].map((d) => (
              <option key={d} value={d}>
                {naam(d)}
              </option>
            ))}
          </select>
        </label>
        <p>Uitsluiten:</p>
        <div className="vinkjes">
          {vragenlijst.uitsluitingen.map((u) => (
            <label className="keuze" key={u}>
              <input
                type="checkbox"
                checked={uitsluitingen.includes(u)}
                onChange={(e) =>
                  setUitsluitingen(e.target.checked ? [...uitsluitingen, u] : uitsluitingen.filter((x) => x !== u))
                }
              />
              {naam(u)}
            </label>
          ))}
        </div>
        <label>
          Toelichting (optioneel)
          <textarea value={duurzaamToelichting} onChange={(e) => setDuurzaamToelichting(e.target.value)} maxLength={1000} />
        </label>
      </fieldset>

      <fieldset>
        <legend>Risicoprofiel</legend>
        {uitkomst && afgeleid ? (
          <>
            <p>
              Afgeleid profiel: <strong>{afgeleid.naam}</strong>, bepaald door de {naam(uitkomst.bepalende_factor)}.
            </p>
            <p className="zacht">
              Risicobereidheid {uitkomst.score_bereidheid}/100 · risicocapaciteit {uitkomst.score_capaciteit}/100 · kennis
              en ervaring {uitkomst.score_kennis}/100
            </p>
            {uitkomst.lage_kennis && (
              <div className="melding let-op">
                Beperkte kennis en ervaring: licht de kenmerken en risico's van de portefeuille extra toe.
              </div>
            )}
            {defensiever.length > 0 && (
              <label>
                Werken met een defensiever profiel (optioneel)
                <select value={gekozen} onChange={(e) => setGekozen(e.target.value)}>
                  <option value="">Nee, gebruik {afgeleid.naam}</option>
                  {defensiever.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.naam}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {gekozen && (
              <label>
                Waarom wordt afgeweken?
                <textarea value={afwijking} onChange={(e) => setAfwijking(e.target.value)} maxLength={1000} required />
              </label>
            )}
          </>
        ) : (
          <p className="zacht">Vul de horizon in en beantwoord alle vragen om het afgeleide profiel te zien.</p>
        )}
      </fieldset>

      <Fouten meldingen={fouten} />
      <div className="rij">
        <button disabled={bezig}>{bezig ? "Bezig…" : "Profiel vastleggen"}</button>
        <button type="button" className="tekstknop" onClick={annuleer}>
          Annuleren
        </button>
      </div>
    </form>
  );
}
