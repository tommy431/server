import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import instellingen
from app.db import sessie
from app.main import app
from app.models import Adviseur, Logboek
from app.security import hash_wachtwoord
from tests.conftest import WACHTWOORD

FOUT = "verkeerd-wachtwoord-123"


@pytest.fixture
def vanaf(db):
    """Testclients met een eigen IP-adres."""
    app.dependency_overrides[sessie] = lambda: db
    yield lambda ip: TestClient(app, client=(ip, 50000))
    app.dependency_overrides.clear()


def maak(db, email):
    db.add(Adviseur(email=email, naam=email, wachtwoord_hash=hash_wachtwoord(WACHTWOORD)))
    db.commit()


def login(c, email, wachtwoord=WACHTWOORD):
    return c.post("/auth/login", json={"email": email, "wachtwoord": wachtwoord}).status_code


def test_aanvaller_elders_kan_de_gebruiker_niet_buitensluiten(vanaf, db):
    maak(db, "a@voorbeeld.nl")
    aanvaller, gebruiker = vanaf("203.0.113.9"), vanaf("198.51.100.4")
    assert [login(aanvaller, "a@voorbeeld.nl", FOUT) for _ in range(6)] == [401] * 5 + [429]
    # Vanaf het eigen adres kan de gebruiker gewoon inloggen.
    assert login(gebruiker, "a@voorbeeld.nl") == 200
    # De aanvaller blijft geblokkeerd, ook met het juiste wachtwoord.
    assert login(aanvaller, "a@voorbeeld.nl") == 429


def test_een_adres_dat_veel_accounts_probeert_wordt_geblokkeerd(vanaf, db):
    for i in range(6):
        maak(db, f"a{i}@voorbeeld.nl")
    aanvaller = vanaf("203.0.113.9")
    uitkomsten = [login(aanvaller, f"a{i % 6}@voorbeeld.nl", FOUT) for i in range(21)]
    assert uitkomsten[:20] == [401] * 20 and uitkomsten[20] == 429
    assert login(aanvaller, "a5@voorbeeld.nl") == 429  # ook een ander account
    assert login(vanaf("198.51.100.4"), "a5@voorbeeld.nl") == 200


def test_grootschalige_aanval_op_een_account_sluit_dat_account_tijdelijk(vanaf, db, monkeypatch):
    monkeypatch.setattr(instellingen(), "max_mislukte_logins_per_account", 8)
    maak(db, "a@voorbeeld.nl")
    for i in range(8):  # vanaf acht verschillende adressen
        assert login(vanaf(f"203.0.113.{i}"), "a@voorbeeld.nl", FOUT) == 401
    assert login(vanaf("198.51.100.4"), "a@voorbeeld.nl") == 429


def test_ip_adres_staat_in_het_logboek(vanaf, db):
    maak(db, "a@voorbeeld.nl")
    login(vanaf("203.0.113.9"), "a@voorbeeld.nl", FOUT)
    login(vanaf("198.51.100.4"), "a@voorbeeld.nl")
    regels = db.scalars(
        select(Logboek).where(Logboek.actie.in_(["login", "login_mislukt"])).order_by(Logboek.id)
    ).all()
    assert [(r.actie, r.details["ip"]) for r in regels] == [
        ("login_mislukt", "203.0.113.9"),
        ("login", "198.51.100.4"),
    ]


def test_algemene_verzoeklimiet_per_ip(vanaf, monkeypatch):
    monkeypatch.setattr(instellingen(), "limiet_verzoeken_per_minuut", 5)
    druk, rustig = vanaf("203.0.113.9"), vanaf("198.51.100.4")
    codes = [druk.get("/auth/mij").status_code for _ in range(7)]
    assert codes == [401] * 5 + [429] * 2
    r = druk.get("/auth/mij")
    assert r.headers["Retry-After"] == "60" and "Te veel verzoeken" in r.json()["detail"]
    assert rustig.get("/auth/mij").status_code == 401  # ander adres heeft eigen teller
    assert druk.get("/gezondheid").status_code == 200  # gezondheidscontrole uitgezonderd
