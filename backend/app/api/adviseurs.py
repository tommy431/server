"""Gebruikersbeheer door beheerders.

Om het vier-ogenprincipe niet te kunnen omzeilen:
- wordt iemand alleen via een goedgekeurd voorstel beheerder;
- worden beheerders alleen via een goedgekeurd voorstel geblokkeerd of teruggezet naar adviseur;
- kunnen wachtwoord en tweestapsverificatie alleen worden gereset voor adviseurs. Voor een
  beheerder kan dat alleen op de server, met de beheeropdrachten.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.afhankelijkheden import Beheerder, Db
from app.api.wijzigingen import VoorstelUit, dien_in, toepasser
from app.config import instellingen
from app.logboek import leg_vast
from app.models import Adviseur, Klant
from app.security import hash_wachtwoord, tijdelijk_wachtwoord

router = APIRouter(tags=["gebruikers"])


class AccountUit(BaseModel):
    id: int
    email: str
    naam: str
    rol: str
    actief: bool
    tweestaps_actief: bool
    wachtwoord_wijzigen: bool
    aantal_klanten: int
    aangemaakt_op: datetime


class NieuwAccount(BaseModel):
    email: EmailStr
    naam: str = Field(min_length=1, max_length=200)


class NieuwAccountUit(BaseModel):
    account: AccountUit
    tijdelijk_wachtwoord: str


class RolIn(BaseModel):
    rol: Literal["adviseur", "beheerder"]


class StatusIn(BaseModel):
    actief: bool


def _uit(db: Session, a: Adviseur) -> AccountUit:
    klanten = db.scalar(select(func.count()).select_from(Klant).where(Klant.adviseur_id == a.id))
    return AccountUit(
        id=a.id,
        email=a.email,
        naam=a.naam,
        rol=a.rol,
        actief=a.actief,
        tweestaps_actief=a.tweestaps_actief,
        wachtwoord_wijzigen=a.wachtwoord_wijzigen,
        aantal_klanten=klanten,
        aangemaakt_op=a.aangemaakt_op,
    )


def _ander_account(db: Db, beheerder: Adviseur, account_id: int) -> Adviseur:
    account = db.get(Adviseur, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account niet gevonden")
    if account.id == beheerder.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "U kunt uw eigen account hier niet wijzigen")
    return account


def _alleen_adviseur(account: Adviseur) -> None:
    if account.rol != "adviseur":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Voor een beheerder kan dit alleen op de server, met de beheeropdrachten",
        )


@router.get("/adviseurs", response_model=list[AccountUit])
def lijst(db: Db, _: Beheerder) -> list[AccountUit]:
    return [_uit(db, a) for a in db.scalars(select(Adviseur).order_by(Adviseur.naam))]


@router.post("/adviseurs", response_model=NieuwAccountUit, status_code=status.HTTP_201_CREATED)
def maak(invoer: NieuwAccount, db: Db, beheerder: Beheerder) -> NieuwAccountUit:
    """Maakt een adviseur aan met een tijdelijk wachtwoord, dat bij eerste gebruik moet worden gewijzigd."""
    email = invoer.email.lower()
    if db.scalar(select(Adviseur).where(Adviseur.email == email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Er bestaat al een account met dit e-mailadres"
        )
    wachtwoord = tijdelijk_wachtwoord()
    account = Adviseur(
        email=email,
        naam=invoer.naam.strip(),
        rol="adviseur",
        wachtwoord_hash=hash_wachtwoord(wachtwoord),
        wachtwoord_wijzigen=True,
        tijdelijk_wachtwoord_door=beheerder.id,
    )
    db.add(account)
    db.flush()
    leg_vast(
        db, "account_aangemaakt", adviseur_id=beheerder.id, entiteit="adviseur", entiteit_id=email
    )
    db.commit()
    return NieuwAccountUit(account=_uit(db, account), tijdelijk_wachtwoord=wachtwoord)


@router.post("/adviseurs/{account_id}/wachtwoord-resetten", response_model=NieuwAccountUit)
def wachtwoord_resetten(account_id: int, db: Db, beheerder: Beheerder) -> NieuwAccountUit:
    account = _ander_account(db, beheerder, account_id)
    _alleen_adviseur(account)
    wachtwoord = tijdelijk_wachtwoord()
    account.wachtwoord_hash = hash_wachtwoord(wachtwoord)
    account.wachtwoord_wijzigen = True
    account.tijdelijk_wachtwoord_door = beheerder.id
    account.sessie_versie += 1
    leg_vast(
        db,
        "wachtwoord_gereset",
        adviseur_id=beheerder.id,
        entiteit="adviseur",
        entiteit_id=account.email,
    )
    db.commit()
    return NieuwAccountUit(account=_uit(db, account), tijdelijk_wachtwoord=wachtwoord)


@router.post("/adviseurs/{account_id}/tweestaps-resetten", response_model=AccountUit)
def tweestaps_resetten(account_id: int, db: Db, beheerder: Beheerder) -> AccountUit:
    """Zet tweestapsverificatie uit, bijvoorbeeld bij een verloren telefoon."""
    account = _ander_account(db, beheerder, account_id)
    _alleen_adviseur(account)
    account.tweestaps_actief = False
    account.totp_geheim = None
    account.totp_laatste_stap = None
    account.sessie_versie += 1
    leg_vast(
        db,
        "tweestaps_gereset",
        adviseur_id=beheerder.id,
        entiteit="adviseur",
        entiteit_id=account.email,
    )
    db.commit()
    return _uit(db, account)


@router.put("/adviseurs/{account_id}/status")
def wijzig_status(account_id: int, invoer: StatusIn, db: Db, beheerder: Beheerder) -> dict:
    """Blokkeert of deblokkeert een account. Voor een beheerder gaat dat via een voorstel."""
    account = _ander_account(db, beheerder, account_id)
    if account.rol == "beheerder":
        voorstel = dien_in(
            db,
            beheerder,
            "account",
            str(account.id),
            {"actief": invoer.actief},
            {"actief": account.actief, "email": account.email},
        )
        return {"voorstel": voorstel.model_dump(mode="json")}
    account.actief = invoer.actief
    if not invoer.actief:
        account.sessie_versie += 1
    leg_vast(
        db,
        "account_gedeblokkeerd" if invoer.actief else "account_geblokkeerd",
        adviseur_id=beheerder.id,
        entiteit="adviseur",
        entiteit_id=account.email,
    )
    db.commit()
    return {"account": _uit(db, account).model_dump(mode="json")}


@router.put("/adviseurs/{account_id}/rol", response_model=VoorstelUit)
def wijzig_rol(account_id: int, invoer: RolIn, db: Db, beheerder: Beheerder) -> VoorstelUit:
    """Een rolwijziging gaat altijd via een voorstel."""
    account = _ander_account(db, beheerder, account_id)
    if account.rol == invoer.rol:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Dit account is al {invoer.rol}")
    if invoer.rol == "beheerder":
        _controleer_nieuwe_beheerder(account, beheerder)
    return dien_in(
        db,
        beheerder,
        "account",
        str(account.id),
        {"rol": invoer.rol},
        {"rol": account.rol, "email": account.email},
    )


def _controleer_nieuwe_beheerder(account: Adviseur, betrokkene: Adviseur) -> None:
    """Voorkomt dat iemand via een zelf aangemaakt account een tweede beheerdersaccount krijgt."""
    if account.tijdelijk_wachtwoord_door == betrokkene.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "U heeft het tijdelijke wachtwoord van dit account uitgegeven; een andere beheerder moet dit voorstellen en goedkeuren",
        )
    if account.wachtwoord_wijzigen or not account.actief:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "De adviseur moet eerst zelf inloggen en een eigen wachtwoord kiezen",
        )
    if instellingen().tweestaps_verplicht_beheerder and not account.tweestaps_actief:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "De adviseur moet eerst zelf tweestapsverificatie instellen"
        )


def _actieve_beheerders(db: Session) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Adviseur)
        .where(Adviseur.rol == "beheerder", Adviseur.actief)
    )


@toepasser("account")
def _pas_toe(db: Session, voorstel) -> int:
    account = db.get(Adviseur, int(voorstel.sleutel))
    if account is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Het account bestaat niet meer")
    if (
        voorstel.inhoud.get("rol") == "beheerder"
        and voorstel.beoordeeld_door != voorstel.voorgesteld_door
    ):
        _controleer_nieuwe_beheerder(account, db.get(Adviseur, voorstel.beoordeeld_door))
    nodig = 2 if instellingen().vier_ogen else 1
    verliest_beheerder = (
        account.rol == "beheerder"
        and account.actief
        and (voorstel.inhoud.get("rol") == "adviseur" or voorstel.inhoud.get("actief") is False)
    )
    if verliest_beheerder and _actieve_beheerders(db) - 1 < nodig:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Er moeten minstens {nodig} actieve beheerders overblijven",
        )
    if "rol" in voorstel.inhoud:
        account.rol = voorstel.inhoud["rol"]
    if "actief" in voorstel.inhoud:
        account.actief = voorstel.inhoud["actief"]
    account.sessie_versie += 1
    leg_vast(
        db,
        "account_gewijzigd",
        adviseur_id=voorstel.voorgesteld_door,
        entiteit="adviseur",
        entiteit_id=account.email,
        details={**voorstel.inhoud, "voorstel": voorstel.id},
    )
    return account.id


class OverdrachtIn(BaseModel):
    naar_id: int


@router.post("/adviseurs/{account_id}/klanten-overdragen", response_model=VoorstelUit)
def klanten_overdragen(
    account_id: int, invoer: OverdrachtIn, db: Db, beheerder: Beheerder
) -> VoorstelUit:
    """Draagt alle klanten van een adviseur over aan een andere, bijvoorbeeld bij vertrek.

    Dit geeft toegang tot klantdossiers en gaat daarom via een voorstel.
    """
    van = db.get(Adviseur, account_id)
    naar = db.get(Adviseur, invoer.naar_id)
    if van is None or naar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account niet gevonden")
    if van.id == naar.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Kies een andere adviseur")
    if not naar.actief or naar.wachtwoord_wijzigen:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "De nieuwe adviseur moet actief zijn en een eigen wachtwoord hebben",
        )
    aantal = db.scalar(select(func.count()).select_from(Klant).where(Klant.adviseur_id == van.id))
    if not aantal:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze adviseur heeft geen klanten")
    return dien_in(
        db,
        beheerder,
        "klantoverdracht",
        str(van.id),
        {"naar": naar.id, "naar_email": naar.email, "aantal": aantal},
        {"van_email": van.email},
    )


@toepasser("klantoverdracht")
def _draag_over(db: Session, voorstel) -> int:
    from sqlalchemy import update

    naar = db.get(Adviseur, voorstel.inhoud["naar"])
    if naar is None or not naar.actief:
        raise HTTPException(status.HTTP_409_CONFLICT, "De nieuwe adviseur is niet meer actief")
    resultaat = db.execute(
        update(Klant).where(Klant.adviseur_id == int(voorstel.sleutel)).values(adviseur_id=naar.id)
    )
    leg_vast(
        db,
        "klanten_overgedragen",
        adviseur_id=voorstel.voorgesteld_door,
        entiteit="adviseur",
        entiteit_id=voorstel.inhoud["naar_email"],
        details={
            "van": voorstel.oud["van_email"],
            "aantal": resultaat.rowcount,
            "voorstel": voorstel.id,
        },
    )
    return naar.id
