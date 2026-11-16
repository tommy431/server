from sqlalchemy.orm import Session

from app.models import Logboek


def leg_vast(
    db: Session,
    actie: str,
    *,
    adviseur_id: int | None = None,
    entiteit: str | None = None,
    entiteit_id: str | int | None = None,
    details: dict | None = None,
) -> None:
    """Voegt een logboekregel toe aan de lopende transactie; de aanroeper commit."""
    db.add(
        Logboek(
            adviseur_id=adviseur_id,
            actie=actie,
            entiteit=entiteit,
            entiteit_id=None if entiteit_id is None else str(entiteit_id),
            details=details,
        )
    )
