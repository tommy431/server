import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { Adviseur, api, registreerUitloggen, token } from "./api";
import Aannames from "./pages/Aannames";
import Data from "./pages/Data";
import KlantDetail from "./pages/KlantDetail";
import Klanten from "./pages/Klanten";
import Login from "./pages/Login";
import Modelallocaties from "./pages/Modelallocaties";
import Portefeuille from "./pages/Portefeuille";

export default function App() {
  const [adviseur, setAdviseur] = useState<Adviseur | null>(null);
  const [laden, setLaden] = useState(token.lees() !== null);

  const uitloggen = useCallback(() => {
    token.wis();
    setAdviseur(null);
  }, []);

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

  return (
    <>
      <header className="balk">
        <strong>Portefeuille op maat</strong>
        <nav>
          <NavLink to="/klanten">Klanten</NavLink>
          <NavLink to="/modelallocaties">Modelallocaties</NavLink>
          <NavLink to="/aannames">Aannames</NavLink>
          <NavLink to="/data">Data</NavLink>
        </nav>
        <span className="wie">
          {adviseur.naam}
          <button className="tekstknop" onClick={uitloggen}>
            Uitloggen
          </button>
        </span>
      </header>
      <main>
        <Routes>
          <Route path="/klanten" element={<Klanten />} />
          <Route path="/klanten/:id" element={<KlantDetail />} />
          <Route path="/klanten/:id/portefeuille" element={<Portefeuille />} />
          <Route path="/modelallocaties" element={<Modelallocaties />} />
          <Route path="/aannames" element={<Aannames />} />
          <Route path="/data" element={<Data />} />
          <Route path="*" element={<Navigate to="/klanten" replace />} />
        </Routes>
      </main>
    </>
  );
}
