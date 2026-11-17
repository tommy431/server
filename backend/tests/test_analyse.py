import math
import statistics
from datetime import date, timedelta

import pytest

from app.analyse import (
    analyseer,
    bruikbaar_deel,
    jaren_terug,
    kengetallen,
    naar_euro,
    rente_index,
    verleng,
    waardeverloop,
)

D = date
EIND = D(2026, 11, 13)


def groei(per_jaar, begin, eind=EIND, start=100.0):
    """Reeks die elke kalenderdag gelijkmatig groeit met `per_jaar` (bijv. 0.10)."""
    dagen = (eind - begin).days
    return {
        begin + timedelta(days=i): start * (1 + per_jaar) ** (i / 365.25) for i in range(dagen + 1)
    }


def golf(per_jaar, begin, uitslag=0.01, eind=EIND):
    """Groeireeks met om de dag een afwijking, zodat er volatiliteit is."""
    return {
        dag: koers * (1 + uitslag * (1 if i % 2 else -1))
        for i, (dag, koers) in enumerate(groei(per_jaar, begin, eind).items())
    }


# --- handmatig nagerekend voorbeeld ----------------------------------------------------

A = {
    D(2023, 12, 28): 100.0,
    D(2023, 12, 29): 110.0,
    D(2024, 1, 2): 121.0,
    D(2024, 1, 3): 121.0,
    D(2024, 1, 4): 108.9,
}
B = {
    D(2023, 12, 28): 50.0,
    D(2023, 12, 29): 50.0,
    D(2024, 1, 2): 50.0,
    D(2024, 1, 3): 55.0,
    D(2024, 1, 4): 55.0,
}


def test_handmatig_nagerekend_waardeverloop_met_herbalancering():
    # Start 100 met 60% A en 40% B: 60 in A, 40 in B.
    # 29-12: A +10% → 66 + 40 = 106.
    # 02-01: A op 121 → 72,6 + 40 = 112,6. Nieuw jaar: herbalanceren naar 67,56 A en 45,04 B.
    # 03-01: B +10% → 67,56 + 49,544 = 117,104. (Zonder herbalanceren zou het 116,6 zijn.)
    # 04-01: A −10% → 60,804 + 49,544 = 110,348.
    verloop = waardeverloop({"A": A, "B": B}, {"A": 0.6, "B": 0.4}, D(2023, 12, 28), D(2024, 1, 4))
    assert [d for d, _ in verloop] == sorted(A)
    assert [w for _, w in verloop] == pytest.approx([100, 106, 112.6, 117.104, 110.348])


def test_handmatig_nagerekende_kengetallen():
    verloop = list(zip(sorted(A), [100, 106, 112.6, 117.104, 110.348], strict=True))
    k = kengetallen(verloop, risicovrij_per_jaar=0.02)
    assert k.rendement_cumulatief == pytest.approx(0.10348)
    assert k.rendement_per_jaar == pytest.approx(0.10348)  # korter dan een jaar: niet omgerekend
    # Grootste daling: van de top 117,104 op 3 januari naar 110,348 op 4 januari.
    assert k.max_daling == pytest.approx(110.348 / 117.104 - 1) == pytest.approx(-0.0576923)
    assert (k.max_daling_top, k.max_daling_dal) == (D(2024, 1, 3), D(2024, 1, 4))
    # Dagrendementen: +6%, +6,2264%, +4%, −5,7692%. Vier waarnemingen in 7 dagen.
    dag = [0.06, 112.6 / 106 - 1, 0.04, 110.348 / 117.104 - 1]
    assert k.volatiliteit == pytest.approx(statistics.stdev(dag) * math.sqrt(4 / (7 / 365.25)))
    assert k.sharpe is None


def test_kengetallen_over_twee_jaar():
    # 100 → 121 in precies 731 dagen; elke dag een waarde om en om hoger en lager dan de trend.
    begin = D(2022, 1, 1)
    reeks = sorted(golf(0.10, begin, eind=D(2024, 1, 2)).items())
    k = kengetallen(reeks, 0.02)
    jaren = 731 / 365.25
    assert k.rendement_cumulatief == pytest.approx(reeks[-1][1] / reeks[0][1] - 1)
    assert k.rendement_per_jaar == pytest.approx((1 + k.rendement_cumulatief) ** (1 / jaren) - 1)
    # De golf telt aan begin en eind elk 1% mee: (1,21 × 1,01 / 0,99) over twee jaar ≈ 11,1%.
    assert k.rendement_per_jaar == pytest.approx(0.111, abs=0.001)
    assert k.sharpe == pytest.approx((k.rendement_per_jaar - 0.02) / k.volatiliteit)
    # Om de dag ±2%: standaarddeviatie per dag ≈ 2%, per jaar ≈ 2% × √365.
    assert k.volatiliteit == pytest.approx(0.02 * math.sqrt(365.25), rel=0.02)


def test_dalende_reeks_en_vlakke_reeks():
    dalend = [(D(2024, 1, 1) + timedelta(days=i), 100 - i) for i in range(11)]
    k = kengetallen(dalend, None)
    assert k.max_daling == pytest.approx(-0.10)
    assert (k.max_daling_top, k.max_daling_dal) == (D(2024, 1, 1), D(2024, 1, 11))
    vlak = [(D(2022, 1, 1) + timedelta(days=i), 100.0) for i in range(800)]
    k = kengetallen(vlak, 0.02)
    assert (k.volatiliteit, k.max_daling, k.sharpe) == (0.0, 0.0, None)


def test_herstel_na_daling_onthoudt_de_diepste_daling():
    waarden = [100, 120, 90, 130, 117]
    verloop = [(D(2024, 1, 1) + timedelta(days=i), float(w)) for i, w in enumerate(waarden)]
    k = kengetallen(verloop, None)
    assert k.max_daling == pytest.approx(-0.25)
    assert (k.max_daling_top, k.max_daling_dal) == (D(2024, 1, 2), D(2024, 1, 3))


# --- bouwstenen ------------------------------------------------------------------------


def test_ontbrekende_koers_gebruikt_laatst_bekende():
    a = {D(2024, 3, 1): 100.0, D(2024, 3, 4): 110.0, D(2024, 3, 5): 120.0}
    b = {D(2024, 2, 28): 10.0, D(2024, 3, 5): 11.0}  # geen koers op 1 en 4 maart
    verloop = waardeverloop({"A": a, "B": b}, {"A": 0.5, "B": 0.5}, D(2024, 3, 1), D(2024, 3, 5))
    assert verloop == [
        (D(2024, 3, 1), 100.0),
        (D(2024, 3, 4), pytest.approx(105.0)),
        (D(2024, 3, 5), pytest.approx(115.0)),
    ]


def test_start_op_dag_zonder_handel_en_ontbrekende_beginkoers():
    a = {D(2024, 3, 1): 100.0, D(2024, 3, 4): 110.0}
    verloop = waardeverloop({"A": a}, {"A": 1.0}, D(2024, 3, 2), D(2024, 3, 4))
    assert verloop == [(D(2024, 3, 2), 100.0), (D(2024, 3, 4), pytest.approx(110.0))]
    with pytest.raises(ValueError):
        waardeverloop({"A": a}, {"A": 1.0}, D(2024, 2, 1), D(2024, 3, 4))


def test_jaren_terug_ook_op_schrikkeldag():
    assert jaren_terug(D(2026, 11, 13), 10) == D(2016, 11, 13)
    assert jaren_terug(D(2024, 2, 29), 1) == D(2023, 2, 28)
    assert jaren_terug(D(2024, 2, 29), 4) == D(2020, 2, 29)


def test_bruikbaar_deel_begint_na_de_laatste_koerssprong():
    reeks = {D(2024, 1, i): k for i, k in enumerate([100, 101, 140, 141, 100, 101, 121.2], 1)}
    deel, ingekort = bruikbaar_deel(reeks)
    # Sprongen op dag 3 (+38,6%) en dag 5 (−29,1%); dag 7 is precies +20% en telt niet.
    assert ingekort and sorted(deel) == [D(2024, 1, 5), D(2024, 1, 6), D(2024, 1, 7)]
    schoon = {D(2024, 1, 1): 100.0, D(2024, 1, 2): 119.0}
    assert bruikbaar_deel(schoon) == (schoon, False)


def test_omrekenen_naar_euro():
    koersen = {D(2024, 1, 1): 110.0, D(2024, 1, 2): 220.0, D(2024, 1, 3): 330.0}
    usd = {D(2024, 1, 2): 1.10, D(2024, 1, 3): 1.00}
    # 1 januari heeft nog geen wisselkoers en vervalt.
    assert naar_euro(koersen, "USD", usd) == pytest.approx(
        {D(2024, 1, 2): 200.0, D(2024, 1, 3): 330.0}
    )
    assert naar_euro(koersen, "EUR", None) is koersen
    pence = naar_euro({D(2024, 1, 4): 850.0}, "GBp", {D(2024, 1, 2): 0.85})
    assert pence == pytest.approx(
        {D(2024, 1, 4): 10.0}
    )  # 850 pence = £8,50 = € 10; oudere wisselkoers
    with pytest.raises(ValueError):
        naar_euro(koersen, "USD", {})


# --- volledige analyse -----------------------------------------------------------------

NAMEN = {
    "AAND": "Aandelenfonds",
    "OBL": "Obligatiefonds",
    "GELD": "Geldmarktfonds",
    "NIEUW": "Nieuw fonds",
    "BM": "Benchmarkfonds",
}


def periode(analyse, code):
    return next(p for p in analyse.perioden if p.code == code)


def test_constante_groei_geeft_exact_het_bekende_rendement_voor_elke_periode():
    reeksen = {"AAND": groei(0.08, D(2010, 1, 1)), "OBL": groei(0.08, D(2010, 1, 1), start=40.0)}
    a = analyseer({"AAND": 0.6, "OBL": 0.4}, reeksen, NAMEN)
    assert a.peildatum == EIND and a.waarschuwingen == []
    for code, jaren in [("1j", 1), ("3j", 3), ("5j", 5), ("10j", 10)]:
        p = periode(a, code)
        assert p.beschikbaar and (p.van, p.tot) == (jaren_terug(EIND, jaren), EIND)
        assert p.portefeuille.rendement_per_jaar == pytest.approx(0.08, abs=2e-4)
        assert p.portefeuille.max_daling == 0.0
        assert p.portefeuille.volatiliteit == pytest.approx(0.0, abs=1e-6)
        assert p.benchmark is None and p.portefeuille.sharpe is None
    start = periode(a, "start")
    assert (start.van, start.jaren) == (D(2010, 1, 1), None)
    assert start.portefeuille.rendement_cumulatief == pytest.approx(
        1.08 ** ((EIND - D(2010, 1, 1)).days / 365.25) - 1
    )


def test_korte_historie_maakt_lange_perioden_onbeschikbaar_met_reden():
    reeksen = {"AAND": groei(0.08, D(2010, 1, 1)), "NIEUW": groei(0.03, D(2022, 6, 1))}
    a = analyseer({"AAND": 0.5, "NIEUW": 0.5}, reeksen, NAMEN)
    assert [(p.code, p.beschikbaar) for p in a.perioden] == [
        ("1j", True),
        ("3j", True),
        ("5j", False),
        ("10j", False),
        ("start", True),
    ]
    assert periode(a, "5j").reden == "Nieuw fonds heeft bruikbare koersen vanaf 2022-06-01"
    assert periode(a, "5j").portefeuille is None
    assert periode(a, "start").van == D(2022, 6, 1)
    assert [(h.isin, h.eerste_koers) for h in a.instrumenten] == [
        ("NIEUW", D(2022, 6, 1)),
        ("AAND", D(2010, 1, 1)),
    ]
    # Precies op de grens: historie vanaf exact drie jaar terug maakt 3 jaar beschikbaar.
    reeksen["NIEUW"] = groei(0.03, jaren_terug(EIND, 3))
    assert periode(analyseer({"AAND": 0.5, "NIEUW": 0.5}, reeksen, NAMEN), "3j").beschikbaar
    reeksen["NIEUW"] = groei(0.03, jaren_terug(EIND, 3) + timedelta(days=1))
    assert not periode(analyseer({"AAND": 0.5, "NIEUW": 0.5}, reeksen, NAMEN), "3j").beschikbaar


def test_koerssprong_kort_de_historie_in_en_wordt_gemeld():
    reeks = groei(0.08, D(2010, 1, 1))
    for dag in list(reeks):
        if dag < D(2019, 3, 1):
            reeks[dag] *= 3  # tot 1 maart 2019 staan de koersen een factor 3 te hoog
    a = analyseer({"AAND": 1.0}, {"AAND": reeks}, NAMEN)
    assert a.waarschuwingen == [
        (
            "Aandelenfonds: koersen van vóór 2019-03-01 zijn niet gebruikt vanwege een koerssprong "
            "in de brondata"
        )
    ]
    assert a.instrumenten[0].ingekort and a.instrumenten[0].eerste_koers == D(2010, 1, 1)
    assert not periode(a, "10j").beschikbaar and periode(a, "5j").beschikbaar
    assert periode(a, "start").van == D(2019, 3, 1)
    assert periode(a, "start").portefeuille.max_daling == 0.0  # de sprong zelf telt niet mee


def test_benchmark_en_sharpe():
    reeksen = {
        "AAND": golf(0.09, D(2010, 1, 1)),
        "BM": golf(0.06, D(2010, 1, 1), uitslag=0.005),
        "GELD": groei(0.02, D(2010, 1, 1)),
    }
    a = analyseer({"AAND": 1.0}, reeksen, NAMEN, benchmark={"BM": 1.0}, risicovrij="GELD")
    p = periode(a, "5j")
    assert p.risicovrij_per_jaar == pytest.approx(0.02, abs=1e-6)
    assert p.portefeuille.rendement_per_jaar == pytest.approx(0.09, abs=0.03)
    assert p.benchmark.rendement_per_jaar == pytest.approx(0.06, abs=0.02)
    assert p.benchmark.volatiliteit == pytest.approx(p.portefeuille.volatiliteit / 2, rel=0.01)
    assert p.portefeuille.sharpe == pytest.approx(
        (p.portefeuille.rendement_per_jaar - p.risicovrij_per_jaar) / p.portefeuille.volatiliteit
    )
    assert a.waarschuwingen == []
    # Ook over precies één jaar (365 dagen) wordt de Sharpe-ratio berekend.
    assert periode(a, "1j").portefeuille.sharpe is not None


def test_benchmark_met_te_korte_historie_valt_weg_voor_die_periode():
    reeksen = {"AAND": groei(0.08, D(2010, 1, 1)), "BM": groei(0.05, D(2023, 1, 1))}
    a = analyseer({"AAND": 1.0}, reeksen, NAMEN, benchmark={"BM": 1.0}, risicovrij="GELD")
    assert periode(a, "3j").benchmark is not None
    assert periode(a, "5j").benchmark is None and periode(a, "5j").beschikbaar
    assert a.waarschuwingen == [
        "De benchmark heeft geen koersen over de hele periode sinds start en is daar weggelaten",
        "Geen risicovrij rendement beschikbaar; de Sharpe-ratio is niet berekend",
    ]
    assert all(punt[2] is None for punt in a.waardeverloop)


def test_kalenderjaren_alleen_volledige_jaren():
    reeksen = {"AAND": groei(0.10, D(2021, 7, 1)), "BM": groei(0.04, D(2021, 7, 1))}
    a = analyseer({"AAND": 1.0}, reeksen, NAMEN, benchmark={"BM": 1.0})
    # 2021 is onvolledig aan het begin, 2026 aan het eind.
    assert [j.jaar for j in a.kalenderjaren] == [2022, 2023, 2024, 2025]
    for j in a.kalenderjaren:
        assert j.portefeuille == pytest.approx(0.10, abs=3e-4)
        assert j.benchmark == pytest.approx(0.04, abs=2e-4)


def test_kalenderjaar_komt_overeen_met_handmatige_berekening():
    # Eind 2022: 100. Eind 2023: 108 → +8%. Eind 2024: 91,8 → −15%. 2025 is onvolledig.
    reeks = {
        D(2022, 12, 30): 100.0,
        D(2023, 6, 30): 90.0,
        D(2023, 12, 29): 108.0,
        D(2024, 12, 31): 91.8,
        D(2025, 3, 3): 100.98,
    }
    a = analyseer({"AAND": 1.0}, {"AAND": reeks}, NAMEN)
    assert a.waarschuwingen == []
    assert [(j.jaar, round(j.portefeuille, 6)) for j in a.kalenderjaren] == [
        (2023, 0.08),
        (2024, -0.15),
    ]
    start = periode(a, "start").portefeuille
    assert start.rendement_cumulatief == pytest.approx(0.0098)
    assert start.max_daling == pytest.approx(-0.15)
    assert (start.max_daling_top, start.max_daling_dal) == (D(2023, 12, 29), D(2024, 12, 31))


def test_waardeverloop_per_maand_begint_op_100():
    a = analyseer({"AAND": 1.0}, {"AAND": groei(0.08, D(2024, 1, 15))}, NAMEN)
    eerste, laatste = a.waardeverloop[0], a.waardeverloop[-1]
    assert eerste == (D(2024, 1, 15), 100.0, None)
    assert laatste[0] == EIND
    assert laatste[1] == pytest.approx(
        100 * (1 + periode(a, "start").portefeuille.rendement_cumulatief)
    )
    maanden = [(d.year, d.month) for d, _, _ in a.waardeverloop[1:]]
    assert maanden == sorted(set(maanden)) and len(maanden) == 35


def test_verouderde_koers_wordt_gemeld():
    reeksen = {
        "AAND": groei(0.08, D(2015, 1, 1)),
        "OBL": groei(0.02, D(2015, 1, 1), eind=EIND - timedelta(days=20)),
    }
    a = analyseer({"AAND": 0.5, "OBL": 0.5}, reeksen, NAMEN)
    assert a.peildatum == EIND
    assert a.waarschuwingen == [
        (
            f"Obligatiefonds: laatste koers is van {EIND - timedelta(days=20)}; daarna is met die "
            "koers doorgerekend"
        )
    ]


def test_geen_koersen_of_te_weinig_historie():
    a = analyseer({"AAND": 0.5, "OBL": 0.5}, {"AAND": groei(0.08, D(2015, 1, 1))}, NAMEN)
    assert a.peildatum is None and a.perioden == []
    assert a.waarschuwingen == ["Geen koersen beschikbaar voor: Obligatiefonds"]
    assert analyseer({}, {}, NAMEN).waarschuwingen == ["De portefeuille bevat geen posities"]
    kort = analyseer({"AAND": 1.0}, {"AAND": groei(0.08, EIND - timedelta(days=10))}, NAMEN)
    assert [(p.code, p.beschikbaar) for p in kort.perioden][-1] == ("start", False)
    assert kort.kalenderjaren == [] and kort.waardeverloop == []


def test_als_dict_is_json_geschikt():
    import json

    a = analyseer({"AAND": 1.0}, {"AAND": golf(0.08, D(2015, 1, 1))}, NAMEN)
    tekst = json.dumps(a.als_dict())
    terug = json.loads(tekst)
    assert terug["peildatum"] == "2026-11-13"
    assert terug["perioden"][0]["portefeuille"]["max_daling_top"][:2] == "20"
    assert terug["waardeverloop"][0] == ["2015-01-01", 100.0, None]


def test_rente_index_act_360_met_weekend():
    # Vrijdag 3,6% geldt drie dagen: 100 × (1 + 0,036 × 3/360) = 100,03. Maandag 1,8% één dag.
    index = rente_index({D(2024, 1, 5): 3.6, D(2024, 1, 8): 1.8, D(2024, 1, 9): 0.0})
    assert index == pytest.approx(
        {D(2024, 1, 5): 100.0, D(2024, 1, 8): 100.03, D(2024, 1, 9): 100.03 * 1.00005}
    )
    assert rente_index({}) == {}
    # Negatieve rente laat de index dalen.
    assert rente_index({D(2020, 1, 1): -0.5, D(2020, 1, 2): -0.5})[D(2020, 1, 2)] < 100


def test_verleng_sluit_aan_en_neemt_het_rendement_van_de_vervanger():
    eigen = {D(2024, 1, 3): 50.0, D(2024, 1, 4): 55.0}
    vervanger = {
        D(2024, 1, 1): 100.0,
        D(2024, 1, 2): 110.0,
        D(2024, 1, 3): 121.0,
        D(2024, 1, 4): 1.0,
    }
    uit = verleng(eigen, vervanger)
    assert uit[D(2024, 1, 3)] == 50.0 and uit[D(2024, 1, 4)] == 55.0  # eigen koersen ongemoeid
    assert uit[D(2024, 1, 2)] == pytest.approx(50 / 1.1)  # rendement 2→3 januari is +10%
    assert uit[D(2024, 1, 1)] == pytest.approx(50 / 1.21)
    assert verleng(eigen, {D(2024, 2, 1): 1.0}) == eigen  # vervanger begint later: niets te doen


def test_analyse_met_vervanger_markeert_gesimuleerde_perioden():
    reeksen = {"AAND": groei(0.08, D(2010, 1, 1)), "NIEUW": groei(0.03, D(2022, 6, 1))}
    a = analyseer({"AAND": 0.5, "NIEUW": 0.5}, reeksen, NAMEN, vervangers={"NIEUW": "AAND"})
    assert all(p.beschikbaar for p in a.perioden)
    assert [(p.code, p.gesimuleerd) for p in a.perioden] == [
        ("1j", False),
        ("3j", False),
        ("5j", True),
        ("10j", True),
        ("start", True),
    ]
    nieuw = next(h for h in a.instrumenten if h.isin == "NIEUW")
    assert (nieuw.vervanger, nieuw.eigen_koersen_vanaf, nieuw.eerste_koers) == (
        "Aandelenfonds",
        D(2022, 6, 1),
        D(2022, 6, 1),
    )
    # Volledig gesimuleerd verleden: 8% per jaar vóór juni 2022, dus ook voor de mix.
    tien = next(p for p in a.perioden if p.code == "10j").portefeuille
    assert 0.03 < tien.rendement_per_jaar < 0.08
