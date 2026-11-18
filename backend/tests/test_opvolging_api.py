# ruff: noqa: F811  (klant_id is een fixture uit test_portefeuille_api)
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Instrument, Koers, Logboek
from tests.test_klanten import antwoorden, profiel
from tests.test_portefeuille_api import GELD, WERELD, klant_id, pad  # noqa: F401


def _koers(db, isin, slot, dagen_geleden=1):
    i = db.scalar(select(Instrument).where(Instrument.isin == isin))
    d = date.today() - timedelta(days=dagen_geleden)
    db.add(
        Koers(
            instrument_id=i.id,
            datum=d,
            slot=slot,
            slot_gecorrigeerd=slot * 2,
            bron="test",
            opgehaald_op=datetime.now(UTC),
        )
    )
    db.commit()


def _advies(ingelogd, kid):
    posities = [{"isin": WERELD, "gewicht": 6000}, {"isin": GELD, "gewicht": 4000}]
    r = ingelogd.post(
        pad(kid, "versies"), json={"posities": posities, "toelichting": "Eenvoudig testadvies"}
    )
    assert r.status_code == 201, r.text


def _bezit(ingelogd, kid, posities, kas=0.0, peildatum=None):
    return ingelogd.post(
        f"/klanten/{kid}/bezit",
        json={
            "peildatum": (peildatum or date.today()).isoformat(),
            "posities": [{"isin": i, "aantal": a} for i, a in posities.items()],
            "kas_eur": kas,
        },
    )


def codes(r):
    return [s["code"] for s in r["signalen"]]


def test_zonder_advies_alleen_signaal(ingelogd, klant_id):
    r = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    assert codes(r) == ["geen_advies"] and r["advies"] is None and r["waardering"] is None


def test_bezit_waarderen_vergelijken_en_herbalanceren(ingelogd, klant_id, db):
    _advies(ingelogd, klant_id)
    _koers(db, WERELD, 50.0, dagen_geleden=5)
    _koers(db, WERELD, 100.0)  # de laatste slotkoers telt, niet de gecorrigeerde
    _koers(db, GELD, 10.0)
    r = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    assert codes(r) == ["geen_bezit"]
    assert r["advies"]["posities"] == {WERELD: 6000, GELD: 4000}

    # 800 × 100 = 80.000 wereld, 1.000 × 10 = 10.000 geldmarkt, 10.000 kas → 90/10 i.p.v. 60/40.
    assert _bezit(ingelogd, klant_id, {WERELD: 800, GELD: 1000}, kas=10000).status_code == 201
    r = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    w = r["waardering"]
    assert w["totaal"] == 100000
    assert {p["isin"]: p["gewicht"] for p in w["posities"]} == {WERELD: 8000, GELD: 1000}
    assert codes(r)[0] == "buiten_bandbreedte"
    assert "Aandelen weegt 80,0%" in r["signalen"][0]["melding"]
    t = {(x["isin"], x["actie"]): x["aantal"] for x in r["herbalancering"]["transacties"]}
    assert t == {(WERELD, "verkoop"): 200, (GELD, "koop"): 3000}
    assert r["herbalancering"]["kas_na"] == 0
    assert r["bezit"]["kas_eur"] == 10000

    acties = db.scalars(select(Logboek.actie)).all()
    assert "bezit_vastgelegd" in acties


def test_bezit_invoer_wordt_gecontroleerd(ingelogd, klant_id):
    assert _bezit(ingelogd, klant_id, {"XX0000000000": 1}).status_code == 422
    morgen = date.today() + timedelta(days=1)
    assert _bezit(ingelogd, klant_id, {WERELD: 1}, peildatum=morgen).status_code == 422
    r = ingelogd.post(
        f"/klanten/{klant_id}/bezit",
        json={
            "peildatum": date.today().isoformat(),
            "posities": [{"isin": WERELD, "aantal": 1}, {"isin": WERELD, "aantal": 2}],
            "kas_eur": 0,
        },
    )
    assert r.status_code == 422
    assert _bezit(ingelogd, klant_id, {WERELD: 0}).status_code == 422


def test_zonder_koers_geen_herbalancering(ingelogd, klant_id):
    _advies(ingelogd, klant_id)
    _bezit(ingelogd, klant_id, {WERELD: 10}, kas=500)
    r = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    assert "geen_koers" in codes(r)
    assert r["herbalancering"] is None and r["herbalancering_fout"]


def test_evaluatie_vastleggen_en_volgende_datum(ingelogd, klant_id, db):
    _advies(ingelogd, klant_id)
    vandaag = date.today()
    r = ingelogd.post(
        f"/klanten/{klant_id}/evaluaties",
        json={
            "datum": vandaag.isoformat(),
            "uitkomst": "ongewijzigd",
            "notitie": " Alles in orde ",
        },
    )
    assert r.status_code == 201 and r.json()["notitie"] == "Alles in orde"
    o = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    assert o["evaluaties"][0]["door"] == "Test Adviseur"
    assert (
        o["volgende_evaluatie"] == vandaag.replace(year=vandaag.year + 1).isoformat()
        or vandaag.month == 2
    )
    assert "evaluatie_verlopen" not in codes(o)
    bad = ingelogd.post(
        f"/klanten/{klant_id}/evaluaties", json={"datum": vandaag.isoformat(), "uitkomst": "x"}
    )
    assert bad.status_code == 422
    assert "evaluatie_vastgelegd" in db.scalars(select(Logboek.actie)).all()


def test_profiel_herzien_na_advies_en_signalenoverzicht(ingelogd, klant_id):
    _advies(ingelogd, klant_id)
    ingelogd.post(f"/klanten/{klant_id}/profielen", json=profiel(antwoorden=antwoorden(2, 2)))
    zonder = ingelogd.post("/klanten", json={"naam": "Anna"}).json()["id"]
    lijst = ingelogd.get("/signalen").json()
    assert [k["klant_id"] for k in lijst] == [klant_id, zonder]
    assert lijst[0]["signalen"][0]["code"] == "profiel_herzien"
    assert [s["code"] for s in lijst[1]["signalen"]] == ["geen_profiel"]


def test_andermans_klant_niet_zichtbaar(client, ingelogd, klant_id, db):
    from app.models import Adviseur
    from app.security import hash_wachtwoord
    from tests.conftest import WACHTWOORD

    db.add(
        Adviseur(
            email="ander@voorbeeld.nl",
            rol="adviseur",
            naam="Ander",
            wachtwoord_hash=hash_wachtwoord(WACHTWOORD),
        )
    )
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "ander@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/klanten/{klant_id}/opvolging", headers=h).status_code == 404
    assert (
        client.post(
            f"/klanten/{klant_id}/bezit",
            headers=h,
            json={"peildatum": date.today().isoformat(), "posities": [], "kas_eur": 1},
        ).status_code
        == 404
    )
    assert client.get("/signalen", headers=h).json() == []


def test_bezit_inlezen_uit_csv(ingelogd, klant_id, db):
    tekst = f"Product;ISIN;Aantal\nWereld;{WERELD};1.250\nApple;US0378331005;10\nGeldsaldo;;\n"
    r = ingelogd.post(f"/klanten/{klant_id}/bezit/inlezen", json={"tekst": tekst})
    assert r.status_code == 200
    assert [(p["isin"], p["aantal"]) for p in r.json()["posities"]] == [(WERELD, 1250)]
    # Zonder waardekolom: de waarde vult de adviseur zelf in.
    assert r.json()["overig"] == [
        {"isin": "US0378331005", "omschrijving": "Apple", "aantal": 10, "waarde_eur": None}
    ]
    assert r.json()["meldingen"][0].startswith("1 positie(s) buiten de fondsenlijst")
    assert "vul de waarde in" in r.json()["meldingen"][0]
    # Er is niets opgeslagen.
    assert ingelogd.get(f"/klanten/{klant_id}/opvolging").json()["bezit"] is None
    assert "bezit_vastgelegd" not in db.scalars(select(Logboek.actie)).all()


def test_overig_bezit_vastleggen_en_waarderen(ingelogd, klant_id, db):
    _advies(ingelogd, klant_id)
    _koers(db, WERELD, 100.0)
    _koers(db, GELD, 10.0)
    overig = [
        {
            "omschrijving": "Apple aandelen",
            "isin": "US0378331005",
            "categorie": "aandelen",
            "waarde_eur": 10000,
        },
        {
            "omschrijving": "Vastgoedfonds X",
            "categorie": "vastgoed",
            "waarde_eur": 5000,
            "behouden": True,
        },
    ]
    r = ingelogd.post(
        f"/klanten/{klant_id}/bezit",
        json={
            "peildatum": date.today().isoformat(),
            "posities": [{"isin": WERELD, "aantal": 500}, {"isin": GELD, "aantal": 3500}],
            "overig": overig,
            "kas_eur": 0,
        },
    )
    assert r.status_code == 201, r.text
    o = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    # 50.000 + 35.000 + 10.000 + 5.000 = 100.000
    assert o["waardering"]["totaal"] == 100000
    assert [
        (x["omschrijving"], x["gewicht"], x["behouden"]) for x in o["waardering"]["overig"]
    ] == [
        ("Apple aandelen", 1000, False),
        ("Vastgoedfonds X", 500, True),
    ]
    assert o["bezit"]["overig"][0]["isin"] == "US0378331005"
    verkoop = [t for t in o["herbalancering"]["transacties"] if t["geschat"]]
    assert [(t["naam"], t["bedrag"], t["aantal"]) for t in verkoop] == [
        ("Apple aandelen", 10000, None)
    ]
    meldingen = [s["melding"] for s in o["signalen"]]
    assert "Apple aandelen (overig bezit) zit niet in het advies" in meldingen
    assert not any("Vastgoedfonds" in m for m in meldingen)


def test_overig_bezit_wordt_gecontroleerd(ingelogd, klant_id):
    def met(overig):
        return ingelogd.post(
            f"/klanten/{klant_id}/bezit",
            json={
                "peildatum": date.today().isoformat(),
                "posities": [],
                "overig": [overig],
                "kas_eur": 0,
            },
        )

    goed = {"omschrijving": "Apple", "categorie": "aandelen", "waarde_eur": 100}
    assert (
        met(goed | {"isin": WERELD})
        .json()["detail"]
        .startswith(f"{WERELD} staat in de fondsenlijst")
    )
    assert "Ongeldig ISIN" in met(goed | {"isin": "US0378331006"}).json()["detail"]
    assert met(goed | {"categorie": "crypto"}).status_code == 422
    assert met(goed | {"waarde_eur": 0}).status_code == 422
    assert met(goed | {"omschrijving": ""}).status_code == 422
    assert met(goed).status_code == 201


class NepBronnen:
    """Yahoo en ECB zonder netwerk: Apple in dollars, Vodafone in pence."""

    naam = "test"

    def __init__(self, koersdatum=None, mislukt=False):
        self.koersdatum = koersdatum or date.today() - timedelta(days=1)
        self.mislukt = mislukt
        self.gezocht = []

    def zoek_isin(self, isin):
        from app.data.bronnen import BronFout

        self.gezocht.append(isin)
        if self.mislukt:
            raise BronFout("Yahoo niet bereikbaar")
        return {APPLE: ("AAPL", "Apple Inc."), VODAFONE: ("VOD.L", "Vodafone Group")}.get(isin)

    def haal_koersen(self, symbool, vanaf):
        from app.data.bronnen import Koerspunt, Koersreeks

        valuta, slot = {"AAPL": ("USD", 200.0), "VOD.L": ("GBp", 80.0)}[symbool]
        return Koersreeks(valuta, [Koerspunt(self.koersdatum, slot, slot)])

    def haal_wisselkoersen(self, valuta, vanaf):
        koersen = {"USD": 1.25, "GBP": 0.8}
        return {v: {date.today() - timedelta(days=1): koersen[v]} for v in valuta}


APPLE, VODAFONE = "US0378331005", "GB00BH4HKS39"


@pytest.fixture
def nep(client):
    from app.api.opvolging import koersbronnen
    from app.main import app

    bronnen = NepBronnen()
    app.dependency_overrides[koersbronnen] = lambda: (bronnen, bronnen)
    return bronnen


def _bezit_overig(ingelogd, kid, overig):
    return ingelogd.post(
        f"/klanten/{kid}/bezit",
        json={
            "peildatum": date.today().isoformat(),
            "posities": [],
            "overig": overig,
            "kas_eur": 0,
        },
    )


def test_overig_bezit_gewaardeerd_met_marktkoers_in_euro(ingelogd, klant_id, nep, db):
    _advies(ingelogd, klant_id)
    _koers(db, WERELD, 100.0)
    _koers(db, GELD, 10.0)
    r = _bezit_overig(
        ingelogd,
        klant_id,
        [
            # 10 × $ 200 / 1,25 = € 1.600; de opgegeven waarde telt dan niet.
            {
                "omschrijving": "Apple",
                "isin": APPLE,
                "aantal": 10,
                "waarde_eur": 999,
                "categorie": "aandelen",
            },
            # 1.000 × 80 pence = £ 800 / 0,8 = € 1.000.
            {"omschrijving": "Vodafone", "isin": VODAFONE, "aantal": 1000, "categorie": "aandelen"},
        ],
    )
    assert r.status_code == 201, r.text
    assert sorted(nep.gezocht) == sorted([APPLE, VODAFONE])
    o = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    overig = {x["omschrijving"]: x for x in o["waardering"]["overig"]}
    assert overig["Apple"]["waarde"] == pytest.approx(1600) and overig["Apple"]["bron"] == "koers"
    assert overig["Apple"]["koers"] == pytest.approx(160)
    assert overig["Vodafone"]["waarde"] == pytest.approx(1000)
    assert o["waardering"]["totaal"] == pytest.approx(2600)
    # Verkoop tegen de marktkoers: het aantal is bekend en het bedrag geen schatting.
    verkoop = {t["naam"]: t for t in o["herbalancering"]["transacties"] if t["actie"] == "verkoop"}
    assert verkoop["Apple"]["aantal"] == 10 and not verkoop["Apple"]["geschat"]


def test_zonder_koers_geldt_de_opgegeven_waarde(ingelogd, klant_id, client):
    from app.api.opvolging import koersbronnen
    from app.main import app

    _advies(ingelogd, klant_id)
    for bronnen, verwacht in [
        (NepBronnen(mislukt=True), "opgegeven"),
        (NepBronnen(koersdatum=date.today() - timedelta(days=30)), "opgegeven"),
    ]:
        app.dependency_overrides[koersbronnen] = lambda b=bronnen: (b, b)
        r = _bezit_overig(
            ingelogd,
            klant_id,
            [
                {
                    "omschrijving": "Apple",
                    "isin": APPLE,
                    "aantal": 10,
                    "waarde_eur": 1500,
                    "categorie": "aandelen",
                }
            ],
        )
        assert r.status_code == 201
        ingelogd.post(f"/klanten/{klant_id}/koersen")
        x = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()["waardering"]["overig"][0]
        assert (x["bron"], x["waarde"]) == (verwacht, 1500)


def test_zonder_koers_en_zonder_waarde_geen_voorstel(ingelogd, klant_id, client):
    from app.api.opvolging import koersbronnen
    from app.main import app

    _advies(ingelogd, klant_id)
    b = NepBronnen(mislukt=True)
    app.dependency_overrides[koersbronnen] = lambda: (b, b)
    r = _bezit_overig(
        ingelogd,
        klant_id,
        [{"omschrijving": "Apple", "isin": APPLE, "aantal": 10, "categorie": "aandelen"}],
    )
    assert r.status_code == 201
    o = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()
    assert o["waardering"]["overig"][0]["bron"] == "geen"
    assert "geen_koers" in codes(o) and o["herbalancering"] is None


def test_overig_zonder_waarde_en_zonder_aantal_geweigerd(ingelogd, klant_id, nep):
    r = _bezit_overig(
        ingelogd, klant_id, [{"omschrijving": "Apple", "isin": APPLE, "categorie": "aandelen"}]
    )
    assert r.status_code == 422 and "waarde op, of een ISIN met het aantal" in r.json()["detail"]


def test_koersen_opnieuw_ophalen(ingelogd, klant_id, nep):
    _bezit_overig(
        ingelogd,
        klant_id,
        [{"omschrijving": "Apple", "isin": APPLE, "aantal": 10, "categorie": "aandelen"}],
    )
    r = ingelogd.post(f"/klanten/{klant_id}/koersen").json()
    assert r == {"opgehaald": 1, "fouten": []}


def test_verouderde_koers_wordt_bij_opslaan_vernieuwd(ingelogd, klant_id, client):
    from app.api.opvolging import koersbronnen
    from app.main import app

    oud = NepBronnen(koersdatum=date.today() - timedelta(days=30))
    app.dependency_overrides[koersbronnen] = lambda: (oud, oud)
    apple = [
        {
            "omschrijving": "Apple",
            "isin": APPLE,
            "aantal": 10,
            "waarde_eur": 1500,
            "categorie": "aandelen",
        }
    ]
    _bezit_overig(ingelogd, klant_id, apple)
    nieuw = NepBronnen()
    app.dependency_overrides[koersbronnen] = lambda: (nieuw, nieuw)
    _bezit_overig(ingelogd, klant_id, apple)
    _advies(ingelogd, klant_id)
    x = ingelogd.get(f"/klanten/{klant_id}/opvolging").json()["waardering"]["overig"][0]
    assert x["bron"] == "koers" and x["waarde"] == pytest.approx(1600)
