"""Opvolging na het advies: werkelijk bezit waarderen, vergelijken en herbalanceren.

Rekent in euro's en hele stukken. Transactiekosten en belastingen bij verkoop zijn niet
meegerekend; het herbalanceringsvoorstel is een hulpmiddel voor de adviseur, geen opdracht.
"""

import math
from dataclasses import dataclass, field
from datetime import date

from app.portefeuille import Fonds

KAS = "KAS"  # sleutel voor het geldsaldo in verdelingen
MIN_TRANSACTIE_EUR = 250.0  # kleinere aan- of verkopen worden niet voorgesteld
AFWIJKING_POSITIE_BP = 500  # meer dan 5 procentpunt afwijking van het advies is een signaal
EVALUATIE_MAANDEN = 12
BEZIT_VEROUDERD_DAGEN = 92


@dataclass(frozen=True)
class Positiewaarde:
    isin: str
    naam: str
    categorie: str
    aantal: float
    koers: float | None
    koersdatum: date | None
    waarde: float
    gewicht: int  # basispunten van het totaal
    advies: int  # basispunten volgens het advies (0 als niet in het advies)


@dataclass(frozen=True)
class Waardering:
    totaal: float
    kas: float
    posities: list[Positiewaarde]
    per_categorie: dict[str, int]  # basispunten; het geldsaldo telt als liquiditeiten
    zonder_koers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Transactie:
    isin: str
    naam: str
    actie: str  # "koop" of "verkoop"
    aantal: int
    koers: float
    bedrag: float


@dataclass(frozen=True)
class Herbalancering:
    transacties: list[Transactie]
    kas_na: float
    gewichten_na: dict[str, int]  # per ISIN, basispunten


@dataclass(frozen=True)
class Signaal:
    ernst: str  # "hoog", "middel" of "laag"
    code: str
    melding: str


def _bp(deel: float, totaal: float) -> int:
    return round(10_000 * deel / totaal) if totaal > 0 else 0


def waardeer(
    bezit: dict[str, float],
    kas: float,
    koersen: dict[str, tuple[date, float]],
    advies: dict[str, int],
    fondsen: dict[str, Fonds],
) -> Waardering:
    """Waardeert het bezit tegen de laatst bekende koersen (in euro's)."""
    regels = []
    zonder_koers = []
    for isin, aantal in bezit.items():
        f = fondsen.get(isin)
        if isin in koersen:
            datum, koers = koersen[isin]
        else:
            datum, koers = None, None
            zonder_koers.append(f.naam if f else isin)
        regels.append((isin, f, aantal, koers, datum, aantal * koers if koers else 0.0))
    totaal = kas + sum(r[5] for r in regels)

    posities = [
        Positiewaarde(
            isin=isin,
            naam=f.naam if f else isin,
            categorie=f.categorie if f else "onbekend",
            aantal=aantal,
            koers=koers,
            koersdatum=datum,
            waarde=waarde,
            gewicht=_bp(waarde, totaal),
            advies=advies.get(isin, 0),
        )
        for isin, f, aantal, koers, datum, waarde in regels
    ]
    # Fondsen in het advies die niet in bezit zijn, tonen we met waarde 0.
    for isin, gewicht in advies.items():
        if isin not in bezit:
            f = fondsen.get(isin)
            koersinfo = koersen.get(isin)
            posities.append(
                Positiewaarde(
                    isin=isin,
                    naam=f.naam if f else isin,
                    categorie=f.categorie if f else "onbekend",
                    aantal=0,
                    koers=koersinfo[1] if koersinfo else None,
                    koersdatum=koersinfo[0] if koersinfo else None,
                    waarde=0.0,
                    gewicht=0,
                    advies=gewicht,
                )
            )
    per_categorie: dict[str, float] = {}
    for p in posities:
        per_categorie[p.categorie] = per_categorie.get(p.categorie, 0.0) + p.waarde
    per_categorie["liquiditeiten"] = per_categorie.get("liquiditeiten", 0.0) + kas
    return Waardering(
        totaal=totaal,
        kas=kas,
        posities=sorted(posities, key=lambda p: (-p.advies, -p.waarde, p.naam)),
        per_categorie={c: _bp(w, totaal) for c, w in per_categorie.items()},
        zonder_koers=zonder_koers,
    )


def herbalanceer(
    w: Waardering, advies: dict[str, int], min_bedrag: float = MIN_TRANSACTIE_EUR
) -> Herbalancering:
    """Voorstel om terug te gaan naar de gewichten van het advies, in hele stukken.

    Eerst verkopen (wat te veel is, en fondsen buiten het advies), daarna kopen met het geldsaldo
    plus de opbrengst. Is er te weinig geld, dan worden alle aankopen naar rato verkleind.
    Afwijkingen kleiner dan `min_bedrag` blijven staan.
    """
    if w.zonder_koers or any(p.koers is None for p in w.posities if p.advies):
        raise ValueError("Niet van alle fondsen in bezit of advies is een koers bekend")
    totaal = w.totaal
    transacties: list[Transactie] = []
    kas = w.kas
    na = {p.isin: p.aantal for p in w.posities}
    koers = {p.isin: p.koers for p in w.posities}

    for p in w.posities:
        teveel = p.waarde - totaal * advies.get(p.isin, 0) / 10_000
        if teveel >= min_bedrag and p.koers:
            # Buiten het advies: alles verkopen, ook een gebroken aantal.
            aantal = p.aantal if p.isin not in advies else math.floor(teveel / p.koers)
            if aantal > 0:
                bedrag = aantal * p.koers
                transacties.append(Transactie(p.isin, p.naam, "verkoop", aantal, p.koers, bedrag))
                kas += bedrag
                na[p.isin] -= aantal

    tekorten = {}
    for p in w.posities:
        tekort = totaal * advies.get(p.isin, 0) / 10_000 - p.waarde
        if tekort >= min_bedrag and p.koers:
            tekorten[p.isin] = tekort
    benodigd = sum(tekorten.values())
    factor = min(1.0, kas / benodigd) if benodigd else 0.0
    for p in w.posities:
        if p.isin in tekorten:
            aantal = math.floor(tekorten[p.isin] * factor / p.koers)
            if aantal > 0:
                bedrag = aantal * p.koers
                transacties.append(Transactie(p.isin, p.naam, "koop", aantal, p.koers, bedrag))
                kas -= bedrag
                na[p.isin] += aantal

    waarde_na = {isin: aantal * (koers[isin] or 0) for isin, aantal in na.items()}
    return Herbalancering(
        transacties=transacties,
        kas_na=kas,
        gewichten_na={isin: _bp(v, totaal) for isin, v in waarde_na.items() if v > 0},
    )


def signalen(
    *,
    vandaag: date,
    heeft_profiel: bool,
    advies_datum: date | None,
    profiel_na_advies: bool,
    laatste_evaluatie: date | None,
    bezit_peildatum: date | None,
    waardering: Waardering | None,
    banden: dict[str, dict] | None,
) -> list[Signaal]:
    """Wat bij deze klant aandacht vraagt, het belangrijkste eerst."""
    uit: list[Signaal] = []
    if not heeft_profiel:
        return [Signaal("middel", "geen_profiel", "Nog geen klantprofiel vastgelegd")]
    if advies_datum is None:
        return [
            Signaal(
                "middel",
                "geen_advies",
                "Profiel vastgelegd, maar nog geen portefeuille geadviseerd",
            )
        ]
    if profiel_na_advies:
        uit.append(
            Signaal(
                "hoog",
                "profiel_herzien",
                "Het klantprofiel is herzien na het laatste advies; beoordeel de portefeuille opnieuw",
            )
        )

    basis = max(d for d in (advies_datum, laatste_evaluatie) if d is not None)
    volgende = _plus_maanden(basis, EVALUATIE_MAANDEN)
    if vandaag >= volgende:
        uit.append(
            Signaal(
                "hoog",
                "evaluatie_verlopen",
                f"Jaarlijkse evaluatie was gepland voor {volgende.isoformat()}",
            )
        )
    elif vandaag >= _plus_maanden(volgende, -1):
        uit.append(
            Signaal(
                "laag",
                "evaluatie_binnenkort",
                f"Jaarlijkse evaluatie gepland voor {volgende.isoformat()}",
            )
        )

    if bezit_peildatum is None or waardering is None:
        uit.append(Signaal("middel", "geen_bezit", "Het werkelijke bezit is nog niet vastgelegd"))
        return _sorteer(uit)
    if (vandaag - bezit_peildatum).days > BEZIT_VEROUDERD_DAGEN:
        uit.append(
            Signaal(
                "laag",
                "bezit_verouderd",
                f"Het bezit is voor het laatst vastgelegd op {bezit_peildatum.isoformat()}",
            )
        )
    if waardering.zonder_koers:
        uit.append(
            Signaal(
                "middel", "geen_koers", "Geen koers voor: " + ", ".join(waardering.zonder_koers)
            )
        )

    for categorie, band in (banden or {}).items():
        gewicht = waardering.per_categorie.get(categorie, 0)
        if not band["minimum"] * 100 <= gewicht <= band["maximum"] * 100:
            uit.append(
                Signaal(
                    "hoog",
                    "buiten_bandbreedte",
                    f"{categorie.capitalize()} weegt {gewicht / 100:.1f}% en valt buiten "
                    f"{band['minimum']}%–{band['maximum']}%; herbalanceren nodig".replace(".", ","),
                )
            )
    # Valt een categorie buiten de bandbreedte, dan dekt het herbalanceringsvoorstel de
    # afwijkingen per fonds; die melden we dan niet ook nog afzonderlijk.
    buiten = any(s.code == "buiten_bandbreedte" for s in uit)
    for p in waardering.posities:
        if p.advies == 0 and p.waarde > 0:
            uit.append(
                Signaal(
                    "middel", "niet_in_advies", f"{p.naam} zit in het bezit maar niet in het advies"
                )
            )
        elif not buiten and abs(p.gewicht - p.advies) > AFWIJKING_POSITIE_BP:
            uit.append(
                Signaal(
                    "laag",
                    "afwijking_positie",
                    f"{p.naam} weegt {p.gewicht / 100:.1f}% tegen {p.advies / 100:.1f}% in het advies".replace(
                        ".", ","
                    ),
                )
            )
    return _sorteer(uit)


def _sorteer(signalen_: list[Signaal]) -> list[Signaal]:
    volgorde = {"hoog": 0, "middel": 1, "laag": 2}
    return sorted(signalen_, key=lambda s: volgorde[s.ernst])


def _plus_maanden(d: date, maanden: int) -> date:
    jaar, maand = divmod(d.month - 1 + maanden, 12)
    jaar += d.year
    maand += 1
    for dag in (d.day, 30, 29, 28):
        try:
            return date(jaar, maand, dag)
        except ValueError:
            continue
    raise ValueError(d)
