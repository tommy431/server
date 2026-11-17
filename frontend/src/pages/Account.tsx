import { FormEvent, useState } from "react";

import { Adviseur, api, token } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

/** Eigen wachtwoord kiezen; verplicht na een tijdelijk wachtwoord. */
export function WachtwoordFormulier({ verplicht, naWijziging }: { verplicht: boolean; naWijziging: () => void }) {
  const [huidig, setHuidig] = useState("");
  const [nieuw, setNieuw] = useState("");
  const [herhaling, setHerhaling] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);
  const [gelukt, setGelukt] = useState(false);

  async function verstuur(e: FormEvent) {
    e.preventDefault();
    setGelukt(false);
    if (nieuw !== herhaling) {
      setFouten(["De nieuwe wachtwoorden zijn niet gelijk."]);
      return;
    }
    try {
      const { access_token } = await api<{ access_token: string }>("/auth/wachtwoord", {
        methode: "POST",
        body: { huidig, nieuw },
      });
      token.zet(access_token);
      setFouten([]);
      setHuidig("");
      setNieuw("");
      setHerhaling("");
      setGelukt(true);
      naWijziging();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  return (
    <form className="kaart" onSubmit={verstuur}>
      <h2>{verplicht ? "Kies een eigen wachtwoord" : "Wachtwoord wijzigen"}</h2>
      {verplicht && (
        <p className="zacht">U bent ingelogd met een tijdelijk wachtwoord. Kies eerst een eigen wachtwoord.</p>
      )}
      <label>
        {verplicht ? "Tijdelijk wachtwoord" : "Huidig wachtwoord"}
        <input type="password" autoComplete="current-password" value={huidig} onChange={(e) => setHuidig(e.target.value)} required />
      </label>
      <label>
        Nieuw wachtwoord (minimaal 12 tekens)
        <input type="password" autoComplete="new-password" minLength={12} value={nieuw} onChange={(e) => setNieuw(e.target.value)} required />
      </label>
      <label>
        Herhaal nieuw wachtwoord
        <input type="password" autoComplete="new-password" minLength={12} value={herhaling} onChange={(e) => setHerhaling(e.target.value)} required />
      </label>
      <Fouten meldingen={fouten} />
      {gelukt && <div className="melding goed">Uw wachtwoord is gewijzigd. Andere sessies zijn afgemeld.</div>}
      <button>Wachtwoord opslaan</button>
    </form>
  );
}

function Tweestaps({ adviseur, naWijziging }: { adviseur: Adviseur; naWijziging: () => void }) {
  const [start, setStart] = useState<{ geheim: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [wachtwoord, setWachtwoord] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);

  async function begin() {
    setFouten([]);
    try {
      setStart(await api<{ geheim: string; qr_svg: string }>("/auth/tweestaps/starten", { methode: "POST" }));
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  async function bevestig(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/tweestaps/bevestigen", { methode: "POST", body: { code } });
      setStart(null);
      setCode("");
      setFouten([]);
      naWijziging();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  async function uitzetten(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/auth/tweestaps/uitzetten", { methode: "POST", body: { wachtwoord, code } });
      setCode("");
      setWachtwoord("");
      setFouten([]);
      naWijziging();
    } catch (f) {
      setFouten(meldingenVan(f));
    }
  }

  return (
    <section className="kaart">
      <h2>Tweestapsverificatie</h2>
      {adviseur.tweestaps_actief ? (
        <>
          <div className="melding goed">Tweestapsverificatie staat aan.</div>
          {adviseur.rol === "adviseur" && (
            <form onSubmit={uitzetten}>
              <p className="zacht">Uitzetten kan met uw wachtwoord en een code uit de app.</p>
              <div className="kolommen">
                <label>
                  Wachtwoord
                  <input type="password" value={wachtwoord} onChange={(e) => setWachtwoord(e.target.value)} required />
                </label>
                <label>
                  Code
                  <input inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} required />
                </label>
              </div>
              <Fouten meldingen={fouten} />
              <button className="tweede">Tweestapsverificatie uitzetten</button>
            </form>
          )}
        </>
      ) : start ? (
        <form onSubmit={bevestig}>
          <p>
            Scan deze code met een authenticator-app, zoals Google Authenticator of Microsoft Authenticator, en vul
            daarna de code van zes cijfers in.
          </p>
          <div className="qr" dangerouslySetInnerHTML={{ __html: start.qr_svg }} />
          <p className="zacht klein-tekst">
            Lukt scannen niet? Voer dan deze sleutel handmatig in: <code data-testid="totp-geheim">{start.geheim}</code>
          </p>
          <label>
            Code uit de app
            <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required />
          </label>
          <Fouten meldingen={fouten} />
          <button>Bevestigen</button>
        </form>
      ) : (
        <>
          <p>
            Met tweestapsverificatie heeft u bij het inloggen naast uw wachtwoord ook een code uit een app op uw telefoon
            nodig.{adviseur.rol === "beheerder" && " Voor beheerders is dit verplicht om beheertaken te doen."}
          </p>
          <Fouten meldingen={fouten} />
          <button onClick={begin}>Tweestapsverificatie aanzetten</button>
        </>
      )}
    </section>
  );
}

export default function Account({ adviseur, naWijziging }: { adviseur: Adviseur; naWijziging: () => void }) {
  return (
    <>
      <h1>Mijn account</h1>
      <p className="zacht">
        {adviseur.naam} · {adviseur.email} · {adviseur.rol === "beheerder" ? "beheerder" : "adviseur"}
      </p>
      <Tweestaps adviseur={adviseur} naWijziging={naWijziging} />
      <WachtwoordFormulier verplicht={false} naWijziging={naWijziging} />
    </>
  );
}
