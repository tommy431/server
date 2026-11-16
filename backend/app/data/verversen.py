"""Koersen en wisselkoersen ophalen, controleren en opslaan."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.data.bronnen import BronFout, EcbBron, Koersbron, Koerspunt
from app.data.kwaliteit import Bevinding, controleer_reeks
from app.models import Instrument, Koers, Wisselkoers

BEGIN_HISTORIE = date(2005, 1, 1)


@dataclass
class Resultaat:
    onderdeel: str  # ISIN of "wisselkoersen"
    opgeslagen: int = 0
    fout: str | None = None
    bevindingen: list[Bevinding] = field(default_factory=list)


def sla_koersen_op(db: Session, instrument: Instrument, punten: list[Koerspunt], bron: str) -> None:
    """Vervangt de hele reeks van het instrument; de aanroeper commit.

    Altijd volledig vervangen: na elke dividenduitkering wijzigen de gecorrigeerde koersen
    met terugwerkende kracht, dus een gedeeltelijke aanvulling geeft een inconsistente reeks.
    """
    nu = datetime.now(UTC)
    db.execute(delete(Koers).where(Koers.instrument_id == instrument.id))
    db.execute(
        insert(Koers),
        [
            {
                "instrument_id": instrument.id,
                "datum": p.datum,
                "slot": p.slot,
                "slot_gecorrigeerd": p.slot_gecorrigeerd,
                "bron": bron,
                "opgehaald_op": nu,
            }
            for p in punten
        ],
    )


def ververs_instrument(
    db: Session, instrument: Instrument, bron: Koersbron, vandaag: date
) -> Resultaat:
    resultaat = Resultaat(instrument.isin)
    try:
        reeks = bron.haal_koersen(instrument.ticker, BEGIN_HISTORIE)
    except BronFout as fout:
        resultaat.fout = str(fout)
        return resultaat
    if reeks.valuta != instrument.valuta:
        resultaat.fout = (
            f"Bron levert koersen in {reeks.valuta or 'onbekende valuta'}, "
            f"maar het instrument staat geregistreerd in {instrument.valuta}"
        )
        return resultaat
    resultaat.bevindingen = controleer_reeks(reeks.punten, vandaag)
    fouten = [b.melding for b in resultaat.bevindingen if b.ernst == "fout"]
    if fouten:
        resultaat.fout = "; ".join(fouten)  # bestaande koersen blijven staan
        return resultaat
    sla_koersen_op(db, instrument, reeks.punten, bron.naam)
    db.commit()
    resultaat.opgeslagen = len(reeks.punten)
    return resultaat


def ververs_wisselkoersen(db: Session, ecb: EcbBron) -> Resultaat:
    resultaat = Resultaat("wisselkoersen")
    # Yahoo noteert Londense fondsen soms in pence ("GBp"); de wisselkoers is die van GBP.
    valuta = sorted({v.upper() for v in db.scalars(select(Instrument.valuta).distinct())} - {"EUR"})
    if not valuta:
        return resultaat
    try:
        koersen = ecb.haal_wisselkoersen(valuta, BEGIN_HISTORIE)
    except BronFout as fout:
        resultaat.fout = str(fout)
        return resultaat
    nu = datetime.now(UTC)
    rijen = [
        {"valuta": v, "datum": dag, "koers": koers, "bron": ecb.naam, "opgehaald_op": nu}
        for v, per_dag in koersen.items()
        for dag, koers in per_dag.items()
    ]
    db.execute(delete(Wisselkoers).where(Wisselkoers.valuta.in_(valuta)))
    db.execute(insert(Wisselkoers), rijen)
    db.commit()
    resultaat.opgeslagen = len(rijen)
    return resultaat


def ververs_alles(
    db: Session, bron: Koersbron, ecb: EcbBron, vandaag: date | None = None
) -> list[Resultaat]:
    """Ververst elk actief instrument in een eigen transactie: één fout stopt de rest niet."""
    vandaag = vandaag or date.today()
    instrumenten = db.scalars(
        select(Instrument).where(Instrument.actief).order_by(Instrument.isin)
    ).all()
    resultaten = [ververs_instrument(db, i, bron, vandaag) for i in instrumenten]
    resultaten.append(ververs_wisselkoersen(db, ecb))
    return resultaten
