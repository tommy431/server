import { useEffect, useRef, useState } from "react";

import { maand } from "./api";

type Punt = [string, number, number | null];

const MARGE = { boven: 16, rechts: 44, onder: 28, links: 40 };

/** Ronde stapgrootte zodat er ongeveer vier rasterlijnen staan. */
function stap(bereik: number) {
  const ruw = bereik / 4;
  const macht = 10 ** Math.floor(Math.log10(ruw));
  return [1, 2, 2.5, 5, 10].map((f) => f * macht).find((s) => s >= ruw) ?? ruw;
}

/** Waardeontwikkeling van portefeuille en benchmark, beginwaarde 100. */
export function Waardegrafiek({ punten }: { punten: Punt[] }) {
  const [actief, setActief] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const vlak = useRef<HTMLDivElement>(null);
  // Tekenen op de werkelijke breedte, zodat tekst ook op een telefoon 12 pixels blijft.
  const [B, setB] = useState(720);
  useEffect(() => {
    const el = vlak.current;
    if (!el) return;
    const meet = () => setB(Math.max(280, Math.round(el.clientWidth)));
    meet();
    const waarnemer = new ResizeObserver(meet);
    waarnemer.observe(el);
    return () => waarnemer.disconnect();
  }, []);
  const H = B < 500 ? 220 : 280;
  if (punten.length < 2) return null;

  const metBenchmark = punten.every((p) => p[2] !== null);
  const tijden = punten.map((p) => new Date(p[0]).getTime());
  const waarden = punten.flatMap((p) => (p[2] === null ? [p[1]] : [p[1], p[2]]));
  const s = stap(Math.max(...waarden) - Math.min(...waarden) || 1);
  const yMin = Math.floor(Math.min(...waarden) / s) * s;
  const yMax = Math.ceil(Math.max(...waarden) / s) * s;
  const [t0, t1] = [tijden[0], tijden[tijden.length - 1]];

  const x = (t: number) => MARGE.links + ((t - t0) / (t1 - t0)) * (B - MARGE.links - MARGE.rechts);
  const y = (w: number) => H - MARGE.onder - ((w - yMin) / (yMax - yMin)) * (H - MARGE.boven - MARGE.onder);
  const lijn = (kolom: 1 | 2) =>
    punten.map((p, i) => `${i ? "L" : "M"}${x(tijden[i]).toFixed(1)},${y(p[kolom] as number).toFixed(1)}`).join("");

  const rasters = [];
  for (let w = yMin; w <= yMax + 1e-9; w += s) rasters.push(w);
  const eersteJaar = new Date(t0).getFullYear() + 1;
  const laatsteJaar = new Date(t1).getFullYear();
  const jaarStap = Math.max(1, Math.ceil((laatsteJaar - eersteJaar + 1) / (B < 500 ? 4 : 8)));
  const jaren = [];
  for (let j = eersteJaar; j <= laatsteJaar; j += jaarStap) jaren.push(j);

  function beweeg(e: React.PointerEvent) {
    const vak = svg.current!.getBoundingClientRect();
    const t = t0 + (((e.clientX - vak.left) / vak.width) * B - MARGE.links) / (B - MARGE.links - MARGE.rechts) * (t1 - t0);
    let dichtst = 0;
    tijden.forEach((tijd, i) => {
      if (Math.abs(tijd - t) < Math.abs(tijden[dichtst] - t)) dichtst = i;
    });
    setActief(dichtst);
  }

  const laatste = punten[punten.length - 1];
  const getal = (w: number) => new Intl.NumberFormat("nl-NL", { maximumFractionDigits: 0 }).format(w);
  // Eindlabels uit elkaar houden als de lijnen dicht bij elkaar eindigen.
  let yPf = y(laatste[1]);
  let yBm = metBenchmark ? y(laatste[2] as number) : 0;
  if (metBenchmark && Math.abs(yPf - yBm) < 14) {
    const midden = (yPf + yBm) / 2;
    [yPf, yBm] = yPf <= yBm ? [midden - 7, midden + 7] : [midden + 7, midden - 7];
  }
  const punt = actief === null ? null : punten[actief];

  return (
    <figure className="grafiek">
      {metBenchmark && (
        <div className="legenda">
          <span>
            <i className="sleutel pf" /> Portefeuille
          </span>
          <span>
            <i className="sleutel bm" /> Benchmark
          </span>
        </div>
      )}
      <div className="grafiekvlak" ref={vlak}>
        <svg
          ref={svg}
          width={B}
          height={H}
          viewBox={`0 0 ${B} ${H}`}
          role="img"
          aria-label={`Waardeontwikkeling sinds ${maand(punten[0][0])}, beginwaarde 100. Portefeuille eindigt op ${getal(laatste[1])}${
            metBenchmark ? `, benchmark op ${getal(laatste[2] as number)}` : ""
          }.`}
          onPointerMove={beweeg}
          onPointerLeave={() => setActief(null)}
        >
          {rasters.map((w) => (
            <g key={w}>
              <line className="raster" x1={MARGE.links} x2={B - MARGE.rechts} y1={y(w)} y2={y(w)} />
              <text className="as" x={MARGE.links - 8} y={y(w) + 4} textAnchor="end">
                {getal(w)}
              </text>
            </g>
          ))}
          {jaren.map((j) => {
            const t = new Date(j, 0, 1).getTime();
            return (
              <text key={j} className="as" x={x(t)} y={H - 8} textAnchor="middle">
                {j}
              </text>
            );
          })}
          {metBenchmark && <path className="lijn bm" d={lijn(2)} />}
          <path className="lijn pf" d={lijn(1)} />
          {metBenchmark && (
            <text className="eind" x={B - MARGE.rechts + 8} y={yBm + 4}>
              {getal(laatste[2] as number)}
            </text>
          )}
          <text className="eind" x={B - MARGE.rechts + 8} y={yPf + 4}>
            {getal(laatste[1])}
          </text>
          {punt && actief !== null && (
            <g>
              <line className="kruis" x1={x(tijden[actief])} x2={x(tijden[actief])} y1={MARGE.boven} y2={H - MARGE.onder} />
              {metBenchmark && <circle className="stipje bm" cx={x(tijden[actief])} cy={y(punt[2] as number)} r={4} />}
              <circle className="stipje pf" cx={x(tijden[actief])} cy={y(punt[1])} r={4} />
            </g>
          )}
        </svg>
        {punt && actief !== null && (
          <div
            className="zweeftekst"
            style={{ left: `${(x(tijden[actief]) / B) * 100}%` }}
            data-rechts={x(tijden[actief]) > B * 0.65 ? "ja" : "nee"}
          >
            <strong>{maand(punt[0])}</strong>
            <span>
              <i className="sleutel pf" /> Portefeuille {getal(punt[1])}
            </span>
            {metBenchmark && (
              <span>
                <i className="sleutel bm" /> Benchmark {getal(punt[2] as number)}
              </span>
            )}
          </div>
        )}
      </div>
      <figcaption className="zacht klein-tekst">
        Waardeontwikkeling sinds {maand(punten[0][0])}, beginwaarde 100, maandwaarden.
      </figcaption>
    </figure>
  );
}
