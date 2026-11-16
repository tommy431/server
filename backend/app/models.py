from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Basis

CATEGORIEEN = ("aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten")
REGIOS = ("wereld", "noord-amerika", "europa", "opkomende-markten", "azie-pacific")
# GICS-sectoren; "breed" voor instrumenten die niet op één sector gericht zijn.
SECTOREN = (
    "breed",
    "energie",
    "materialen",
    "industrie",
    "duurzame-consumptiegoederen",
    "dagelijkse-consumptiegoederen",
    "gezondheidszorg",
    "financiele-dienstverlening",
    "informatietechnologie",
    "communicatiediensten",
    "nutsbedrijven",
    "vastgoed",
)


class Adviseur(Basis):
    __tablename__ = "adviseur"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    naam: Mapped[str] = mapped_column(String(200))
    wachtwoord_hash: Mapped[str] = mapped_column(String(200))
    actief: Mapped[bool] = mapped_column(Boolean, default=True)
    aangemaakt_op: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Logboek(Basis):
    """Wie heeft wat wanneer gedaan. Regels worden alleen toegevoegd, nooit gewijzigd."""

    __tablename__ = "logboek"

    id: Mapped[int] = mapped_column(primary_key=True)
    tijdstip: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    adviseur_id: Mapped[int | None] = mapped_column(ForeignKey("adviseur.id"), index=True)
    actie: Mapped[str] = mapped_column(String(100), index=True)
    entiteit: Mapped[str | None] = mapped_column(String(100))
    entiteit_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict | None] = mapped_column(JSON)


class Instrument(Basis):
    __tablename__ = "instrument"

    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True)
    ticker: Mapped[str] = mapped_column(String(20))
    naam: Mapped[str] = mapped_column(String(200))
    categorie: Mapped[str] = mapped_column(String(30), index=True)
    regio: Mapped[str] = mapped_column(String(30), index=True)
    sector: Mapped[str] = mapped_column(String(40), index=True)
    valuta: Mapped[str] = mapped_column(String(3))
    # Lopende kosten in procenten per jaar, bijv. 0.20 voor 0,20%.
    lopende_kosten: Mapped[float] = mapped_column(Float)
    # False zolang de kosten niet tegen het actuele essentiële-informatiedocument zijn gecontroleerd.
    kosten_geverifieerd: Mapped[bool] = mapped_column(Boolean, default=False)
    uitkerend: Mapped[bool] = mapped_column(Boolean)
    startdatum: Mapped[date | None] = mapped_column(Date)
    actief: Mapped[bool] = mapped_column(Boolean, default=True)


class Koers(Basis):
    __tablename__ = "koers"

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True
    )
    datum: Mapped[date] = mapped_column(Date, primary_key=True)
    slot: Mapped[float] = mapped_column(Float)
    # Gecorrigeerd voor dividend en splitsingen; basis voor totaalrendement.
    slot_gecorrigeerd: Mapped[float] = mapped_column(Float)
    bron: Mapped[str] = mapped_column(String(30))
    opgehaald_op: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Wisselkoers(Basis):
    """Eenheden vreemde valuta per 1 euro (ECB-referentiekoers)."""

    __tablename__ = "wisselkoers"

    valuta: Mapped[str] = mapped_column(String(3), primary_key=True)
    datum: Mapped[date] = mapped_column(Date, primary_key=True)
    koers: Mapped[float] = mapped_column(Float)
    bron: Mapped[str] = mapped_column(String(30))
    opgehaald_op: Mapped[datetime] = mapped_column(DateTime(timezone=True))
