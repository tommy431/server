import { AllocatieRegel, naam } from "./api";

export function Allocatiebalk({ regels }: { regels: AllocatieRegel[] }) {
  const zichtbaar = regels.filter((r) => r.streef > 0);
  return (
    <div>
      <div className="balkgrafiek" role="img" aria-label="Strategische asset allocatie">
        {zichtbaar.map((r) => (
          <span key={r.categorie} className={`deel ${r.categorie}`} style={{ width: `${r.streef}%` }} />
        ))}
      </div>
      <table className="compact">
        <thead>
          <tr>
            <th>Categorie</th>
            <th className="getal">Streefgewicht</th>
            <th className="getal">Bandbreedte</th>
          </tr>
        </thead>
        <tbody>
          {regels.map((r) => (
            <tr key={r.categorie}>
              <td>
                <span className={`stip ${r.categorie}`} />
                {naam(r.categorie)}
              </td>
              <td className="getal">{r.streef}%</td>
              <td className="getal">
                {r.minimum}–{r.maximum}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
