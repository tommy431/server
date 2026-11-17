from dataclasses import asdict
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.analyse import analyseer, jaren_terug, naar_euro, rente_index
from app.api.aannames import als_aannames, huidige
from app.api.afhankelijkheden import Db, Ingelogd
from app.api.klanten import _eigen_klant
from app.logboek import leg_vast
from app.models import (
    CATEGORIEEN,
    REGIOS,
    SECTOREN,
    Adviseur,
    Instrument,
    Klant,
    Klantprofiel,
    Koers,
    Modelallocatie,
    Portefeuille,
    Positie,
    Rente,
    Risicoprofiel,
    Wisselkoers,
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
from app.scenario import simuleer
from app.standaarden import STANDAARD_STRESS

router = APIRouter(tags=["portefeuille"])

# "wereld" en "breed" zijn geen regio of sector om uit te sluiten: ze betekenen juist spreiding.
UITSLUITBARE_REGIOS = tuple(r for r in REGIOS if r != "wereld")
UITSLUITBARE_SECTOREN = tuple(s for s in SECTOREN if s != "breed")

# De benchmark is de strategische asset allocatie van het risicoprofiel, ingevuld met één breed
# fonds per categorie. Voorbeeldkeuze; gekozen op lange koershistorie.
BENCHMARK_FONDSEN = {
    "aandelen": "IE00B4L5Y983",
    "obligaties": "IE00B3DKXQ41",
    "vastgoed": "IE00B1FZS350",
    "grondstoffen": "DE000A0H0728",
    "liquiditeiten": "LU0290358497",
}
# Risicovrij rendement voor de Sharpe-ratio: de kortlopende eurorente van de ECB. Is die niet
# opgehaald, dan het rendement van dit geldmarktfonds (na kosten, dus iets lager).
RISICOVRIJ_RENTE = "ECB-RENTE"
RISICOVRIJ_RENTE_NAAM = "de kortlopende eurorente van de ECB (€STR, vóór oktober 2019 EONIA)"
RISICOVRIJ_FONDS = "LU0290358497"


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


class AnalyseIn(PortefeuilleIn):
    # Korte fondshistorie aanvullen met een vergelijkbaar fonds (gesimuleerd, en zo gemarkeerd).
    verlengen: bool = False


class ScenarioIn(PortefeuilleIn):
    # Kosten bovenop de lopende fondskosten, bijv. advies- of beheerkosten, in procenten per jaar.
    overige_kosten_pct: float = Field(default=0.0, ge=0, le=5)
    # Benadering van de vermogensheffing (box 3) als percentage van het vermogen per jaar.
    belasting_pct: float = Field(default=0.0, ge=0, le=5)


class VersieIn(ScenarioIn):
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


class BenchmarkRegel(BaseModel):
    categorie: str
    naam: str
    gewicht: int  # hele procenten


class AnalyseUit(BaseModel):
    analyse: dict
    benchmark: list[BenchmarkRegel]
    risicovrij: str | None


class ScenarioUit(BaseModel):
    scenario: dict | None
    reden: str | None  # waarom er geen scenario is
    lopende_kosten_pct: float
    overige_kosten_pct: float
    belasting_pct: float = 0.0
    doel_in_koopkracht: bool = False
    gewichten: dict[str, float]  # per categorie, als fractie
    aannames: dict
    # Hypothetische zware crisis: directe waardeverandering van de mix en het verlies op de inleg.
    crisis_rendement: float | None = None
    crisis_verlies_eur: int | None = None


class VersieUit(ResultaatUit):
    id: int
    versie: int
    vastgelegd_op: datetime
    toelichting: str | None
    analyse: AnalyseUit | None
    scenario: ScenarioUit | None


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
        regels = {
            r.categorie: Band(r.streef, r.minimum, r.maximum)
            for r in db.scalars(
                select(Modelallocatie).where(
                    Modelallocatie.risicoprofiel_id == self.risicoprofiel.id
                )
            )
        }
        # Vaste volgorde: de database geeft de regels in willekeurige volgorde terug.
        self.banden = {c: regels[c] for c in CATEGORIEEN if c in regels}
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

    def vervangers(self, db: Db, posities: dict[str, int]) -> dict[str, str]:
        """Per fonds het actieve fonds met dezelfde categorie, regio en sector en de langste
        koershistorie, als die langer is dan die van het fonds zelf."""
        eerste = {
            iid: d
            for iid, d in db.execute(
                select(Koers.instrument_id, func.min(Koers.datum)).group_by(Koers.instrument_id)
            ).all()
        }
        start = {i.isin: eerste.get(i.id, date.max) for i in self.instrumenten.values()}
        # Alleen fondsen die de langste analyseperiode (10 jaar) niet zelf afdekken.
        grens = jaren_terug(date.today(), 10)
        uit = {}
        for isin in posities:
            if start[isin] <= grens:
                continue
            eigen = self.instrumenten[isin]
            kandidaten = [
                i
                for i in self.instrumenten.values()
                if i.isin != isin
                and i.actief
                and (i.categorie, i.regio, i.sector) == (eigen.categorie, eigen.regio, eigen.sector)
            ]
            if kandidaten:
                beste = min(kandidaten, key=lambda i: (start[i.isin], i.isin))
                if start[beste.isin] < start[isin]:
                    uit[isin] = beste.isin
        return uit

    def analyseer(self, db: Db, posities: dict[str, int], verlengen: bool = False) -> AnalyseUit:
        """Historische analyse van de posities tegen de benchmark van het risicoprofiel."""
        benchmark = {
            BENCHMARK_FONDSEN[c]: b.streef / 100
            for c, b in self.banden.items()
            if b.streef > 0 and BENCHMARK_FONDSEN.get(c) in self.instrumenten
        }
        if abs(sum(benchmark.values()) - 1) > 1e-9:
            benchmark = {}  # een onvolledige benchmark is geen eerlijke vergelijking
        rente = dict(db.execute(select(Rente.datum, Rente.waarde)).all())
        if rente:
            risicovrij, risicovrij_naam = RISICOVRIJ_RENTE, RISICOVRIJ_RENTE_NAAM
        elif RISICOVRIJ_FONDS in self.instrumenten:
            risicovrij = RISICOVRIJ_FONDS
            risicovrij_naam = f"het geldmarktfonds {self.instrumenten[RISICOVRIJ_FONDS].naam}"
        else:
            risicovrij = risicovrij_naam = None
        vervangers = self.vervangers(db, posities) if verlengen else {}
        nodig = set(posities) | set(benchmark) | set(vervangers.values())
        if risicovrij == RISICOVRIJ_FONDS:
            nodig.add(risicovrij)

        wissel: dict[str, dict] = {}
        reeksen = {}
        for isin in nodig:
            instrument = self.instrumenten[isin]
            reeks = dict(
                db.execute(
                    select(Koers.datum, Koers.slot_gecorrigeerd).where(
                        Koers.instrument_id == instrument.id
                    )
                ).all()
            )
            valuta = instrument.valuta
            if valuta != "EUR" and valuta.upper() not in wissel:
                wissel[valuta.upper()] = dict(
                    db.execute(
                        select(Wisselkoers.datum, Wisselkoers.koers).where(
                            Wisselkoers.valuta == valuta.upper()
                        )
                    ).all()
                )
            try:
                reeksen[isin] = naar_euro(reeks, valuta, wissel.get(valuta.upper()))
            except ValueError:
                reeksen[isin] = {}
        if risicovrij == RISICOVRIJ_RENTE:
            reeksen[RISICOVRIJ_RENTE] = rente_index(rente)
        uitkomst = analyseer(
            {isin: gewicht / 10_000 for isin, gewicht in posities.items()},
            reeksen,
            {isin: i.naam for isin, i in self.instrumenten.items()},
            benchmark=benchmark or None,
            risicovrij=risicovrij,
            vervangers=vervangers,
        )
        per_fonds = {v: k for k, v in BENCHMARK_FONDSEN.items()}
        return AnalyseUit(
            analyse=uitkomst.als_dict(),
            benchmark=[
                BenchmarkRegel(
                    categorie=per_fonds[isin],
                    naam=self.instrumenten[isin].naam,
                    gewicht=round(gewicht * 100),
                )
                for isin, gewicht in benchmark.items()
            ],
            risicovrij=risicovrij_naam,
        )

    def scenario(
        self, db: Db, d: Doorrekening, overige_kosten_pct: float, belasting_pct: float = 0.0
    ) -> tuple[ScenarioUit, int]:
        """Monte Carlo-scenario's voor de verdeling naar categorie, met de huidige aannames."""
        rij = huidige(db)
        gewichten = {c: g / 10_000 for c, g in d.per_categorie.items() if g}
        p = self.profiel
        uit = ScenarioUit(
            scenario=None,
            reden=None,
            lopende_kosten_pct=d.kosten_pct,
            overige_kosten_pct=overige_kosten_pct,
            belasting_pct=belasting_pct,
            doel_in_koopkracht=p.doel_in_koopkracht,
            gewichten=gewichten,
            aannames={
                "id": rij.id,
                "bron": rij.bron,
                "peildatum": rij.peildatum.isoformat(),
                "categorieen": rij.categorieen,
                "correlaties": rij.correlaties,
                "inflatie": rij.inflatie,
                "stress": rij.stress or STANDAARD_STRESS,
            },
        )
        schokken = rij.stress or STANDAARD_STRESS
        uit.crisis_rendement = sum(g * schokken.get(c, 0.0) for c, g in gewichten.items())
        uit.crisis_verlies_eur = round(-uit.crisis_rendement * p.inleg_eur)
        if d.totaal != 10_000:
            uit.reden = "De gewichten tellen niet op tot 100%"
            return uit, rij.id
        uit.scenario = simuleer(
            gewichten,
            als_aannames(rij),
            horizon_jaren=p.horizon_jaren,
            inleg=p.inleg_eur,
            storting_per_maand=p.storting_per_maand_eur,
            kosten_pct=d.kosten_pct + overige_kosten_pct,
            belasting_pct=belasting_pct,
            doelvermogen=p.doelvermogen_eur,
        ).als_dict()
        return uit, rij.id

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


@router.post("/klanten/{klant_id}/portefeuille/analyse", response_model=AnalyseUit)
def analyse(klant_id: int, invoer: AnalyseIn, db: Db, adviseur: Ingelogd) -> AnalyseUit:
    """Historische analyse van een portefeuille. Slaat niets op."""
    ctx = _Context(db, adviseur, klant_id)
    uitsluitingen = ctx.uitsluitingen(invoer.uitsluitingen)
    posities = _posities(invoer.posities)
    d = ctx.reken_door(posities, uitsluitingen)
    blokkerend = [b.melding for b in d.fouten if b.code != "uitgesloten"]
    if blokkerend:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, blokkerend)
    return ctx.analyseer(db, posities, invoer.verlengen)


@router.post("/klanten/{klant_id}/portefeuille/scenario", response_model=ScenarioUit)
def scenario(klant_id: int, invoer: ScenarioIn, db: Db, adviseur: Ingelogd) -> ScenarioUit:
    """Scenario's voor de vermogensontwikkeling. Slaat niets op."""
    ctx = _Context(db, adviseur, klant_id)
    uitsluitingen = ctx.uitsluitingen(invoer.uitsluitingen)
    posities = _posities(invoer.posities)
    d = ctx.reken_door(posities, uitsluitingen)
    blokkerend = [b.melding for b in d.fouten if b.code != "uitgesloten"]
    if blokkerend:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, blokkerend)
    return ctx.scenario(db, d, invoer.overige_kosten_pct, invoer.belasting_pct)[0]


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
        analyse=p.analyse,
        scenario=p.scenario,
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

    scenario_uit, aannameset_id = ctx.scenario(
        db, d, invoer.overige_kosten_pct, invoer.belasting_pct
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
        analyse=ctx.analyseer(db, posities).model_dump(),
        scenario=scenario_uit.model_dump(),
        aannameset_id=aannameset_id,
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
