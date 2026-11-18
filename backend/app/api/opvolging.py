from dataclasses import asdict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.api.klanten import _eigen_klant
from app.bezitimport import MAX_TEKENS, isin_geldig, lees_bezit
from app.config import instellingen
from app.data.bronnen import BronFout, EcbBron, YahooBron
from app.data.verversen import ververs_marktkoersen, wisselvaluta
from app.logboek import leg_vast
from app.models import (
    Adviseur,
    Bezitsopgave,
    Evaluatie,
    Instrument,
    Klant,
    Klantprofiel,
    Koers,
    Marktkoers,
    Portefeuille,
    Positie,
    Wisselkoers,
)
from app.opvolging import Overig, herbalanceer, signalen, waardeer
from app.portefeuille import Fonds

router = APIRouter(tags=["opvolging"])


class BezitRegel(BaseModel):
    isin: str
    aantal: float = Field(gt=0, le=1e9)


class OverigIn(BaseModel):
    omschrijving: str = Field(min_length=1, max_length=200)
    isin: str | None = Field(default=None, max_length=12)
    categorie: Literal[
        "aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten", "overig"
    ]
    waarde_eur: float | None = Field(default=None, gt=0, le=1e10)
    aantal: float | None = Field(default=None, gt=0, le=1e9)
    behouden: bool = False


class BezitIn(BaseModel):
    peildatum: date
    posities: list[BezitRegel] = Field(max_length=200)
    overig: list[OverigIn] = Field(default_factory=list, max_length=50)
    kas_eur: float = Field(ge=0, le=1e10)


class InlezenIn(BaseModel):
    tekst: str = Field(max_length=MAX_TEKENS)


class IngelezenRegel(BaseModel):
    isin: str
    naam: str
    aantal: float


class OverigVoorstel(BaseModel):
    isin: str
    omschrijving: str
    aantal: float
    waarde_eur: float | None


class InlezenUit(BaseModel):
    posities: list[IngelezenRegel]
    overig: list[OverigVoorstel]
    meldingen: list[str]


class EvaluatieIn(BaseModel):
    datum: date
    uitkomst: Literal["ongewijzigd", "aangepast", "herbalanceren"]
    notitie: str | None = Field(default=None, max_length=4000)


class EvaluatieUit(BaseModel):
    id: int
    datum: date
    uitkomst: str
    notitie: str | None
    door: str


class SignaalUit(BaseModel):
    ernst: str
    code: str
    melding: str


class OpvolgingUit(BaseModel):
    advies: dict | None  # versie, datum, risicoprofiel, banden
    bezit: dict | None  # peildatum, posities, kas_eur, vastgelegd_op
    waardering: dict | None
    herbalancering: dict | None
    herbalancering_fout: str | None
    signalen: list[SignaalUit]
    evaluaties: list[EvaluatieUit]
    volgende_evaluatie: date | None


class KlantSignalen(BaseModel):
    klant_id: int
    naam: str
    signalen: list[SignaalUit]


def _fondsen(db: Db) -> dict[str, Fonds]:
    return {
        i.isin: Fonds(
            i.isin,
            i.naam,
            i.categorie,
            i.regio,
            i.sector,
            i.lopende_kosten,
            i.kosten_geverifieerd,
            i.actief,
        )
        for i in db.scalars(select(Instrument))
    }


def _laatste_koersen(db: Db) -> dict[str, tuple[date, float]]:
    """Laatste slotkoers per instrument (niet gecorrigeerd: de waarde van één stuk vandaag)."""
    laatste = (
        select(Koers.instrument_id, func.max(Koers.datum).label("datum"))
        .group_by(Koers.instrument_id)
        .subquery()
    )
    rijen = db.execute(
        select(Instrument.isin, Koers.datum, Koers.slot)
        .join(
            laatste,
            (Koers.instrument_id == laatste.c.instrument_id) & (Koers.datum == laatste.c.datum),
        )
        .join(Instrument, Instrument.id == Koers.instrument_id)
    ).all()
    # Alle fondsen noteren in euro's; een fonds in een andere valuta wordt niet gewaardeerd.
    valuta = dict(db.execute(select(Instrument.isin, Instrument.valuta)).all())
    return {isin: (d, slot) for isin, d, slot in rijen if valuta.get(isin) == "EUR"}


MARKTKOERS_MAX_DAGEN = 10  # oudere koersen gebruiken we niet: dan geldt de opgegeven waarde


def _koers_eur(db: Db, mk: Marktkoers) -> float | None:
    """Marktkoers in euro's met de laatste ECB-wisselkoers; pence en centen naar de hoofdmunt."""
    if mk.koers is None or mk.valuta is None:
        return None
    koers = mk.koers / 100 if mk.valuta in {"GBp", "GBX", "ZAc", "ILA"} else mk.koers
    munt = wisselvaluta(mk.valuta)
    if munt == "EUR":
        return koers
    wissel = db.scalar(
        select(Wisselkoers.koers)
        .where(Wisselkoers.valuta == munt)
        .order_by(Wisselkoers.datum.desc())
        .limit(1)
    )
    return koers / wissel if wissel else None


def _overig(db: Db, regels: list[dict], vandaag: date | None = None) -> list[Overig]:
    vandaag = vandaag or date.today()
    uit = []
    for o in regels:
        koers = koersdatum = None
        mk = db.get(Marktkoers, o["isin"]) if o.get("isin") else None
        if mk and mk.datum and (vandaag - mk.datum).days <= MARKTKOERS_MAX_DAGEN:
            koers, koersdatum = _koers_eur(db, mk), mk.datum
        uit.append(
            Overig(
                o["omschrijving"],
                o["categorie"],
                o.get("waarde"),
                o["behouden"],
                o.get("isin"),
                o.get("aantal"),
                koers,
                koersdatum if koers else None,
            )
        )
    return uit


class _GeenBron:
    """Bron die niets ophaalt, als het ophalen van marktkoersen uit staat."""

    naam = "geen"

    def zoek_isin(self, isin: str):
        raise BronFout("Het ophalen van marktkoersen staat uit")

    def haal_koersen(self, symbool: str, vanaf: date):
        raise BronFout("Het ophalen van marktkoersen staat uit")

    def haal_wisselkoersen(self, valuta: list[str], vanaf: date):
        raise BronFout("Het ophalen van marktkoersen staat uit")


def koersbronnen() -> tuple:
    if not instellingen().marktkoersen_ophalen:
        return _GeenBron(), _GeenBron()
    return YahooBron(), EcbBron()


Bronnen = Annotated[tuple, Depends(koersbronnen)]


def _toestand(db: Db, klant: Klant, vandaag: date, koersen=None, fondsen=None) -> dict:
    profiel = db.scalar(
        select(Klantprofiel)
        .where(Klantprofiel.klant_id == klant.id)
        .order_by(Klantprofiel.versie.desc())
        .limit(1)
    )
    advies = db.scalar(
        select(Portefeuille)
        .where(Portefeuille.klant_id == klant.id)
        .order_by(Portefeuille.versie.desc())
        .limit(1)
    )
    bezit = db.scalar(
        select(Bezitsopgave)
        .where(Bezitsopgave.klant_id == klant.id)
        .order_by(Bezitsopgave.id.desc())
        .limit(1)
    )
    evaluaties = db.scalars(
        select(Evaluatie)
        .where(Evaluatie.klant_id == klant.id)
        .order_by(Evaluatie.datum.desc(), Evaluatie.id.desc())
    ).all()
    gewichten: dict[str, int] = {}
    if advies:
        ids = {i.id: i.isin for i in db.scalars(select(Instrument))}
        gewichten = {
            ids[p.instrument_id]: p.gewicht
            for p in db.scalars(select(Positie).where(Positie.portefeuille_id == advies.id))
        }
    waardering = None
    if bezit and advies:
        waardering = waardeer(
            bezit.posities,
            bezit.kas_eur,
            koersen if koersen is not None else _laatste_koersen(db),
            gewichten,
            fondsen or _fondsen(db),
            _overig(db, bezit.overig or []),
        )
    profiel_na_advies = bool(
        profiel and advies and db.get(Klantprofiel, advies.klantprofiel_id).versie < profiel.versie
    )
    return {
        "profiel": profiel,
        "advies": advies,
        "gewichten": gewichten,
        "bezit": bezit,
        "evaluaties": evaluaties,
        "waardering": waardering,
        "signalen": signalen(
            vandaag=vandaag,
            heeft_profiel=profiel is not None,
            advies_datum=advies.vastgelegd_op.date() if advies else None,
            profiel_na_advies=profiel_na_advies,
            laatste_evaluatie=evaluaties[0].datum if evaluaties else None,
            bezit_peildatum=bezit.peildatum if bezit else None,
            waardering=waardering,
            banden=advies.banden if advies else None,
        ),
    }


@router.get("/klanten/{klant_id}/opvolging", response_model=OpvolgingUit)
def opvolging(klant_id: int, db: Db, adviseur: Ingelogd) -> OpvolgingUit:
    from app.opvolging import EVALUATIE_MAANDEN, _plus_maanden

    klant = _eigen_klant(db, adviseur, klant_id)
    t = _toestand(db, klant, date.today())
    advies, bezit, w = t["advies"], t["bezit"], t["waardering"]
    h, fout = None, None
    if w is not None:
        try:
            h = herbalanceer(w, t["gewichten"])
        except ValueError as e:
            fout = str(e)
    namen = dict(db.execute(select(Adviseur.id, Adviseur.naam)).all())
    basis = [
        d
        for d in (
            advies.vastgelegd_op.date() if advies else None,
            t["evaluaties"][0].datum if t["evaluaties"] else None,
        )
        if d
    ]
    return OpvolgingUit(
        advies={
            "versie": advies.versie,
            "datum": advies.vastgelegd_op.date().isoformat(),
            "risicoprofiel": advies.risicoprofiel,
            "banden": advies.banden,
            "posities": t["gewichten"],
        }
        if advies
        else None,
        bezit={
            "peildatum": bezit.peildatum.isoformat(),
            "posities": bezit.posities,
            "kas_eur": bezit.kas_eur,
            "overig": bezit.overig or [],
            "vastgelegd_op": bezit.vastgelegd_op.isoformat(),
        }
        if bezit
        else None,
        waardering=asdict(w) if w else None,
        herbalancering=asdict(h) if h else None,
        herbalancering_fout=fout,
        signalen=[SignaalUit(**asdict(s)) for s in t["signalen"]],
        evaluaties=[
            EvaluatieUit(
                id=e.id,
                datum=e.datum,
                uitkomst=e.uitkomst,
                notitie=e.notitie,
                door=namen.get(e.vastgelegd_door, ""),
            )
            for e in t["evaluaties"]
        ],
        volgende_evaluatie=_plus_maanden(max(basis), EVALUATIE_MAANDEN) if basis else None,
    )


@router.post("/klanten/{klant_id}/bezit", status_code=status.HTTP_201_CREATED)
def leg_bezit_vast(
    klant_id: int, invoer: BezitIn, db: Db, adviseur: Ingelogd, bronnen: Bronnen
) -> dict:
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.gearchiveerd:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is gearchiveerd")
    if invoer.peildatum > date.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "De peildatum mag niet in de toekomst liggen"
        )
    bekend = set(db.scalars(select(Instrument.isin)))
    onbekend = [p.isin for p in invoer.posities if p.isin not in bekend]
    if onbekend:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Onbekend fonds: {', '.join(onbekend)}"
        )
    if len({p.isin for p in invoer.posities}) != len(invoer.posities):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Een fonds komt dubbel voor")
    for o in invoer.overig:
        if o.isin and o.isin in bekend:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{o.isin} staat in de fondsenlijst; leg het vast als fonds met een aantal",
            )
        if o.isin and not isin_geldig(o.isin):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Ongeldig ISIN bij {o.omschrijving}: {o.isin}",
            )
        if o.waarde_eur is None and not (o.isin and o.aantal):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Geef bij {o.omschrijving} een waarde op, of een ISIN met het aantal stukken",
            )
    opgave = Bezitsopgave(
        klant_id=klant.id,
        peildatum=invoer.peildatum,
        posities={p.isin: p.aantal for p in invoer.posities},
        kas_eur=invoer.kas_eur,
        overig=[
            {
                "omschrijving": o.omschrijving.strip(),
                "isin": o.isin or None,
                "categorie": o.categorie,
                "waarde": o.waarde_eur,
                "aantal": o.aantal,
                "behouden": o.behouden,
            }
            for o in invoer.overig
        ],
        vastgelegd_door=adviseur.id,
    )
    db.add(opgave)
    db.flush()
    leg_vast(
        db,
        "bezit_vastgelegd",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
        details={
            "peildatum": invoer.peildatum.isoformat(),
            "fondsen": len(invoer.posities),
            "overig": len(invoer.overig),
        },
    )
    db.commit()
    # Koersen van nieuw overig bezit meteen ophalen; mislukt dat, dan geldt de opgegeven waarde.
    isins = {o.isin for o in invoer.overig if o.isin and o.aantal}
    if isins:
        ververs_marktkoersen(db, *bronnen, isins, alleen_ontbrekend=True)
    return {"id": opgave.id}


@router.post("/klanten/{klant_id}/koersen")
def koersen_ophalen(klant_id: int, db: Db, adviseur: Ingelogd, bronnen: Bronnen) -> dict:
    """Haalt de koersen van het overige bezit van deze klant opnieuw op."""
    klant = _eigen_klant(db, adviseur, klant_id)
    bezit = db.scalar(
        select(Bezitsopgave)
        .where(Bezitsopgave.klant_id == klant.id)
        .order_by(Bezitsopgave.id.desc())
        .limit(1)
    )
    isins = {o["isin"] for o in (bezit.overig or []) if o.get("isin")} if bezit else set()
    resultaten = ververs_marktkoersen(db, *bronnen, isins) if isins else []
    return {
        "opgehaald": sum(r.opgeslagen for r in resultaten if r.onderdeel != "wisselkoersen"),
        "fouten": [r.fout for r in resultaten if r.fout],
    }


@router.post("/klanten/{klant_id}/bezit/inlezen", response_model=InlezenUit)
def bezit_inlezen(klant_id: int, invoer: InlezenIn, db: Db, adviseur: Ingelogd) -> InlezenUit:
    """Leest een depotoverzicht (CSV) voor controle in het formulier. Slaat niets op."""
    _eigen_klant(db, adviseur, klant_id)
    r = lees_bezit(invoer.tekst)
    namen = dict(db.execute(select(Instrument.isin, Instrument.naam)).all())
    onbekend = [i for i in r.posities if i not in namen]
    meldingen = list(r.meldingen)
    if onbekend:
        zonder_waarde = [i for i in onbekend if r.waarden.get(i) is None]
        meldingen.insert(
            0,
            f"{len(onbekend)} positie(s) buiten de fondsenlijst zijn als overig bezit opgenomen; "
            "kies de beleggingscategorie"
            + (" en vul de waarde in" if zonder_waarde else " en controleer de waarde")
            + ".",
        )
    return InlezenUit(
        posities=[
            IngelezenRegel(isin=i, naam=namen[i], aantal=a)
            for i, a in r.posities.items()
            if i in namen
        ],
        overig=[
            OverigVoorstel(
                isin=i,
                omschrijving=r.omschrijvingen.get(i, i),
                aantal=r.posities[i],
                waarde_eur=r.waarden.get(i),
            )
            for i in onbekend
        ],
        meldingen=meldingen,
    )


@router.post(
    "/klanten/{klant_id}/evaluaties",
    response_model=EvaluatieUit,
    status_code=status.HTTP_201_CREATED,
)
def leg_evaluatie_vast(
    klant_id: int, invoer: EvaluatieIn, db: Db, adviseur: Ingelogd
) -> EvaluatieUit:
    klant = _eigen_klant(db, adviseur, klant_id)
    if invoer.datum > date.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "De datum mag niet in de toekomst liggen"
        )
    e = Evaluatie(
        klant_id=klant.id,
        datum=invoer.datum,
        uitkomst=invoer.uitkomst,
        notitie=(invoer.notitie or "").strip() or None,
        vastgelegd_door=adviseur.id,
    )
    db.add(e)
    db.flush()
    leg_vast(
        db,
        "evaluatie_vastgelegd",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
        details={"datum": invoer.datum.isoformat(), "uitkomst": invoer.uitkomst},
    )
    db.commit()
    return EvaluatieUit(
        id=e.id, datum=e.datum, uitkomst=e.uitkomst, notitie=e.notitie, door=adviseur.naam
    )


@router.get("/signalen", response_model=list[KlantSignalen])
def alle_signalen(db: Db, adviseur: Ingelogd) -> list[KlantSignalen]:
    """Signalen voor alle actieve klanten van deze adviseur, de meest dringende eerst."""
    vandaag = date.today()
    koersen, fondsen = _laatste_koersen(db), _fondsen(db)
    uit = []
    for klant in db.scalars(
        select(Klant).where(Klant.adviseur_id == adviseur.id, ~Klant.gearchiveerd)
    ):
        s = _toestand(db, klant, vandaag, koersen, fondsen)["signalen"]
        if s:
            uit.append(
                KlantSignalen(
                    klant_id=klant.id,
                    naam=klant.naam,
                    signalen=[SignaalUit(**asdict(x)) for x in s],
                )
            )
    volgorde = {"hoog": 0, "middel": 1, "laag": 2}
    return sorted(
        uit, key=lambda k: (min(volgorde[s.ernst] for s in k.signalen), k.naam.casefold())
    )
