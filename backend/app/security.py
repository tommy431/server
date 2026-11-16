from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import instellingen

_hasher = PasswordHasher()
_ALGORITME = "HS256"
MIN_WACHTWOORDLENGTE = 12


def hash_wachtwoord(wachtwoord: str) -> str:
    if len(wachtwoord) < MIN_WACHTWOORDLENGTE:
        raise ValueError(f"Wachtwoord moet minimaal {MIN_WACHTWOORDLENGTE} tekens zijn")
    return _hasher.hash(wachtwoord)


def controleer_wachtwoord(wachtwoord: str, hash_: str) -> bool:
    try:
        return _hasher.verify(hash_, wachtwoord)
    except (VerificationError, InvalidHashError):
        return False


def maak_token(adviseur_id: int) -> str:
    nu = datetime.now(UTC)
    verloopt = nu + timedelta(minutes=instellingen().token_geldigheid_minuten)
    return jwt.encode(
        {"sub": str(adviseur_id), "iat": nu, "exp": verloopt},
        instellingen().jwt_geheim,
        algorithm=_ALGORITME,
    )


def lees_token(token: str) -> int | None:
    try:
        inhoud = jwt.decode(token, instellingen().jwt_geheim, algorithms=[_ALGORITME])
        return int(inhoud["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
