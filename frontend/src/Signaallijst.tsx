import { Signaal } from "./api";

const KLASSE = { hoog: "fout", middel: "let-op", laag: "" } as const;

export default function Signaallijst({ signalen }: { signalen: Signaal[] }) {
  if (signalen.length === 0) return <p className="melding goed">Geen aandachtspunten.</p>;
  return (
    <ul className="signalen">
      {signalen.map((s) => (
        <li key={s.code + s.melding} className={`melding ${KLASSE[s.ernst]}`}>
          {s.melding}
        </li>
      ))}
    </ul>
  );
}
