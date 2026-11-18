"""Koersen en wisselkoersen ophalen, controleren en opslaan."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.data.bronnen import BronFout, EcbBron, Koersbron, Koerspunt, haal_kortlopende_rente
from app.data.kwaliteit import Bevinding, controleer_reeks
from app.models import Bezitsopgave, Instrument, Koers, Marktkoers, Rente, Wisselkoers

BEGIN_HISTORIE = date(2005, 1, 1)
# Een marktkoers van overig bezit die ouder is, telt niet: dan geldt de opgegeven waarde.
MARKTKOERS_MAX_DAGEN = 10


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
    valuta = sorted(
        {v.upper() for v in db.scalars(select(Instrument.valuta).distinct())}
        | {wisselvaluta(v) for v in db.scalars(select(Marktkoers.valuta).distinct()) if v}
    )
    valuta = [v for v in valuta if v != "EUR"]
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


def wisselvaluta(valuta: str) -> str:
    """Valuta voor de wisselkoers: pence (GBp, GBX) en Zuid-Afrikaanse cent (ZAc) horen bij de hoofdmunt."""
    return {"GBP": "GBP", "GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"}.get(
        valuta.upper(), valuta.upper()
    )


def isins_overig_bezit(db: Session) -> set[str]:
    """ISIN's van overig bezit in de laatste opgave per klant."""
    laatste: dict[int, Bezitsopgave] = {}
    for b in db.scalars(select(Bezitsopgave).order_by(Bezitsopgave.id)):
        laatste[b.klant_id] = b
    return {o["isin"] for b in laatste.values() for o in b.overig or [] if o.get("isin")}


def ververs_marktkoersen(
    db: Session, bron, ecb: EcbBron, isins: set[str], alleen_ontbrekend: bool = False
) -> list[Resultaat]:
    """Haalt de laatste koers van overig bezit op, en de wisselkoers als die nog ontbreekt."""
    resultaten = []
    nu = datetime.now(UTC)
    for isin in sorted(isins):
        r = Resultaat(isin)
        rij = db.get(Marktkoers, isin)
        recent = (
            rij is not None
            and rij.datum is not None
            and (date.today() - rij.datum).days <= MARKTKOERS_MAX_DAGEN
        )
        if alleen_ontbrekend and recent and rij.koers is not None:
            continue
        try:
            if rij is None or rij.symbool is None:
                gevonden = bron.zoek_isin(isin)
                if rij is None:
                    rij = Marktkoers(isin=isin, bron=bron.naam, opgehaald_op=nu)
                    db.add(rij)
                if gevonden is None:
                    rij.opgehaald_op = nu
                    r.fout = f"{isin}: geen koers gevonden"
                    resultaten.append(r)
                    continue
                rij.symbool, rij.naam = gevonden
            reeks = bron.haal_koersen(rij.symbool, date.today() - timedelta(days=14))
            if not reeks.punten:
                raise BronFout(f"{isin}: geen recente koers")
            laatste = reeks.punten[-1]
            rij.valuta, rij.datum, rij.koers = reeks.valuta or None, laatste.datum, laatste.slot
            rij.bron, rij.opgehaald_op = bron.naam, nu
            r.opgeslagen = 1
        except BronFout as fout:
            r.fout = str(fout)
        resultaten.append(r)
    db.commit()

    # Ontbrekende wisselkoersen voor deze valuta's: alleen de laatste weken.
    nodig = {
        wisselvaluta(v)
        for v in db.scalars(select(Marktkoers.valuta).where(Marktkoers.isin.in_(isins)))
        if v and wisselvaluta(v) != "EUR"
    }
    bekend = set(db.scalars(select(Wisselkoers.valuta).distinct()))
    ontbrekend = sorted(nodig - bekend)
    if ontbrekend:
        r = Resultaat("wisselkoersen")
        try:
            koersen = ecb.haal_wisselkoersen(ontbrekend, date.today() - timedelta(days=14))
            db.execute(
                insert(Wisselkoers),
                [
                    {"valuta": v, "datum": d, "koers": k, "bron": ecb.naam, "opgehaald_op": nu}
                    for v, per_dag in koersen.items()
                    for d, k in per_dag.items()
                ],
            )
            db.commit()
            r.opgeslagen = sum(len(x) for x in koersen.values())
        except BronFout as fout:
            r.fout = str(fout)
        resultaten.append(r)
    return resultaten


def ververs_rente(db: Session, ecb: EcbBron) -> Resultaat:
    resultaat = Resultaat("rente")
    try:
        waarden = haal_kortlopende_rente(ecb._client, BEGIN_HISTORIE)
    except BronFout as fout:
        resultaat.fout = str(fout)
        return resultaat
    nu = datetime.now(UTC)
    db.execute(delete(Rente))
    db.execute(
        insert(Rente),
        [
            {"datum": d, "waarde": w, "reeks": r, "bron": "ecb", "opgehaald_op": nu}
            for d, w, r in waarden
        ],
    )
    db.commit()
    resultaat.opgeslagen = len(waarden)
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
    if hasattr(bron, "zoek_isin"):
        resultaten += ververs_marktkoersen(db, bron, ecb, isins_overig_bezit(db))
    resultaten.append(ververs_wisselkoersen(db, ecb))
    if hasattr(ecb, "_client"):
        resultaten.append(ververs_rente(db, ecb))
    return resultaten
