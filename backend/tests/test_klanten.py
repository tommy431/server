import pytest
from sqlalchemy import select, text

from app.models import CATEGORIEEN, Adviseur, Logboek
from app.profiel import (
    RISICOPROFIELEN,
    STANDAARD_ALLOCATIES,
    VRAGEN,
    bereken,
    controleer_allocatie,
)
from app.security import hash_wachtwoord
from tests.conftest import WACHTWOORD

CODES = [v["code"] for v in VRAGEN]


def antwoorden(bereidheid=2, capaciteit=2, kennis=2):
    waarde = {"bereidheid": bereidheid, "capaciteit": capaciteit, "kennis": kennis}
    return {v["code"]: waarde[v["dimensie"]] for v in VRAGEN}


def profiel(**extra):
    return {
        "doel": "Aanvulling pensioen",
        "horizon_jaren": 15,
        "inleg_eur": 50000,
        "storting_per_maand_eur": 250,
        "doelvermogen_eur": 200000,
        "antwoorden": antwoorden(),
        "duurzaamheid": "enigszins",
        "uitsluitingen": ["wapens", "tabak"],
    } | extra


# --- berekening ------------------------------------------------------------------------


def test_standaardallocaties_zijn_geldig_en_oplopend_in_aandelen():
    aandelen = []
    for code, _ in RISICOPROFIELEN:
        assert controleer_allocatie(STANDAARD_ALLOCATIES[code], CATEGORIEEN) == []
        aandelen.append(STANDAARD_ALLOCATIES[code]["aandelen"][0])
    assert aandelen == sorted(aandelen) and len(set(aandelen)) == 5


@pytest.mark.parametrize(
    ("punten", "score", "niveau"),
    [(0, 0, 1), (1, 33, 2), (2, 67, 4), (3, 100, 5)],
)
def test_score_en_niveau_bij_gelijke_antwoorden(punten, score, niveau):
    u = bereken(antwoorden(punten, punten, punten), 20)
    assert (u.score_bereidheid, u.score_capaciteit, u.score_kennis) == (score, score, score)
    assert u.niveau == niveau


def test_handmatig_nagerekend_voorbeeld():
    # Bereidheid 3+2+1+2 = 8 van 12 → 67 → niveau 4. Capaciteit 1+2+2+1 = 6 van 12 → 50 →
    # niveau 3. Horizon 8 jaar → hooguit niveau 4. De laagste, capaciteit, bepaalt: niveau 3.
    a = dict(zip(CODES, [3, 2, 1, 2, 1, 2, 2, 1, 0, 1, 0], strict=True))
    u = bereken(a, 8)
    assert (u.score_bereidheid, u.score_capaciteit, u.score_kennis) == (67, 50, 11)
    assert (u.niveau, u.bepalende_factor, u.lage_kennis) == (3, "capaciteit", True)


def test_voorzichtigste_factor_bepaalt():
    assert bereken(antwoorden(1, 3), 20).bepalende_factor == "bereidheid"
    assert bereken(antwoorden(3, 0), 20).niveau == 1
    kort = bereken(antwoorden(3, 3), 2)
    assert (kort.niveau, kort.bepalende_factor) == (1, "horizon")
    # Kennis verlaagt het profiel niet, maar wordt wel gesignaleerd.
    onervaren = bereken(antwoorden(3, 3, 0), 20)
    assert onervaren.niveau == 5 and onervaren.lage_kennis
    assert bereken(antwoorden(3, 3, 1), 20).lage_kennis  # score 33, net onder de grens
    assert not bereken(antwoorden(3, 3, 2), 20).lage_kennis


@pytest.mark.parametrize(
    ("jaren", "niveau"),
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3), (7, 4), (9, 4), (10, 5), (40, 5)],
)
def test_horizongrenzen(jaren, niveau):
    assert bereken(antwoorden(3, 3), jaren).niveau == niveau


@pytest.mark.parametrize(
    "fout",
    [
        {},
        {**antwoorden(), "extra": 1},
        {**antwoorden(), "daling": 4},
        {**antwoorden(), "daling": -1},
        {**antwoorden(), "daling": True},
        {k: v for k, v in antwoorden().items() if k != "daling"},
    ],
)
def test_ongeldige_antwoorden_geweigerd(fout):
    with pytest.raises(ValueError):
        bereken(fout, 10)


def test_horizon_onder_een_jaar_geweigerd():
    with pytest.raises(ValueError):
        bereken(antwoorden(), 0)


def test_controle_op_allocatie():
    goed = dict(STANDAARD_ALLOCATIES["neutraal"])
    assert controleer_allocatie({**goed, "aandelen": (51, 40, 60)}, CATEGORIEEN) == [
        "De streefgewichten tellen op tot 101% in plaats van 100%"
    ]
    assert len(controleer_allocatie({**goed, "aandelen": (50, 55, 60)}, CATEGORIEEN)) == 1
    assert len(controleer_allocatie({**goed, "aandelen": (50, 40, 101)}, CATEGORIEEN)) == 1
    zonder = {k: v for k, v in goed.items() if k != "vastgoed"}
    assert len(controleer_allocatie(zonder, CATEGORIEEN)) == 1


# --- klanten ---------------------------------------------------------------------------


def test_klant_aanmaken_wijzigen_en_archiveren(ingelogd, db):
    r = ingelogd.post(
        "/klanten",
        json={"naam": "  Jan Jansen ", "email": "Jan@Voorbeeld.nl", "geboortedatum": "1970-05-17"},
    )
    assert r.status_code == 201
    klant = r.json()
    assert (klant["naam"], klant["email"], klant["geboortedatum"]) == (
        "Jan Jansen",
        "jan@voorbeeld.nl",
        "1970-05-17",
    )
    assert klant["huidig_profiel"] is None and klant["gearchiveerd"] is False

    r = ingelogd.put(f"/klanten/{klant['id']}", json={"naam": "Jan Jansen", "email": None})
    assert r.json()["email"] is None and r.json()["geboortedatum"] is None

    ingelogd.post("/klanten", json={"naam": "anna de Vries"})
    assert [k["naam"] for k in ingelogd.get("/klanten").json()] == ["anna de Vries", "Jan Jansen"]

    ingelogd.put(f"/klanten/{klant['id']}/archief", json={"gearchiveerd": True})
    assert [k["naam"] for k in ingelogd.get("/klanten").json()] == ["anna de Vries"]
    archief = ingelogd.get("/klanten", params={"gearchiveerd": True}).json()
    assert [k["naam"] for k in archief] == ["Jan Jansen"]
    r = ingelogd.post(f"/klanten/{klant['id']}/profielen", json=profiel())
    assert r.status_code == 409

    acties = db.scalars(select(Logboek.actie).where(Logboek.entiteit == "klant")).all()
    assert acties == [
        "klant_aangemaakt",
        "klant_gewijzigd",
        "klant_aangemaakt",
        "klant_gearchiveerd",
    ]
    gewijzigd = db.scalar(select(Logboek).where(Logboek.actie == "klant_gewijzigd"))
    assert gewijzigd.details == {"velden": ["email", "geboortedatum"]}


def test_ongeldige_klantgegevens_geweigerd(ingelogd):
    assert ingelogd.post("/klanten", json={"naam": ""}).status_code == 422
    assert ingelogd.post("/klanten", json={"naam": "A", "email": "geen-adres"}).status_code == 422
    r = ingelogd.post("/klanten", json={"naam": "A", "geboortedatum": "17-05-1970"})
    assert r.status_code == 422


def test_persoonsgegevens_staan_versleuteld_in_de_database_en_niet_in_het_logboek(ingelogd, db):
    kid = ingelogd.post(
        "/klanten", json={"naam": "Geheime Naam", "email": "geheim@voorbeeld.nl"}
    ).json()["id"]
    ingelogd.post(
        f"/klanten/{kid}/profielen",
        json=profiel(doel="Geheim doel", duurzaamheid_toelichting="Geheim"),
    )
    ruw = db.execute(text("select naam, email from klant")).one()
    ruw_profiel = db.execute(text("select doel, duurzaamheid_toelichting from klantprofiel")).one()
    for waarde in (*ruw, *ruw_profiel):
        assert "eheim" not in waarde and waarde.startswith("gAAAA")
    logboek = " ".join(str(r.details) + str(r.entiteit_id) for r in db.scalars(select(Logboek)))
    assert "Geheim" not in logboek and "geheim@" not in logboek


def test_adviseur_ziet_alleen_eigen_klanten(ingelogd, client, db):
    kid = ingelogd.post("/klanten", json={"naam": "Van adviseur 1"}).json()["id"]
    ingelogd.post(f"/klanten/{kid}/profielen", json=profiel())

    db.add(
        Adviseur(
            email="ander@voorbeeld.nl", naam="Ander", wachtwoord_hash=hash_wachtwoord(WACHTWOORD)
        )
    )
    db.commit()
    token = client.post(
        "/auth/login", json={"email": "ander@voorbeeld.nl", "wachtwoord": WACHTWOORD}
    ).json()["access_token"]
    ander = {"Authorization": f"Bearer {token}"}

    assert client.get("/klanten", headers=ander).json() == []
    assert client.get("/klanten", headers=ander, params={"gearchiveerd": True}).json() == []
    for methode, pad, body in [
        ("get", f"/klanten/{kid}", None),
        ("put", f"/klanten/{kid}", {"naam": "Gekaapt"}),
        ("put", f"/klanten/{kid}/archief", {"gearchiveerd": True}),
        ("get", f"/klanten/{kid}/profielen", None),
        ("post", f"/klanten/{kid}/profielen", profiel()),
    ]:
        r = client.request(methode, pad, headers=ander, json=body)
        assert r.status_code == 404, (methode, pad)
    assert ingelogd.get(f"/klanten/{kid}").json()["naam"] == "Van adviseur 1"
    assert len(ingelogd.get(f"/klanten/{kid}/profielen").json()) == 1


def test_zonder_inloggen_geen_toegang(client):
    for methode, pad in [
        ("get", "/klanten"),
        ("post", "/klanten"),
        ("get", "/klanten/1"),
        ("get", "/klanten/1/profielen"),
        ("post", "/klanten/1/profielen"),
        ("get", "/vragenlijst"),
        ("get", "/risicoprofielen"),
        ("put", "/risicoprofielen/neutraal/allocatie"),
    ]:
        assert client.request(methode, pad).status_code == 401, (methode, pad)


# --- profielen -------------------------------------------------------------------------


@pytest.fixture
def klant_id(ingelogd):
    return ingelogd.post("/klanten", json={"naam": "Jan Jansen"}).json()["id"]


def test_profiel_vastleggen_en_versies(ingelogd, klant_id, adviseur, db):
    r = ingelogd.post(f"/klanten/{klant_id}/profielen", json=profiel())
    assert r.status_code == 201
    p = r.json()
    assert p["versie"] == 1
    assert (p["score_bereidheid"], p["score_capaciteit"], p["score_kennis"]) == (67, 67, 67)
    assert p["afgeleid_risicoprofiel"] == p["risicoprofiel"] == "offensief"
    assert p["bepalende_factor"] == "bereidheid" and p["lage_kennis"] is False
    assert p["uitsluitingen"] == ["tabak", "wapens"] and p["afwijking_toelichting"] is None

    tweede = ingelogd.post(
        f"/klanten/{klant_id}/profielen",
        json=profiel(horizon_jaren=4, antwoorden=antwoorden(3, 3, 0)),
    ).json()
    assert tweede["versie"] == 2
    assert (tweede["risicoprofiel"], tweede["bepalende_factor"]) == ("defensief", "horizon")
    assert tweede["lage_kennis"] is True

    geschiedenis = ingelogd.get(f"/klanten/{klant_id}/profielen").json()
    assert [(g["versie"], g["risicoprofiel"]) for g in geschiedenis] == [
        (2, "defensief"),
        (1, "offensief"),
    ]
    assert ingelogd.get(f"/klanten/{klant_id}").json()["huidig_profiel"]["versie"] == 2
    regels = db.scalars(select(Logboek).where(Logboek.actie == "klantprofiel_vastgelegd")).all()
    assert [r.details for r in regels] == [
        {"versie": 1, "risicoprofiel": "offensief"},
        {"versie": 2, "risicoprofiel": "defensief"},
    ]
    assert {r.adviseur_id for r in regels} == {adviseur.id}


def test_defensiever_profiel_kiezen_vereist_toelichting(ingelogd, klant_id):
    pad = f"/klanten/{klant_id}/profielen"
    r = ingelogd.post(pad, json=profiel(gekozen_risicoprofiel="neutraal"))
    assert r.status_code == 422 and "Licht toe" in r.json()["detail"]
    r = ingelogd.post(
        pad, json=profiel(gekozen_risicoprofiel="neutraal", afwijking_toelichting="  ")
    )
    assert r.status_code == 422

    r = ingelogd.post(
        pad, json=profiel(gekozen_risicoprofiel="neutraal", afwijking_toelichting="Klant wil rust")
    )
    p = r.json()
    assert (p["afgeleid_risicoprofiel"], p["risicoprofiel"]) == ("offensief", "neutraal")
    assert p["afwijking_toelichting"] == "Klant wil rust"

    # Hetzelfde profiel kiezen als het afgeleide is geen afwijking.
    p = ingelogd.post(pad, json=profiel(gekozen_risicoprofiel="offensief")).json()
    assert p["risicoprofiel"] == "offensief" and p["afwijking_toelichting"] is None


def test_offensiever_profiel_dan_afgeleid_is_niet_toegestaan(ingelogd, klant_id):
    pad = f"/klanten/{klant_id}/profielen"
    r = ingelogd.post(
        pad,
        json=profiel(gekozen_risicoprofiel="zeer-offensief", afwijking_toelichting="Klant wil het"),
    )
    assert r.status_code == 422 and "offensiever" in r.json()["detail"]
    r = ingelogd.post(
        pad, json=profiel(gekozen_risicoprofiel="bestaat-niet", afwijking_toelichting="x")
    )
    assert r.status_code == 422
    assert ingelogd.get(pad).json() == []


@pytest.mark.parametrize(
    "extra",
    [
        {"horizon_jaren": 0},
        {"horizon_jaren": 61},
        {"inleg_eur": -1},
        {"inleg_eur": 0, "storting_per_maand_eur": 0},
        {"doelvermogen_eur": 0},
        {"doel": ""},
        {"duurzaamheid": "misschien"},
        {"uitsluitingen": ["snoep"]},
        {"antwoorden": {}},
        {"antwoorden": {**antwoorden(), "daling": 9}},
    ],
)
def test_ongeldig_profiel_geweigerd(ingelogd, klant_id, extra):
    r = ingelogd.post(f"/klanten/{klant_id}/profielen", json=profiel(**extra))
    assert r.status_code == 422
    assert ingelogd.get(f"/klanten/{klant_id}/profielen").json() == []


def test_alleen_storting_zonder_inleg_en_zonder_doelvermogen_mag(ingelogd, klant_id):
    r = ingelogd.post(
        f"/klanten/{klant_id}/profielen", json=profiel(inleg_eur=0, doelvermogen_eur=None)
    )
    assert r.status_code == 201 and r.json()["doelvermogen_eur"] is None


# --- vragenlijst en modelallocaties ----------------------------------------------------


def test_vragenlijst_en_risicoprofielen_opvragen(ingelogd):
    v = ingelogd.get("/vragenlijst").json()
    assert len(v["vragen"]) == 11 and all(len(q["antwoorden"]) == 4 for q in v["vragen"])
    profielen = ingelogd.get("/risicoprofielen").json()
    assert [p["code"] for p in profielen] == [c for c, _ in RISICOPROFIELEN]
    neutraal = profielen[2]
    assert [r["categorie"] for r in neutraal["allocatie"]] == list(CATEGORIEEN)
    assert neutraal["allocatie"][0] == {
        "categorie": "aandelen",
        "streef": 50,
        "minimum": 40,
        "maximum": 60,
    }


def regels(**wijzig):
    basis = {c: list(v) for c, v in STANDAARD_ALLOCATIES["neutraal"].items()} | wijzig
    return [
        {"categorie": c, "streef": s, "minimum": lo, "maximum": hi}
        for c, (s, lo, hi) in basis.items()
    ]


def test_modelallocatie_wijzigen_met_logboek(ingelogd, db, adviseur):
    nieuw = regels(aandelen=[55, 45, 65], obligaties=[33, 20, 45])
    r = ingelogd.put("/risicoprofielen/neutraal/allocatie", json=nieuw)
    assert r.status_code == 200 and r.json()["allocatie"][0]["streef"] == 55
    opgehaald = ingelogd.get("/risicoprofielen").json()
    assert opgehaald[2]["allocatie"][1] == {
        "categorie": "obligaties",
        "streef": 33,
        "minimum": 20,
        "maximum": 45,
    }
    assert opgehaald[3]["allocatie"][0]["streef"] == 70  # andere profielen ongemoeid
    regel = db.scalar(select(Logboek).where(Logboek.actie == "modelallocatie_gewijzigd"))
    assert regel.adviseur_id == adviseur.id and regel.entiteit_id == "neutraal"
    assert regel.details["oud"]["aandelen"] == [50, 40, 60]
    assert regel.details["nieuw"]["aandelen"] == [55, 45, 65]


@pytest.mark.parametrize(
    "fout",
    [
        regels(aandelen=[55, 40, 60]),  # telt op tot 105
        regels(aandelen=[50, 55, 60]),  # minimum boven streefgewicht
        regels()[:-1],  # categorie ontbreekt
        regels() + regels()[:1],  # dubbele categorie
        [],
    ],
)
def test_ongeldige_modelallocatie_geweigerd(ingelogd, fout):
    r = ingelogd.put("/risicoprofielen/neutraal/allocatie", json=fout)
    assert r.status_code == 422
    assert ingelogd.get("/risicoprofielen").json()[2]["allocatie"][0]["streef"] == 50


def test_onbekend_risicoprofiel(ingelogd):
    assert ingelogd.put("/risicoprofielen/onbekend/allocatie", json=regels()).status_code == 404
