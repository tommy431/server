from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.api.klanten import _eigen_klant
from app.bezitimport import MAX_TEKENS, lees_bezit
from app.logboek import leg_vast
from app.models import (
    Adviseur,
    Bezitsopgave,
    Evaluatie,
    Instrument,
    Klant,
    Klantprofiel,
    Koers,
    Portefeuille,
    Positie,
)
from app.opvolging import herbalanceer, signalen, waardeer
from app.portefeuille import Fonds

router = APIRouter(tags=["opvolging"])


class BezitRegel(BaseModel):
    isin: str
    aantal: float = Field(gt=0, le=1e9)


class BezitIn(BaseModel):
    peildatum: date
    posities: list[BezitRegel]
    kas_eur: float = Field(ge=0, le=1e10)


class InlezenIn(BaseModel):
    tekst: str = Field(max_length=MAX_TEKENS)


class IngelezenRegel(BaseModel):
    isin: str
    naam: str
    aantal: float


class InlezenUit(BaseModel):
    posities: list[IngelezenRegel]
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
def leg_bezit_vast(klant_id: int, invoer: BezitIn, db: Db, adviseur: Ingelogd) -> dict:
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
    opgave = Bezitsopgave(
        klant_id=klant.id,
        peildatum=invoer.peildatum,
        posities={p.isin: p.aantal for p in invoer.posities},
        kas_eur=invoer.kas_eur,
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
        details={"peildatum": invoer.peildatum.isoformat(), "fondsen": len(invoer.posities)},
    )
    db.commit()
    return {"id": opgave.id}


@router.post("/klanten/{klant_id}/bezit/inlezen", response_model=InlezenUit)
def bezit_inlezen(klant_id: int, invoer: InlezenIn, db: Db, adviseur: Ingelogd) -> InlezenUit:
    """Leest een depotoverzicht (CSV) voor controle in het formulier. Slaat niets op."""
    _eigen_klant(db, adviseur, klant_id)
    r = lees_bezit(invoer.tekst)
    namen = dict(db.execute(select(Instrument.isin, Instrument.naam)).all())
    onbekend = [i for i in r.posities if i not in namen]
    meldingen = list(r.meldingen)
    if onbekend:
        meldingen.insert(
            0,
            "Niet in de fondsenlijst, dus niet overgenomen: "
            + ", ".join(onbekend)
            + ". Laat deze fondsen eerst toevoegen of neem ze buiten het overzicht op.",
        )
    return InlezenUit(
        posities=[
            IngelezenRegel(isin=i, naam=namen[i], aantal=a)
            for i, a in r.posities.items()
            if i in namen
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
