"""Beheeropdrachten: python -m app.cli <opdracht>."""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.bronnen import EcbBron, YahooBron
from app.data.universum import UniversumFout, laad_universum
from app.data.verversen import ververs_alles
from app.db import engine
from app.logboek import leg_vast
from app.models import Adviseur
from app.security import hash_wachtwoord


def adviseur_aanmaken(db: Session, args: argparse.Namespace) -> int:
    email = args.email.lower()
    if db.scalar(select(Adviseur).where(Adviseur.email == email)):
        print(f"Er bestaat al een adviseur met {email}", file=sys.stderr)
        return 1
    if sys.stdin.isatty():
        wachtwoord = getpass.getpass("Wachtwoord: ")
        if wachtwoord != getpass.getpass("Herhaal wachtwoord: "):
            print("Wachtwoorden komen niet overeen", file=sys.stderr)
            return 1
    else:
        # Zonder toetsenbord (bijvoorbeeld in een script): het wachtwoord op de eerste regel.
        wachtwoord = sys.stdin.readline().rstrip("\n")
    try:
        hash_ = hash_wachtwoord(wachtwoord)
    except ValueError as fout:
        print(fout, file=sys.stderr)
        return 1
    db.add(Adviseur(email=email, naam=args.naam, rol=args.rol, wachtwoord_hash=hash_))
    leg_vast(db, "adviseur_aangemaakt", entiteit="adviseur", entiteit_id=email)
    db.commit()
    print(f"Adviseur {email} aangemaakt met rol {args.rol}")
    return 0


def rol_wijzigen(db: Session, args: argparse.Namespace) -> int:
    adviseur = db.scalar(select(Adviseur).where(Adviseur.email == args.email.lower()))
    if adviseur is None:
        print(f"Geen adviseur met {args.email}", file=sys.stderr)
        return 1
    oud, adviseur.rol = adviseur.rol, args.rol
    leg_vast(
        db,
        "rol_gewijzigd",
        entiteit="adviseur",
        entiteit_id=adviseur.email,
        details={"oud": oud, "nieuw": args.rol},
    )
    db.commit()
    print(f"Rol van {adviseur.email}: {oud} → {args.rol}")
    return 0


def tweestaps_resetten(db: Session, args: argparse.Namespace) -> int:
    """Voor een beheerder die zijn telefoon kwijt is; alleen met toegang tot de server."""
    adviseur = db.scalar(select(Adviseur).where(Adviseur.email == args.email.lower()))
    if adviseur is None:
        print(f"Geen adviseur met {args.email}", file=sys.stderr)
        return 1
    adviseur.tweestaps_actief = False
    adviseur.totp_geheim = None
    adviseur.totp_laatste_stap = None
    adviseur.sessie_versie += 1
    leg_vast(
        db,
        "tweestaps_gereset",
        entiteit="adviseur",
        entiteit_id=adviseur.email,
        details={"via": "server"},
    )
    db.commit()
    print(f"Tweestapsverificatie van {adviseur.email} staat uit; stel haar opnieuw in")
    return 0


def logboek_controleren(db: Session, args: argparse.Namespace) -> int:
    from app.logboek import controleer_keten

    c = controleer_keten(db)
    if c.in_orde:
        print(f"Logboek in orde: {c.aantal} regels, laatste hash {c.laatste_hash}")
        return 0
    print(f"LOGBOEK NIET IN ORDE bij regel {c.fout_bij}: {c.fout}", file=sys.stderr)
    return 2


def universum_laden(db: Session, args: argparse.Namespace) -> int:
    try:
        toegevoegd, bijgewerkt = laad_universum(db, Path(args.bestand).read_text("utf-8-sig"))
    except UniversumFout as fout:
        print("\n".join(fout.fouten), file=sys.stderr)
        return 1
    leg_vast(
        db,
        "universum_geimporteerd",
        entiteit="instrument",
        details={"toegevoegd": toegevoegd, "bijgewerkt": bijgewerkt},
    )
    db.commit()
    print(f"{toegevoegd} toegevoegd, {bijgewerkt} bijgewerkt")
    return 0


def data_verversen(db: Session, args: argparse.Namespace) -> int:
    resultaten = ververs_alles(db, YahooBron(), EcbBron())
    for r in resultaten:
        if r.fout:
            print(f"FOUT  {r.onderdeel}: {r.fout}")
        else:
            print(f"OK    {r.onderdeel}: {r.opgeslagen} koersen")
        for b in r.bevindingen:
            if b.ernst == "waarschuwing":
                print(f"      let op: {b.melding}")
    mislukt = [r.onderdeel for r in resultaten if r.fout]
    leg_vast(
        db,
        "data_ververst",
        details={"gelukt": len(resultaten) - len(mislukt), "mislukt": mislukt},
    )
    db.commit()
    return 1 if mislukt else 0


def sleutels_maken(_db, _args: argparse.Namespace) -> int:
    """Drukt nieuwe, sterke waarden af voor JWT_GEHEIM en VERSLEUTELSLEUTEL (voor .env)."""
    import secrets

    from cryptography.fernet import Fernet

    print(f"JWT_GEHEIM={secrets.token_urlsafe(48)}")
    print(f"VERSLEUTELSLEUTEL={Fernet.generate_key().decode()}")
    return 0


def testomgeving(db: Session, args: argparse.Namespace) -> int:
    # Wist alles: alleen op een SQLite-testdatabase, of met uitdrukkelijke bevestiging.
    if db.get_bind().dialect.name != "sqlite" and not args.wis_alles:
        print(
            "Weigering: dit wist de hele database. Alleen voor een SQLite-testdatabase, "
            "of geef --wis-alles mee als u dit echt wilt.",
            file=sys.stderr,
        )
        return 1
    from app.config import instellingen
    from app.testomgeving import vul

    url = instellingen().database_url
    # Wist de hele database: alleen toegestaan voor een SQLite-bestand met "e2e" in de naam.
    if not (url.startswith("sqlite") and "e2e" in url):
        print(
            "Alleen toegestaan voor een SQLite-testdatabase met 'e2e' in de naam", file=sys.stderr
        )
        return 1
    vul(db)
    print("Testomgeving klaar")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("adviseur-aanmaken", help="Maak een account voor een adviseur")
    p.add_argument("--email", required=True)
    p.add_argument("--naam", required=True)
    p.add_argument("--rol", choices=("adviseur", "beheerder"), default="adviseur")
    p.set_defaults(func=adviseur_aanmaken)

    p = sub.add_parser("rol-wijzigen", help="Maak een adviseur beheerder of weer adviseur")
    p.add_argument("--email", required=True)
    p.add_argument("--rol", choices=("adviseur", "beheerder"), required=True)
    p.set_defaults(func=rol_wijzigen)

    p = sub.add_parser("tweestaps-resetten", help="Zet tweestapsverificatie van een account uit")
    p.add_argument("--email", required=True)
    p.set_defaults(func=tweestaps_resetten)

    p = sub.add_parser("logboek-controleren", help="Controleer of het logboek ongewijzigd is")
    p.set_defaults(func=logboek_controleren)

    p = sub.add_parser("universum-laden", help="Laad of werk de instrumentenlijst bij uit CSV")
    p.add_argument("bestand", nargs="?", default="data/universum.csv")
    p.set_defaults(func=universum_laden)

    p = sub.add_parser("testomgeving", help="Vul een lege e2e-testdatabase (wist alles)")
    p.add_argument("--wis-alles", action="store_true", help="Ook op een andere database dan SQLite")
    p.set_defaults(func=testomgeving)

    p = sub.add_parser("sleutels-maken", help="Maak waarden voor JWT_GEHEIM en VERSLEUTELSLEUTEL")
    p.set_defaults(func=sleutels_maken, zonder_database=True)

    p = sub.add_parser("data-verversen", help="Haal koersen en wisselkoersen opnieuw op")
    p.set_defaults(func=data_verversen)

    args = parser.parse_args()
    if getattr(args, "zonder_database", False):
        return args.func(None, args)
    with Session(engine(), expire_on_commit=False) as db:
        return args.func(db, args)


if __name__ == "__main__":
    sys.exit(main())
