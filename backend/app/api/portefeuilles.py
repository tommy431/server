from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.api.klanten import _eigen_klant
from app.logboek import leg_vast
from app.models import (
    REGIOS,
    SECTOREN,
    Adviseur,
    Instrument,
    Klant,
    Klantprofiel,
    Modelallocatie,
    Portefeuille,
    Positie,
    Risicoprofiel,
)
from app.portefeuille import (
    BEPERKINGEN,
    Band,
    Doorrekening,
    Fonds,
    Uitsluiting,
    maak_voorstel,
    reken_door,
)

router = APIRouter(tags=["portefeuille"])

# "wereld" en "breed" zijn geen regio of sector om uit te sluiten: ze betekenen juist spreiding.
UITSLUITBARE_REGIOS = tuple(r for r in REGIOS if r != "wereld")
UITSLUITBARE_SECTOREN = tuple(s for s in SECTOREN if s != "breed")


class UitsluitingIn(BaseModel):
    soort: Literal["instrument", "sector", "regio"]
    waarde: str
    reden: str = Field(default="", max_length=300)


class PositieIn(BaseModel):
    isin: str
    gewicht: int  # basispunten; 10000 = 100%


class VoorstelIn(BaseModel):
    uitsluitingen: list[UitsluitingIn] = []


class PortefeuilleIn(BaseModel):
    posities: list[PositieIn]
    uitsluitingen: list[UitsluitingIn] = []


class VersieIn(PortefeuilleIn):
    toelichting: str | None = Field(default=None, max_length=2000)


class BevindingUit(BaseModel):
    ernst: str
    code: str
    melding: str


class DoorrekeningUit(BaseModel):
    totaal: int
    per_categorie: dict[str, int]
    per_regio: dict[str, int]
    per_sector: dict[str, int]
    zakelijke_waarden: int
    grootste_positie: int
    aantal_instrumenten: int
    kosten_pct: float
    kosten_per_positie: dict[str, float]
    kosten_eur_per_jaar: int
    bevindingen: list[BevindingUit]


class BandUit(BaseModel):
    streef: int
    minimum: int
    maximum: int


class ResultaatUit(BaseModel):
    risicoprofiel: str
    klantprofiel_versie: int
    banden: dict[str, BandUit]
    beperkingen: dict[str, int]
    posities: list[PositieIn]
    uitsluitingen: list[UitsluitingIn]
    doorrekening: DoorrekeningUit


class VersieUit(ResultaatUit):
    id: int
    versie: int
    vastgelegd_op: datetime
    toelichting: str | None


class _Context:
    """Alles wat nodig is om voor een klant een portefeuille door te rekenen."""

    def __init__(self, db: Db, adviseur: Adviseur, klant_id: int) -> None:
        self.klant: Klant = _eigen_klant(db, adviseur, klant_id)
        self.profiel: Klantprofiel | None = db.scalar(
            select(Klantprofiel)
            .where(Klantprofiel.klant_id == klant_id)
            .order_by(Klantprofiel.versie.desc())
            .limit(1)
        )
        if self.profiel is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Leg eerst een klantprofiel vast voor deze klant"
            )
        self.risicoprofiel: Risicoprofiel = db.get(Risicoprofiel, self.profiel.risicoprofiel_id)
        self.banden = {
            r.categorie: Band(r.streef, r.minimum, r.maximum)
            for r in db.scalars(
                select(Modelallocatie).where(
                    Modelallocatie.risicoprofiel_id == self.risicoprofiel.id
                )
            )
        }
        self.instrumenten = {i.isin: i for i in db.scalars(select(Instrument))}
        self.fondsen = {
            i.isin: Fonds(
                isin=i.isin,
                naam=i.naam,
                categorie=i.categorie,
                regio=i.regio,
                sector=i.sector,
                lopende_kosten=i.lopende_kosten,
                kosten_geverifieerd=i.kosten_geverifieerd,
                actief=i.actief,
            )
            for i in self.instrumenten.values()
        }

    def uitsluitingen(self, invoer: list[UitsluitingIn]) -> list[Uitsluiting]:
        fouten = []
        for u in invoer:
            toegestaan = {
                "instrument": self.fondsen,
                "sector": UITSLUITBARE_SECTOREN,
                "regio": UITSLUITBARE_REGIOS,
            }[u.soort]
            if u.waarde not in toegestaan:
                fouten.append(f"Onbekende uitsluiting: {u.soort} '{u.waarde}'")
        if len({(u.soort, u.waarde) for u in invoer}) != len(invoer):
            fouten.append("Een uitsluiting komt dubbel voor")
        if fouten:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, fouten)
        return [Uitsluiting(u.soort, u.waarde, u.reden.strip()) for u in invoer]

    def reken_door(
        self, posities: dict[str, int], uitsluitingen: list[Uitsluiting]
    ) -> Doorrekening:
        return reken_door(
            posities,
            self.fondsen,
            self.banden,
            uitsluitingen,
            klant_duurzaamheid=self.profiel.duurzaamheid,
            klant_uitsluitingen=tuple(self.profiel.uitsluitingen),
        )

    def doorrekening_uit(self, d: Doorrekening | dict) -> DoorrekeningUit:
        gegevens = d.als_dict() if isinstance(d, Doorrekening) else d
        return DoorrekeningUit(
            **gegevens,
            kosten_eur_per_jaar=round(self.profiel.inleg_eur * gegevens["kosten_pct"] / 100),
        )

    def resultaat(
        self, posities: dict[str, int], uitsluitingen: list[Uitsluiting], d: Doorrekening
    ) -> ResultaatUit:
        return ResultaatUit(
            risicoprofiel=self.risicoprofiel.code,
            klantprofiel_versie=self.profiel.versie,
            banden={c: BandUit(**asdict(b)) for c, b in self.banden.items()},
            beperkingen=BEPERKINGEN,
            posities=[PositieIn(isin=i, gewicht=g) for i, g in posities.items()],
            uitsluitingen=[UitsluitingIn(**asdict(u)) for u in uitsluitingen],
            doorrekening=self.doorrekening_uit(d),
        )


def _posities(invoer: list[PositieIn]) -> dict[str, int]:
    if len({p.isin for p in invoer}) != len(invoer):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Een instrument komt dubbel voor"
        )
    return {p.isin: p.gewicht for p in invoer}


@router.post("/klanten/{klant_id}/portefeuille/voorstel", response_model=ResultaatUit)
def voorstel(klant_id: int, invoer: VoorstelIn, db: Db, adviseur: Ingelogd) -> ResultaatUit:
    """Stelt een startportefeuille voor op basis van het risicoprofiel. Slaat niets op."""
    ctx = _Context(db, adviseur, klant_id)
    uitsluitingen = ctx.uitsluitingen(invoer.uitsluitingen)
    posities, opmerkingen = maak_voorstel(
        ctx.banden, ctx.fondsen, uitsluitingen, duurzaam=ctx.profiel.duurzaamheid == "sterk"
    )
    d = ctx.reken_door(posities, uitsluitingen)
    d.bevindingen[:0] = opmerkingen
    return ctx.resultaat(posities, uitsluitingen, d)


@router.post("/klanten/{klant_id}/portefeuille/doorrekenen", response_model=ResultaatUit)
def doorrekenen(klant_id: int, invoer: PortefeuilleIn, db: Db, adviseur: Ingelogd) -> ResultaatUit:
    """Rekent een portefeuille door zonder iets op te slaan."""
    ctx = _Context(db, adviseur, klant_id)
    uitsluitingen = ctx.uitsluitingen(invoer.uitsluitingen)
    posities = _posities(invoer.posities)
    return ctx.resultaat(posities, uitsluitingen, ctx.reken_door(posities, uitsluitingen))


def _versie_uit(
    db: Db, ctx: _Context, p: Portefeuille, profielversies: dict[int, int]
) -> VersieUit:
    per_id = {i.id: i.isin for i in ctx.instrumenten.values()}
    posities = db.scalars(
        select(Positie).where(Positie.portefeuille_id == p.id).order_by(Positie.gewicht.desc())
    )
    return VersieUit(
        id=p.id,
        versie=p.versie,
        vastgelegd_op=p.vastgelegd_op,
        toelichting=p.toelichting,
        risicoprofiel=p.risicoprofiel,
        klantprofiel_versie=profielversies[p.klantprofiel_id],
        banden=p.banden,
        beperkingen=BEPERKINGEN,
        posities=[PositieIn(isin=per_id[x.instrument_id], gewicht=x.gewicht) for x in posities],
        uitsluitingen=p.uitsluitingen,
        doorrekening=ctx.doorrekening_uit(p.doorrekening),
    )


@router.get("/klanten/{klant_id}/portefeuille/versies", response_model=list[VersieUit])
def versies(klant_id: int, db: Db, adviseur: Ingelogd) -> list[VersieUit]:
    _eigen_klant(db, adviseur, klant_id)
    rijen = db.scalars(
        select(Portefeuille)
        .where(Portefeuille.klant_id == klant_id)
        .order_by(Portefeuille.versie.desc())
    ).all()
    if not rijen:
        return []
    ctx = _Context(db, adviseur, klant_id)
    profielversies = dict(
        db.execute(
            select(Klantprofiel.id, Klantprofiel.versie).where(Klantprofiel.klant_id == klant_id)
        ).all()
    )
    return [_versie_uit(db, ctx, p, profielversies) for p in rijen]


@router.post(
    "/klanten/{klant_id}/portefeuille/versies",
    response_model=VersieUit,
    status_code=status.HTTP_201_CREATED,
)
def leg_vast_versie(klant_id: int, invoer: VersieIn, db: Db, adviseur: Ingelogd) -> VersieUit:
    """Legt een nieuwe versie van de portefeuille vast; eerdere versies blijven bewaard."""
    ctx = _Context(db, adviseur, klant_id)
    if ctx.klant.gearchiveerd:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is gearchiveerd")
    uitsluitingen = ctx.uitsluitingen(invoer.uitsluitingen)
    posities = _posities(invoer.posities)
    d = ctx.reken_door(posities, uitsluitingen)
    if d.fouten:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, [b.melding for b in d.fouten])
    toelichting = (invoer.toelichting or "").strip() or None
    if d.afwijkingen and not toelichting:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ["De portefeuille wijkt af van het risicoprofiel of de beperkingen; licht toe waarom:"]
            + [b.melding for b in d.afwijkingen],
        )

    vorige = db.scalar(
        select(func.max(Portefeuille.versie)).where(Portefeuille.klant_id == klant_id)
    )
    portefeuille = Portefeuille(
        klant_id=klant_id,
        versie=(vorige or 0) + 1,
        vastgelegd_door=adviseur.id,
        klantprofiel_id=ctx.profiel.id,
        risicoprofiel=ctx.risicoprofiel.code,
        banden={c: asdict(b) for c, b in ctx.banden.items()},
        uitsluitingen=[asdict(u) for u in uitsluitingen],
        doorrekening=d.als_dict(),
        toelichting=toelichting,
    )
    db.add(portefeuille)
    db.flush()
    for isin, gewicht in posities.items():
        db.add(
            Positie(
                portefeuille_id=portefeuille.id,
                instrument_id=ctx.instrumenten[isin].id,
                gewicht=gewicht,
            )
        )
    leg_vast(
        db,
        "portefeuille_vastgelegd",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant_id,
        details={
            "versie": portefeuille.versie,
            "risicoprofiel": ctx.risicoprofiel.code,
            "afwijkingen": [b.code for b in d.afwijkingen],
        },
    )
    db.commit()
    return _versie_uit(db, ctx, portefeuille, {ctx.profiel.id: ctx.profiel.versie})
