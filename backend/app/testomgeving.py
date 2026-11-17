"""Vaste testomgeving voor de browsertests: lege database met voorspelbare gegevens.

Koersen worden gegenereerd in plaats van opgehaald, zodat de tests zonder internet draaien en
elke keer hetzelfde resultaat geven. Alleen bedoeld voor een aparte testdatabase.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.data.universum import laad_universum
from app.db import Basis
from app.models import Adviseur, Instrument, Koers, Rente
from app.security import hash_wachtwoord
from app.standaarden import zaai_aannames, zaai_standaarden

WACHTWOORD = "test-wachtwoord-e2e"
GEBRUIKERS = (
    ("beheerder1@voorbeeld.nl", "Bea Beheer", "beheerder"),
    ("beheerder2@voorbeeld.nl", "Bob Beheer", "beheerder"),
    ("adviseur@voorbeeld.nl", "Anna Adviseur", "adviseur"),
)
# Verwacht rendement en volatiliteit per jaar voor de gegenereerde koersen.
PROFIEL = {
    "aandelen": (0.07, 0.16),
    "obligaties": (0.025, 0.05),
    "vastgoed": (0.05, 0.18),
    "grondstoffen": (0.03, 0.17),
    "liquiditeiten": (0.015, 0.005),
}
JAREN = 11


def vul(db: Session, einddatum: date | None = None) -> None:
    """Maakt alle tabellen opnieuw aan en vult ze. Wist alles wat er stond."""
    engine = db.get_bind()
    Basis.metadata.drop_all(engine)
    Basis.metadata.create_all(engine)
    zaai_standaarden(db)
    zaai_aannames(db)
    for email, naam, rol in GEBRUIKERS:
        db.add(
            Adviseur(email=email, naam=naam, rol=rol, wachtwoord_hash=hash_wachtwoord(WACHTWOORD))
        )
    universum = Path(__file__).parent.parent / "data" / "universum.csv"
    laad_universum(db, universum.read_text("utf-8"))
    db.flush()

    eind = einddatum or date.today()
    dagen = [eind - timedelta(days=i) for i in range(JAREN * 365, -1, -1)]
    dagen = [d for d in dagen if d.weekday() < 5]
    nu = datetime.now(UTC)
    for instrument in db.scalars(select(Instrument).order_by(Instrument.isin)):
        mu, vol = PROFIEL[instrument.categorie]
        rng = np.random.default_rng(int(instrument.isin[-6:], 36) % 2**32)
        stappen = rng.normal(mu / 252 - vol**2 / 504, vol / np.sqrt(252), len(dagen))
        koersen = 100 * np.exp(np.cumsum(stappen))
        db.execute(
            insert(Koers),
            [
                {
                    "instrument_id": instrument.id,
                    "datum": d,
                    "slot": float(k),
                    "slot_gecorrigeerd": float(k),
                    "bron": "test",
                    "opgehaald_op": nu,
                }
                for d, k in zip(dagen, koersen, strict=True)
            ],
        )
    db.execute(
        insert(Rente),
        [
            {"datum": d, "waarde": 2.0, "reeks": "ESTR", "bron": "test", "opgehaald_op": nu}
            for d in dagen
        ],
    )
    db.commit()
