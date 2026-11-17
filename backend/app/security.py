import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
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


def maak_token(adviseur_id: int, sessie_versie: int = 1) -> str:
    nu = datetime.now(UTC)
    verloopt = nu + timedelta(minutes=instellingen().token_geldigheid_minuten)
    return jwt.encode(
        {"sub": str(adviseur_id), "ver": sessie_versie, "iat": nu, "exp": verloopt},
        instellingen().jwt_geheim,
        algorithm=_ALGORITME,
    )


def lees_token(token: str) -> tuple[int, int] | None:
    """Geeft (adviseur-id, sessieversie) terug, of None bij een ongeldig of verlopen token."""
    try:
        inhoud = jwt.decode(token, instellingen().jwt_geheim, algorithms=[_ALGORITME])
        return int(inhoud["sub"]), int(inhoud.get("ver", 1))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def tijdelijk_wachtwoord() -> str:
    """Willekeurig wachtwoord van 16 tekens, zonder tekens die op elkaar lijken."""
    tekens = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(tekens) for _ in range(16))


def controleer_totp(geheim: str, code: str, laatste_stap: int | None) -> int | None:
    """Controleert een code uit een authenticator-app. Geeft de gebruikte tijdstap terug, of
    None als de code onjuist is of al eerder is gebruikt. Eén stap speling voor klokverschil."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(geheim)
    nu = int(datetime.now(UTC).timestamp()) // totp.interval
    for stap in (nu, nu - 1, nu + 1):
        if laatste_stap is not None and stap <= laatste_stap:
            continue
        if secrets.compare_digest(totp.generate_otp(stap), code):
            return stap
    return None
