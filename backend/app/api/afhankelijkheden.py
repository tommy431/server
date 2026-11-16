from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import sessie
from app.models import Adviseur
from app.security import lees_token

Db = Annotated[Session, Depends(sessie)]
_bearer = HTTPBearer(auto_error=False)


def huidige_adviseur(
    db: Db, inlog: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Adviseur:
    adviseur_id = lees_token(inlog.credentials) if inlog else None
    adviseur = db.get(Adviseur, adviseur_id) if adviseur_id is not None else None
    if adviseur is None or not adviseur.actief:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Niet ingelogd",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return adviseur


Ingelogd = Annotated[Adviseur, Depends(huidige_adviseur)]
