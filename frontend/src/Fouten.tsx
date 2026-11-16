import { ApiFout } from "./api";

export function meldingenVan(fout: unknown): string[] {
  if (fout instanceof ApiFout) return fout.meldingen;
  return ["Er ging iets onverwachts mis."];
}

export function Fouten({ meldingen }: { meldingen: string[] }) {
  if (meldingen.length === 0) return null;
  return (
    <div className="melding fout" role="alert">
      {meldingen.length === 1 ? (
        meldingen[0]
      ) : (
        <ul>
          {meldingen.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
