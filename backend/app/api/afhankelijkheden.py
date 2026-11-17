from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import instellingen
from app.db import sessie
from app.models import Adviseur
from app.security import lees_token

Db = Annotated[Session, Depends(sessie)]
_bearer = HTTPBearer(auto_error=False)


def huidige_adviseur(
    db: Db, inlog: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Adviseur:
    gegevens = lees_token(inlog.credentials) if inlog else None
    adviseur = db.get(Adviseur, gegevens[0]) if gegevens else None
    if adviseur is None or not adviseur.actief or gegevens[1] != adviseur.sessie_versie:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Niet ingelogd",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return adviseur


# Ingelogd, ook met een tijdelijk wachtwoord: alleen voor de eigen accountinstellingen.
IngelogdTijdelijk = Annotated[Adviseur, Depends(huidige_adviseur)]


def ingelogd_met_eigen_wachtwoord(adviseur: IngelogdTijdelijk) -> Adviseur:
    if adviseur.wachtwoord_wijzigen:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Kies eerst een eigen wachtwoord")
    return adviseur


Ingelogd = Annotated[Adviseur, Depends(ingelogd_met_eigen_wachtwoord)]


def huidige_beheerder(adviseur: Ingelogd) -> Adviseur:
    if adviseur.rol != "beheerder":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Alleen een beheerder mag dit doen")
    if instellingen().tweestaps_verplicht_beheerder and not adviseur.tweestaps_actief:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Zet eerst tweestapsverificatie aan om beheertaken te doen"
        )
    return adviseur


Beheerder = Annotated[Adviseur, Depends(huidige_beheerder)]
