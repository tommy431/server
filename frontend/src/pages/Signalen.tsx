import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { KlantSignalen, api } from "../api";
import { Fouten, meldingenVan } from "../Fouten";
import Signaallijst from "../Signaallijst";

export default function Signalen() {
  const [lijst, setLijst] = useState<KlantSignalen[] | null>(null);
  const [fouten, setFouten] = useState<string[]>([]);

  useEffect(() => {
    api<KlantSignalen[]>("/signalen")
      .then(setLijst)
      .catch((f) => setFouten(meldingenVan(f)));
  }, []);

  return (
    <>
      <h1>Signalen</h1>
      <p className="zacht">
        Wat bij uw klanten aandacht vraagt: verlopen evaluaties, een herzien profiel, bezit buiten de bandbreedtes.
        De meest dringende staan bovenaan.
      </p>
      <Fouten meldingen={fouten} />
      {lijst === null ? (
        fouten.length === 0 && <p className="zacht">Laden…</p>
      ) : lijst.length === 0 ? (
        <p className="melding goed">Geen aandachtspunten bij uw klanten.</p>
      ) : (
        lijst.map((k) => (
          <section className="kaart" key={k.klant_id}>
            <h2>
              <Link to={`/klanten/${k.klant_id}/opvolging`}>{k.naam}</Link>
            </h2>
            <Signaallijst signalen={k.signalen} />
          </section>
        ))
      )}
    </>
  );
}
