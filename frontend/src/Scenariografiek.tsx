import { useEffect, useRef, useState } from "react";

import { Jaarpunt, euro } from "./api";

const MARGE = { boven: 16, rechts: 16, onder: 28, links: 64 };

function stap(bereik: number) {
  const ruw = bereik / 5;
  const macht = 10 ** Math.floor(Math.log10(ruw));
  return [1, 2, 2.5, 5, 10].map((f) => f * macht).find((s) => s >= ruw) ?? ruw;
}

const kort = (w: number) =>
  w >= 1_000_000
    ? `€ ${new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 1 }).format(w / 1_000_000)} mln`
    : `€ ${new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 0 }).format(w / 1000)}k`;

/** Waaier van het slechte tot het goede scenario, met het verwachte scenario en de inleg. */
export function Scenariografiek({ jaren, reeel, doel }: { jaren: Jaarpunt[]; reeel: boolean; doel: number | null }) {
  const vlak = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [B, setB] = useState(720);
  const [actief, setActief] = useState<number | null>(null);
  useEffect(() => {
    const el = vlak.current;
    if (!el) return;
    const meet = () => setB(Math.max(280, Math.round(el.clientWidth)));
    meet();
    const waarnemer = new ResizeObserver(meet);
    waarnemer.observe(el);
    return () => waarnemer.disconnect();
  }, []);
  const H = B < 500 ? 240 : 300;

  const waarde = (j: Jaarpunt) => (reeel ? j.reeel : j.nominaal);
  const max = Math.max(...jaren.map((j) => waarde(j)[2]), doel ?? 0);
  const s = stap(max || 1);
  const yMax = Math.ceil(max / s) * s;
  const n = jaren.length - 1;
  const x = (jaar: number) => MARGE.links + (jaar / n) * (B - MARGE.links - MARGE.rechts);
  const y = (w: number) => H - MARGE.onder - (w / yMax) * (H - MARGE.boven - MARGE.onder);
  const pad = (f: (j: Jaarpunt) => number) =>
    jaren.map((j, i) => `${i ? "L" : "M"}${x(j.jaar).toFixed(1)},${y(f(j)).toFixed(1)}`).join("");
  const band =
    jaren.map((j, i) => `${i ? "L" : "M"}${x(j.jaar).toFixed(1)},${y(waarde(j)[2]).toFixed(1)}`).join("") +
    [...jaren]
      .reverse()
      .map((j) => `L${x(j.jaar).toFixed(1)},${y(waarde(j)[0]).toFixed(1)}`)
      .join("") +
    "Z";
  const rasters = [];
  for (let w = 0; w <= yMax + 1e-6; w += s) rasters.push(w);
  const jaarStap = Math.max(1, Math.ceil(n / (B < 500 ? 4 : 8)));
  const labels = jaren.filter((j) => j.jaar % jaarStap === 0 || j.jaar === n);

  function beweeg(e: React.PointerEvent) {
    const vak = svg.current!.getBoundingClientRect();
    const jaar = Math.round((((e.clientX - vak.left) - MARGE.links) / (B - MARGE.links - MARGE.rechts)) * n);
    setActief(Math.min(n, Math.max(0, jaar)));
  }
  const punt = actief === null ? null : jaren[actief];

  return (
    <figure className="grafiek">
      <div className="legenda">
        <span>
          <i className="vlakje waaier" /> 90% van de uitkomsten
        </span>
        <span>
          <i className="sleutel pf" /> Verwacht
        </span>
        <span>
          <i className="sleutel inleg" /> Ingelegd
        </span>
      </div>
      <div className="grafiekvlak" ref={vlak}>
        <svg
          ref={svg}
          width={B}
          height={H}
          viewBox={`0 0 ${B} ${H}`}
          role="img"
          aria-label={`Scenario's over ${n} jaar. Verwacht eindvermogen ${euro(waarde(jaren[n])[1])}, slecht scenario ${euro(
            waarde(jaren[n])[0],
          )}, goed scenario ${euro(waarde(jaren[n])[2])}.`}
          onPointerMove={beweeg}
          onPointerLeave={() => setActief(null)}
        >
          {rasters.map((w) => (
            <g key={w}>
              <line className="raster" x1={MARGE.links} x2={B - MARGE.rechts} y1={y(w)} y2={y(w)} />
              <text className="as" x={MARGE.links - 8} y={y(w) + 4} textAnchor="end">
                {w === 0 ? "€ 0" : kort(w)}
              </text>
            </g>
          ))}
          {labels.map((j) => (
            <text key={j.jaar} className="as" x={x(j.jaar)} y={H - 8} textAnchor="middle">
              {j.jaar === 0 ? "nu" : `${j.jaar} jr`}
            </text>
          ))}
          <path className="waaier" d={band} />
          <path className="lijn inleg" d={pad((j) => (reeel ? j.ingelegd_reeel : j.ingelegd))} />
          {doel && (
            <g>
              <line className="doellijn" x1={MARGE.links} x2={B - MARGE.rechts} y1={y(doel)} y2={y(doel)} />
              <text className="eind" x={MARGE.links + 6} y={y(doel) - 6}>
                Doel {euro(doel)}
              </text>
            </g>
          )}
          <path className="lijn pf" d={pad((j) => waarde(j)[1])} />
          {punt && (
            <g>
              <line className="kruis" x1={x(punt.jaar)} x2={x(punt.jaar)} y1={MARGE.boven} y2={H - MARGE.onder} />
              <circle className="stipje pf" cx={x(punt.jaar)} cy={y(waarde(punt)[1])} r={4} />
            </g>
          )}
        </svg>
        {punt && (
          <div
            className="zweeftekst"
            style={{ left: `${(x(punt.jaar) / B) * 100}%` }}
            data-rechts={x(punt.jaar) > B * 0.6 ? "ja" : "nee"}
          >
            <strong>{punt.jaar === 0 ? "Nu" : `Na ${punt.jaar} jaar`}</strong>
            <span>Goed: {euro(waarde(punt)[2])}</span>
            <span>
              <i className="sleutel pf" /> Verwacht: {euro(waarde(punt)[1])}
            </span>
            <span>Slecht: {euro(waarde(punt)[0])}</span>
            <span className="zacht">Ingelegd: {euro(reeel ? punt.ingelegd_reeel : punt.ingelegd)}</span>
          </div>
        )}
      </div>
      <figcaption className="zacht klein-tekst">
        {reeel ? "In koopkracht van vandaag." : "In euro's van dat moment (nominaal)."} Het gekleurde vlak loopt van het
        slechte scenario (5% van de uitkomsten is lager) tot het goede scenario (5% is hoger).
      </figcaption>
    </figure>
  );
}
