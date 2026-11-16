import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Allocatiebalk } from "../Allocatiebalk";
import { Klant, Profiel, Risicoprofiel, Vragenlijst, api, datum, euro, naam } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import ProfielFormulier from "../ProfielFormulier";

export default function KlantDetail() {
  const id = Number(useParams().id);
  const [klant, setKlant] = useState<Klant | null>(null);
  const [geschiedenis, setGeschiedenis] = useState<Profiel[]>([]);
  const [vragenlijst, setVragenlijst] = useState<Vragenlijst | null>(null);
  const [risicoprofielen, setRisicoprofielen] = useState<Risicoprofiel[]>([]);
  const [formulier, setFormulier] = useState(false);
  const [bewerken, setBewerken] = useState(false);
  const [fouten, setFouten] = useState<string[]>([]);

  const laad = useCallback(async () => {
    try {
      const [k, g, v, r] = await Promise.all([
        api<Klant>(`/klanten/${id}`),
        api<Profiel[]>(`/klanten/${id}/profielen`),
        api<Vragenlijst>("/vragenlijst"),
        api<Risicoprofiel[]>("/risicoprofielen"),
      ]);
      setKlant(k);
      setGeschiedenis(g);
      setVragenlijst(v);
      setRisicoprofielen(r);
      setFouten([]);
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }, [id]);

  useEffect(() => {
    void laad();
  }, [laad]);

  if (!klant || !vragenlijst) {
    return (
      <>
        <Fouten meldingen={fouten} />
        {fouten.length === 0 && <p className="zacht">Laden…</p>}
        <Link to="/klanten">Terug naar klanten</Link>
      </>
    );
  }

  const profiel = klant.huidig_profiel;
  const model = risicoprofielen.find((p) => p.code === profiel?.risicoprofiel);

  async function bewaarGegevens(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const velden = new FormData(e.currentTarget);
    try {
      await api(`/klanten/${id}`, {
        methode: "PUT",
        body: {
          naam: velden.get("naam"),
          email: velden.get("email") || null,
          geboortedatum: velden.get("geboortedatum") || null,
        },
      });
      setBewerken(false);
      await laad();
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  async function archiveer(gearchiveerd: boolean) {
    try {
      await api(`/klanten/${id}/archief`, { methode: "PUT", body: { gearchiveerd } });
      await laad();
    } catch (fout) {
      setFouten(meldingenVan(fout));
    }
  }

  return (
    <>
      <p>
        <Link to="/klanten">← Klanten</Link>
      </p>
      <div className="kop">
        <h1>{klant.naam}</h1>
        {klant.gearchiveerd && <span className="label">Gearchiveerd</span>}
      </div>
      <Fouten meldingen={fouten} />

      <section className="kaart">
        <h2>Klantgegevens</h2>
        {bewerken ? (
          <form onSubmit={bewaarGegevens}>
            <div className="kolommen">
              <label>
                Naam
                <input name="naam" defaultValue={klant.naam} required maxLength={200} />
              </label>
              <label>
                E-mailadres
                <input name="email" type="email" defaultValue={klant.email ?? ""} />
              </label>
              <label>
                Geboortedatum
                <input name="geboortedatum" type="date" defaultValue={klant.geboortedatum ?? ""} />
              </label>
            </div>
            <div className="rij">
              <button>Opslaan</button>
              <button type="button" className="tekstknop" onClick={() => setBewerken(false)}>
                Annuleren
              </button>
            </div>
          </form>
        ) : (
          <>
            <dl>
              <dt>E-mailadres</dt>
              <dd>{klant.email ?? "—"}</dd>
              <dt>Geboortedatum</dt>
              <dd>{klant.geboortedatum ? datum(klant.geboortedatum) : "—"}</dd>
              <dt>Klant sinds</dt>
              <dd>{datum(klant.aangemaakt_op)}</dd>
            </dl>
            <div className="rij">
              <button className="tekstknop" onClick={() => setBewerken(true)}>
                Gegevens wijzigen
              </button>
              <button className="tekstknop" onClick={() => archiveer(!klant.gearchiveerd)}>
                {klant.gearchiveerd ? "Terugzetten uit archief" : "Archiveren"}
              </button>
            </div>
          </>
        )}
      </section>

      {formulier ? (
        <ProfielFormulier
          klantId={id}
          vorige={profiel}
          vragenlijst={vragenlijst}
          risicoprofielen={risicoprofielen}
          annuleer={() => setFormulier(false)}
          naOpslaan={() => {
            setFormulier(false);
            void laad();
          }}
        />
      ) : (
        <section className="kaart">
          <h2>Klantprofiel</h2>
          {profiel ? (
            <>
              <p className="uitkomst">
                {naam(profiel.risicoprofiel)}
                <span className="zacht">
                  {" "}
                  · versie {profiel.versie}, vastgelegd op {datum(profiel.vastgelegd_op)}
                </span>
              </p>
              {profiel.afwijking_toelichting ? (
                <div className="melding let-op">
                  Afgeleid profiel was {naam(profiel.afgeleid_risicoprofiel)}; er is gekozen voor een defensiever profiel.
                  Toelichting: {profiel.afwijking_toelichting}
                </div>
              ) : (
                <p className="zacht">Bepaald door de {naam(profiel.bepalende_factor)}.</p>
              )}
              {profiel.lage_kennis && (
                <div className="melding let-op">
                  Beperkte kennis en ervaring: licht de kenmerken en risico's van de portefeuille extra toe.
                </div>
              )}
              <dl>
                <dt>Doel</dt>
                <dd>{profiel.doel}</dd>
                <dt>Horizon</dt>
                <dd>{profiel.horizon_jaren} jaar</dd>
                <dt>Inleg</dt>
                <dd>{euro(profiel.inleg_eur)}</dd>
                <dt>Storting per maand</dt>
                <dd>{euro(profiel.storting_per_maand_eur)}</dd>
                <dt>Doelvermogen</dt>
                <dd>{profiel.doelvermogen_eur ? euro(profiel.doelvermogen_eur) : "—"}</dd>
                <dt>Risicobereidheid</dt>
                <dd>{profiel.score_bereidheid}/100</dd>
                <dt>Risicocapaciteit</dt>
                <dd>{profiel.score_capaciteit}/100</dd>
                <dt>Kennis en ervaring</dt>
                <dd>{profiel.score_kennis}/100</dd>
                <dt>Duurzaamheid</dt>
                <dd>
                  {naam(profiel.duurzaamheid)}
                  {profiel.uitsluitingen.length > 0 && `; uitsluiten: ${profiel.uitsluitingen.map(naam).join(", ").toLowerCase()}`}
                </dd>
              </dl>
              {model && (
                <>
                  <h3>Strategische asset allocatie bij {model.naam.toLowerCase()}</h3>
                  <Allocatiebalk regels={model.allocatie} />
                </>
              )}
            </>
          ) : (
            <p className="zacht">Voor deze klant is nog geen profiel vastgelegd.</p>
          )}
          {!klant.gearchiveerd && (
            <button onClick={() => setFormulier(true)}>{profiel ? "Profiel herzien" : "Profiel vastleggen"}</button>
          )}
        </section>
      )}

      {geschiedenis.length > 1 && (
        <section className="kaart">
          <h2>Eerdere versies</h2>
          <table className="compact">
            <thead>
              <tr>
                <th>Versie</th>
                <th>Vastgelegd</th>
                <th>Risicoprofiel</th>
                <th>Horizon</th>
                <th className="getal">Inleg</th>
              </tr>
            </thead>
            <tbody>
              {geschiedenis.map((g) => (
                <tr key={g.id}>
                  <td>{g.versie}</td>
                  <td>{datum(g.vastgelegd_op)}</td>
                  <td>{naam(g.risicoprofiel)}</td>
                  <td>{g.horizon_jaren} jaar</td>
                  <td className="getal">{euro(g.inleg_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
