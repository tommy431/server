"""Logboek met hashketen: achteraf wijzigen, invoegen of verwijderen is aantoonbaar."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Logboek, LogboekKop

BEGIN = "0" * 64


def _tijd(tijdstip: datetime) -> str:
    """Tijdstip in UTC zonder tijdzone, zodat de hash gelijk is in PostgreSQL en SQLite."""
    if tijdstip.tzinfo is not None:
        tijdstip = tijdstip.astimezone(UTC).replace(tzinfo=None)
    return tijdstip.isoformat(timespec="microseconds")


def bereken_hash(regel: Logboek, vorige_hash: str) -> str:
    inhoud = json.dumps(
        {
            "id": regel.id,
            "tijdstip": _tijd(regel.tijdstip),
            "adviseur_id": regel.adviseur_id,
            "actie": regel.actie,
            "entiteit": regel.entiteit,
            "entiteit_id": regel.entiteit_id,
            "details": regel.details,
            "vorige": vorige_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(inhoud.encode()).hexdigest()


def _kop(db: Session) -> LogboekKop:
    kop = db.scalar(select(LogboekKop).where(LogboekKop.id == 1).with_for_update())
    if kop is None:
        kop = LogboekKop(id=1, laatste_id=0, laatste_hash=BEGIN)
        db.add(kop)
    return kop


def leg_vast(
    db: Session,
    actie: str,
    *,
    adviseur_id: int | None = None,
    entiteit: str | None = None,
    entiteit_id: str | int | None = None,
    details: dict | None = None,
) -> None:
    """Voegt een logboekregel toe aan de lopende transactie; de aanroeper commit.

    De kop van de keten wordt vergrendeld tot het einde van de transactie, zodat gelijktijdige
    regels elkaar niet als voorganger kunnen nemen.
    """
    kop = _kop(db)
    regel = Logboek(
        tijdstip=datetime.now(UTC),
        adviseur_id=adviseur_id,
        actie=actie,
        entiteit=entiteit,
        entiteit_id=None if entiteit_id is None else str(entiteit_id),
        details=details,
        vorige_hash=kop.laatste_hash,
    )
    db.add(regel)
    db.flush()
    regel.hash = bereken_hash(regel, kop.laatste_hash)
    kop.laatste_hash = regel.hash
    kop.laatste_id = regel.id


@dataclass
class Controle:
    in_orde: bool
    aantal: int
    laatste_hash: str
    fout_bij: int | None = None
    fout: str | None = None


def controleer_keten(db: Session) -> Controle:
    vorige = BEGIN
    aantal = 0
    laatste_id = 0
    for regel in db.scalars(select(Logboek).order_by(Logboek.id).execution_options(yield_per=1000)):
        aantal += 1
        if regel.vorige_hash != vorige:
            return Controle(
                False,
                aantal,
                vorige,
                regel.id,
                "De verwijzing naar de vorige regel klopt niet; er is een regel verwijderd of ingevoegd",
            )
        if regel.hash != bereken_hash(regel, vorige):
            return Controle(
                False, aantal, vorige, regel.id, "De inhoud van deze regel is gewijzigd"
            )
        vorige = regel.hash
        laatste_id = regel.id
    kop = db.get(LogboekKop, 1)
    if kop is not None and (kop.laatste_id != laatste_id or kop.laatste_hash != vorige):
        return Controle(
            False,
            aantal,
            vorige,
            laatste_id or None,
            "Er ontbreken regels aan het eind van het logboek",
        )
    return Controle(True, aantal, vorige)
