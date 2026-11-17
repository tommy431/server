import time

import pyotp
import pytest
from sqlalchemy import select

from app.config import instellingen
from app.models import Adviseur, Logboek
from app.security import hash_wachtwoord
from tests.conftest import WACHTWOORD


def maak(db, email, rol="adviseur", **extra):
    a = Adviseur(
        email=email,
        naam=email.split("@")[0],
        rol=rol,
        wachtwoord_hash=hash_wachtwoord(WACHTWOORD),
        **extra,
    )
    db.add(a)
    db.commit()
    return a


def login(client, email, wachtwoord=WACHTWOORD, code=None):
    return client.post("/auth/login", json={"email": email, "wachtwoord": wachtwoord, "code": code})


def kop(token):
    return {"Authorization": f"Bearer {token}"}


def huidige_code(geheim, verschuiving=0):
    totp = pyotp.TOTP(geheim)
    return totp.at(time.time() + verschuiving * totp.interval)


# --- wachtwoord ------------------------------------------------------------------------


def test_wachtwoord_wijzigen_maakt_oude_sessies_ongeldig(client, db, adviseur):
    oud = login(client, adviseur.email).json()["access_token"]
    ander_apparaat = login(client, adviseur.email).json()["access_token"]
    r = client.post(
        "/auth/wachtwoord",
        json={"huidig": WACHTWOORD, "nieuw": "nog-een-lang-wachtwoord"},
        headers=kop(oud),
    )
    assert r.status_code == 200
    nieuw = r.json()["access_token"]
    assert client.get("/auth/mij", headers=kop(ander_apparaat)).status_code == 401
    assert client.get("/auth/mij", headers=kop(oud)).status_code == 401
    assert client.get("/auth/mij", headers=kop(nieuw)).status_code == 200
    assert login(client, adviseur.email).status_code == 401
    assert login(client, adviseur.email, "nog-een-lang-wachtwoord").status_code == 200


@pytest.mark.parametrize(
    ("huidig", "nieuw", "status_code"),
    [
        ("fout-wachtwoord-123", "nog-een-lang-wachtwoord", 403),
        (WACHTWOORD, "kort", 422),
        (WACHTWOORD, WACHTWOORD, 422),
    ],
)
def test_ongeldige_wachtwoordwijziging(client, ingelogd, huidig, nieuw, status_code):
    assert (
        ingelogd.post("/auth/wachtwoord", json={"huidig": huidig, "nieuw": nieuw}).status_code
        == status_code
    )


# --- tweestapsverificatie --------------------------------------------------------------


def zet_tweestaps_aan(client, token):
    start = client.post("/auth/tweestaps/starten", headers=kop(token)).json()
    assert start["uri"].startswith("otpauth://totp/") and "<svg" in start["qr_svg"]
    assert (
        client.post(
            "/auth/tweestaps/bevestigen", json={"code": "000000"}, headers=kop(token)
        ).status_code
        == 422
    )
    r = client.post(
        "/auth/tweestaps/bevestigen",
        json={"code": huidige_code(start["geheim"])},
        headers=kop(token),
    )
    assert r.status_code == 200
    return start["geheim"]


def test_tweestaps_aanzetten_en_inloggen_met_code(client, db, adviseur):
    token = login(client, adviseur.email).json()["access_token"]
    geheim = zet_tweestaps_aan(client, token)
    assert client.get("/auth/mij", headers=kop(token)).json()["tweestaps_actief"] is True

    r = login(client, adviseur.email)
    assert r.status_code == 401 and r.json()["detail"] == "tweestaps_nodig"
    assert login(client, adviseur.email, code="123456").json()["detail"] == "Onjuiste code"
    # Een volgende code werkt; dezelfde code nog eens niet (tegen afluisteren).
    code = huidige_code(geheim, 1)
    assert login(client, adviseur.email, code=code).status_code == 200
    assert login(client, adviseur.email, code=code).status_code == 401
    # Zonder juist wachtwoord helpt een code niet, en de melding verraadt niets.
    r = login(client, adviseur.email, "verkeerd-wachtwoord-123", code=huidige_code(geheim))
    assert r.json()["detail"] == "Onjuist e-mailadres of wachtwoord"
    # Het geheim staat versleuteld opgeslagen.
    from sqlalchemy import text

    ruw = db.execute(
        text("select totp_geheim from adviseur where id = :i"), {"i": adviseur.id}
    ).scalar_one()
    assert geheim not in ruw


def test_foute_codes_tellen_mee_voor_blokkade(client, db, adviseur):
    token = login(client, adviseur.email).json()["access_token"]
    geheim = zet_tweestaps_aan(client, token)
    for _ in range(5):
        login(client, adviseur.email, code="000000")
    assert login(client, adviseur.email, code=huidige_code(geheim, 1)).status_code == 429


def test_beheerder_heeft_tweestaps_nodig_voor_beheertaken(client, db, adviseur, monkeypatch):
    monkeypatch.setattr(instellingen(), "tweestaps_verplicht_beheerder", True)
    token = login(client, adviseur.email).json()["access_token"]
    r = client.get("/adviseurs", headers=kop(token))
    assert r.status_code == 403 and "tweestapsverificatie" in r.json()["detail"]
    assert client.get("/klanten", headers=kop(token)).status_code == 200  # gewoon werk mag wel
    geheim = zet_tweestaps_aan(client, token)
    assert client.get("/adviseurs", headers=kop(token)).status_code == 200
    r = client.post(
        "/auth/tweestaps/uitzetten",
        json={"wachtwoord": WACHTWOORD, "code": huidige_code(geheim, 1)},
        headers=kop(token),
    )
    assert r.status_code == 403 and "verplicht" in r.json()["detail"]


def test_adviseur_kan_tweestaps_uitzetten_met_wachtwoord_en_code(client, db):
    maak(db, "a@voorbeeld.nl")
    token = login(client, "a@voorbeeld.nl").json()["access_token"]
    geheim = zet_tweestaps_aan(client, token)
    pad = "/auth/tweestaps/uitzetten"
    assert (
        client.post(
            pad,
            json={"wachtwoord": "fout-wachtwoord-1", "code": huidige_code(geheim, 1)},
            headers=kop(token),
        ).status_code
        == 403
    )
    assert (
        client.post(
            pad,
            json={"wachtwoord": WACHTWOORD, "code": huidige_code(geheim, 1)},
            headers=kop(token),
        ).status_code
        == 200
    )
    assert login(client, "a@voorbeeld.nl").status_code == 200


# --- gebruikersbeheer ------------------------------------------------------------------


def test_nieuw_account_met_tijdelijk_wachtwoord(ingelogd, client, db):
    r = ingelogd.post("/adviseurs", json={"email": "Nieuw@Voorbeeld.nl", "naam": "Nieuwe Adviseur"})
    assert r.status_code == 201
    uit = r.json()
    assert uit["account"]["rol"] == "adviseur" and uit["account"]["wachtwoord_wijzigen"] is True
    tijdelijk = uit["tijdelijk_wachtwoord"]
    assert len(tijdelijk) == 16
    assert (
        ingelogd.post("/adviseurs", json={"email": "nieuw@voorbeeld.nl", "naam": "X"}).status_code
        == 409
    )

    token = login(client, "nieuw@voorbeeld.nl", tijdelijk).json()["access_token"]
    assert client.get("/auth/mij", headers=kop(token)).json()["wachtwoord_wijzigen"] is True
    r = client.get("/klanten", headers=kop(token))
    assert r.status_code == 403 and r.json()["detail"] == "Kies eerst een eigen wachtwoord"
    nieuw = client.post(
        "/auth/wachtwoord",
        json={"huidig": tijdelijk, "nieuw": "mijn-eigen-wachtwoord"},
        headers=kop(token),
    ).json()["access_token"]
    assert client.get("/klanten", headers=kop(nieuw)).status_code == 200
    # Het tijdelijke wachtwoord staat nergens in het logboek.
    assert tijdelijk not in " ".join(str(r.details) for r in db.scalars(select(Logboek)))


def test_lijst_en_resetten_van_adviseur(ingelogd, client, db):
    a = maak(db, "a@voorbeeld.nl")
    oud = login(client, "a@voorbeeld.nl").json()["access_token"]
    lijst = {x["email"]: x for x in ingelogd.get("/adviseurs").json()}
    assert (
        lijst["a@voorbeeld.nl"]["aantal_klanten"] == 0
        and lijst["adviseur@voorbeeld.nl"]["rol"] == "beheerder"
    )

    r = ingelogd.post(f"/adviseurs/{a.id}/wachtwoord-resetten")
    assert r.status_code == 200 and r.json()["account"]["wachtwoord_wijzigen"] is True
    assert client.get("/auth/mij", headers=kop(oud)).status_code == 401  # oude sessie vervalt
    assert login(client, "a@voorbeeld.nl", r.json()["tijdelijk_wachtwoord"]).status_code == 200

    db.refresh(a)
    a.tweestaps_actief, a.totp_geheim = True, pyotp.random_base32()
    db.commit()
    r = ingelogd.post(f"/adviseurs/{a.id}/tweestaps-resetten")
    assert r.status_code == 200 and r.json()["tweestaps_actief"] is False


def test_adviseur_blokkeren_en_deblokkeren(ingelogd, client, db):
    a = maak(db, "a@voorbeeld.nl")
    token = login(client, "a@voorbeeld.nl").json()["access_token"]
    r = ingelogd.put(f"/adviseurs/{a.id}/status", json={"actief": False})
    assert r.json()["account"]["actief"] is False
    assert client.get("/auth/mij", headers=kop(token)).status_code == 401
    assert login(client, "a@voorbeeld.nl").status_code == 401
    ingelogd.put(f"/adviseurs/{a.id}/status", json={"actief": True})
    assert login(client, "a@voorbeeld.nl").status_code == 200


def test_beheerder_kan_eigen_account_en_andere_beheerders_niet_zomaar_wijzigen(
    ingelogd, db, adviseur
):
    b = maak(db, "b@voorbeeld.nl", rol="beheerder")
    assert (
        ingelogd.put(f"/adviseurs/{adviseur.id}/status", json={"actief": False}).status_code == 403
    )
    assert (
        ingelogd.put(f"/adviseurs/{adviseur.id}/rol", json={"rol": "adviseur"}).status_code == 403
    )
    for pad in [f"/adviseurs/{b.id}/wachtwoord-resetten", f"/adviseurs/{b.id}/tweestaps-resetten"]:
        r = ingelogd.post(pad)
        assert r.status_code == 403 and "beheeropdrachten" in r.json()["detail"]
    assert ingelogd.put("/adviseurs/999/rol", json={"rol": "beheerder"}).status_code == 404


def test_beheerder_worden_vereist_goedkeuring_van_een_ander(client, db, monkeypatch):
    monkeypatch.setattr(instellingen(), "vier_ogen", True)
    b1 = maak(db, "b1@voorbeeld.nl", rol="beheerder")
    maak(db, "b2@voorbeeld.nl", rol="beheerder")
    a = maak(db, "a@voorbeeld.nl")
    t1 = login(client, "b1@voorbeeld.nl").json()["access_token"]
    t2 = login(client, "b2@voorbeeld.nl").json()["access_token"]

    # Een beheerder kan niet zelf een extra beheerder maken om eigen voorstellen goed te keuren.
    r = client.put(f"/adviseurs/{a.id}/rol", json={"rol": "beheerder"}, headers=kop(t1))
    voorstel = r.json()
    assert voorstel["status"] == "open" and voorstel["soort"] == "account"
    assert voorstel["oud"] == {"rol": "adviseur", "email": "a@voorbeeld.nl"}
    db.refresh(a)
    assert a.rol == "adviseur"
    assert (
        client.post(
            f"/wijzigingsvoorstellen/{voorstel['id']}/goedkeuren", headers=kop(t1)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/wijzigingsvoorstellen/{voorstel['id']}/goedkeuren", headers=kop(t2)
        ).status_code
        == 200
    )
    db.refresh(a)
    assert a.rol == "beheerder"

    # Blokkeren van een beheerder gaat ook via een voorstel, en er moeten er twee overblijven.
    r = client.put(f"/adviseurs/{b1.id}/status", json={"actief": False}, headers=kop(t2)).json()
    assert r["voorstel"]["status"] == "open"
    ta = login(client, "a@voorbeeld.nl").json()["access_token"]
    assert (
        client.post(
            f"/wijzigingsvoorstellen/{r['voorstel']['id']}/goedkeuren", headers=kop(ta)
        ).status_code
        == 200
    )
    db.refresh(b1)
    assert b1.actief is False
    # Nu zijn er nog twee beheerders: b2 en a. Eén daarvan weghalen kan niet meer.
    r = client.put(f"/adviseurs/{a.id}/rol", json={"rol": "adviseur"}, headers=kop(t2)).json()
    goed = client.post(f"/wijzigingsvoorstellen/{r['id']}/goedkeuren", headers=kop(ta))
    assert goed.status_code == 409 and "minstens 2" in goed.json()["detail"]


def test_gewone_adviseur_heeft_geen_toegang_tot_gebruikersbeheer(client, db):
    maak(db, "a@voorbeeld.nl")
    token = login(client, "a@voorbeeld.nl").json()["access_token"]
    for methode, pad in [
        ("get", "/adviseurs"),
        ("post", "/adviseurs"),
        ("put", "/adviseurs/1/rol"),
        ("post", "/adviseurs/1/wachtwoord-resetten"),
    ]:
        assert client.request(methode, pad, headers=kop(token), json={}).status_code == 403, pad
