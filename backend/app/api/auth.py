from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.config import instellingen
from app.logboek import leg_vast
from app.models import Adviseur, Logboek
from app.security import controleer_wachtwoord, hash_wachtwoord, maak_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Wordt gecontroleerd als het e-mailadres onbekend is, zodat de responstijd niet verraadt
# welke adressen bestaan.
_DUMMY_HASH = hash_wachtwoord("niet-bestaand-account-wachtwoord")


class LoginVerzoek(BaseModel):
    email: EmailStr
    wachtwoord: str


class TokenAntwoord(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdviseurUit(BaseModel):
    id: int
    email: str
    naam: str


@router.post("/login", response_model=TokenAntwoord)
def login(verzoek: LoginVerzoek, db: Db) -> TokenAntwoord:
    cfg = instellingen()
    email = verzoek.email.lower()
    sinds = datetime.now(UTC) - timedelta(minutes=cfg.login_blokkade_minuten)
    mislukt = db.scalar(
        select(func.count())
        .select_from(Logboek)
        .where(
            Logboek.actie == "login_mislukt",
            Logboek.entiteit_id == email,
            Logboek.tijdstip >= sinds,
        )
    )
    if mislukt >= cfg.max_mislukte_logins:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Te veel mislukte pogingen; probeer het over {cfg.login_blokkade_minuten} minuten opnieuw",
        )

    adviseur = db.scalar(select(Adviseur).where(Adviseur.email == email))
    juist = controleer_wachtwoord(
        verzoek.wachtwoord, adviseur.wachtwoord_hash if adviseur else _DUMMY_HASH
    )
    if adviseur is None or not adviseur.actief or not juist:
        leg_vast(db, "login_mislukt", entiteit="adviseur", entiteit_id=email)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Onjuist e-mailadres of wachtwoord")

    leg_vast(db, "login", adviseur_id=adviseur.id, entiteit="adviseur", entiteit_id=email)
    db.commit()
    return TokenAntwoord(access_token=maak_token(adviseur.id))


@router.get("/mij", response_model=AdviseurUit)
def mij(adviseur: Ingelogd) -> Adviseur:
    return adviseur
