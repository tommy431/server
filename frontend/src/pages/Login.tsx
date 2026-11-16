import { FormEvent, useState } from "react";

import { api, token } from "../api";
import { Fouten, meldingenVan } from "../Fouten";

export default function Login({ naInloggen }: { naInloggen: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [wachtwoord, setWachtwoord] = useState("");
  const [fouten, setFouten] = useState<string[]>([]);
  const [bezig, setBezig] = useState(false);

  async function verstuur(e: FormEvent) {
    e.preventDefault();
    setBezig(true);
    setFouten([]);
    try {
      const { access_token } = await api<{ access_token: string }>("/auth/login", {
        methode: "POST",
        body: { email, wachtwoord },
      });
      token.zet(access_token);
      await naInloggen();
    } catch (fout) {
      setFouten(meldingenVan(fout));
      setBezig(false);
    }
  }

  return (
    <form className="kaart inlog" onSubmit={verstuur}>
      <h1>Portefeuille op maat</h1>
      <p className="zacht">Log in met uw adviseursaccount.</p>
      <Fouten meldingen={fouten} />
      <label>
        E-mailadres
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
      </label>
      <label>
        Wachtwoord
        <input
          type="password"
          value={wachtwoord}
          onChange={(e) => setWachtwoord(e.target.value)}
          required
        />
      </label>
      <button disabled={bezig}>{bezig ? "Bezig…" : "Inloggen"}</button>
    </form>
  );
}
