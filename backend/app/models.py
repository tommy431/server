from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Basis
from app.versleuteling import VersleuteldeTekst

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


class Risicoprofiel(Basis):
    __tablename__ = "risicoprofiel"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    naam: Mapped[str] = mapped_column(String(50))
    # 1 = meest defensief; hoger is meer risico.
    niveau: Mapped[int] = mapped_column(Integer, unique=True)


class Modelallocatie(Basis):
    """Strategische asset allocatie per risicoprofiel, in hele procenten."""

    __tablename__ = "modelallocatie"

    risicoprofiel_id: Mapped[int] = mapped_column(
        ForeignKey("risicoprofiel.id", ondelete="CASCADE"), primary_key=True
    )
    categorie: Mapped[str] = mapped_column(String(30), primary_key=True)
    streef: Mapped[int] = mapped_column(Integer)
    minimum: Mapped[int] = mapped_column(Integer)
    maximum: Mapped[int] = mapped_column(Integer)


class Klant(Basis):
    __tablename__ = "klant"

    id: Mapped[int] = mapped_column(primary_key=True)
    adviseur_id: Mapped[int] = mapped_column(ForeignKey("adviseur.id"), index=True)
    naam: Mapped[str] = mapped_column(VersleuteldeTekst)
    email: Mapped[str | None] = mapped_column(VersleuteldeTekst)
    geboortedatum: Mapped[str | None] = mapped_column(VersleuteldeTekst)  # JJJJ-MM-DD
    gearchiveerd: Mapped[bool] = mapped_column(Boolean, default=False)
    aangemaakt_op: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Klantprofiel(Basis):
    """Eén vastgelegde versie van het klantprofiel. Wordt na opslaan niet meer gewijzigd."""

    __tablename__ = "klantprofiel"
    __table_args__ = (UniqueConstraint("klant_id", "versie"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    klant_id: Mapped[int] = mapped_column(ForeignKey("klant.id", ondelete="CASCADE"), index=True)
    versie: Mapped[int] = mapped_column(Integer)
    vastgelegd_op: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vastgelegd_door: Mapped[int] = mapped_column(ForeignKey("adviseur.id"))

    doel: Mapped[str] = mapped_column(VersleuteldeTekst)
    horizon_jaren: Mapped[int] = mapped_column(Integer)
    inleg_eur: Mapped[int] = mapped_column(Integer)
    storting_per_maand_eur: Mapped[int] = mapped_column(Integer)
    doelvermogen_eur: Mapped[int | None] = mapped_column(Integer)

    vragenlijst_versie: Mapped[int] = mapped_column(Integer)
    antwoorden: Mapped[dict] = mapped_column(JSON)
    score_bereidheid: Mapped[int] = mapped_column(Integer)
    score_capaciteit: Mapped[int] = mapped_column(Integer)
    score_kennis: Mapped[int] = mapped_column(Integer)

    duurzaamheid: Mapped[str] = mapped_column(String(20))
    uitsluitingen: Mapped[list] = mapped_column(JSON)
    duurzaamheid_toelichting: Mapped[str | None] = mapped_column(VersleuteldeTekst)

    # Uitkomst van de vragenlijst en horizon.
    afgeleid_risicoprofiel_id: Mapped[int] = mapped_column(ForeignKey("risicoprofiel.id"))
    bepalende_factor: Mapped[str] = mapped_column(String(30))
    # Het profiel waarmee gewerkt wordt: gelijk aan of defensiever dan het afgeleide profiel.
    risicoprofiel_id: Mapped[int] = mapped_column(ForeignKey("risicoprofiel.id"))
    afwijking_toelichting: Mapped[str | None] = mapped_column(VersleuteldeTekst)


class Portefeuille(Basis):
    """Eén vastgelegde versie van de portefeuille van een klant. Wordt niet meer gewijzigd.

    Risicoprofiel, banden en doorrekening zijn momentopnamen, zodat later te reconstrueren is
    waarop het advies was gebaseerd, ook als modelallocaties of fondsgegevens daarna wijzigen.
    """

    __tablename__ = "portefeuille"
    __table_args__ = (UniqueConstraint("klant_id", "versie"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    klant_id: Mapped[int] = mapped_column(ForeignKey("klant.id", ondelete="CASCADE"), index=True)
    versie: Mapped[int] = mapped_column(Integer)
    vastgelegd_op: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vastgelegd_door: Mapped[int] = mapped_column(ForeignKey("adviseur.id"))
    klantprofiel_id: Mapped[int] = mapped_column(ForeignKey("klantprofiel.id"))
    risicoprofiel: Mapped[str] = mapped_column(String(30))
    banden: Mapped[dict] = mapped_column(JSON)
    uitsluitingen: Mapped[list] = mapped_column(JSON)
    doorrekening: Mapped[dict] = mapped_column(JSON)
    # Historische analyse op het moment van vastleggen; leeg als er geen koersen waren.
    analyse: Mapped[dict | None] = mapped_column(JSON)
    toelichting: Mapped[str | None] = mapped_column(VersleuteldeTekst)


class Positie(Basis):
    __tablename__ = "positie"

    portefeuille_id: Mapped[int] = mapped_column(
        ForeignKey("portefeuille.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), primary_key=True)
    gewicht: Mapped[int] = mapped_column(Integer)  # basispunten
