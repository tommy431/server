from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Modelallocatie, Risicoprofiel
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
