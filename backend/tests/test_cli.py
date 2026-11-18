import argparse
import io

from sqlalchemy import select

from app import cli
from app.models import Adviseur, Logboek
from app.security import controleer_wachtwoord


def _args(**kw):
    return argparse.Namespace(**kw)


def test_adviseur_aanmaken_met_wachtwoord_via_invoer(db, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("een-heel-lang-wachtwoord\n"))
    code = cli.adviseur_aanmaken(
        db, _args(email="Nieuw@Voorbeeld.nl", naam="Nieuw", rol="beheerder")
    )
    assert code == 0
    a = db.scalar(select(Adviseur).where(Adviseur.email == "nieuw@voorbeeld.nl"))
    assert a.rol == "beheerder" and controleer_wachtwoord(
        "een-heel-lang-wachtwoord", a.wachtwoord_hash
    )
    assert "adviseur_aangemaakt" in db.scalars(select(Logboek.actie)).all()
    # Nog een keer: bestaat al.
    monkeypatch.setattr("sys.stdin", io.StringIO("een-heel-lang-wachtwoord\n"))
    assert (
        cli.adviseur_aanmaken(db, _args(email="nieuw@voorbeeld.nl", naam="X", rol="adviseur")) == 1
    )


def test_te_kort_wachtwoord_geweigerd(db, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("kort\n"))
    assert cli.adviseur_aanmaken(db, _args(email="a@voorbeeld.nl", naam="A", rol="adviseur")) == 1
    assert db.scalar(select(Adviseur)) is None


def test_sleutels_maken_geeft_bruikbare_waarden(capsys):
    from cryptography.fernet import Fernet

    assert cli.sleutels_maken(None, _args()) == 0
    regels = dict(r.split("=", 1) for r in capsys.readouterr().out.split())
    assert len(regels["JWT_GEHEIM"]) >= 32
    Fernet(regels["VERSLEUTELSLEUTEL"])


def test_testomgeving_weigert_zonder_bevestiging_buiten_sqlite(db, monkeypatch):
    if db.get_bind().dialect.name == "sqlite":
        return  # op SQLite mag het; de weigering geldt voor andere databases
    assert cli.testomgeving(db, _args(wis_alles=False)) == 1
