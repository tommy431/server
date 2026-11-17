from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.api.afhankelijkheden import Db, Ingelogd
from app.logboek import leg_vast
from app.models import (
    CATEGORIEEN,
    Adviseur,
    Klant,
    Klantprofiel,
    Modelallocatie,
    Portefeuille,
    Risicoprofiel,
)
from app.profiel import (
    DIMENSIES,
    LAGE_KENNIS_GRENS,
    VRAGEN,
    VRAGENLIJST_VERSIE,
    bereken,
    controleer_allocatie,
)

router = APIRouter(tags=["klanten en profielen"])

# Adviesdossiers moeten minimaal vijf jaar na het advies bewaard blijven (MiFID II, art. 16 lid 6
# en art. 72 van Gedelegeerde Verordening 2017/565). Tot die tijd geldt het recht op
# verwijdering uit de AVG niet voor het dossier (art. 17 lid 3 onder b AVG).
BEWAARTERMIJN_JAREN = 5
VERWIJDERD = "[verwijderd]"

UITSLUITINGEN = ("wapens", "tabak", "fossiele-brandstoffen", "gokken", "alcohol", "kernenergie")


class KlantIn(BaseModel):
    naam: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    geboortedatum: date | None = None


class ProfielIn(BaseModel):
    doel: str = Field(min_length=1, max_length=500)
    horizon_jaren: int = Field(ge=1, le=60)
    inleg_eur: int = Field(ge=0, le=1_000_000_000)
    storting_per_maand_eur: int = Field(ge=0, le=10_000_000)
    doelvermogen_eur: int | None = Field(default=None, gt=0, le=2_000_000_000)
    doel_in_koopkracht: bool = False
    antwoorden: dict[str, int]
    duurzaamheid: Literal["geen", "enigszins", "sterk"]
    uitsluitingen: list[Literal[UITSLUITINGEN]] = []
    duurzaamheid_toelichting: str | None = Field(default=None, max_length=1000)
    # Leeg laten om het afgeleide profiel te gebruiken; alleen een defensiever profiel is toegestaan.
    gekozen_risicoprofiel: str | None = None
    afwijking_toelichting: str | None = Field(default=None, max_length=1000)


class ProfielUit(BaseModel):
    id: int
    versie: int
    vastgelegd_op: datetime
    doel: str
    horizon_jaren: int
    inleg_eur: int
    storting_per_maand_eur: int
    doelvermogen_eur: int | None
    doel_in_koopkracht: bool
    vragenlijst_versie: int
    antwoorden: dict[str, int]
    score_bereidheid: int
    score_capaciteit: int
    score_kennis: int
    lage_kennis: bool
    duurzaamheid: str
    uitsluitingen: list[str]
    duurzaamheid_toelichting: str | None
    afgeleid_risicoprofiel: str
    bepalende_factor: str
    risicoprofiel: str
    afwijking_toelichting: str | None


class KlantUit(BaseModel):
    id: int
    naam: str
    email: str | None
    geboortedatum: date | None
    gearchiveerd: bool
    geanonimiseerd_op: datetime | None
    bewaren_tot: date | None  # einde bewaartermijn van het laatste advies
    aangemaakt_op: datetime
    huidig_profiel: ProfielUit | None


class AllocatieRegel(BaseModel):
    categorie: str
    streef: int
    minimum: int
    maximum: int


class RisicoprofielUit(BaseModel):
    code: str
    naam: str
    niveau: int
    allocatie: list[AllocatieRegel]


def _eigen_klant(db: Db, adviseur: Adviseur, klant_id: int) -> Klant:
    klant = db.get(Klant, klant_id)
    # Ook bij een klant van een andere adviseur 404, zodat het bestaan niet uitlekt.
    if klant is None or klant.adviseur_id != adviseur.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Klant niet gevonden")
    return klant


def _profiel_uit(profiel: Klantprofiel, codes: dict[int, str]) -> ProfielUit:
    return ProfielUit(
        id=profiel.id,
        versie=profiel.versie,
        vastgelegd_op=profiel.vastgelegd_op,
        doel=profiel.doel,
        horizon_jaren=profiel.horizon_jaren,
        inleg_eur=profiel.inleg_eur,
        storting_per_maand_eur=profiel.storting_per_maand_eur,
        doelvermogen_eur=profiel.doelvermogen_eur,
        doel_in_koopkracht=profiel.doel_in_koopkracht,
        vragenlijst_versie=profiel.vragenlijst_versie,
        antwoorden=profiel.antwoorden,
        score_bereidheid=profiel.score_bereidheid,
        score_capaciteit=profiel.score_capaciteit,
        score_kennis=profiel.score_kennis,
        lage_kennis=profiel.score_kennis < LAGE_KENNIS_GRENS,
        duurzaamheid=profiel.duurzaamheid,
        uitsluitingen=profiel.uitsluitingen,
        duurzaamheid_toelichting=profiel.duurzaamheid_toelichting,
        afgeleid_risicoprofiel=codes[profiel.afgeleid_risicoprofiel_id],
        bepalende_factor=profiel.bepalende_factor,
        risicoprofiel=codes[profiel.risicoprofiel_id],
        afwijking_toelichting=profiel.afwijking_toelichting,
    )


def _profielcodes(db: Db) -> dict[int, str]:
    return {p.id: p.code for p in db.scalars(select(Risicoprofiel))}


def _klant_uit(db: Db, klant: Klant, codes: dict[int, str]) -> KlantUit:
    huidig = db.scalar(
        select(Klantprofiel)
        .where(Klantprofiel.klant_id == klant.id)
        .order_by(Klantprofiel.versie.desc())
        .limit(1)
    )
    return KlantUit(
        id=klant.id,
        naam=klant.naam,
        email=klant.email,
        geboortedatum=date.fromisoformat(klant.geboortedatum) if klant.geboortedatum else None,
        gearchiveerd=klant.gearchiveerd,
        geanonimiseerd_op=klant.geanonimiseerd_op,
        bewaren_tot=_bewaren_tot(db, klant),
        aangemaakt_op=klant.aangemaakt_op,
        huidig_profiel=_profiel_uit(huidig, codes) if huidig else None,
    )


def _bewaren_tot(db: Db, klant: Klant) -> date | None:
    laatste = db.scalar(
        select(func.max(Portefeuille.vastgelegd_op)).where(Portefeuille.klant_id == klant.id)
    )
    if laatste is None:
        return None
    dag = laatste.date()
    try:
        return dag.replace(year=dag.year + BEWAARTERMIJN_JAREN)
    except ValueError:  # 29 februari
        return dag.replace(year=dag.year + BEWAARTERMIJN_JAREN, day=28)


def _vul_klant(klant: Klant, gegevens: KlantIn) -> None:
    klant.naam = gegevens.naam.strip()
    klant.email = gegevens.email.lower() if gegevens.email else None
    klant.geboortedatum = gegevens.geboortedatum.isoformat() if gegevens.geboortedatum else None


# --- vragenlijst en risicoprofielen ----------------------------------------------------


@router.get("/vragenlijst")
def vragenlijst(_: Ingelogd) -> dict:
    return {
        "versie": VRAGENLIJST_VERSIE,
        "dimensies": DIMENSIES,
        "vragen": VRAGEN,
        "uitsluitingen": UITSLUITINGEN,
    }


class UitkomstIn(BaseModel):
    antwoorden: dict[str, int]
    horizon_jaren: int = Field(ge=1, le=60)


class UitkomstUit(BaseModel):
    score_bereidheid: int
    score_capaciteit: int
    score_kennis: int
    lage_kennis: bool
    risicoprofiel: str
    bepalende_factor: str


@router.post("/vragenlijst/uitkomst", response_model=UitkomstUit)
def uitkomst(invoer: UitkomstIn, db: Db, _: Ingelogd) -> UitkomstUit:
    """Berekent het afgeleide risicoprofiel zonder iets op te slaan."""
    try:
        u = bereken(invoer.antwoorden, invoer.horizon_jaren)
    except ValueError as fout:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fout)) from fout
    code = db.scalar(select(Risicoprofiel.code).where(Risicoprofiel.niveau == u.niveau))
    return UitkomstUit(
        score_bereidheid=u.score_bereidheid,
        score_capaciteit=u.score_capaciteit,
        score_kennis=u.score_kennis,
        lage_kennis=u.lage_kennis,
        risicoprofiel=code,
        bepalende_factor=u.bepalende_factor,
    )


def _risicoprofiel_uit(db: Db, profiel: Risicoprofiel) -> RisicoprofielUit:
    regels = {
        r.categorie: r
        for r in db.scalars(
            select(Modelallocatie).where(Modelallocatie.risicoprofiel_id == profiel.id)
        )
    }
    return RisicoprofielUit(
        code=profiel.code,
        naam=profiel.naam,
        niveau=profiel.niveau,
        allocatie=[
            AllocatieRegel(
                categorie=c,
                streef=regels[c].streef,
                minimum=regels[c].minimum,
                maximum=regels[c].maximum,
            )
            for c in CATEGORIEEN
            if c in regels
        ],
    )


@router.get("/risicoprofielen", response_model=list[RisicoprofielUit])
def risicoprofielen(db: Db, _: Ingelogd) -> list[RisicoprofielUit]:
    profielen = db.scalars(select(Risicoprofiel).order_by(Risicoprofiel.niveau))
    return [_risicoprofiel_uit(db, p) for p in profielen]


@router.put("/risicoprofielen/{code}/allocatie", response_model=RisicoprofielUit)
def wijzig_allocatie(
    code: str, regels: list[AllocatieRegel], db: Db, adviseur: Ingelogd
) -> RisicoprofielUit:
    """Wijzigt de modelallocatie. Geldt voor alle adviseurs; al vastgelegde adviezen wijzigen niet."""
    profiel = db.scalar(select(Risicoprofiel).where(Risicoprofiel.code == code))
    if profiel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Risicoprofiel niet gevonden")
    if len({r.categorie for r in regels}) != len(regels):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, ["Een categorie komt dubbel voor"]
        )
    nieuw = {r.categorie: (r.streef, r.minimum, r.maximum) for r in regels}
    fouten = controleer_allocatie(nieuw, CATEGORIEEN)
    if fouten:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, fouten)

    bestaand = {
        r.categorie: r
        for r in db.scalars(
            select(Modelallocatie).where(Modelallocatie.risicoprofiel_id == profiel.id)
        )
    }
    oud = {c: [r.streef, r.minimum, r.maximum] for c, r in bestaand.items()}
    for categorie, (streef, minimum, maximum) in nieuw.items():
        regel = bestaand.get(categorie)
        if regel is None:
            regel = Modelallocatie(risicoprofiel_id=profiel.id, categorie=categorie)
            db.add(regel)
        regel.streef, regel.minimum, regel.maximum = streef, minimum, maximum
    leg_vast(
        db,
        "modelallocatie_gewijzigd",
        adviseur_id=adviseur.id,
        entiteit="risicoprofiel",
        entiteit_id=code,
        details={"oud": oud, "nieuw": {c: list(v) for c, v in nieuw.items()}},
    )
    db.commit()
    return _risicoprofiel_uit(db, profiel)


# --- klanten ---------------------------------------------------------------------------


@router.get("/klanten", response_model=list[KlantUit])
def klanten(db: Db, adviseur: Ingelogd, gearchiveerd: bool = False) -> list[KlantUit]:
    codes = _profielcodes(db)
    rijen = db.scalars(
        select(Klant).where(Klant.adviseur_id == adviseur.id, Klant.gearchiveerd == gearchiveerd)
    )
    # Sorteren kan niet in de database: de naam staat daar versleuteld.
    return sorted((_klant_uit(db, k, codes) for k in rijen), key=lambda k: k.naam.casefold())


@router.post("/klanten", response_model=KlantUit, status_code=status.HTTP_201_CREATED)
def maak_klant(gegevens: KlantIn, db: Db, adviseur: Ingelogd) -> KlantUit:
    klant = Klant(adviseur_id=adviseur.id)
    _vul_klant(klant, gegevens)
    db.add(klant)
    db.flush()
    # Geen persoonsgegevens in het logboek: alleen het klantnummer.
    leg_vast(
        db, "klant_aangemaakt", adviseur_id=adviseur.id, entiteit="klant", entiteit_id=klant.id
    )
    db.commit()
    return _klant_uit(db, klant, _profielcodes(db))


@router.get("/klanten/{klant_id}", response_model=KlantUit)
def klant(klant_id: int, db: Db, adviseur: Ingelogd) -> KlantUit:
    return _klant_uit(db, _eigen_klant(db, adviseur, klant_id), _profielcodes(db))


@router.put("/klanten/{klant_id}", response_model=KlantUit)
def wijzig_klant(klant_id: int, gegevens: KlantIn, db: Db, adviseur: Ingelogd) -> KlantUit:
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.geanonimiseerd_op is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is geanonimiseerd")
    gewijzigd = [
        veld
        for veld, nieuw in (
            ("naam", gegevens.naam.strip()),
            ("email", gegevens.email.lower() if gegevens.email else None),
            (
                "geboortedatum",
                gegevens.geboortedatum.isoformat() if gegevens.geboortedatum else None,
            ),
        )
        if getattr(klant, veld) != nieuw
    ]
    _vul_klant(klant, gegevens)
    leg_vast(
        db,
        "klant_gewijzigd",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
        details={"velden": gewijzigd},
    )
    db.commit()
    return _klant_uit(db, klant, _profielcodes(db))


class ArchiefIn(BaseModel):
    gearchiveerd: bool


@router.put("/klanten/{klant_id}/archief", response_model=KlantUit)
def archiveer(klant_id: int, verzoek: ArchiefIn, db: Db, adviseur: Ingelogd) -> KlantUit:
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.geanonimiseerd_op is not None and not verzoek.gearchiveerd:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Een geanonimiseerde klant blijft gearchiveerd"
        )
    klant.gearchiveerd = verzoek.gearchiveerd
    leg_vast(
        db,
        "klant_gearchiveerd" if verzoek.gearchiveerd else "klant_teruggezet",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
    )
    db.commit()
    return _klant_uit(db, klant, _profielcodes(db))


@router.post("/klanten/{klant_id}/anonimiseren", response_model=KlantUit)
def anonimiseer(klant_id: int, db: Db, adviseur: Ingelogd) -> KlantUit:
    """Verwijdert de persoonsgegevens van een klant na afloop van de bewaartermijn.

    Naam, e-mailadres, geboortedatum, beleggingsdoel en alle toelichtingen worden gewist. De
    cijfers van profielen en portefeuilles blijven bewaard, maar zijn niet meer tot een persoon
    te herleiden. Dit kan niet ongedaan worden gemaakt.
    """
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.geanonimiseerd_op is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is al geanonimiseerd")
    if not klant.gearchiveerd:
        raise HTTPException(status.HTTP_409_CONFLICT, "Archiveer de klant eerst")
    bewaren_tot = _bewaren_tot(db, klant)
    if bewaren_tot is not None and bewaren_tot > date.today():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Het adviesdossier moet bewaard blijven tot {bewaren_tot.isoformat()} "
            f"({BEWAARTERMIJN_JAREN} jaar na het laatste advies)",
        )
    klant.naam = f"Geanonimiseerde klant {klant.id}"
    klant.email = None
    klant.geboortedatum = None
    klant.geanonimiseerd_op = datetime.now(UTC)
    for profiel in db.scalars(select(Klantprofiel).where(Klantprofiel.klant_id == klant.id)):
        profiel.doel = VERWIJDERD
        profiel.duurzaamheid_toelichting = None
        profiel.afwijking_toelichting = VERWIJDERD if profiel.afwijking_toelichting else None
    for portefeuille in db.scalars(select(Portefeuille).where(Portefeuille.klant_id == klant.id)):
        if portefeuille.toelichting:
            portefeuille.toelichting = VERWIJDERD
        portefeuille.uitsluitingen = [
            {**u, "reden": VERWIJDERD if u.get("reden") else ""} for u in portefeuille.uitsluitingen
        ]
    leg_vast(
        db, "klant_geanonimiseerd", adviseur_id=adviseur.id, entiteit="klant", entiteit_id=klant.id
    )
    db.commit()
    return _klant_uit(db, klant, _profielcodes(db))


# --- klantprofielen --------------------------------------------------------------------


@router.get("/klanten/{klant_id}/profielen", response_model=list[ProfielUit])
def profielen(klant_id: int, db: Db, adviseur: Ingelogd) -> list[ProfielUit]:
    _eigen_klant(db, adviseur, klant_id)
    codes = _profielcodes(db)
    rijen = db.scalars(
        select(Klantprofiel)
        .where(Klantprofiel.klant_id == klant_id)
        .order_by(Klantprofiel.versie.desc())
    )
    return [_profiel_uit(p, codes) for p in rijen]


@router.post(
    "/klanten/{klant_id}/profielen", response_model=ProfielUit, status_code=status.HTTP_201_CREATED
)
def leg_profiel_vast(klant_id: int, invoer: ProfielIn, db: Db, adviseur: Ingelogd) -> ProfielUit:
    """Legt een nieuwe versie van het profiel vast; eerdere versies blijven bewaard."""
    klant = _eigen_klant(db, adviseur, klant_id)
    if klant.gearchiveerd:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deze klant is gearchiveerd")
    if invoer.inleg_eur == 0 and invoer.storting_per_maand_eur == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Vul een inleg of een periodieke storting in"
        )
    try:
        uitkomst = bereken(invoer.antwoorden, invoer.horizon_jaren)
    except ValueError as fout:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(fout)) from fout

    per_niveau = {p.niveau: p for p in db.scalars(select(Risicoprofiel))}
    afgeleid = per_niveau[uitkomst.niveau]
    gekozen = afgeleid
    toelichting = None
    if invoer.gekozen_risicoprofiel and invoer.gekozen_risicoprofiel != afgeleid.code:
        gekozen = next(
            (p for p in per_niveau.values() if p.code == invoer.gekozen_risicoprofiel), None
        )
        if gekozen is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Onbekend risicoprofiel")
        if gekozen.niveau > afgeleid.niveau:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Het gekozen profiel ({gekozen.naam}) is offensiever dan het afgeleide profiel "
                f"({afgeleid.naam}); alleen een defensiever profiel is toegestaan",
            )
        toelichting = (invoer.afwijking_toelichting or "").strip()
        if not toelichting:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Licht toe waarom van het afgeleide profiel wordt afgeweken",
            )

    vorige = db.scalar(
        select(func.max(Klantprofiel.versie)).where(Klantprofiel.klant_id == klant.id)
    )
    profiel = Klantprofiel(
        klant_id=klant.id,
        versie=(vorige or 0) + 1,
        vastgelegd_door=adviseur.id,
        doel=invoer.doel.strip(),
        horizon_jaren=invoer.horizon_jaren,
        inleg_eur=invoer.inleg_eur,
        storting_per_maand_eur=invoer.storting_per_maand_eur,
        doelvermogen_eur=invoer.doelvermogen_eur,
        doel_in_koopkracht=invoer.doel_in_koopkracht,
        vragenlijst_versie=VRAGENLIJST_VERSIE,
        antwoorden=invoer.antwoorden,
        score_bereidheid=uitkomst.score_bereidheid,
        score_capaciteit=uitkomst.score_capaciteit,
        score_kennis=uitkomst.score_kennis,
        duurzaamheid=invoer.duurzaamheid,
        uitsluitingen=sorted(set(invoer.uitsluitingen)),
        duurzaamheid_toelichting=(invoer.duurzaamheid_toelichting or "").strip() or None,
        afgeleid_risicoprofiel_id=afgeleid.id,
        bepalende_factor=uitkomst.bepalende_factor,
        risicoprofiel_id=gekozen.id,
        afwijking_toelichting=toelichting,
    )
    db.add(profiel)
    db.flush()
    leg_vast(
        db,
        "klantprofiel_vastgelegd",
        adviseur_id=adviseur.id,
        entiteit="klant",
        entiteit_id=klant.id,
        details={"versie": profiel.versie, "risicoprofiel": gekozen.code},
    )
    db.commit()
    return _profiel_uit(profiel, _profielcodes(db))
