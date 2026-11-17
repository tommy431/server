import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { Adviseur, api, registreerUitloggen, token } from "./api";
import Aannames from "./pages/Aannames";
import Data from "./pages/Data";
import KlantDetail from "./pages/KlantDetail";
import Klanten from "./pages/Klanten";
import Login from "./pages/Login";
import Account, { WachtwoordFormulier } from "./pages/Account";
import Gebruikers from "./pages/Gebruikers";
import Logboek from "./pages/Logboek";
import Modelallocaties from "./pages/Modelallocaties";
import Onderneming from "./pages/Onderneming";
import Opvolging from "./pages/Opvolging";
import Signalen from "./pages/Signalen";
import Portefeuille from "./pages/Portefeuille";

export default function App() {
  const [adviseur, setAdviseur] = useState<Adviseur | null>(null);
  const [laden, setLaden] = useState(token.lees() !== null);

  const navigeer = useNavigate();
  const uitloggen = useCallback(() => {
    token.wis();
    setAdviseur(null);
    // Na opnieuw inloggen, mogelijk door iemand anders, altijd beginnen bij de klanten.
    navigeer("/klanten");
  }, [navigeer]);

  const haalAdviseur = useCallback(async () => {
    try {
      setAdviseur(await api<Adviseur>("/auth/mij"));
    } catch {
      uitloggen();
    } finally {
      setLaden(false);
    }
  }, [uitloggen]);

  useEffect(() => {
    registreerUitloggen(uitloggen);
    if (token.lees()) void haalAdviseur();
  }, [haalAdviseur, uitloggen]);

  if (laden) return <p className="midden">Laden…</p>;
  if (!adviseur) return <Login naInloggen={haalAdviseur} />;
  if (adviseur.wachtwoord_wijzigen) {
    return (
      <main className="smal">
        <WachtwoordFormulier verplicht naWijziging={haalAdviseur} />
        <button className="tekstknop" onClick={uitloggen}>
          Uitloggen
        </button>
      </main>
    );
  }

  return (
    <>
      <header className="balk">
        <strong>Portefeuille op maat</strong>
        <nav>
          <NavLink to="/klanten">Klanten</NavLink>
          <NavLink to="/signalen">Signalen</NavLink>
          <NavLink to="/modelallocaties">Modelallocaties</NavLink>
          <NavLink to="/aannames">Aannames</NavLink>
          <NavLink to="/data">Data</NavLink>
          <NavLink to="/onderneming">Onderneming</NavLink>
          {adviseur.rol === "beheerder" && <NavLink to="/gebruikers">Gebruikers</NavLink>}
          {adviseur.rol === "beheerder" && <NavLink to="/logboek">Logboek</NavLink>}
          <NavLink to="/account">Mijn account</NavLink>
        </nav>
        <span className="wie">
          {adviseur.naam}
          {adviseur.rol === "beheerder" && <span className="label">Beheerder</span>}
          <button className="tekstknop" onClick={uitloggen}>
            Uitloggen
          </button>
        </span>
      </header>
      {adviseur.rol === "beheerder" && !adviseur.tweestaps_actief && (
        <div className="melding let-op balkmelding">
          Als beheerder heeft u tweestapsverificatie nodig voor beheertaken. <NavLink to="/account">Nu instellen</NavLink>
        </div>
      )}
      <main>
        <Routes>
          <Route path="/klanten" element={<Klanten />} />
          <Route path="/klanten/:id" element={<KlantDetail />} />
          <Route path="/klanten/:id/portefeuille" element={<Portefeuille />} />
          <Route path="/klanten/:id/opvolging" element={<Opvolging />} />
          <Route path="/signalen" element={<Signalen />} />
          <Route path="/modelallocaties" element={<Modelallocaties adviseur={adviseur} />} />
          <Route path="/aannames" element={<Aannames adviseur={adviseur} />} />
          <Route path="/data" element={<Data adviseur={adviseur} />} />
          <Route path="/onderneming" element={<Onderneming adviseur={adviseur} />} />
          {adviseur.rol === "beheerder" && <Route path="/gebruikers" element={<Gebruikers adviseur={adviseur} />} />}
          {adviseur.rol === "beheerder" && <Route path="/logboek" element={<Logboek />} />}
          <Route path="/account" element={<Account adviseur={adviseur} naWijziging={haalAdviseur} />} />
          <Route path="*" element={<Navigate to="/klanten" replace />} />
        </Routes>
      </main>
    </>
  );
}
