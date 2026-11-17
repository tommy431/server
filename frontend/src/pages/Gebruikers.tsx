import { FormEvent, useCallback, useEffect, useState } from "react";

import { Account, Adviseur, Voorstel, api, datum } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import { Voorstellen } from "../Voorstellen";

export default function Gebruikers({ adviseur }: { adviseur: Adviseur }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [verversing, setVerversing] = useState(0);
  const [fouten, setFouten] = useState<string[]>([]);
  const [melding, setMelding] = useState<string | null>(null);
  const [tijdelijk, setTijdelijk] = useState<{ email: string; wachtwoord: string } | null>(null);
  const [email, setEmail] = useState("");
  const [naam, setNaam] = useState("");

  const laad = useCallback(async () => {
    try {
      setAccounts(await api<Account[]>("/adviseurs"));
      setFouten([]);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }, []);
  useEffect(() => {
    void laad();
  }, [laad, verversing]);

  async function actie(uitvoeren: () => Promise<void>) {
    setMelding(null);
    setTijdelijk(null);
    try {
      await uitvoeren();
      setVerversing((v) => v + 1);
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  async function nieuw(e: FormEvent) {
    e.preventDefault();
    await actie(async () => {
      const uit = await api<{ account: Account; tijdelijk_wachtwoord: string }>("/adviseurs", {
        methode: "POST",
        body: { email, naam },
      });
      setEmail("");
      setNaam("");
      setTijdelijk({ email: uit.account.email, wachtwoord: uit.tijdelijk_wachtwoord });
    });
  }

  const reset = (a: Account) =>
    actie(async () => {
      const uit = await api<{ account: Account; tijdelijk_wachtwoord: string }>(`/adviseurs/${a.id}/wachtwoord-resetten`, {
        methode: "POST",
      });
      setTijdelijk({ email: a.email, wachtwoord: uit.tijdelijk_wachtwoord });
    });

  const voorstelMelding = (v: Voorstel) =>
    setMelding(
      v.status === "doorgevoerd" ? "Doorgevoerd." : "Voorstel ingediend; een tweede beheerder moet het goedkeuren.",
    );

  return (
    <>
      <h1>Gebruikers</h1>
      <p className="zacht">
        Iemand beheerder maken of een beheerder blokkeren gaat via een voorstel dat een tweede beheerder goedkeurt.
        Wachtwoord en tweestapsverificatie van een beheerder kunnen alleen op de server worden gereset.
      </p>
      <Fouten meldingen={fouten} />
      {melding && <div className="melding goed">{melding}</div>}
      {tijdelijk && (
        <div className="melding let-op" role="status">
          Tijdelijk wachtwoord voor {tijdelijk.email}: <code data-testid="tijdelijk-wachtwoord">{tijdelijk.wachtwoord}</code>
          <br />
          Geef dit veilig door, bijvoorbeeld telefonisch. Het wordt maar één keer getoond; bij de eerste keer inloggen
          kiest de adviseur een eigen wachtwoord.
        </div>
      )}
      <Voorstellen soort="account" adviseur={adviseur} verversing={verversing} naWijziging={() => setVerversing((v) => v + 1)} />

      <section className="kaart">
        <h2>Accounts</h2>
        <div className="schuifvlak">
          <table className="compact">
            <thead>
              <tr>
                <th>Naam</th>
                <th>Rol</th>
                <th>Status</th>
                <th className="getal">Klanten</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => {
                const zelf = a.id === adviseur.id;
                return (
                  <tr key={a.id}>
                    <td>
                      {a.naam}
                      <div className="zacht klein-tekst">
                        {a.email} · sinds {datum(a.aangemaakt_op)}
                      </div>
                    </td>
                    <td>{a.rol === "beheerder" ? "Beheerder" : "Adviseur"}</td>
                    <td>
                      {a.actief ? "Actief" : <span className="rood">Geblokkeerd</span>}
                      <div className="zacht klein-tekst">
                        {a.tweestaps_actief ? "Tweestaps aan" : "Tweestaps uit"}
                        {a.wachtwoord_wijzigen && " · tijdelijk wachtwoord"}
                      </div>
                    </td>
                    <td className="getal">{a.aantal_klanten}</td>
                    <td>
                      {zelf ? (
                        <span className="zacht klein-tekst">Uw eigen account</span>
                      ) : (
                        <div className="acties">
                          <button
                            className="tekstknop"
                            onClick={() =>
                              actie(async () =>
                                voorstelMelding(
                                  await api<Voorstel>(`/adviseurs/${a.id}/rol`, {
                                    methode: "PUT",
                                    body: { rol: a.rol === "beheerder" ? "adviseur" : "beheerder" },
                                  }),
                                ),
                              )
                            }
                          >
                            {a.rol === "beheerder" ? "Adviseur maken" : "Beheerder maken"}
                          </button>
                          <button
                            className="tekstknop"
                            onClick={() =>
                              actie(async () => {
                                const uit = await api<{ voorstel?: Voorstel }>(`/adviseurs/${a.id}/status`, {
                                  methode: "PUT",
                                  body: { actief: !a.actief },
                                });
                                if (uit.voorstel) voorstelMelding(uit.voorstel);
                              })
                            }
                          >
                            {a.actief ? "Blokkeren" : "Deblokkeren"}
                          </button>
                          {a.rol === "adviseur" && (
                            <>
                              <button className="tekstknop" onClick={() => reset(a)}>
                                Wachtwoord resetten
                              </button>
                              {a.tweestaps_actief && (
                                <button
                                  className="tekstknop"
                                  onClick={() => actie(async () => void (await api(`/adviseurs/${a.id}/tweestaps-resetten`, { methode: "POST" })))}
                                >
                                  Tweestaps resetten
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <form className="kaart" onSubmit={nieuw}>
        <h2>Nieuwe adviseur</h2>
        <div className="kolommen">
          <label>
            Naam
            <input value={naam} onChange={(e) => setNaam(e.target.value)} required maxLength={200} />
          </label>
          <label>
            E-mailadres
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
        </div>
        <button>Account aanmaken</button>
      </form>
    </>
  );
}
