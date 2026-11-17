import { useCallback, useEffect, useState } from "react";

import { Adviseur, Voorstel, api, datum, naam } from "./api";
import { Fouten, meldingenVan } from "./Fouten";

type Regels = Record<string, [number, number, number]>;
type Aannamesinhoud = {
  bron: string;
  peildatum: string;
  inflatie: number;
  categorieen: Record<string, { rendement: number; volatiliteit: number }>;
  stress?: Record<string, number>;
  correlaties: Record<string, Record<string, number>>;
};

const p = (f: number) => `${String(Math.round(f * 10000) / 100).replace(".", ",")}%`;

/** De inhoudelijke verschillen van een voorstel ten opzichte van wat nu geldt, in woorden. */
export const ONDERNEMINGSVELDEN: Record<string, string> = {
  naam: "Naam",
  adres: "Adres",
  postcode_plaats: "Postcode en plaats",
  telefoon: "Telefoon",
  email: "E-mailadres",
  website: "Website",
  kvk_nummer: "KvK-nummer",
  afm_vergunningnummer: "AFM-vergunningnummer",
  kifid_nummer: "Kifid-aansluitnummer",
  klachtenregeling: "Klachtenregeling",
};

function verschillen(v: Voorstel): string[] {
  if (v.soort === "klantoverdracht") {
    const i = v.inhoud as { naar_email: string; aantal: number };
    return [`${i.aantal} klant(en) overdragen aan ${i.naar_email}`];
  }
  if (v.soort === "account") {
    const oud = (v.oud ?? {}) as Record<string, unknown>;
    return Object.entries(v.inhoud).map(([k, w]) =>
      k === "rol"
        ? `Rol: ${String(oud.rol)} → ${String(w)}`
        : `Status: ${oud.actief ? "actief" : "geblokkeerd"} → ${w ? "actief" : "geblokkeerd"}`,
    );
  }
  if (v.soort === "onderneming") {
    const oud = (v.oud ?? {}) as Record<string, unknown>;
    return Object.entries(v.inhoud)
      .filter(([k, w]) => (w ?? "") !== (oud[k] ?? ""))
      .map(([k, w]) => `${ONDERNEMINGSVELDEN[k] ?? k}: ${String(oud[k] || "—")} → ${String(w || "—")}`);
  }
  if (v.soort === "modelallocatie") {
    const nieuw = (v.inhoud.regels ?? {}) as Regels;
    const oud = ((v.oud?.regels ?? {}) as Regels) || {};
    return Object.entries(nieuw)
      .filter(([c, r]) => JSON.stringify(r) !== JSON.stringify(oud[c]))
      .map(([c, [s, lo, hi]]) => {
        const o = oud[c];
        return `${naam(c)}: ${o ? `${o[0]}% (${o[1]}–${o[2]}%)` : "nieuw"} → ${s}% (${lo}–${hi}%)`;
      });
  }
  const nieuw = v.inhoud as unknown as Aannamesinhoud;
  const oud = v.oud as unknown as Aannamesinhoud | null;
  const uit: string[] = [];
  for (const [c, w] of Object.entries(nieuw.categorieen)) {
    const o = oud?.categorieen[c];
    if (!o || o.rendement !== w.rendement) uit.push(`${naam(c)} rendement: ${o ? p(o.rendement) : "—"} → ${p(w.rendement)}`);
    if (!o || o.volatiliteit !== w.volatiliteit)
      uit.push(`${naam(c)} volatiliteit: ${o ? p(o.volatiliteit) : "—"} → ${p(w.volatiliteit)}`);
    const so = oud?.stress?.[c];
    const sn = nieuw.stress?.[c];
    if (sn !== undefined && so !== sn) uit.push(`${naam(c)} zware crisis: ${so !== undefined ? p(so) : "—"} → ${p(sn)}`);
  }
  if (!oud || oud.inflatie !== nieuw.inflatie) uit.push(`Inflatie: ${oud ? p(oud.inflatie) : "—"} → ${p(nieuw.inflatie)}`);
  const gewijzigdeCorrelaties = Object.entries(nieuw.correlaties).flatMap(([a, rij]) =>
    Object.entries(rij).filter(([b, w]) => a < b && oud?.correlaties?.[a]?.[b] !== w),
  ).length;
  if (gewijzigdeCorrelaties) uit.push(`${gewijzigdeCorrelaties} correlatie(s) gewijzigd`);
  if (!oud || oud.peildatum !== nieuw.peildatum) uit.push(`Peildatum: ${datum(nieuw.peildatum)}`);
  if (!oud || oud.bron !== nieuw.bron) uit.push(`Bron: ${nieuw.bron}`);
  return uit;
}

/** Openstaande voorstellen van één soort, met goedkeuren en afwijzen voor beheerders. */
export function Voorstellen({
  soort,
  adviseur,
  verversing,
  naWijziging,
}: {
  soort: Voorstel["soort"];
  adviseur: Adviseur;
  verversing: number;
  naWijziging: () => void;
}) {
  const [voorstellen, setVoorstellen] = useState<Voorstel[]>([]);
  const [fouten, setFouten] = useState<string[]>([]);

  const laad = useCallback(async () => {
    try {
      setVoorstellen(await api<Voorstel[]>(`/wijzigingsvoorstellen?status=open&soort=${soort}`));
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }, [soort]);

  useEffect(() => {
    void laad();
  }, [laad, verversing]);

  async function beoordeel(v: Voorstel, goed: boolean) {
    setFouten([]);
    let reden: string | null = null;
    if (!goed) {
      reden = window.prompt(v.voorgesteld_door_id === adviseur.id ? "Waarom trekt u dit voorstel in?" : "Waarom wijst u dit voorstel af?");
      if (!reden) return;
    }
    try {
      await api(`/wijzigingsvoorstellen/${v.id}/${goed ? "goedkeuren" : "afwijzen"}`, {
        methode: "POST",
        body: goed ? undefined : { reden },
      });
      await laad();
      naWijziging();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  if (voorstellen.length === 0 && fouten.length === 0) return null;
  const beheerder = adviseur.rol === "beheerder";
  return (
    <section className="kaart voorstellen">
      <h2>Wacht op goedkeuring</h2>
      <Fouten meldingen={fouten} />
      {voorstellen.map((v) => {
        const eigen = v.voorgesteld_door_id === adviseur.id;
        return (
          <div key={v.id} className="voorstel">
            <p>
              <strong>
                {v.soort === "account"
                  ? `Account ${String((v.oud as Record<string, unknown> | null)?.email ?? v.sleutel)}`
                  : v.soort === "klantoverdracht"
                    ? `Klanten van ${String((v.oud as Record<string, unknown> | null)?.van_email ?? v.sleutel)}`
                  : v.sleutel
                    ? naam(v.sleutel)
                    : v.soort === "onderneming"
                      ? "Gegevens van de onderneming"
                      : "Nieuwe aannames"}
              </strong>
              <span className="zacht">
                {" "}
                · voorgesteld door {v.voorgesteld_door} op {datum(v.voorgesteld_op)}
              </span>
            </p>
            <ul className="klein-tekst">
              {verschillen(v).map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            {beheerder && (
              <div className="rij">
                <button
                  disabled={eigen}
                  title={eigen ? "Een tweede beheerder moet uw voorstel goedkeuren" : undefined}
                  onClick={() => beoordeel(v, true)}
                >
                  Goedkeuren
                </button>
                <button className="tweede" onClick={() => beoordeel(v, false)}>
                  {eigen ? "Intrekken" : "Afwijzen"}
                </button>
                {eigen && <span className="zacht klein-tekst">Een andere beheerder moet dit goedkeuren.</span>}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
