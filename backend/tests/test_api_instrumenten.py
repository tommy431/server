from datetime import date, timedelta

from sqlalchemy import select

from app.models import Logboek
from tests.conftest import UNIVERSUM


def upload(tekst, naam="bestand.csv"):
    return {"bestand": (naam, tekst.encode("utf-8"), "text/csv")}


def koersen_csv(n=5, eind=None):
    eind = eind or date.today()
    regels = [f"{eind - timedelta(days=n - 1 - i)},{100 + i},{99 + i}" for i in range(n)]
    return "datum,slot,slot_gecorrigeerd\n" + "\n".join(regels) + "\n"


def test_universum_importeren_filteren_en_logboek(ingelogd, db, adviseur):
    r = ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    assert r.json() == {"toegevoegd": 2, "bijgewerkt": 0}
    assert len(ingelogd.get("/instrumenten").json()) == 2
    obligaties = ingelogd.get("/instrumenten", params={"categorie": "obligaties"}).json()
    assert [i["isin"] for i in obligaties] == ["IE00B4WXJJ64"]
    assert obligaties[0]["kosten_geverifieerd"] is True and obligaties[0]["startdatum"] is None
    assert (
        ingelogd.get("/instrumenten", params={"regio": "europa", "sector": "energie"}).json() == []
    )
    regel = db.scalar(select(Logboek).where(Logboek.actie == "universum_geimporteerd"))
    assert regel.adviseur_id == adviseur.id and regel.details == {"toegevoegd": 2, "bijgewerkt": 0}


def test_fout_universum_wordt_geweigerd_met_regelnummer(ingelogd):
    r = ingelogd.post(
        "/instrumenten/import", files=upload(UNIVERSUM.replace("IE00B4L5Y983", "IE00B4L5Y984"))
    )
    assert r.status_code == 422
    assert r.json()["detail"][0].startswith("Regel 2:")
    assert ingelogd.get("/instrumenten").json() == []
    assert ingelogd.post("/instrumenten/import", files=upload("")).status_code == 422
    binair = {"bestand": ("x.csv", b"\xff\xfe\x00", "text/csv")}
    assert ingelogd.post("/instrumenten/import", files=binair).status_code == 422


def test_koersen_importeren_opvragen_en_status(ingelogd):
    ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    wereld, staats = sorted(ingelogd.get("/instrumenten").json(), key=lambda i: i["isin"])
    vandaag = date.today()

    r = ingelogd.post(f"/instrumenten/{wereld['id']}/koersen/import", files=upload(koersen_csv()))
    assert r.json() == {"opgeslagen": 5, "bevindingen": []}

    alle = ingelogd.get(f"/instrumenten/{wereld['id']}/koersen").json()
    assert len(alle) == 5
    assert alle[-1] == {
        "datum": str(vandaag),
        "slot": 104.0,
        "slot_gecorrigeerd": 103.0,
        "bron": "csv",
    }
    deel = ingelogd.get(
        f"/instrumenten/{wereld['id']}/koersen",
        params={"vanaf": str(vandaag - timedelta(days=2)), "tot": str(vandaag - timedelta(days=1))},
    ).json()
    assert [k["slot"] for k in deel] == [102.0, 103.0]

    status = {s["isin"]: s for s in ingelogd.get("/data/status").json()}
    assert status[wereld["isin"]] | {"naam": "", "instrument_id": 0} == {
        "instrument_id": 0,
        "isin": wereld["isin"],
        "naam": "",
        "lopende_kosten": 0.2,
        "kosten_geverifieerd": False,
        "kosten_gecontroleerd_op": None,
        "kosten_bron": None,
        "aantal_koersen": 5,
        "eerste_koers": str(vandaag - timedelta(days=4)),
        "laatste_koers": str(vandaag),
        "bron": "csv",
        "bevindingen": [],
    }
    leeg = status[staats["isin"]]
    assert leeg["aantal_koersen"] == 0 and leeg["bron"] is None
    assert [b["code"] for b in leeg["bevindingen"]] == ["geen_data"]


def test_verouderde_koersen_geven_waarschuwing_en_ongeldige_worden_geweigerd(ingelogd):
    ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    iid = ingelogd.get("/instrumenten").json()[0]["id"]
    oud = koersen_csv(eind=date.today() - timedelta(days=30))
    r = ingelogd.post(f"/instrumenten/{iid}/koersen/import", files=upload(oud))
    assert [b["code"] for b in r.json()["bevindingen"]] == ["verouderd"]

    r = ingelogd.post(
        f"/instrumenten/{iid}/koersen/import", files=upload("datum,slot\n2026-01-02,-5\n")
    )
    assert r.status_code == 422
    assert len(ingelogd.get(f"/instrumenten/{iid}/koersen").json()) == 5  # oude reeks staat er nog

    assert (
        ingelogd.post(f"/instrumenten/{iid}/koersen/import", files=upload("x\n")).status_code == 422
    )


def test_onbekend_instrument_en_verversen_zonder_universum(ingelogd):
    assert ingelogd.get("/instrumenten/999/koersen").status_code == 404
    r = ingelogd.post("/instrumenten/999/koersen/import", files=upload(koersen_csv()))
    assert r.status_code == 404
    assert ingelogd.post("/data/verversen").status_code == 409


def test_alleen_beheerder_mag_koersen_verversen(client, db):
    from app.models import Adviseur
    from app.security import hash_wachtwoord
    from tests.conftest import WACHTWOORD

    db.add(Adviseur(email="a@voorbeeld.nl", naam="A", wachtwoord_hash=hash_wachtwoord(WACHTWOORD)))
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "a@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    r = client.post("/data/verversen", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def _status(ingelogd, isin):
    return next(s for s in ingelogd.get("/data/status").json() if s["isin"] == isin)


def test_kosten_controleren_en_behouden_bij_opnieuw_laden(ingelogd, db):
    ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    wereld = _status(ingelogd, "IE00B4L5Y983")
    assert (wereld["lopende_kosten"], wereld["kosten_geverifieerd"]) == (0.2, False)

    r = ingelogd.put(
        f"/instrumenten/{wereld['instrument_id']}/kosten",
        json={"lopende_kosten": 0.2, "bron": "EID maart 2026"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["kosten_geverifieerd"] is True
    assert r.json()["kosten_gecontroleerd_op"] == date.today().isoformat()
    regel = db.scalar(select(Logboek).where(Logboek.actie == "kosten_gecontroleerd"))
    assert regel.details == {"oud": 0.2, "nieuw": 0.2, "bron": "EID maart 2026"}

    # Opnieuw laden met dezelfde kosten: de controle blijft staan.
    ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    assert _status(ingelogd, "IE00B4L5Y983")["kosten_geverifieerd"] is True
    # Met andere kosten in het bestand: niet meer gecontroleerd.
    ingelogd.post(
        "/instrumenten/import", files=upload(UNIVERSUM.replace(",0.20,nee,", ",0.22,nee,"))
    )
    s = _status(ingelogd, "IE00B4L5Y983")
    assert (s["lopende_kosten"], s["kosten_geverifieerd"], s["kosten_bron"]) == (0.22, False, None)


def test_kosten_controleren_alleen_beheerder_en_met_bron(client, ingelogd, db):
    from app.models import Adviseur
    from app.security import hash_wachtwoord
    from tests.conftest import WACHTWOORD

    ingelogd.post("/instrumenten/import", files=upload(UNIVERSUM))
    iid = _status(ingelogd, "IE00B4L5Y983")["instrument_id"]
    assert (
        ingelogd.put(
            f"/instrumenten/{iid}/kosten", json={"lopende_kosten": 0.2, "bron": ""}
        ).status_code
        == 422
    )
    assert (
        ingelogd.put(
            f"/instrumenten/{iid}/kosten", json={"lopende_kosten": -1, "bron": "EID"}
        ).status_code
        == 422
    )
    db.add(Adviseur(email="a@voorbeeld.nl", naam="A", wachtwoord_hash=hash_wachtwoord(WACHTWOORD)))
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "a@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    r = client.put(
        f"/instrumenten/{iid}/kosten",
        json={"lopende_kosten": 0.2, "bron": "EID"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
