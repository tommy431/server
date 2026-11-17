from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Aannameset, Modelallocatie, Risicoprofiel
from app.profiel import RISICOPROFIELEN, STANDAARD_ALLOCATIES


def zaai_standaarden(db: Session) -> None:
    """Voegt ontbrekende risicoprofielen met hun standaardallocatie toe; de aanroeper commit.

    Bestaande profielen en allocaties blijven ongemoeid, zodat beheerde waarden niet
    worden overschreven.
    """
    bestaand = set(db.scalars(select(Risicoprofiel.code)))
    for niveau, (code, naam) in enumerate(RISICOPROFIELEN, start=1):
        if code in bestaand:
            continue
        profiel = Risicoprofiel(code=code, naam=naam, niveau=niveau)
        db.add(profiel)
        db.flush()
        for categorie, (streef, minimum, maximum) in STANDAARD_ALLOCATIES[code].items():
            db.add(
                Modelallocatie(
                    risicoprofiel_id=profiel.id,
                    categorie=categorie,
                    streef=streef,
                    minimum=minimum,
                    maximum=maximum,
                )
            )


# Voorbeeldwaarden: nominaal verwacht rekenkundig rendement per jaar, vóór kosten, en
# volatiliteit per jaar. Niet afkomstig uit een gepubliceerde bron; vervangen vóór gebruik.
STANDAARD_AANNAMES = {
    "aandelen": {"rendement": 0.065, "volatiliteit": 0.16},
    "obligaties": {"rendement": 0.030, "volatiliteit": 0.055},
    "vastgoed": {"rendement": 0.055, "volatiliteit": 0.18},
    "grondstoffen": {"rendement": 0.035, "volatiliteit": 0.17},
    "liquiditeiten": {"rendement": 0.020, "volatiliteit": 0.01},
}
_PAREN = {
    ("aandelen", "obligaties"): 0.1,
    ("aandelen", "vastgoed"): 0.7,
    ("aandelen", "grondstoffen"): 0.3,
    ("aandelen", "liquiditeiten"): 0.0,
    ("obligaties", "vastgoed"): 0.2,
    ("obligaties", "grondstoffen"): 0.0,
    ("obligaties", "liquiditeiten"): 0.2,
    ("vastgoed", "grondstoffen"): 0.2,
    ("vastgoed", "liquiditeiten"): 0.0,
    ("grondstoffen", "liquiditeiten"): 0.0,
}
STANDAARD_CORRELATIES = {
    a: {b: 1.0 if a == b else _PAREN.get((a, b), _PAREN.get((b, a))) for b in STANDAARD_AANNAMES}
    for a in STANDAARD_AANNAMES
}
STANDAARD_INFLATIE = 0.02
STANDAARD_BRON = (
    "Voorbeeldwaarden, niet afkomstig uit een gepubliceerde bron. Vervang ze door aannames uit "
    "een erkende bron voordat ze in een advies worden gebruikt."
)


def zaai_aannames(db: Session) -> None:
    """Voegt de voorbeeldaannames toe als er nog geen aannameset is; de aanroeper commit."""
    if db.scalar(select(Aannameset.id).limit(1)) is None:
        db.add(
            Aannameset(
                bron=STANDAARD_BRON,
                peildatum=date(2026, 11, 17),
                categorieen=STANDAARD_AANNAMES,
                correlaties=STANDAARD_CORRELATIES,
                inflatie=STANDAARD_INFLATIE,
            )
        )
