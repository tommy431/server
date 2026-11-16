"""Historische analyse van een portefeuille.

Uitgangspunten:
- Gerekend wordt met voor dividend gecorrigeerde slotkoersen in euro (totaalrendement).
- De lopende fondskosten zitten al in de koers verwerkt en worden dus niet nog eens afgetrokken.
  Transactiekosten en kosten van adviseur of bank zijn niet meegerekend.
- De portefeuille wordt bij de start en daarna op de eerste handelsdag van elk kalenderjaar
  teruggebracht naar de opgegeven gewichten; daartussen lopen de gewichten met de koersen mee.
- Ontbreekt op een dag een koers, dan geldt de laatst bekende koers.
- Koersen van vóór een onverklaarbare koerssprong worden niet gebruikt; dat wordt gemeld.
"""

import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from itertools import pairwise

from app.data.kwaliteit import MAX_DAGBEWEGING

PERIODEN = (("1j", 1), ("3j", 3), ("5j", 5), ("10j", 10))
MAX_ACHTERSTAND_DAGEN = 7

Reeks = dict[date, float]


@dataclass(frozen=True)
class Kengetallen:
    rendement_cumulatief: float
    rendement_per_jaar: float
    volatiliteit: float
    max_daling: float  # negatief getal, bijv. -0.25
    max_daling_top: date
    max_daling_dal: date
    sharpe: float | None


@dataclass(frozen=True)
class Periode:
    code: str
    jaren: int | None  # None = sinds start
    beschikbaar: bool
    reden: str | None = None
    van: date | None = None
    tot: date | None = None
    portefeuille: Kengetallen | None = None
    benchmark: Kengetallen | None = None
    risicovrij_per_jaar: float | None = None


@dataclass(frozen=True)
class Jaarrendement:
    jaar: int
    portefeuille: float
    benchmark: float | None


@dataclass(frozen=True)
class InstrumentHistorie:
    isin: str
    naam: str
    eerste_koers: date
    laatste_koers: date
    bruikbaar_vanaf: date
    ingekort: bool


@dataclass(frozen=True)
class Analyse:
    peildatum: date | None
    perioden: list[Periode] = field(default_factory=list)
    kalenderjaren: list[Jaarrendement] = field(default_factory=list)
    instrumenten: list[InstrumentHistorie] = field(default_factory=list)
    # Maandwaarden sinds start, beginwaarde 100: (datum, portefeuille, benchmark of None).
    waardeverloop: list[tuple[date, float, float | None]] = field(default_factory=list)
    waarschuwingen: list[str] = field(default_factory=list)

    def als_dict(self) -> dict:
        def zet_om(waarde):
            if isinstance(waarde, date):
                return waarde.isoformat()
            if isinstance(waarde, dict):
                return {k: zet_om(v) for k, v in waarde.items()}
            if isinstance(waarde, list | tuple):
                return [zet_om(v) for v in waarde]
            return waarde

        return zet_om(asdict(self))


def bruikbaar_deel(reeks: Reeks) -> tuple[Reeks, bool]:
    """Laat alles vóór de laatste koerssprong van meer dan 20% weg.

    Zo'n sprong is bij een breed gespreid fonds vrijwel zeker een fout in de brondata; de
    koersen ervoor zijn dan niet te vertrouwen.
    """
    dagen = sorted(reeks)
    begin = 0
    for i in range(1, len(dagen)):
        if abs(reeks[dagen[i]] / reeks[dagen[i - 1]] - 1) > MAX_DAGBEWEGING:
            begin = i
    return {d: reeks[d] for d in dagen[begin:]}, begin > 0


def jaren_terug(dag: date, jaren: int) -> date:
    try:
        return dag.replace(year=dag.year - jaren)
    except ValueError:  # 29 februari
        return dag.replace(year=dag.year - jaren, day=28)


def _koers_op(reeks: Reeks, dagen: list[date], dag: date) -> float | None:
    """Laatst bekende koers op of vóór `dag`; `dagen` is de gesorteerde lijst van de reeks."""
    lo, hi = 0, len(dagen)
    while lo < hi:
        mid = (lo + hi) // 2
        if dagen[mid] <= dag:
            lo = mid + 1
        else:
            hi = mid
    return reeks[dagen[lo - 1]] if lo else None


def waardeverloop(
    reeksen: dict[str, Reeks], gewichten: dict[str, float], van: date, tot: date
) -> list[tuple[date, float]]:
    """Waarde van de portefeuille van `van` t/m `tot`, beginwaarde 100.

    Elk instrument moet een koers hebben op of vóór `van`. De gewichten tellen op tot 1.
    """
    gesorteerd = {isin: sorted(reeksen[isin]) for isin in gewichten}
    kalender = sorted({van} | {d for isin in gewichten for d in gesorteerd[isin] if van < d <= tot})

    def koersen(dag: date) -> dict[str, float]:
        uit = {}
        for isin in gewichten:
            koers = _koers_op(reeksen[isin], gesorteerd[isin], dag)
            if koers is None:
                raise ValueError(f"{isin} heeft geen koers op of vóór {dag}")
            uit[isin] = koers
        return uit

    waarde = 100.0
    stukken: dict[str, float] = {}
    uit = []
    vorige_jaar = None
    for dag in kalender:
        nu = koersen(dag)
        if stukken:
            waarde = sum(stukken[i] * nu[i] for i in gewichten)
        if dag.year != vorige_jaar:  # start en eerste handelsdag van elk jaar: herbalanceren
            stukken = {i: gewichten[i] * waarde / nu[i] for i in gewichten}
            vorige_jaar = dag.year
        uit.append((dag, waarde))
    return uit


def kengetallen(
    waarden: list[tuple[date, float]], risicovrij_per_jaar: float | None
) -> Kengetallen:
    (begin, w0), (eind, wn) = waarden[0], waarden[-1]
    jaren = (eind - begin).days / 365.25
    cumulatief = wn / w0 - 1
    # Korter dan een jaar wordt niet naar jaarbasis omgerekend: dat blaast toeval op.
    heel_jaar = (eind - begin).days >= 365
    per_jaar = (1 + cumulatief) ** (1 / jaren) - 1 if heel_jaar else cumulatief

    dagrendementen = [b / a - 1 for (_, a), (_, b) in pairwise(waarden)]
    # Omrekenen naar jaarbasis met het werkelijke aantal waarnemingen per jaar.
    volatiliteit = (
        statistics.stdev(dagrendementen) * math.sqrt(len(dagrendementen) / jaren)
        if len(dagrendementen) > 1
        else 0.0
    )

    top_dag, top = begin, w0
    daling, daling_top, daling_dal = 0.0, begin, begin
    for dag, waarde in waarden:
        if waarde > top:
            top_dag, top = dag, waarde
        if waarde / top - 1 < daling:
            daling, daling_top, daling_dal = waarde / top - 1, top_dag, dag

    sharpe = None
    if risicovrij_per_jaar is not None and volatiliteit > 1e-9 and heel_jaar:
        sharpe = (per_jaar - risicovrij_per_jaar) / volatiliteit
    return Kengetallen(cumulatief, per_jaar, volatiliteit, daling, daling_top, daling_dal, sharpe)


def _rendement_per_jaar(reeks: Reeks, van: date, tot: date) -> float | None:
    dagen = sorted(reeks)
    begin, eind = _koers_op(reeks, dagen, van), _koers_op(reeks, dagen, tot)
    if begin is None or eind is None or dagen[-1] < tot - timedelta(days=MAX_ACHTERSTAND_DAGEN):
        return None
    return (eind / begin) ** (365.25 / (tot - van).days) - 1


def analyseer(
    gewichten: dict[str, float],
    reeksen: dict[str, Reeks],
    namen: dict[str, str],
    benchmark: dict[str, float] | None = None,
    risicovrij: str | None = None,
) -> Analyse:
    """Analyseert een portefeuille over 1, 3, 5 en 10 jaar en sinds start.

    `gewichten` en `benchmark` zijn ISIN → gewicht en tellen elk op tot 1. `reeksen` bevat per
    ISIN de gecorrigeerde koersen in euro; `risicovrij` is de ISIN van het geldmarktinstrument
    waarmee de Sharpe-ratio wordt berekend.
    """
    waarschuwingen: list[str] = []
    ontbreekt = [namen.get(i, i) for i in gewichten if not reeksen.get(i)]
    if not gewichten or ontbreekt:
        reden = (
            "Geen koersen beschikbaar voor: " + ", ".join(ontbreekt)
            if ontbreekt
            else "De portefeuille bevat geen posities"
        )
        return Analyse(peildatum=None, waarschuwingen=[reden])

    bruikbaar: dict[str, Reeks] = {}
    historie = []
    nodig = set(gewichten) | set(benchmark or {}) | ({risicovrij} if risicovrij else set())
    for isin in nodig:
        if not reeksen.get(isin):
            continue
        deel, ingekort = bruikbaar_deel(reeksen[isin])
        bruikbaar[isin] = deel
        if isin in gewichten:
            historie.append(
                InstrumentHistorie(
                    isin=isin,
                    naam=namen.get(isin, isin),
                    eerste_koers=min(reeksen[isin]),
                    laatste_koers=max(reeksen[isin]),
                    bruikbaar_vanaf=min(deel),
                    ingekort=ingekort,
                )
            )
            if ingekort:
                waarschuwingen.append(
                    f"{namen.get(isin, isin)}: koersen van vóór {min(deel)} zijn niet gebruikt "
                    "vanwege een koerssprong in de brondata"
                )
    historie.sort(key=lambda h: (h.bruikbaar_vanaf, h.naam), reverse=True)

    peildatum = max(h.laatste_koers for h in historie)
    for h in historie:
        if h.laatste_koers < peildatum - timedelta(days=MAX_ACHTERSTAND_DAGEN):
            waarschuwingen.append(
                f"{h.naam}: laatste koers is van {h.laatste_koers}; daarna is met die koers "
                "doorgerekend"
            )
    start = max(h.bruikbaar_vanaf for h in historie)
    kortste = historie[0]

    def bruikbaar_voor(samenstelling: dict[str, float] | None, van: date) -> bool:
        return bool(samenstelling) and all(
            i in bruikbaar
            and min(bruikbaar[i]) <= van
            and max(bruikbaar[i]) >= peildatum - timedelta(days=MAX_ACHTERSTAND_DAGEN)
            for i in samenstelling
        )

    def reken(code: str, jaren: int | None, van: date) -> tuple[Periode, list, list | None]:
        verloop = waardeverloop(bruikbaar, gewichten, van, peildatum)
        rf = (
            _rendement_per_jaar(bruikbaar[risicovrij], van, peildatum)
            if risicovrij in bruikbaar
            else None
        )
        verloop_bm = (
            waardeverloop(bruikbaar, benchmark, van, peildatum)
            if bruikbaar_voor(benchmark, van)
            else None
        )
        periode = Periode(
            code=code,
            jaren=jaren,
            beschikbaar=True,
            van=van,
            tot=peildatum,
            portefeuille=kengetallen(verloop, rf),
            benchmark=kengetallen(verloop_bm, rf) if verloop_bm else None,
            risicovrij_per_jaar=rf,
        )
        return periode, verloop, verloop_bm

    perioden = []
    for code, jaren in PERIODEN:
        van = jaren_terug(peildatum, jaren)
        if van < start:
            perioden.append(
                Periode(
                    code=code,
                    jaren=jaren,
                    beschikbaar=False,
                    reden=f"{kortste.naam} heeft bruikbare koersen vanaf {kortste.bruikbaar_vanaf}",
                )
            )
        else:
            perioden.append(reken(code, jaren, van)[0])

    if (peildatum - start).days < 30:
        perioden.append(
            Periode("start", None, False, reden="Minder dan een maand gezamenlijke historie")
        )
        return Analyse(peildatum, perioden, [], historie, [], waarschuwingen)

    sinds_start, verloop, verloop_bm = reken("start", None, start)
    perioden.append(sinds_start)
    if benchmark and verloop_bm is None:
        waarschuwingen.append(
            "De benchmark heeft geen koersen over de hele periode sinds start en is daar weggelaten"
        )
    if risicovrij and sinds_start.risicovrij_per_jaar is None:
        waarschuwingen.append(
            "Geen risicovrij rendement beschikbaar; de Sharpe-ratio is niet berekend"
        )

    # Volledige kalenderjaren: van de laatste waarde van het vorige jaar tot de laatste van het jaar.
    def jaareinden(reeks: list[tuple[date, float]]) -> dict[int, float]:
        return {dag.year: waarde for dag, waarde in reeks}

    eind_pf = jaareinden(verloop)
    eind_bm = jaareinden(verloop_bm) if verloop_bm else {}
    kalenderjaren = [
        Jaarrendement(
            jaar=jaar,
            portefeuille=eind_pf[jaar] / eind_pf[jaar - 1] - 1,
            benchmark=eind_bm[jaar] / eind_bm[jaar - 1] - 1 if jaar - 1 in eind_bm else None,
        )
        for jaar in sorted(eind_pf)
        if jaar - 1 in eind_pf and jaar < peildatum.year
    ]

    per_maand: dict[tuple[int, int], tuple[date, float, float | None]] = {}
    bm_op = dict(verloop_bm) if verloop_bm else {}
    for dag, waarde in verloop:
        per_maand[(dag.year, dag.month)] = (dag, waarde, bm_op.get(dag))
    maandwaarden = [(verloop[0][0], 100.0, 100.0 if verloop_bm else None)] + [
        punt for punt in per_maand.values() if punt[0] != verloop[0][0]
    ]
    return Analyse(peildatum, perioden, kalenderjaren, historie, maandwaarden, waarschuwingen)


def naar_euro(reeks: Reeks, valuta: str, wisselkoersen: Reeks | None) -> Reeks:
    """Rekent koersen om naar euro. `wisselkoersen` is vreemde valuta per 1 euro (ECB).

    Yahoo noteert sommige Londense fondsen in pence ("GBp"): eerst delen door 100.
    Dagen zonder wisselkoers gebruiken de laatst bekende; dagen vóór de eerste wisselkoers vervallen.
    """
    if valuta == "EUR":
        return reeks
    if not wisselkoersen:
        raise ValueError(f"Geen wisselkoersen beschikbaar voor {valuta.upper()}")
    deler = 100.0 if valuta == "GBp" else 1.0
    dagen = sorted(wisselkoersen)
    uit = {}
    for dag, koers in reeks.items():
        wissel = _koers_op(wisselkoersen, dagen, dag)
        if wissel is not None:
            uit[dag] = koers / deler / wissel
    return uit
