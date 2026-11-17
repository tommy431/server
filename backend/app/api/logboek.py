from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.afhankelijkheden import Beheerder, Db
from app.logboek import controleer_keten
from app.models import Adviseur, Logboek

router = APIRouter(tags=["logboek"])


class RegelUit(BaseModel):
    id: int
    tijdstip: datetime
    door: str | None
    actie: str
    entiteit: str | None
    entiteit_id: str | None
    details: dict | None


class ControleUit(BaseModel):
    in_orde: bool
    aantal: int
    laatste_hash: str
    fout_bij: int | None
    fout: str | None


@router.get("/logboek", response_model=list[RegelUit])
def lijst(
    db: Db,
    _: Beheerder,
    actie: str | None = None,
    voor_id: Annotated[int | None, Query(description="Alleen regels ouder dan dit nummer")] = None,
    aantal: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[RegelUit]:
    namen = dict(db.execute(select(Adviseur.id, Adviseur.naam)).all())
    vraag = select(Logboek).order_by(Logboek.id.desc()).limit(aantal)
    if actie:
        vraag = vraag.where(Logboek.actie == actie)
    if voor_id:
        vraag = vraag.where(Logboek.id < voor_id)
    return [
        RegelUit(
            id=r.id,
            tijdstip=r.tijdstip,
            door=namen.get(r.adviseur_id),
            actie=r.actie,
            entiteit=r.entiteit,
            entiteit_id=r.entiteit_id,
            details=r.details,
        )
        for r in db.scalars(vraag)
    ]


@router.get("/logboek/controle", response_model=ControleUit)
def controle(db: Db, _: Beheerder) -> ControleUit:
    """Controleert de hele keten. De laatste hash kan buiten het systeem worden bewaard als bewijs."""
    c = controleer_keten(db)
    return ControleUit(**c.__dict__)
