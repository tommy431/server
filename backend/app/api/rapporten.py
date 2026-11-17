import hashlib
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.api.klanten import _eigen_klant
from app.logboek import leg_vast
from app.models import Adviseur, Instrument, Klant, Klantprofiel, Portefeuille, Positie, Rapport
from app.rapport import maak_rapport

router = APIRouter(tags=["rapporten"])

DATABRON = (
    "Koersen: Yahoo Finance (dagkoersen, gecorrigeerd voor dividend). Wisselkoersen en "
    "risicovrije rente: Europese Centrale Bank."
)


class RapportUit(BaseModel):
    id: int
    portefeuille_versie: int
    volgnummer: int
    opgesteld_op: datetime
    opgesteld_door: str
    sha256: str
    grootte: int
    beschikbaar: bool


def rapportgegevens(db: Db, klant: Klant, portefeuille: Portefeuille, opgesteld_op: date) -> dict:
    """Stelt alle gegevens voor het rapport samen uit de momentopname van de portefeuille."""
    profiel = db.get(Klantprofiel, portefeuille.klantprofiel_id)
    adviseur = db.get(Adviseur, portefeuille.vastgelegd_door)
    instrumenten = {i.id: i for i in db.scalars(select(Instrument))}
    kosten = portefeuille.doorrekening.get("kosten_per_positie", {})
    posities = []
    for pos in db.scalars(select(Positie).where(Positie.portefeuille_id == portefeuille.id)):
        i = instrumenten[pos.instrument_id]
        posities.append(
            {
                "isin": i.isin,
                "naam": i.naam,
                "categorie": i.categorie,
                "regio": i.regio,
                "sector": i.sector,
                "gewicht": pos.gewicht,
                # Kosten uit de momentopname: bijdrage in procentpunten terug naar kosten van het fonds.
                "lopende_kosten": kosten.get(i.isin, i.lopende_kosten * pos.gewicht / 10_000)
                * 10_000
                / pos.gewicht,
            }
        )
    waarschuwingen = []
    if (
        (portefeuille.scenario or {})
        .get("aannames", {})
        .get("bron", "")
        .startswith("Voorbeeldwaarden")
    ):
        waarschuwingen.append(
            "Concept: de scenario's in dit rapport rekenen met voorbeeldaannames zonder gepubliceerde "
            "bron. Niet aan de klant verstrekken voordat de aannames zijn vervangen."
        )
    if any(
        b["code"] == "kosten_ongeverifieerd"
        for b in portefeuille.doorrekening.get("bevindingen", [])
    ):
        waarschuwingen.append(
            "Concept: de lopende kosten van een of meer fondsen zijn niet gecontroleerd tegen de "
            "fondsdocumentatie."
        )
    return {
        "klant": {"naam": klant.naam},
        "adviseur": adviseur.naam,
        "opgesteld_op": opgesteld_op,
        "profiel": {
            "versie": profiel.versie,
            "doel": profiel.doel,
            "horizon_jaren": profiel.horizon_jaren,
            "inleg_eur": profiel.inleg_eur,
            "storting_per_maand_eur": profiel.storting_per_maand_eur,
            "doelvermogen_eur": profiel.doelvermogen_eur,
            "doel_in_koopkracht": profiel.doel_in_koopkracht,
            "score_bereidheid": profiel.score_bereidheid,
            "score_capaciteit": profiel.score_capaciteit,
            "score_kennis": profiel.score_kennis,
            "duurzaamheid": profiel.duurzaamheid,
            "uitsluitingen": profiel.uitsluitingen,
            "afgeleid_risicoprofiel": _code(db, profiel.afgeleid_risicoprofiel_id),
            "risicoprofiel": _code(db, profiel.risicoprofiel_id),
            "bepalende_factor": profiel.bepalende_factor,
            "afwijking_toelichting": profiel.afwijking_toelichting,
        },
        "portefeuille": {
            "versie": portefeuille.versie,
            "vastgelegd_op": portefeuille.vastgelegd_op.date().isoformat(),
            "risicoprofiel": portefeuille.risicoprofiel,
            "banden": portefeuille.banden,
            "uitsluitingen": portefeuille.uitsluitingen,
            "doorrekening": portefeuille.doorrekening,
            "analyse": portefeuille.analyse,
            "scenario": portefeuille.scenario,
            "toelichting": portefeuille.toelichting,
        },
        "posities": posities,
        "fondsnamen": {i.isin: i.naam for i in instrumenten.values()},
        "waarschuwingen_vooraf": waarschuwingen,
        "databron": DATABRON,
    }


def _code(db: Db, risicoprofiel_id: int) -> str:
    from app.models import Risicoprofiel

    return db.get(Risicoprofiel, risicoprofiel_id).code


def _uit(r: Rapport, versie: int, namen: dict[int, str]) -> RapportUit:
    return RapportUit(
        id=r.id,
        portefeuille_versie=versie,
        volgnummer=r.volgnummer,
        opgesteld_op=r.opgesteld_op,
        opgesteld_door=namen.get(r.opgesteld_door, ""),
        sha256=r.sha256,
        grootte=r.grootte,
        beschikbaar=r.pdf is not None,
    )


def _adviseursnamen(db: Db) -> dict[int, str]:
    return dict(db.execute(select(Adviseur.id, Adviseur.naam)).all())


@router.post(
    "/klanten/{klant_id}/portefeuille/versies/{versie}/rapporten",
    response_model=RapportUit,
    status_code=status.HTTP_201_CREATED,
)
def maak(klant_id: int, versie: int, db: Db, adviseur: Ingelogd) -> RapportUit:
    """Stelt een adviesrapport op bij een vastgelegde portefeuilleversie en bewaart het."""
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.geanonimiseerd_op is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is geanonimiseerd")
    portefeuille = db.scalar(
        select(Portefeuille).where(Portefeuille.klant_id == klant_id, Portefeuille.versie == versie)
    )
    if portefeuille is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portefeuilleversie niet gevonden")
    pdf = maak_rapport(rapportgegevens(db, klant, portefeuille, date.today()))
    vorige = db.scalar(
        select(func.max(Rapport.volgnummer)).where(Rapport.portefeuille_id == portefeuille.id)
    )
    rapport = Rapport(
        portefeuille_id=portefeuille.id,
        volgnummer=(vorige or 0) + 1,
        opgesteld_door=adviseur.id,
        sha256=hashlib.sha256(pdf).hexdigest(),
        grootte=len(pdf),
        pdf=pdf,
    )
    db.add(rapport)
    db.flush()
    leg_vast(
        db,
        "rapport_opgesteld",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant_id,
        details={"versie": versie, "rapport": rapport.id, "sha256": rapport.sha256},
    )
    db.commit()
    return _uit(rapport, versie, _adviseursnamen(db))


@router.get("/klanten/{klant_id}/rapporten", response_model=list[RapportUit])
def lijst(klant_id: int, db: Db, adviseur: Ingelogd) -> list[RapportUit]:
    _eigen_klant(db, adviseur, klant_id)
    rijen = db.execute(
        select(Rapport, Portefeuille.versie)
        .join(Portefeuille, Rapport.portefeuille_id == Portefeuille.id)
        .where(Portefeuille.klant_id == klant_id)
        .order_by(Rapport.opgesteld_op.desc(), Rapport.id.desc())
    ).all()
    namen = _adviseursnamen(db)
    return [_uit(r, v, namen) for r, v in rijen]


@router.get("/klanten/{klant_id}/rapporten/{rapport_id}/pdf")
def download(klant_id: int, rapport_id: int, db: Db, adviseur: Ingelogd) -> Response:
    klant = _eigen_klant(db, adviseur, klant_id)
    rij = db.execute(
        select(Rapport, Portefeuille.versie)
        .join(Portefeuille, Rapport.portefeuille_id == Portefeuille.id)
        .where(Rapport.id == rapport_id, Portefeuille.klant_id == klant.id)
    ).first()
    if rij is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rapport niet gevonden")
    rapport, versie = rij
    if rapport.pdf is None:
        raise HTTPException(status.HTTP_410_GONE, "Dit rapport is verwijderd bij het anonimiseren")
    leg_vast(
        db,
        "rapport_gedownload",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
        details={"rapport": rapport.id},
    )
    db.commit()
    bestandsnaam = f"adviesrapport-klant-{klant.id}-versie-{versie}-{rapport.volgnummer}.pdf"
    return Response(
        content=rapport.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{bestandsnaam}"',
            "Cache-Control": "no-store",
        },
    )


def verwijder_pdfs(db: Db, klant_id: int) -> None:
    """Wist de PDF's van een klant (bij anonimiseren); de aanroeper commit."""
    for rapport in db.scalars(
        select(Rapport)
        .join(Portefeuille, Rapport.portefeuille_id == Portefeuille.id)
        .where(Portefeuille.klant_id == klant_id)
    ):
        rapport.pdf = None
        rapport.verwijderd_op = datetime.now(UTC)
