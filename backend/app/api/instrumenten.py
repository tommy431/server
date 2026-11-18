from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.afhankelijkheden import Beheerder, Db, Ingelogd
from app.data.bronnen import BronFout, EcbBron, Koerspunt, YahooBron, lees_koersen_csv
from app.data.kwaliteit import controleer_reeks
from app.data.universum import UniversumFout, laad_universum
from app.data.verversen import Resultaat, sla_koersen_op, ververs_alles
from app.logboek import leg_vast
from app.models import Instrument, Koers

router = APIRouter(tags=["instrumenten en data"])
MAX_UPLOAD = 5 * 1024 * 1024


class InstrumentUit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    isin: str
    ticker: str
    naam: str
    categorie: str
    regio: str
    sector: str
    valuta: str
    lopende_kosten: float
    kosten_geverifieerd: bool
    uitkerend: bool
    valutarisico: str
    startdatum: date | None
    actief: bool


class KoersUit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    datum: date
    slot: float
    slot_gecorrigeerd: float
    bron: str


class BevindingUit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ernst: str
    code: str
    melding: str


class KostenIn(BaseModel):
    lopende_kosten: float = Field(ge=0, le=5)
    bron: str = Field(min_length=3, max_length=300)


class DataStatus(BaseModel):
    instrument_id: int
    isin: str
    naam: str
    lopende_kosten: float
    kosten_geverifieerd: bool
    kosten_gecontroleerd_op: date | None
    kosten_bron: str | None
    aantal_koersen: int
    eerste_koers: date | None
    laatste_koers: date | None
    bron: str | None
    bevindingen: list[BevindingUit]


class VerversResultaat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    onderdeel: str
    opgeslagen: int
    fout: str | None
    bevindingen: list[BevindingUit]


async def _lees_upload(bestand: UploadFile) -> str:
    inhoud = await bestand.read(MAX_UPLOAD + 1)
    if len(inhoud) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Bestand is groter dan 5 MB")
    try:
        return inhoud.decode("utf-8-sig")
    except UnicodeDecodeError as fout:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Bestand is geen UTF-8-tekst"
        ) from fout


def _instrument(db: Db, instrument_id: int) -> Instrument:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instrument niet gevonden")
    return instrument


@router.get("/instrumenten", response_model=list[InstrumentUit])
def lijst(
    db: Db,
    _: Ingelogd,
    categorie: str | None = None,
    regio: str | None = None,
    sector: str | None = None,
) -> list[Instrument]:
    vraag = select(Instrument).order_by(Instrument.categorie, Instrument.naam)
    for kolom, waarde in (
        (Instrument.categorie, categorie),
        (Instrument.regio, regio),
        (Instrument.sector, sector),
    ):
        if waarde is not None:
            vraag = vraag.where(kolom == waarde)
    return list(db.scalars(vraag))


@router.post("/instrumenten/import")
async def importeer_universum(db: Db, adviseur: Beheerder, bestand: UploadFile) -> dict:
    tekst = await _lees_upload(bestand)
    try:
        toegevoegd, bijgewerkt = laad_universum(db, tekst)
    except UniversumFout as fout:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, fout.fouten) from fout
    leg_vast(
        db,
        "universum_geimporteerd",
        adviseur_id=adviseur.id,
        entiteit="instrument",
        details={"toegevoegd": toegevoegd, "bijgewerkt": bijgewerkt},
    )
    db.commit()
    return {"toegevoegd": toegevoegd, "bijgewerkt": bijgewerkt}


@router.get("/instrumenten/{instrument_id}/koersen", response_model=list[KoersUit])
def koersen(
    instrument_id: int,
    db: Db,
    _: Ingelogd,
    vanaf: date | None = None,
    tot: date | None = None,
) -> list[Koers]:
    _instrument(db, instrument_id)
    vraag = select(Koers).where(Koers.instrument_id == instrument_id).order_by(Koers.datum)
    if vanaf:
        vraag = vraag.where(Koers.datum >= vanaf)
    if tot:
        vraag = vraag.where(Koers.datum <= tot)
    return list(db.scalars(vraag))


@router.post("/instrumenten/{instrument_id}/koersen/import")
async def importeer_koersen(
    instrument_id: int, db: Db, adviseur: Beheerder, bestand: UploadFile
) -> dict:
    instrument = _instrument(db, instrument_id)
    tekst = await _lees_upload(bestand)
    try:
        punten = lees_koersen_csv(tekst)
    except BronFout as fout:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fout)) from fout
    bevindingen = controleer_reeks(punten, date.today())
    fouten = [b.melding for b in bevindingen if b.ernst == "fout"]
    if fouten:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, fouten)
    sla_koersen_op(db, instrument, punten, "csv")
    leg_vast(
        db,
        "koersen_geimporteerd",
        adviseur_id=adviseur.id,
        entiteit="instrument",
        entiteit_id=instrument.id,
        details={"aantal": len(punten), "bestand": bestand.filename},
    )
    db.commit()
    return {
        "opgeslagen": len(punten),
        "bevindingen": [BevindingUit.model_validate(b) for b in bevindingen],
    }


@router.get("/data/status", response_model=list[DataStatus])
def data_status(db: Db, _: Ingelogd) -> list[DataStatus]:
    vandaag = date.today()
    uit = []
    for instrument in db.scalars(select(Instrument).order_by(Instrument.isin)):
        rijen = db.scalars(
            select(Koers).where(Koers.instrument_id == instrument.id).order_by(Koers.datum)
        ).all()
        punten = [Koerspunt(r.datum, r.slot, r.slot_gecorrigeerd) for r in rijen]
        uit.append(
            DataStatus(
                instrument_id=instrument.id,
                isin=instrument.isin,
                naam=instrument.naam,
                lopende_kosten=instrument.lopende_kosten,
                kosten_geverifieerd=instrument.kosten_geverifieerd,
                kosten_gecontroleerd_op=instrument.kosten_gecontroleerd_op,
                kosten_bron=instrument.kosten_bron,
                aantal_koersen=len(rijen),
                eerste_koers=rijen[0].datum if rijen else None,
                laatste_koers=rijen[-1].datum if rijen else None,
                bron=rijen[-1].bron if rijen else None,
                bevindingen=[
                    BevindingUit.model_validate(b) for b in controleer_reeks(punten, vandaag)
                ],
            )
        )
    return uit


@router.put("/instrumenten/{instrument_id}/kosten", response_model=DataStatus)
def kosten_controleren(
    instrument_id: int, invoer: KostenIn, db: Db, adviseur: Beheerder
) -> DataStatus:
    """Legt vast dat de lopende kosten zijn gecontroleerd tegen de fondsdocumentatie."""
    instrument = _instrument(db, instrument_id)
    oud = instrument.lopende_kosten
    instrument.lopende_kosten = round(invoer.lopende_kosten, 4)
    instrument.kosten_geverifieerd = True
    instrument.kosten_gecontroleerd_op = date.today()
    instrument.kosten_bron = invoer.bron.strip()
    leg_vast(
        db,
        "kosten_gecontroleerd",
        adviseur_id=adviseur.id,
        entiteit="instrument",
        entiteit_id=instrument.isin,
        details={"oud": oud, "nieuw": instrument.lopende_kosten, "bron": instrument.kosten_bron},
    )
    db.commit()
    return next(s for s in data_status(db, adviseur) if s.instrument_id == instrument.id)


@router.post("/data/verversen", response_model=list[VerversResultaat])
def verversen(db: Db, adviseur: Beheerder) -> list[Resultaat]:
    if not db.scalar(select(func.count()).select_from(Instrument)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Er zijn nog geen instrumenten geladen")
    resultaten = ververs_alles(db, YahooBron(), EcbBron())
    leg_vast(
        db,
        "data_ververst",
        adviseur_id=adviseur.id,
        details={
            "gelukt": sum(1 for r in resultaten if r.fout is None),
            "mislukt": [r.onderdeel for r in resultaten if r.fout],
        },
    )
    db.commit()
    return resultaten
