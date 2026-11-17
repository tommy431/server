import io
from datetime import UTC, datetime, timedelta

import pyotp
import segno
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select

from app.api.afhankelijkheden import Db, IngelogdTijdelijk
from app.config import instellingen
from app.logboek import leg_vast
from app.models import Adviseur, Inlogpoging
from app.security import (
    MIN_WACHTWOORDLENGTE,
    controleer_totp,
    controleer_wachtwoord,
    hash_wachtwoord,
    maak_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Wordt gecontroleerd als het e-mailadres onbekend is, zodat de responstijd niet verraadt
# welke adressen bestaan.
_DUMMY_HASH = hash_wachtwoord("niet-bestaand-account-wachtwoord")
# Vaste melding waaraan de schermen herkennen dat er een code nodig is.
CODE_NODIG = "tweestaps_nodig"


class LoginVerzoek(BaseModel):
    email: EmailStr
    wachtwoord: str
    code: str | None = None


class TokenAntwoord(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdviseurUit(BaseModel):
    id: int
    email: str
    naam: str
    rol: str
    tweestaps_actief: bool
    wachtwoord_wijzigen: bool


class WachtwoordIn(BaseModel):
    huidig: str
    nieuw: str = Field(min_length=MIN_WACHTWOORDLENGTE, max_length=200)


class CodeIn(BaseModel):
    code: str


class UitzettenIn(BaseModel):
    wachtwoord: str
    code: str


class TweestapsStart(BaseModel):
    geheim: str
    uri: str
    qr_svg: str


def _mislukt(db: Db, email: str, melding: str) -> HTTPException:
    leg_vast(db, "login_mislukt", entiteit="adviseur", entiteit_id=email)
    db.commit()
    return HTTPException(status.HTTP_401_UNAUTHORIZED, melding)


def _ip(request: Request) -> str:
    # Achter een proxy vult uvicorn dit met --proxy-headers alleen voor vertrouwde proxy's in.
    return (request.client.host if request.client else "onbekend")[:64]


def _aantal_mislukt(db: Db, sinds: datetime, **filters) -> int:
    """Mislukte pogingen sinds `sinds` en sinds de laatste geslaagde poging met dezelfde filters."""
    voorwaarden = [getattr(Inlogpoging, k) == v for k, v in filters.items()]
    laatste_gelukt = db.scalar(
        select(func.max(Inlogpoging.tijdstip)).where(*voorwaarden, Inlogpoging.gelukt)
    )
    if laatste_gelukt is not None:
        sinds = max(sinds, _als_utc(laatste_gelukt))
    return db.scalar(
        select(func.count())
        .select_from(Inlogpoging)
        .where(*voorwaarden, ~Inlogpoging.gelukt, Inlogpoging.tijdstip > sinds)
    )


def _als_utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _poging(db: Db, email: str, ip: str, gelukt: bool) -> None:
    nu = datetime.now(UTC)
    db.add(Inlogpoging(tijdstip=nu, email=email, ip=ip, gelukt=gelukt))
    # Oude pogingen opruimen; voor de controle is alleen het laatste kwartier nodig.
    db.execute(delete(Inlogpoging).where(Inlogpoging.tijdstip < nu - timedelta(days=1)))


def _mislukt(db: Db, email: str, ip: str, melding: str) -> HTTPException:
    _poging(db, email, ip, False)
    leg_vast(db, "login_mislukt", entiteit="adviseur", entiteit_id=email, details={"ip": ip})
    db.commit()
    return HTTPException(status.HTTP_401_UNAUTHORIZED, melding)


@router.post("/login", response_model=TokenAntwoord)
def login(verzoek: LoginVerzoek, request: Request, db: Db) -> TokenAntwoord:
    cfg = instellingen()
    email = verzoek.email.lower()
    ip = _ip(request)
    sinds = datetime.now(UTC) - timedelta(minutes=cfg.login_blokkade_minuten)
    if (
        _aantal_mislukt(db, sinds, ip=ip, email=email) >= cfg.max_mislukte_logins
        or _aantal_mislukt(db, sinds, ip=ip) >= cfg.max_mislukte_logins_per_ip
        or _aantal_mislukt(db, sinds, email=email) >= cfg.max_mislukte_logins_per_account
    ):
        # Zelfde melding voor alle drie, zodat niet te zien is welke grens is bereikt.
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Te veel mislukte pogingen; probeer het over {cfg.login_blokkade_minuten} minuten opnieuw",
        )

    adviseur = db.scalar(select(Adviseur).where(Adviseur.email == email))
    juist = controleer_wachtwoord(
        verzoek.wachtwoord, adviseur.wachtwoord_hash if adviseur else _DUMMY_HASH
    )
    if adviseur is None or not adviseur.actief or not juist:
        raise _mislukt(db, email, ip, "Onjuist e-mailadres of wachtwoord")

    if adviseur.tweestaps_actief:
        if not verzoek.code:
            # Wachtwoord klopt; nu de code. Telt niet als mislukte poging.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, CODE_NODIG)
        stap = controleer_totp(adviseur.totp_geheim, verzoek.code, adviseur.totp_laatste_stap)
        if stap is None:
            raise _mislukt(db, email, ip, "Onjuiste code")
        adviseur.totp_laatste_stap = stap

    _poging(db, email, ip, True)
    leg_vast(
        db,
        "login",
        adviseur_id=adviseur.id,
        entiteit="adviseur",
        entiteit_id=email,
        details={"ip": ip},
    )
    db.commit()
    return TokenAntwoord(access_token=maak_token(adviseur.id, adviseur.sessie_versie))


@router.get("/mij", response_model=AdviseurUit)
def mij(adviseur: IngelogdTijdelijk) -> Adviseur:
    return adviseur


@router.post("/wachtwoord", response_model=TokenAntwoord)
def wijzig_wachtwoord(invoer: WachtwoordIn, db: Db, adviseur: IngelogdTijdelijk) -> TokenAntwoord:
    """Wijzigt het eigen wachtwoord. Andere sessies van deze adviseur worden ongeldig."""
    if not controleer_wachtwoord(invoer.huidig, adviseur.wachtwoord_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Het huidige wachtwoord klopt niet")
    if invoer.nieuw == invoer.huidig:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Kies een ander wachtwoord dan het huidige"
        )
    adviseur.wachtwoord_hash = hash_wachtwoord(invoer.nieuw)
    adviseur.wachtwoord_wijzigen = False
    adviseur.sessie_versie += 1
    leg_vast(
        db,
        "wachtwoord_gewijzigd",
        adviseur_id=adviseur.id,
        entiteit="adviseur",
        entiteit_id=adviseur.email,
    )
    db.commit()
    return TokenAntwoord(access_token=maak_token(adviseur.id, adviseur.sessie_versie))


@router.post("/tweestaps/starten", response_model=TweestapsStart)
def tweestaps_starten(db: Db, adviseur: IngelogdTijdelijk) -> TweestapsStart:
    """Maakt een nieuw geheim aan. Pas actief na bevestigen met een geldige code."""
    if adviseur.tweestaps_actief:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tweestapsverificatie staat al aan")
    geheim = pyotp.random_base32()
    adviseur.totp_geheim = geheim
    db.commit()
    uri = pyotp.TOTP(geheim).provisioning_uri(
        name=adviseur.email, issuer_name="Portefeuille op maat"
    )
    svg = io.BytesIO()
    segno.make(uri, error="m").save(svg, kind="svg", scale=4, border=2, xmldecl=False, svgns=True)
    return TweestapsStart(geheim=geheim, uri=uri, qr_svg=svg.getvalue().decode())


@router.post("/tweestaps/bevestigen")
def tweestaps_bevestigen(invoer: CodeIn, db: Db, adviseur: IngelogdTijdelijk) -> dict:
    if adviseur.tweestaps_actief:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tweestapsverificatie staat al aan")
    if not adviseur.totp_geheim:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start eerst het instellen")
    stap = controleer_totp(adviseur.totp_geheim, invoer.code, None)
    if stap is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Onjuiste code")
    adviseur.tweestaps_actief = True
    adviseur.totp_laatste_stap = stap
    leg_vast(
        db,
        "tweestaps_aangezet",
        adviseur_id=adviseur.id,
        entiteit="adviseur",
        entiteit_id=adviseur.email,
    )
    db.commit()
    return {"tweestaps_actief": True}


@router.post("/tweestaps/uitzetten")
def tweestaps_uitzetten(invoer: UitzettenIn, db: Db, adviseur: IngelogdTijdelijk) -> dict:
    if not adviseur.tweestaps_actief:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tweestapsverificatie staat niet aan")
    if adviseur.rol == "beheerder" and instellingen().tweestaps_verplicht_beheerder:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Voor beheerders is tweestapsverificatie verplicht"
        )
    if not controleer_wachtwoord(invoer.wachtwoord, adviseur.wachtwoord_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Het wachtwoord klopt niet")
    stap = controleer_totp(adviseur.totp_geheim, invoer.code, adviseur.totp_laatste_stap)
    if stap is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Onjuiste code")
    adviseur.tweestaps_actief = False
    adviseur.totp_geheim = None
    adviseur.totp_laatste_stap = None
    leg_vast(
        db,
        "tweestaps_uitgezet",
        adviseur_id=adviseur.id,
        entiteit="adviseur",
        entiteit_id=adviseur.email,
    )
    db.commit()
    return {"tweestaps_actief": False}
