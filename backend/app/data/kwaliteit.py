"""Controles op een koersreeks. Bevindingen worden getoond, nooit stil gecorrigeerd."""

import math
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from app.data.bronnen import Koerspunt

MAX_GAT_DAGEN = 7  # kalenderdagen tussen twee koersen; ruimer dan een lang paasweekend
MAX_DAGBEWEGING = 0.20
MAX_OUDERDOM_DAGEN = 7


@dataclass(frozen=True)
class Bevinding:
    ernst: str  # "fout" maakt de reeks onbruikbaar, "waarschuwing" vraagt aandacht
    code: str
    melding: str


def controleer_reeks(punten: list[Koerspunt], vandaag: date) -> list[Bevinding]:
    if not punten:
        return [Bevinding("fout", "geen_data", "Geen koersen beschikbaar")]

    bevindingen: list[Bevinding] = []
    ongeldig = [
        p.datum
        for p in punten
        if not (math.isfinite(p.slot) and math.isfinite(p.slot_gecorrigeerd))
        or p.slot <= 0
        or p.slot_gecorrigeerd <= 0
    ]
    if ongeldig:
        bevindingen.append(
            Bevinding(
                "fout",
                "ongeldige_koers",
                f"{len(ongeldig)} koers(en) zijn nul, negatief of geen getal (eerste: {ongeldig[0]})",
            )
        )
        return bevindingen

    gaten = [
        (a.datum, b.datum) for a, b in pairwise(punten) if (b.datum - a.datum).days > MAX_GAT_DAGEN
    ]
    if gaten:
        van, tot = max(gaten, key=lambda g: g[1] - g[0])
        bevindingen.append(
            Bevinding(
                "waarschuwing",
                "gat",
                f"{len(gaten)} periode(n) zonder koersen; de langste loopt van {van} tot {tot}",
            )
        )

    sprongen = [
        (b.datum, b.slot_gecorrigeerd / a.slot_gecorrigeerd - 1)
        for a, b in pairwise(punten)
        if abs(b.slot_gecorrigeerd / a.slot_gecorrigeerd - 1) > MAX_DAGBEWEGING
    ]
    if sprongen:
        dag, beweging = max(sprongen, key=lambda s: abs(s[1]))
        bevindingen.append(
            Bevinding(
                "waarschuwing",
                "sprong",
                f"{len(sprongen)} koerssprong(en) van meer dan {MAX_DAGBEWEGING:.0%}; "
                f"de grootste is {beweging:+.1%} op {dag}",
            )
        )

    ouderdom = (vandaag - punten[-1].datum).days
    if ouderdom > MAX_OUDERDOM_DAGEN:
        bevindingen.append(
            Bevinding(
                "waarschuwing",
                "verouderd",
                f"Laatste koers is van {punten[-1].datum} ({ouderdom} dagen oud)",
            )
        )
    return bevindingen
