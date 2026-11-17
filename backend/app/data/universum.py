"""Het beleggingsuniversum als beheerbaar CSV-bestand."""

import csv
import io
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CATEGORIEEN, REGIOS, SECTOREN, Instrument

KOLOMMEN = (
    "isin",
    "ticker",
    "naam",
    "categorie",
    "regio",
    "sector",
    "valuta",
    "lopende_kosten",
    "kosten_geverifieerd",
    "uitkerend",
    "startdatum",
)
_WAAR = {"ja": True, "nee": False}
VALUTARISICO = ("ja", "deels", "nee", "onbekend")


class UniversumFout(Exception):
    def __init__(self, fouten: list[str]) -> None:
        super().__init__("; ".join(fouten))
        self.fouten = fouten


def isin_geldig(isin: str) -> bool:
    """Controleert vorm en controlecijfer (Luhn over de naar cijfers omgezette tekens)."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        return False
    cijfers = "".join(str(int(teken, 36)) for teken in isin)
    totaal = 0
    for positie, cijfer in enumerate(reversed(cijfers)):
        waarde = int(cijfer)
        if positie % 2 == 1:
            waarde = waarde * 2 - 9 if waarde > 4 else waarde * 2
        totaal += waarde
    return totaal % 10 == 0


def _lees_rij(rij: dict[str, str]) -> dict:
    waarden = {k: (rij.get(k) or "").strip() for k in KOLOMMEN}
    valutarisico = (rij.get("valutarisico") or "onbekend").strip()
    if valutarisico not in VALUTARISICO:
        raise ValueError(f"'valutarisico' moet een van {', '.join(VALUTARISICO)} zijn")
    if not isin_geldig(waarden["isin"]):
        raise ValueError(f"ongeldige ISIN '{waarden['isin']}'")
    for veld in ("ticker", "naam", "valuta"):
        if not waarden[veld]:
            raise ValueError(f"'{veld}' ontbreekt")
    for veld, toegestaan in (("categorie", CATEGORIEEN), ("regio", REGIOS), ("sector", SECTOREN)):
        if waarden[veld] not in toegestaan:
            raise ValueError(f"onbekende {veld} '{waarden[veld]}'")
    for veld in ("kosten_geverifieerd", "uitkerend"):
        if waarden[veld] not in _WAAR:
            raise ValueError(f"'{veld}' moet 'ja' of 'nee' zijn")
    kosten = float(waarden["lopende_kosten"])
    if not 0 <= kosten <= 5:
        raise ValueError(f"lopende kosten {kosten}% vallen buiten 0–5%")
    return {
        "isin": waarden["isin"],
        "ticker": waarden["ticker"],
        "naam": waarden["naam"],
        "categorie": waarden["categorie"],
        "regio": waarden["regio"],
        "sector": waarden["sector"],
        "valuta": waarden["valuta"],
        "lopende_kosten": kosten,
        "kosten_geverifieerd": _WAAR[waarden["kosten_geverifieerd"]],
        "uitkerend": _WAAR[waarden["uitkerend"]],
        "startdatum": date.fromisoformat(waarden["startdatum"]) if waarden["startdatum"] else None,
        "valutarisico": valutarisico,
    }


def laad_universum(db: Session, tekst: str) -> tuple[int, int]:
    """Voegt instrumenten toe of werkt ze bij op ISIN. Alles of niets: bij één fout wijzigt er niets.

    Geeft (toegevoegd, bijgewerkt) terug; de aanroeper commit.
    """
    lezer = csv.DictReader(io.StringIO(tekst))
    ontbreekt = set(KOLOMMEN) - set(lezer.fieldnames or [])
    if ontbreekt:
        raise UniversumFout([f"Ontbrekende kolommen: {', '.join(sorted(ontbreekt))}"])

    rijen, fouten, gezien = [], [], set()
    for nummer, rij in enumerate(lezer, start=2):
        try:
            waarden = _lees_rij(rij)
            if waarden["isin"] in gezien:
                raise ValueError(f"ISIN {waarden['isin']} komt dubbel voor")
            gezien.add(waarden["isin"])
            rijen.append(waarden)
        except ValueError as fout:
            fouten.append(f"Regel {nummer}: {fout}")
    if fouten:
        raise UniversumFout(fouten)
    if not rijen:
        raise UniversumFout(["Het bestand bevat geen instrumenten"])

    bestaand = {i.isin: i for i in db.scalars(select(Instrument))}
    toegevoegd = bijgewerkt = 0
    for waarden in rijen:
        instrument = bestaand.get(waarden["isin"])
        if instrument is None:
            db.add(Instrument(**waarden))
            toegevoegd += 1
        else:
            for veld, waarde in waarden.items():
                setattr(instrument, veld, waarde)
            bijgewerkt += 1
    return toegevoegd, bijgewerkt
