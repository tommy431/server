"""Wijzigingsvoorstellen met vier-ogenprincipe voor instellingen die voor iedereen gelden."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.afhankelijkheden import Beheerder, Db, Ingelogd
from app.config import instellingen
from app.logboek import leg_vast
from app.models import Adviseur, Wijzigingsvoorstel

router = APIRouter(tags=["wijzigingsvoorstellen"])

# soort → functie(db, voorstel) die de wijziging doorvoert en een id van het resultaat teruggeeft.
TOEPASSERS: dict[str, Callable[[Session, Wijzigingsvoorstel], int | None]] = {}


def toepasser(soort: str):
    def registreer(functie):
        TOEPASSERS[soort] = functie
        return functie

    return registreer


class VoorstelUit(BaseModel):
    id: int
    soort: str
    sleutel: str | None
    inhoud: dict
    oud: dict | None
    status: str
    voorgesteld_door: str
    voorgesteld_door_id: int
    voorgesteld_op: datetime
    beoordeeld_door: str | None
    beoordeeld_op: datetime | None
    reden: str | None
    resultaat_id: int | None


class AfwijzingIn(BaseModel):
    reden: str = Field(min_length=1, max_length=1000)


def voorstel_uit(db: Session, v: Wijzigingsvoorstel) -> VoorstelUit:
    namen = dict(db.execute(select(Adviseur.id, Adviseur.naam)).all())
    return VoorstelUit(
        id=v.id,
        soort=v.soort,
        sleutel=v.sleutel,
        inhoud=v.inhoud,
        oud=v.oud,
        status=v.status,
        voorgesteld_door=namen.get(v.voorgesteld_door, ""),
        voorgesteld_door_id=v.voorgesteld_door,
        voorgesteld_op=v.voorgesteld_op,
        beoordeeld_door=namen.get(v.beoordeeld_door) if v.beoordeeld_door else None,
        beoordeeld_op=v.beoordeeld_op,
        reden=v.reden,
        resultaat_id=v.resultaat_id,
    )


def _voer_door(db: Session, v: Wijzigingsvoorstel, beoordelaar: Adviseur) -> None:
    v.resultaat_id = TOEPASSERS[v.soort](db, v)
    v.status = "doorgevoerd"
    v.beoordeeld_door = beoordelaar.id
    v.beoordeeld_op = datetime.now(UTC)
    leg_vast(
        db,
        "wijziging_doorgevoerd",
        adviseur_id=beoordelaar.id,
        entiteit=v.soort,
        entiteit_id=v.sleutel or v.id,
        details={"voorstel": v.id, "voorgesteld_door": v.voorgesteld_door},
    )


def dien_in(
    db: Session, adviseur: Adviseur, soort: str, sleutel: str | None, inhoud: dict, oud: dict | None
) -> VoorstelUit:
    """Legt een voorstel vast; zonder vier-ogenprincipe wordt het direct doorgevoerd.

    Per onderwerp kan er maar één voorstel tegelijk openstaan, zodat niet ongemerkt twee
    tegenstrijdige wijzigingen na elkaar worden goedgekeurd.
    """
    open_ = db.scalar(
        select(Wijzigingsvoorstel).where(
            Wijzigingsvoorstel.soort == soort,
            Wijzigingsvoorstel.sleutel.is_(None)
            if sleutel is None
            else Wijzigingsvoorstel.sleutel == sleutel,
            Wijzigingsvoorstel.status == "open",
        )
    )
    if open_ is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Er staat al een voorstel open (nummer {open_.id}); keur dat eerst goed of wijs het af",
        )
    v = Wijzigingsvoorstel(
        soort=soort,
        sleutel=sleutel,
        inhoud=inhoud,
        oud=oud,
        status="open",
        voorgesteld_door=adviseur.id,
    )
    db.add(v)
    db.flush()
    leg_vast(
        db,
        "wijziging_voorgesteld",
        adviseur_id=adviseur.id,
        entiteit=soort,
        entiteit_id=sleutel or v.id,
        details={"voorstel": v.id},
    )
    if not instellingen().vier_ogen:
        _voer_door(db, v, adviseur)
    db.commit()
    return voorstel_uit(db, v)


@router.get("/wijzigingsvoorstellen", response_model=list[VoorstelUit])
def lijst(
    db: Db,
    _: Ingelogd,
    status_: Annotated[str | None, Query(alias="status")] = None,
    soort: str | None = None,
) -> list[VoorstelUit]:
    vraag = select(Wijzigingsvoorstel).order_by(Wijzigingsvoorstel.id.desc())
    if status_:
        vraag = vraag.where(Wijzigingsvoorstel.status == status_)
    if soort:
        vraag = vraag.where(Wijzigingsvoorstel.soort == soort)
    return [voorstel_uit(db, v) for v in db.scalars(vraag.limit(200))]


def _open_voorstel(db: Db, voorstel_id: int) -> Wijzigingsvoorstel:
    v = db.get(Wijzigingsvoorstel, voorstel_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voorstel niet gevonden")
    if v.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Dit voorstel is al {v.status}")
    return v


@router.post("/wijzigingsvoorstellen/{voorstel_id}/goedkeuren", response_model=VoorstelUit)
def goedkeuren(voorstel_id: int, db: Db, beheerder: Beheerder) -> VoorstelUit:
    v = _open_voorstel(db, voorstel_id)
    if v.voorgesteld_door == beheerder.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Een tweede beheerder moet dit voorstel goedkeuren"
        )
    _voer_door(db, v, beheerder)
    db.commit()
    return voorstel_uit(db, v)


@router.post("/wijzigingsvoorstellen/{voorstel_id}/afwijzen", response_model=VoorstelUit)
def afwijzen(voorstel_id: int, invoer: AfwijzingIn, db: Db, beheerder: Beheerder) -> VoorstelUit:
    """Wijst een voorstel af; de indiener kan zijn eigen voorstel op deze manier intrekken."""
    v = _open_voorstel(db, voorstel_id)
    v.status = "afgewezen"
    v.beoordeeld_door = beheerder.id
    v.beoordeeld_op = datetime.now(UTC)
    v.reden = invoer.reden.strip()
    leg_vast(
        db,
        "wijziging_afgewezen",
        adviseur_id=beheerder.id,
        entiteit=v.soort,
        entiteit_id=v.sleutel or v.id,
        details={"voorstel": v.id, "reden": v.reden},
    )
    db.commit()
    return voorstel_uit(db, v)
