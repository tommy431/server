import pytest
from sqlalchemy import select

from app.config import instellingen
from app.models import Adviseur, Logboek
from app.security import hash_wachtwoord
from tests.conftest import UNIVERSUM, WACHTWOORD
from tests.test_aannames_scenario_api import aannames_in
from tests.test_klanten import regels


@pytest.fixture
def vier_ogen(monkeypatch):
    monkeypatch.setattr(instellingen(), "vier_ogen", True)


def inloggen(client, db, email, rol):
    db.add(
        Adviseur(
            email=email,
            naam=email.split("@")[0],
            rol=rol,
            wachtwoord_hash=hash_wachtwoord(WACHTWOORD),
        )
    )
    db.commit()
    token = client.post("/auth/login", json={"email": email, "wachtwoord": WACHTWOORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def streef_aandelen_neutraal(client, kop):
    return client.get("/risicoprofielen", headers=kop).json()[2]["allocatie"][0]["streef"]


def test_adviseur_mag_instellingen_lezen_maar_niet_wijzigen(client, db):
    kop = inloggen(client, db, "adviseur2@voorbeeld.nl", "adviseur")
    assert client.get("/auth/mij", headers=kop).json()["rol"] == "adviseur"
    assert client.get("/risicoprofielen", headers=kop).status_code == 200
    assert client.get("/aannames", headers=kop).status_code == 200
    assert client.get("/wijzigingsvoorstellen", headers=kop).status_code == 200
    nieuw = regels(aandelen=[55, 45, 65], obligaties=[33, 20, 45])
    for methode, pad, body in [
        ("put", "/risicoprofielen/neutraal/allocatie", nieuw),
        ("post", "/aannames", aannames_in()),
    ]:
        r = client.request(methode, pad, json=body, headers=kop)
        assert r.status_code == 403 and r.json()["detail"] == "Alleen een beheerder mag dit doen"
    upload = {"bestand": ("u.csv", UNIVERSUM.encode(), "text/csv")}
    assert client.post("/instrumenten/import", files=upload, headers=kop).status_code == 403
    assert (
        client.post("/instrumenten/1/koersen/import", files=upload, headers=kop).status_code == 403
    )
    assert streef_aandelen_neutraal(client, kop) == 50


def test_vier_ogen_voorstel_pas_na_goedkeuring_door_tweede_beheerder(client, db, vier_ogen):
    eerste = inloggen(client, db, "beheer1@voorbeeld.nl", "beheerder")
    tweede = inloggen(client, db, "beheer2@voorbeeld.nl", "beheerder")
    adviseur = inloggen(client, db, "adviseur2@voorbeeld.nl", "adviseur")
    nieuw = regels(aandelen=[55, 45, 65], obligaties=[33, 20, 45])

    r = client.put("/risicoprofielen/neutraal/allocatie", json=nieuw, headers=eerste)
    assert r.status_code == 200
    voorstel = r.json()
    assert (voorstel["status"], voorstel["sleutel"], voorstel["voorgesteld_door"]) == (
        "open",
        "neutraal",
        "beheer1",
    )
    assert voorstel["inhoud"]["regels"]["aandelen"] == [55, 45, 65]
    assert voorstel["oud"]["regels"]["aandelen"] == [50, 40, 60]
    assert streef_aandelen_neutraal(client, eerste) == 50  # nog niet van kracht

    open_ = client.get("/wijzigingsvoorstellen", params={"status": "open"}, headers=adviseur).json()
    assert [v["id"] for v in open_] == [voorstel["id"]]

    pad = f"/wijzigingsvoorstellen/{voorstel['id']}/goedkeuren"
    r = client.post(pad, headers=eerste)
    assert r.status_code == 403 and "tweede beheerder" in r.json()["detail"]
    assert client.post(pad, headers=adviseur).status_code == 403
    r = client.post(pad, headers=tweede)
    assert r.status_code == 200 and r.json()["status"] == "doorgevoerd"
    assert r.json()["beoordeeld_door"] == "beheer2"
    assert streef_aandelen_neutraal(client, eerste) == 55
    assert client.post(pad, headers=tweede).status_code == 409  # niet twee keer

    acties = db.scalars(
        select(Logboek.actie).where(Logboek.actie.like("%wijzig%")).order_by(Logboek.id)
    ).all()
    assert acties == ["wijziging_voorgesteld", "modelallocatie_gewijzigd", "wijziging_doorgevoerd"]
    regel = db.scalar(select(Logboek).where(Logboek.actie == "modelallocatie_gewijzigd"))
    assert regel.details["voorstel"] == voorstel["id"]


def test_aannames_via_voorstel_en_afwijzen(client, db, vier_ogen):
    eerste = inloggen(client, db, "beheer1@voorbeeld.nl", "beheerder")
    tweede = inloggen(client, db, "beheer2@voorbeeld.nl", "beheerder")
    a = client.post("/aannames", json=aannames_in(bron="Bron A"), headers=eerste).json()
    assert a["status"] == "open"
    assert client.get("/aannames", headers=eerste).json()["bron"].startswith("Voorbeeldwaarden")
    # Een tweede voorstel over hetzelfde onderwerp wacht tot het eerste is afgehandeld.
    r = client.post("/aannames", json=aannames_in(bron="Bron B"), headers=tweede)
    assert r.status_code == 409 and f"nummer {a['id']}" in r.json()["detail"]

    r = client.post(
        f"/wijzigingsvoorstellen/{a['id']}/afwijzen",
        json={"reden": "Bron niet erkend"},
        headers=tweede,
    )
    assert r.json()["status"] == "afgewezen" and r.json()["reden"] == "Bron niet erkend"
    pad_a = f"/wijzigingsvoorstellen/{a['id']}/goedkeuren"
    assert client.post(pad_a, headers=tweede).status_code == 409

    # De indiener kan het eigen voorstel intrekken; een reden is verplicht.
    b = client.post("/aannames", json=aannames_in(bron="Bron B"), headers=eerste).json()
    pad_b = f"/wijzigingsvoorstellen/{b['id']}/afwijzen"
    assert client.post(pad_b, json={"reden": ""}, headers=eerste).status_code == 422
    assert client.post(pad_b, json={"reden": "Ingetrokken"}, headers=eerste).status_code == 200
    assert client.get("/aannames", headers=eerste).json()["bron"].startswith("Voorbeeldwaarden")

    c = client.post("/aannames", json=aannames_in(bron="Bron C"), headers=eerste).json()
    goed = client.post(f"/wijzigingsvoorstellen/{c['id']}/goedkeuren", headers=tweede).json()
    huidig = client.get("/aannames", headers=eerste).json()
    assert huidig["bron"] == "Bron C" and huidig["id"] == goed["resultaat_id"]
    alle = client.get("/wijzigingsvoorstellen", params={"soort": "aannames"}, headers=eerste).json()
    assert [v["status"] for v in alle] == ["doorgevoerd", "afgewezen", "afgewezen"]


def test_ongeldig_voorstel_wordt_meteen_geweigerd(client, db, vier_ogen):
    kop = inloggen(client, db, "beheer1@voorbeeld.nl", "beheerder")
    r = client.put(
        "/risicoprofielen/neutraal/allocatie", json=regels(aandelen=[60, 40, 60]), headers=kop
    )
    assert r.status_code == 422
    assert client.get("/wijzigingsvoorstellen", headers=kop).json() == []
    assert client.post("/wijzigingsvoorstellen/999/goedkeuren", headers=kop).status_code == 404


def test_voorstellen_voor_verschillende_profielen_mogen_naast_elkaar(client, db, vier_ogen):
    kop = inloggen(client, db, "beheer1@voorbeeld.nl", "beheerder")
    nieuw = regels(aandelen=[55, 45, 65], obligaties=[33, 20, 45])
    assert (
        client.put("/risicoprofielen/neutraal/allocatie", json=nieuw, headers=kop).status_code
        == 200
    )
    assert (
        client.put("/risicoprofielen/neutraal/allocatie", json=nieuw, headers=kop).status_code
        == 409
    )
    defensief = [
        {"categorie": c, "streef": s, "minimum": lo, "maximum": hi}
        for c, (s, lo, hi) in {
            "aandelen": (25, 20, 40),
            "obligaties": (60, 40, 70),
            "vastgoed": (5, 0, 10),
            "grondstoffen": (0, 0, 5),
            "liquiditeiten": (10, 0, 25),
        }.items()
    ]
    r = client.put("/risicoprofielen/defensief/allocatie", json=defensief, headers=kop)
    assert r.status_code == 200
