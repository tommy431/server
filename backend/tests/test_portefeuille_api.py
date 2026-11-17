from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.data.universum import laad_universum
from app.models import Adviseur, Instrument, Logboek
from app.security import hash_wachtwoord
from tests.conftest import WACHTWOORD
from tests.test_klanten import antwoorden, profiel

WERELD, EM, KLEIN, SRI = "IE00B4L5Y983", "IE00BKM4GZ66", "IE00BF4RFH31", "IE00BYX2JD69"
GELD, ZORG = "LU0290358497", "IE00BM67HK77"


@pytest.fixture
def klant_id(ingelogd, db):
    tekst = (Path(__file__).parent.parent / "data" / "universum.csv").read_text("utf-8")
    laad_universum(db, tekst)
    db.commit()
    kid = ingelogd.post("/klanten", json={"naam": "Jan Jansen"}).json()["id"]
    # Bereidheid en capaciteit 50 → neutraal; geen duurzaamheidswensen.
    a = antwoorden(2, 2) | {"daling": 1, "verlies": 1, "buffer": 1, "inkomen": 1}
    r = ingelogd.post(
        f"/klanten/{kid}/profielen",
        json=profiel(antwoorden=a, duurzaamheid="geen", uitsluitingen=[], inleg_eur=100000),
    )
    assert r.json()["risicoprofiel"] == "neutraal"
    return kid


def pad(kid, deel):
    return f"/klanten/{kid}/portefeuille/{deel}"


def gewichten(resultaat):
    return {p["isin"]: p["gewicht"] for p in resultaat["posities"]}


def als_invoer(posities: dict[str, int]):
    return [{"isin": i, "gewicht": g} for i, g in posities.items()]


def test_voorstel_volgt_risicoprofiel_en_slaat_niets_op(ingelogd, klant_id):
    r = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    assert r["risicoprofiel"] == "neutraal" and r["klantprofiel_versie"] == 1
    assert r["banden"]["aandelen"] == {"streef": 50, "minimum": 40, "maximum": 60}
    assert gewichten(r)[WERELD] == 3900 and sum(gewichten(r).values()) == 10000
    d = r["doorrekening"]
    assert d["per_categorie"] == {
        "aandelen": 5000,
        "obligaties": 3800,
        "vastgoed": 500,
        "grondstoffen": 200,
        "liquiditeiten": 500,
    }
    # Kosten in euro's volgen uit de inleg van € 100.000.
    assert d["kosten_eur_per_jaar"] == round(100000 * d["kosten_pct"] / 100)
    assert 0.15 < d["kosten_pct"] < 0.30
    # Het meegeleverde universum heeft nog ongecontroleerde kosten: dat wordt gemeld.
    assert [b["code"] for b in d["bevindingen"]] == ["kosten_ongeverifieerd"]
    assert r["beperkingen"]["max_breed_instrument"] == 7000
    assert ingelogd.get(pad(klant_id, "versies")).json() == []


def test_voorstel_houdt_rekening_met_uitsluitingen_en_duurzaamheid(ingelogd, klant_id):
    uit = [{"soort": "regio", "waarde": "opkomende-markten", "reden": "Wens klant"}]
    r = ingelogd.post(pad(klant_id, "voorstel"), json={"uitsluitingen": uit}).json()
    assert EM not in gewichten(r) and sum(gewichten(r).values()) == 10000
    assert r["uitsluitingen"] == uit
    codes = [b["code"] for b in r["doorrekening"]["bevindingen"]]
    assert codes == ["startselectie_aangepast", "kosten_ongeverifieerd", "uitsluiting_op_label"]

    ingelogd.post(
        f"/klanten/{klant_id}/profielen",
        json=profiel(antwoorden=antwoorden(2, 2), duurzaamheid="sterk", uitsluitingen=["wapens"]),
    )
    r = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    assert r["klantprofiel_versie"] == 2 and r["risicoprofiel"] == "offensief"
    assert SRI in gewichten(r) and WERELD not in gewichten(r)
    assert "duurzaamheid" in [b["code"] for b in r["doorrekening"]["bevindingen"]]


def test_doorrekenen_meldt_afwijking_direct(ingelogd, klant_id):
    posities = gewichten(ingelogd.post(pad(klant_id, "voorstel"), json={}).json())
    # 15 procentpunt van obligaties naar aandelen: aandelen 65% > 60%, obligaties 23% < 25%.
    posities[WERELD] += 1500
    posities["IE00BDBRDM35"] -= 1500
    r = ingelogd.post(pad(klant_id, "doorrekenen"), json={"posities": als_invoer(posities)}).json()
    meldingen = [
        b["melding"] for b in r["doorrekening"]["bevindingen"] if b["ernst"] == "afwijking"
    ]
    assert meldingen == [
        "Aandelen weegt 65%; het risicoprofiel staat 40% tot 60% toe",
        "Obligaties weegt 23%; het risicoprofiel staat 25% tot 50% toe",
    ]
    assert r["doorrekening"]["zakelijke_waarden"] == 7200


def test_vastleggen_versies_en_logboek(ingelogd, klant_id, db, adviseur):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    r = ingelogd.post(pad(klant_id, "versies"), json={"posities": v["posities"]})
    assert r.status_code == 201
    eerste = r.json()
    assert (eerste["versie"], eerste["toelichting"], eerste["klantprofiel_versie"]) == (1, None, 1)
    assert gewichten(eerste) == gewichten(v)
    assert [p["gewicht"] for p in eerste["posities"]] == sorted(
        (p["gewicht"] for p in eerste["posities"]), reverse=True
    )

    posities = gewichten(v)
    posities[WERELD] -= 500
    posities[ZORG] = 500
    uit = [{"soort": "sector", "waarde": "energie", "reden": "Wens klant"}]
    r = ingelogd.post(
        pad(klant_id, "versies"), json={"posities": als_invoer(posities), "uitsluitingen": uit}
    )
    assert r.status_code == 201 and r.json()["versie"] == 2

    lijst = ingelogd.get(pad(klant_id, "versies")).json()
    assert [x["versie"] for x in lijst] == [2, 1]
    assert gewichten(lijst[0])[ZORG] == 500 and lijst[0]["uitsluitingen"] == uit
    assert lijst[0]["doorrekening"]["per_sector"]["gezondheidszorg"] == 500
    regels = db.scalars(select(Logboek).where(Logboek.actie == "portefeuille_vastgelegd")).all()
    assert [x.details for x in regels] == [
        {"versie": 1, "risicoprofiel": "neutraal", "afwijkingen": []},
        {"versie": 2, "risicoprofiel": "neutraal", "afwijkingen": []},
    ]
    assert {x.adviseur_id for x in regels} == {adviseur.id}


def test_afwijking_vereist_toelichting_en_wordt_versleuteld_bewaard(ingelogd, klant_id, db):
    posities = gewichten(ingelogd.post(pad(klant_id, "voorstel"), json={}).json())
    posities[WERELD] += 1500
    posities["IE00BDBRDM35"] -= 1500
    body = {"posities": als_invoer(posities)}
    r = ingelogd.post(pad(klant_id, "versies"), json=body)
    assert r.status_code == 422
    assert r.json()["detail"][0].startswith("De portefeuille wijkt af")
    assert len(r.json()["detail"]) == 3
    assert (
        ingelogd.post(pad(klant_id, "versies"), json=body | {"toelichting": "  "}).status_code
        == 422
    )
    assert ingelogd.get(pad(klant_id, "versies")).json() == []

    r = ingelogd.post(pad(klant_id, "versies"), json=body | {"toelichting": "Geheime reden"})
    assert r.status_code == 201 and r.json()["toelichting"] == "Geheime reden"
    opgeslagen = [b["code"] for b in r.json()["doorrekening"]["bevindingen"]]
    assert opgeslagen.count("buiten_risicoprofiel") == 2
    ruw = db.execute(text("select toelichting from portefeuille")).scalar_one()
    assert "Geheim" not in ruw
    regel = db.scalar(select(Logboek).where(Logboek.actie == "portefeuille_vastgelegd"))
    assert regel.details["afwijkingen"] == ["buiten_risicoprofiel", "buiten_risicoprofiel"]
    assert "Geheim" not in str(regel.details)


@pytest.mark.parametrize(
    "wijzig",
    [
        lambda p: p.update({GELD: p[GELD] - 10}),  # totaal 99,9%
        lambda p: p.update({"XX0000000000": 10, GELD: p[GELD] - 10}),  # onbekend instrument
        lambda p: p.update({ZORG: 0}),  # gewicht nul
        lambda p: p.clear(),
    ],
)
def test_fouten_blokkeren_vastleggen_ook_met_toelichting(ingelogd, klant_id, wijzig):
    posities = gewichten(ingelogd.post(pad(klant_id, "voorstel"), json={}).json())
    wijzig(posities)
    r = ingelogd.post(
        pad(klant_id, "versies"),
        json={"posities": als_invoer(posities), "toelichting": "Toch doen"},
    )
    assert r.status_code == 422
    assert ingelogd.get(pad(klant_id, "versies")).json() == []


def test_uitgesloten_instrument_in_portefeuille_blokkeert(ingelogd, klant_id):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    uit = [{"soort": "instrument", "waarde": EM}]
    r = ingelogd.post(
        pad(klant_id, "versies"),
        json={"posities": v["posities"], "uitsluitingen": uit, "toelichting": "x"},
    )
    assert r.status_code == 422 and "valt onder een uitsluiting" in r.json()["detail"][0]


@pytest.mark.parametrize(
    "uitsluiting",
    [
        {"soort": "regio", "waarde": "wereld"},
        {"soort": "sector", "waarde": "breed"},
        {"soort": "sector", "waarde": "europa"},
        {"soort": "instrument", "waarde": "XX0000000000"},
        {"soort": "land", "waarde": "europa"},
    ],
)
def test_ongeldige_uitsluiting_geweigerd(ingelogd, klant_id, uitsluiting):
    r = ingelogd.post(pad(klant_id, "voorstel"), json={"uitsluitingen": [uitsluiting]})
    assert r.status_code == 422


def test_dubbele_invoer_geweigerd(ingelogd, klant_id):
    dubbel = [{"soort": "sector", "waarde": "energie"}] * 2
    assert (
        ingelogd.post(pad(klant_id, "voorstel"), json={"uitsluitingen": dubbel}).status_code == 422
    )
    posities = [{"isin": WERELD, "gewicht": 5000}] * 2
    r = ingelogd.post(pad(klant_id, "doorrekenen"), json={"posities": posities})
    assert r.status_code == 422


def test_zonder_profiel_of_bij_archief_geen_portefeuille(ingelogd, klant_id):
    leeg = ingelogd.post("/klanten", json={"naam": "Zonder profiel"}).json()["id"]
    assert ingelogd.post(pad(leeg, "voorstel"), json={}).status_code == 409
    assert ingelogd.get(pad(leeg, "versies")).json() == []

    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    ingelogd.put(f"/klanten/{klant_id}/archief", json={"gearchiveerd": True})
    r = ingelogd.post(pad(klant_id, "versies"), json={"posities": v["posities"]})
    assert r.status_code == 409


def test_vastgelegde_versie_wijzigt_niet_als_model_of_fonds_later_wijzigt(ingelogd, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    ingelogd.post(pad(klant_id, "versies"), json={"posities": v["posities"]})
    voor = ingelogd.get(pad(klant_id, "versies")).json()[0]

    regels = [
        {"categorie": "aandelen", "streef": 20, "minimum": 10, "maximum": 30},
        {"categorie": "obligaties", "streef": 70, "minimum": 60, "maximum": 80},
        {"categorie": "vastgoed", "streef": 5, "minimum": 0, "maximum": 10},
        {"categorie": "grondstoffen", "streef": 0, "minimum": 0, "maximum": 5},
        {"categorie": "liquiditeiten", "streef": 5, "minimum": 0, "maximum": 15},
    ]
    assert ingelogd.put("/risicoprofielen/neutraal/allocatie", json=regels).status_code == 200
    db.scalar(select(Instrument).where(Instrument.isin == WERELD)).lopende_kosten = 2.0
    db.commit()

    na = ingelogd.get(pad(klant_id, "versies")).json()[0]
    assert na["banden"] == voor["banden"] and na["doorrekening"] == voor["doorrekening"]
    # Een nieuwe doorrekening van dezelfde posities gebruikt wel de nieuwe gegevens.
    nu = ingelogd.post(pad(klant_id, "doorrekenen"), json={"posities": voor["posities"]}).json()
    assert nu["banden"]["aandelen"]["maximum"] == 30
    assert nu["doorrekening"]["kosten_pct"] > voor["doorrekening"]["kosten_pct"] + 0.5
    assert "buiten_risicoprofiel" in [b["code"] for b in nu["doorrekening"]["bevindingen"]]


def test_andere_adviseur_en_niet_ingelogd_hebben_geen_toegang(ingelogd, client, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    ingelogd.post(pad(klant_id, "versies"), json={"posities": v["posities"]})
    db.add(
        Adviseur(email="ander@voorbeeld.nl", naam="A", wachtwoord_hash=hash_wachtwoord(WACHTWOORD))
    )
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "ander@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    body = {"posities": v["posities"]}
    for methode, deel in [
        ("post", "voorstel"),
        ("post", "doorrekenen"),
        ("post", "versies"),
        ("get", "versies"),
    ]:
        r = client.request(
            methode, pad(klant_id, deel), json=body, headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 404, deel
        assert (
            client.request(
                methode, pad(klant_id, deel), json=body, headers={"Authorization": ""}
            ).status_code
            == 401
        )
    assert len(ingelogd.get(pad(klant_id, "versies")).json()) == 1


# --- historische analyse ---------------------------------------------------------------


def vul_koersen(db, per_jaar=0.05, begin=None, isins=None):
    """Zet voor de gevraagde (of alle) instrumenten een gelijkmatig groeiende dagreeks."""
    from datetime import UTC, date, datetime, timedelta

    from sqlalchemy import delete, insert

    from app.models import Koers

    eind = date.today()
    begin = begin or eind.replace(year=eind.year - 12)
    nu = datetime.now(UTC)
    for instrument in db.scalars(select(Instrument)).all():
        if isins is not None and instrument.isin not in isins:
            continue
        db.execute(delete(Koers).where(Koers.instrument_id == instrument.id))
        db.execute(
            insert(Koers),
            [
                {
                    "instrument_id": instrument.id,
                    "datum": begin + timedelta(days=i),
                    "slot": 100 * (1 + per_jaar) ** (i / 365.25),
                    "slot_gecorrigeerd": 100 * (1 + per_jaar) ** (i / 365.25),
                    "bron": "test",
                    "opgehaald_op": nu,
                }
                for i in range((eind - begin).days + 1)
            ],
        )
    db.commit()


def test_analyse_met_benchmark_en_risicovrij(ingelogd, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    vul_koersen(db, isins={p["isin"] for p in v["posities"]})
    r = ingelogd.post(pad(klant_id, "analyse"), json={"posities": v["posities"]})
    assert r.status_code == 200
    uit = r.json()
    assert [(b["categorie"], b["gewicht"]) for b in uit["benchmark"]] == [
        ("aandelen", 50),
        ("obligaties", 38),
        ("vastgoed", 5),
        ("grondstoffen", 2),
        ("liquiditeiten", 5),
    ]
    # Zonder opgehaalde ECB-rente valt de analyse terug op het geldmarktfonds.
    assert (
        uit["risicovrij"] == "het geldmarktfonds Xtrackers II EUR Overnight Rate Swap UCITS ETF 1C"
    )
    a = uit["analyse"]
    assert a["waarschuwingen"] == [] and len(a["instrumenten"]) == 8
    assert [p["code"] for p in a["perioden"]] == ["1j", "3j", "5j", "10j", "start"]
    for p in a["perioden"]:
        assert p["beschikbaar"]
        # Alles groeit 5% per jaar, dus portefeuille, benchmark en risicovrij ook.
        assert p["portefeuille"]["rendement_per_jaar"] == pytest.approx(0.05, abs=2e-4)
        assert p["benchmark"]["rendement_per_jaar"] == pytest.approx(0.05, abs=2e-4)
        assert p["risicovrij_per_jaar"] == pytest.approx(0.05, abs=2e-4)
    assert len(a["kalenderjaren"]) == 11
    assert ingelogd.get(pad(klant_id, "versies")).json() == []


def test_analyse_zonder_koersen_en_met_korte_historie(ingelogd, klant_id, db):
    from datetime import date

    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    a = ingelogd.post(pad(klant_id, "analyse"), json={"posities": v["posities"]}).json()["analyse"]
    assert a["peildatum"] is None and a["perioden"] == []
    assert a["waarschuwingen"][0].startswith("Geen koersen beschikbaar voor:")

    vul_koersen(db)
    vandaag = date.today()
    vul_koersen(db, begin=vandaag.replace(year=vandaag.year - 2), isins={EM})
    a = ingelogd.post(pad(klant_id, "analyse"), json={"posities": v["posities"]}).json()["analyse"]
    beschikbaar = {p["code"]: p["beschikbaar"] for p in a["perioden"]}
    assert beschikbaar == {"1j": True, "3j": False, "5j": False, "10j": False, "start": True}
    reden = next(p["reden"] for p in a["perioden"] if p["code"] == "3j")
    assert reden.startswith(
        "iShares Core MSCI EM IMI UCITS ETF (Acc) heeft bruikbare koersen vanaf"
    )


def test_analyse_weigert_portefeuille_die_niet_op_100_uitkomt(ingelogd, klant_id):
    posities = gewichten(ingelogd.post(pad(klant_id, "voorstel"), json={}).json())
    posities[GELD] -= 100
    r = ingelogd.post(pad(klant_id, "analyse"), json={"posities": als_invoer(posities)})
    assert r.status_code == 422 and "99%" in r.json()["detail"][0]


def test_vastgelegde_versie_bewaart_analyse_ook_als_koersen_later_wijzigen(ingelogd, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    vul_koersen(db, per_jaar=0.05)
    r = ingelogd.post(pad(klant_id, "versies"), json={"posities": v["posities"]})
    bewaard = r.json()["analyse"]
    assert bewaard["analyse"]["perioden"][0]["portefeuille"]["rendement_per_jaar"] == pytest.approx(
        0.05, abs=2e-4
    )
    assert bewaard["benchmark"][0] == {
        "categorie": "aandelen",
        "naam": "iShares Core MSCI World UCITS ETF (Acc)",
        "gewicht": 50,
    }
    vul_koersen(db, per_jaar=0.20)
    assert ingelogd.get(pad(klant_id, "versies")).json()[0]["analyse"] == bewaard
    nu = ingelogd.post(pad(klant_id, "analyse"), json={"posities": v["posities"]}).json()
    assert nu["analyse"]["perioden"][0]["portefeuille"]["rendement_per_jaar"] > 0.19


def test_analyse_alleen_voor_eigen_klant(ingelogd, client, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    db.add(
        Adviseur(email="ander@voorbeeld.nl", naam="A", wachtwoord_hash=hash_wachtwoord(WACHTWOORD))
    )
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "ander@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    body = {"posities": v["posities"]}
    r = client.post(
        pad(klant_id, "analyse"), json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404
    assert (
        client.post(pad(klant_id, "analyse"), json=body, headers={"Authorization": ""}).status_code
        == 401
    )


def test_ecb_rente_heeft_voorrang_als_risicovrij_rendement(ingelogd, klant_id, db):
    from datetime import UTC, datetime, timedelta

    from app.models import Rente

    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    vul_koersen(db, per_jaar=0.05)
    eind = date.today()
    begin = eind.replace(year=eind.year - 12)
    db.add_all(
        Rente(
            datum=begin + timedelta(days=i),
            waarde=1.0,
            reeks="ESTR",
            bron="test",
            opgehaald_op=datetime.now(UTC),
        )
        for i in range((eind - begin).days + 1)
    )
    db.commit()
    uit = ingelogd.post(pad(klant_id, "analyse"), json={"posities": v["posities"]}).json()
    assert uit["risicovrij"].startswith("de kortlopende eurorente van de ECB")
    # 1% per jaar act/360, dagelijks samengesteld: (1 + 0,01/360)^365,25 − 1 ≈ 1,0197%.
    vijf = next(p for p in uit["analyse"]["perioden"] if p["code"] == "5j")
    assert vijf["risicovrij_per_jaar"] == pytest.approx((1 + 0.01 / 360) ** 365.25 - 1, abs=1e-5)


def test_verlengen_met_vervanger_is_gemarkeerd_en_staat_standaard_uit(ingelogd, klant_id, db):
    v = ingelogd.post(pad(klant_id, "voorstel"), json={}).json()
    vul_koersen(db)
    vandaag = date.today()
    vul_koersen(db, begin=vandaag.replace(year=vandaag.year - 4), isins={KLEIN})
    body = {"posities": v["posities"]}

    zonder = ingelogd.post(pad(klant_id, "analyse"), json=body).json()["analyse"]
    tien = next(p for p in zonder["perioden"] if p["code"] == "10j")
    assert not tien["beschikbaar"] and "Small Cap" in tien["reden"]

    met = ingelogd.post(pad(klant_id, "analyse"), json=body | {"verlengen": True}).json()["analyse"]
    tien = next(p for p in met["perioden"] if p["code"] == "10j")
    assert tien["beschikbaar"] and tien["gesimuleerd"]
    assert not next(p for p in met["perioden"] if p["code"] == "3j")["gesimuleerd"]
    klein = next(h for h in met["instrumenten"] if h["isin"] == KLEIN)
    # Vervanger: zelfde categorie, regio en sector, met de langste historie.
    wereldfondsen = {
        i.naam
        for i in db.scalars(select(Instrument))
        if (i.categorie, i.regio, i.sector) == ("aandelen", "wereld", "breed") and i.isin != KLEIN
    }
    assert klein["vervanger"] in wereldfondsen
    assert klein["eigen_koersen_vanaf"] == str(vandaag.replace(year=vandaag.year - 4))
    assert any("gesimuleerd, geen werkelijk behaald resultaat" in w for w in met["waarschuwingen"])
    # Fondsen met tien jaar eigen historie krijgen geen vervanger.
    assert [h["isin"] for h in met["instrumenten"] if h["vervanger"]] == [KLEIN]
