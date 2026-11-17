import jwt
from sqlalchemy import select

from app.models import Logboek
from app.security import controleer_wachtwoord, hash_wachtwoord, lees_token, maak_token
from tests.conftest import WACHTWOORD


def test_wachtwoord_hash_en_controle():
    h = hash_wachtwoord(WACHTWOORD)
    assert h != WACHTWOORD
    assert controleer_wachtwoord(WACHTWOORD, h)
    assert not controleer_wachtwoord("iets-anders-maar-lang", h)
    assert not controleer_wachtwoord(WACHTWOORD, "geen-hash")


def test_te_kort_wachtwoord_geweigerd():
    try:
        hash_wachtwoord("kort")
    except ValueError:
        return
    raise AssertionError("kort wachtwoord werd geaccepteerd")


def test_token_heen_en_terug_en_vervalsing():
    token = maak_token(42)
    assert lees_token(token) == 42
    assert lees_token(token[:-2] + "xx") is None
    vervalst = jwt.encode({"sub": "42"}, "een-ander-geheim-van-voldoende-lengte-123", "HS256")
    assert lees_token(vervalst) is None


def test_login_en_mij(client, adviseur, db):
    r = client.post(
        "/auth/login", json={"email": "Adviseur@Voorbeeld.nl", "wachtwoord": WACHTWOORD}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    mij = client.get("/auth/mij", headers={"Authorization": f"Bearer {token}"})
    assert mij.json() == {
        "id": adviseur.id,
        "email": adviseur.email,
        "naam": adviseur.naam,
        "rol": "beheerder",
    }
    assert "wachtwoord" not in mij.text
    assert db.scalars(select(Logboek.actie)).all() == ["login"]


def test_zonder_of_met_ongeldig_token_geweigerd(client):
    assert client.get("/auth/mij").status_code == 401
    assert client.get("/auth/mij", headers={"Authorization": "Bearer onzin"}).status_code == 401
    assert client.get("/instrumenten").status_code == 401
    assert client.get("/data/status").status_code == 401
    assert client.post("/data/verversen").status_code == 401


def test_fout_wachtwoord_en_onbekend_adres_geven_dezelfde_melding(client, adviseur):
    fout = client.post("/auth/login", json={"email": adviseur.email, "wachtwoord": "x" * 20})
    onbekend = client.post(
        "/auth/login", json={"email": "niemand@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    )
    assert fout.status_code == onbekend.status_code == 401
    assert fout.json() == onbekend.json()


def test_inactieve_adviseur_kan_niet_inloggen_en_token_vervalt(client, adviseur, db):
    token = client.post(
        "/auth/login", json={"email": adviseur.email, "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    adviseur.actief = False
    db.commit()
    assert client.get("/auth/mij", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    r = client.post("/auth/login", json={"email": adviseur.email, "wachtwoord": WACHTWOORD})
    assert r.status_code == 401


def test_blokkade_na_vijf_mislukte_pogingen(client, adviseur):
    for _ in range(5):
        r = client.post("/auth/login", json={"email": adviseur.email, "wachtwoord": "x" * 20})
        assert r.status_code == 401
    # Ook het juiste wachtwoord wordt nu geweigerd.
    r = client.post("/auth/login", json={"email": adviseur.email, "wachtwoord": WACHTWOORD})
    assert r.status_code == 429
