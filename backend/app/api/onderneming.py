from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.afhankelijkheden import Beheerder, Db, Ingelogd
from app.api.wijzigingen import VoorstelUit, dien_in, toepasser
from app.logboek import leg_vast
from app.models import Ondernemingsgegevens

router = APIRouter(tags=["onderneming"])

# Verplicht voordat een rapport aan een klant mag (MiFID II, Wft en Kifid-aansluiting).
VERPLICHT = {
    "naam": "naam van de onderneming",
    "adres": "adres",
    "postcode_plaats": "postcode en plaats",
    "telefoon": "telefoonnummer",
    "email": "e-mailadres",
    "afm_vergunningnummer": "AFM-vergunningnummer",
    "kifid_nummer": "Kifid-aansluitnummer",
    "klachtenregeling": "klachtenregeling",
}


class Onderneming(BaseModel):
    naam: str = Field(default="", max_length=200)
    adres: str = Field(default="", max_length=200)
    postcode_plaats: str = Field(default="", max_length=200)
    telefoon: str = Field(default="", max_length=50)
    email: EmailStr | None = None
    website: str = Field(default="", max_length=200)
    kvk_nummer: str = Field(default="", pattern=r"^(\d{8})?$")
    afm_vergunningnummer: str = Field(default="", max_length=30)
    kifid_nummer: str = Field(default="", max_length=30)
    klachtenregeling: str = Field(default="", max_length=2000)


def huidige(db: Session) -> Onderneming:
    rij = db.scalar(select(Ondernemingsgegevens).order_by(Ondernemingsgegevens.id.desc()).limit(1))
    return Onderneming(**rij.gegevens) if rij else Onderneming()


def ontbrekend(o: Onderneming) -> list[str]:
    return [label for veld, label in VERPLICHT.items() if not str(getattr(o, veld) or "").strip()]


class OndernemingUit(Onderneming):
    ontbrekend: list[str]


@router.get("/onderneming", response_model=OndernemingUit)
def lees(db: Db, _: Ingelogd) -> OndernemingUit:
    o = huidige(db)
    return OndernemingUit(**o.model_dump(), ontbrekend=ontbrekend(o))


@router.put("/onderneming", response_model=VoorstelUit)
def wijzig(invoer: Onderneming, db: Db, beheerder: Beheerder) -> VoorstelUit:
    nieuw = {k: (v.strip() if isinstance(v, str) else v) for k, v in invoer.model_dump().items()}
    return dien_in(db, beheerder, "onderneming", None, nieuw, huidige(db).model_dump())


@toepasser("onderneming")
def _pas_toe(db, voorstel) -> int:
    rij = Ondernemingsgegevens(gegevens=voorstel.inhoud, vastgelegd_door=voorstel.voorgesteld_door)
    db.add(rij)
    db.flush()
    leg_vast(
        db,
        "onderneming_gewijzigd",
        adviseur_id=voorstel.voorgesteld_door,
        entiteit="onderneming",
        entiteit_id=rij.id,
        details={"voorstel": voorstel.id},
    )
    return rij.id
