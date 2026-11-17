from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.afhankelijkheden import Beheerder, Db, Ingelogd
from app.api.wijzigingen import VoorstelUit, dien_in, toepasser
from app.logboek import leg_vast
from app.models import CATEGORIEEN, Aannameset
from app.scenario import Aannames, controleer
from app.standaarden import STANDAARD_STRESS

router = APIRouter(tags=["aannames"])


class CategorieAanname(BaseModel):
    rendement: float
    volatiliteit: float


class AannamesIn(BaseModel):
    bron: str = Field(min_length=3, max_length=500)
    peildatum: date
    categorieen: dict[str, CategorieAanname]
    correlaties: dict[str, dict[str, float]]
    inflatie: float
    # Directe waardeverandering per categorie in een hypothetische zware crisis.
    stress: dict[str, float] = Field(default_factory=lambda: dict(STANDAARD_STRESS))


class AannamesUit(AannamesIn):
    id: int
    vastgelegd_op: datetime


def als_aannames(rij: Aannameset) -> Aannames:
    return Aannames(
        categorieen=CATEGORIEEN,
        rendement={c: rij.categorieen[c]["rendement"] for c in CATEGORIEEN if c in rij.categorieen},
        volatiliteit={
            c: rij.categorieen[c]["volatiliteit"] for c in CATEGORIEEN if c in rij.categorieen
        },
        correlaties=rij.correlaties,
        inflatie=rij.inflatie,
    )


def huidige(db: Db) -> Aannameset:
    rij = db.scalar(select(Aannameset).order_by(Aannameset.id.desc()).limit(1))
    if rij is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Er zijn nog geen aannames vastgelegd")
    return rij


def _uit(rij: Aannameset) -> AannamesUit:
    return AannamesUit(
        id=rij.id,
        vastgelegd_op=rij.vastgelegd_op,
        bron=rij.bron,
        peildatum=rij.peildatum,
        categorieen=rij.categorieen,
        correlaties=rij.correlaties,
        inflatie=rij.inflatie,
        stress=rij.stress or STANDAARD_STRESS,
    )


@router.get("/aannames", response_model=AannamesUit)
def lees(db: Db, _: Ingelogd) -> AannamesUit:
    return _uit(huidige(db))


@router.get("/aannames/geschiedenis", response_model=list[AannamesUit])
def geschiedenis(db: Db, _: Ingelogd) -> list[AannamesUit]:
    return [_uit(r) for r in db.scalars(select(Aannameset).order_by(Aannameset.id.desc()))]


@router.post("/aannames", response_model=VoorstelUit, status_code=status.HTTP_201_CREATED)
def leg_vast_aannames(invoer: AannamesIn, db: Db, beheerder: Beheerder) -> VoorstelUit:
    """Stelt een nieuwe versie van de aannames voor. Geldt na doorvoeren voor alle adviseurs."""
    if set(invoer.categorieen) != set(CATEGORIEEN) or set(invoer.correlaties) != set(CATEGORIEEN):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [f"Geef aannames voor precies deze categorieën: {', '.join(CATEGORIEEN)}"],
        )
    if invoer.peildatum > date.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ["De peildatum mag niet in de toekomst liggen"]
        )
    if set(invoer.stress) != set(CATEGORIEEN):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [f"Geef een crisisschok voor precies deze categorieën: {', '.join(CATEGORIEEN)}"],
        )
    buiten = [c for c, w in invoer.stress.items() if not -0.95 <= w <= 0.50]
    if buiten:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [f"Crisisschok voor {c} valt buiten −95% tot +50%" for c in buiten],
        )
    inhoud = {
        "bron": invoer.bron.strip(),
        "peildatum": invoer.peildatum.isoformat(),
        "categorieen": {c: invoer.categorieen[c].model_dump() for c in CATEGORIEEN},
        "correlaties": {
            a: {b: invoer.correlaties[a].get(b) for b in CATEGORIEEN} for a in CATEGORIEEN
        },
        "stress": {c: invoer.stress[c] for c in CATEGORIEEN},
        "inflatie": invoer.inflatie,
    }
    rij = _als_rij(inhoud)
    onvolledig = [a for a in CATEGORIEEN for b in CATEGORIEEN if rij.correlaties[a][b] is None]
    fouten = ["De correlatiematrix is onvolledig"] if onvolledig else controleer(als_aannames(rij))
    if fouten:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, fouten)
    vorige = db.scalar(select(Aannameset).order_by(Aannameset.id.desc()).limit(1))
    return dien_in(
        db,
        beheerder,
        "aannames",
        None,
        inhoud,
        _uit(vorige).model_dump(mode="json") if vorige else None,
    )


def _als_rij(inhoud: dict) -> Aannameset:
    return Aannameset(
        bron=inhoud["bron"],
        peildatum=date.fromisoformat(inhoud["peildatum"]),
        categorieen=inhoud["categorieen"],
        correlaties=inhoud["correlaties"],
        stress=inhoud["stress"],
        inflatie=inhoud["inflatie"],
    )


@toepasser("aannames")
def _pas_aannames_toe(db, voorstel) -> int:
    rij = _als_rij(voorstel.inhoud)
    rij.vastgelegd_door = voorstel.voorgesteld_door
    db.add(rij)
    db.flush()
    leg_vast(
        db,
        "aannames_vastgelegd",
        adviseur_id=voorstel.voorgesteld_door,
        entiteit="aannameset",
        entiteit_id=rij.id,
        details={"bron": rij.bron, "peildatum": rij.peildatum.isoformat(), "voorstel": voorstel.id},
    )
    return rij.id
