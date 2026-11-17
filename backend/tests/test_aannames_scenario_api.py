import copy
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Logboek
from app.standaarden import STANDAARD_AANNAMES, STANDAARD_CORRELATIES
from tests.test_klanten import antwoorden, profiel
from tests.test_portefeuille_api import GELD, als_invoer, gewichten, klant_id, pad  # noqa: F401


def aannames_in(**wijzig):
    basis = {
        "bron": "Testbron",
        "peildatum": "2026-11-01",
        "categorieen": copy.deepcopy(STANDAARD_AANNAMES),
        "correlaties": copy.deepcopy(STANDAARD_CORRELATIES),
        "inflatie": 0.02,
    }
    return basis | wijzig


def test_standaardaannames_staan_klaar_en_zijn_als_voorbeeld_gemarkeerd(ingelogd):
    a = ingelogd.get("/aannames").json()
    assert a["categorieen"]["aandelen"] == {"rendement": 0.065, "volatiliteit": 0.16}
    assert (
        a["correlaties"]["vastgoed"]["aandelen"] == a["correlaties"]["aandelen"]["vastgoed"] == 0.7
    )
    assert a["bron"].startswith("Voorbeeldwaarden, niet afkomstig uit een gepubliceerde bron")


def test_nieuwe_versie_vastleggen_met_geschiedenis_en_logboek(ingelogd, db, adviseur):
    nieuw = aannames_in()
    nieuw["categorieen"]["aandelen"]["rendement"] = 0.06
    r = ingelogd.post("/aannames", json=nieuw)
    assert r.status_code == 201 and r.json()["bron"] == "Testbron"
    assert ingelogd.get("/aannames").json()["categorieen"]["aandelen"]["rendement"] == 0.06
    assert [x["id"] for x in ingelogd.get("/aannames/geschiedenis").json()] == [r.json()["id"], 1]
    regel = db.scalar(select(Logboek).where(Logboek.actie == "aannames_vastgelegd"))
    assert regel.adviseur_id == adviseur.id and regel.details["bron"] == "Testbron"


def onmogelijk():
    c = copy.deepcopy(STANDAARD_CORRELATIES)
    for a, b, rho in [
        ("aandelen", "vastgoed", 0.95),
        ("aandelen", "obligaties", 0.95),
        ("obligaties", "vastgoed", -0.95),
    ]:
        c[a][b] = c[b][a] = rho
    return c


@pytest.mark.parametrize(
    ("wijzig", "deel"),
    [
        ({"correlaties": onmogelijk()}, "positief semidefiniet"),
        ({"inflatie": 0.2}, "Inflatie"),
        ({"bron": ""}, None),
        ({"peildatum": str(date.today() + timedelta(days=1))}, "toekomst"),
        ({"categorieen": {"aandelen": {"rendement": 0.06, "volatiliteit": 0.16}}}, "precies deze"),
    ],
)
def test_ongeldige_aannames_geweigerd(ingelogd, wijzig, deel):
    r = ingelogd.post("/aannames", json=aannames_in(**wijzig))
    assert r.status_code == 422
    if deel:
        assert any(deel in f for f in r.json()["detail"])
    assert len(ingelogd.get("/aannames/geschiedenis").json()) == 1


def test_asymmetrische_en_onvolledige_correlaties_geweigerd(ingelogd):
    c = copy.deepcopy(STANDAARD_CORRELATIES)
    c["aandelen"]["obligaties"] = 0.5
    assert (
        "niet symmetrisch"
        in ingelogd.post("/aannames", json=aannames_in(correlaties=c)).json()["detail"][0]
    )
    c = copy.deepcopy(STANDAARD_CORRELATIES)
    del c["aandelen"]["obligaties"]
    assert ingelogd.post("/aannames", json=aannames_in(correlaties=c)).json()["detail"] == [
        "De correlatiematrix is onvolledig"
    ]


def test_scenario_voor_portefeuille_gebruikt_profiel_en_kosten(ingelogd, klant_id):  # noqa: F811
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    r = ingelogd.post(pad(klant_id, "scenario"), json={"posities": v["posities"]})
    assert r.status_code == 200
    uit = r.json()
    s = uit["scenario"]
    # Profiel uit de fixture: inleg 100.000, 250 per maand, 15 jaar, doel 200.000.
    assert (s["inleg"], s["storting_per_maand"], s["horizon_jaren"], s["doelvermogen"]) == (
        100000,
        250,
        15,
        200000,
    )
    assert s["paden"] == 10_000 and len(s["jaren"]) == 16
    assert s["jaren"][-1]["ingelegd"] == 100000 + 250 * 12 * 15
    assert uit["gewichten"] == {
        "aandelen": 0.5,
        "obligaties": 0.38,
        "vastgoed": 0.05,
        "grondstoffen": 0.02,
        "liquiditeiten": 0.05,
    }
    assert s["kosten_pct"] == pytest.approx(uit["lopende_kosten_pct"])
    assert 0.04 < s["verwacht_rendement"] < 0.06 and 0.06 < s["verwachte_volatiliteit"] < 0.11
    assert 0 < s["kans_doel_reeel"] < s["kans_doel_nominaal"] < 1
    assert s["kosten_effect_mediaan"] > 0 and s["inflatie_effect_mediaan"] > 0
    assert uit["aannames"]["id"] == 1

    duur = ingelogd.post(
        pad(klant_id, "scenario"), json={"posities": v["posities"], "overige_kosten_pct": 1.0}
    ).json()
    assert duur["scenario"]["kosten_pct"] == pytest.approx(uit["lopende_kosten_pct"] + 1.0)
    assert duur["scenario"]["jaren"][-1]["nominaal"][1] < s["jaren"][-1]["nominaal"][1]
    assert duur["scenario"]["kans_doel_nominaal"] < s["kans_doel_nominaal"]
    assert (
        ingelogd.post(
            pad(klant_id, "scenario"), json={"posities": v["posities"], "overige_kosten_pct": 6}
        ).status_code
        == 422
    )


def test_scenario_weigert_ongeldige_portefeuille(ingelogd, klant_id):  # noqa: F811
    posities = gewichten(ingelogd.post(pad(klant_id, "voorstel"), json={}).json())
    posities[GELD] -= 100
    assert (
        ingelogd.post(
            pad(klant_id, "scenario"), json={"posities": als_invoer(posities)}
        ).status_code
        == 422
    )


def test_versie_bewaart_scenario_en_aannames_ook_na_nieuwe_aannames(ingelogd, klant_id):  # noqa: F811
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    r = ingelogd.post(
        pad(klant_id, "versies"), json={"posities": v["posities"], "overige_kosten_pct": 0.5}
    )
    bewaard = r.json()["scenario"]
    assert bewaard["overige_kosten_pct"] == 0.5 and bewaard["aannames"]["id"] == 1
    nieuw = aannames_in()
    nieuw["categorieen"]["aandelen"]["rendement"] = 0.02
    ingelogd.post("/aannames", json=nieuw)
    assert ingelogd.get(pad(klant_id, "versies")).json()[0]["scenario"] == bewaard
    nu = ingelogd.post(pad(klant_id, "scenario"), json={"posities": v["posities"]}).json()
    assert nu["aannames"]["id"] == 2
    assert nu["scenario"]["verwacht_rendement"] < bewaard["scenario"]["verwacht_rendement"]


def test_hogere_horizon_in_profiel_geeft_langere_reeks(ingelogd, klant_id):  # noqa: F811
    ingelogd.post(
        f"/klanten/{klant_id}/profielen",
        json=profiel(antwoorden=antwoorden(2, 2), horizon_jaren=30),
    )
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    s = ingelogd.post(pad(klant_id, "scenario"), json={"posities": v["posities"]}).json()[
        "scenario"
    ]
    assert s["horizon_jaren"] == 30 and len(s["jaren"]) == 31


def test_zonder_inloggen_geen_toegang(client):
    for methode, p in [
        ("get", "/aannames"),
        ("get", "/aannames/geschiedenis"),
        ("post", "/aannames"),
        ("post", "/klanten/1/portefeuille/scenario"),
    ]:
        assert client.request(methode, p).status_code == 401


def test_crisisschok_en_heffing_in_scenario(ingelogd, klant_id):  # noqa: F811
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    uit = ingelogd.post(pad(klant_id, "scenario"), json={"posities": v["posities"]}).json()
    # Neutraal: 50% × −50% + 38% × 5% + 5% × −60% + 2% × −50% + 5% × 1% = −27,05%.
    assert uit["crisis_rendement"] == pytest.approx(-0.2705)
    assert uit["crisis_verlies_eur"] == 27050  # op de inleg van 100.000
    assert uit["aannames"]["stress"]["aandelen"] == -0.5

    met = ingelogd.post(
        pad(klant_id, "scenario"), json={"posities": v["posities"], "belasting_pct": 1.0}
    ).json()
    assert met["belasting_pct"] == 1.0
    assert met["scenario"]["belasting_effect_mediaan"] > 0
    assert met["scenario"]["jaren"][-1]["nominaal"][1] < uit["scenario"]["jaren"][-1]["nominaal"][1]
    assert uit["scenario"]["belasting_effect_mediaan"] == pytest.approx(0.0)
    assert (
        ingelogd.post(
            pad(klant_id, "scenario"), json={"posities": v["posities"], "belasting_pct": 6}
        ).status_code
        == 422
    )


def test_crisisschok_instellen_en_valideren(ingelogd):
    nieuw = aannames_in(
        stress={
            "aandelen": -0.4,
            "obligaties": 0.0,
            "vastgoed": -0.5,
            "grondstoffen": -0.3,
            "liquiditeiten": 0.0,
        }
    )
    assert ingelogd.post("/aannames", json=nieuw).status_code == 201
    assert ingelogd.get("/aannames").json()["stress"]["aandelen"] == -0.4
    r = ingelogd.post("/aannames", json=aannames_in(stress={**nieuw["stress"], "aandelen": -1.0}))
    assert r.status_code == 422 and "buiten −95% tot +50%" in r.json()["detail"][0]
    r = ingelogd.post("/aannames", json=aannames_in(stress={"aandelen": -0.4}))
    assert r.status_code == 422 and "crisisschok" in r.json()["detail"][0]


def test_grondslag_van_het_doelvermogen_wordt_bewaard_en_doorgegeven(ingelogd, klant_id):  # noqa: F811
    r = ingelogd.post(
        f"/klanten/{klant_id}/profielen",
        json=profiel(antwoorden=antwoorden(2, 2), doel_in_koopkracht=True),
    )
    assert r.json()["doel_in_koopkracht"] is True
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    assert (
        ingelogd.post(pad(klant_id, "scenario"), json={"posities": v["posities"]}).json()[
            "doel_in_koopkracht"
        ]
        is True
    )
