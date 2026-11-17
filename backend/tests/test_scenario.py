import math

import numpy as np
import pytest

from app.scenario import (
    AannameFout,
    Aannames,
    controleer,
    portefeuillekenmerken,
    simuleer,
)

CATS = ("aandelen", "obligaties")


def aannames(r=(0.06, 0.03), v=(0.16, 0.05), rho=0.1, inflatie=0.02):
    return Aannames(
        categorieen=CATS,
        rendement=dict(zip(CATS, r, strict=True)),
        volatiliteit=dict(zip(CATS, v, strict=True)),
        correlaties={
            "aandelen": {"aandelen": 1.0, "obligaties": rho},
            "obligaties": {"aandelen": rho, "obligaties": 1.0},
        },
        inflatie=inflatie,
    )


def sim(gewichten, a, **extra):
    basis = {"horizon_jaren": 10, "inleg": 100_000, "storting_per_maand": 0, "kosten_pct": 0.0}
    return simuleer(gewichten, a, **(basis | extra))


# --- handmatig nagerekend zonder toeval ------------------------------------------------


def test_zonder_volatiliteit_exact_samengestelde_groei():
    # 100.000 tegen 5% per jaar gedurende 10 jaar = 162.889,46. Elk pad is gelijk.
    a = aannames(r=(0.05, 0.05), v=(0.0, 0.0))
    s = sim({"aandelen": 0.5, "obligaties": 0.5}, a)
    for p in s.jaren[-1].nominaal:
        assert p == pytest.approx(100_000 * 1.05**10)
    assert s.jaren[-1].nominaal[1] == pytest.approx(162_889.46, abs=0.01)
    # Koopkracht van vandaag: delen door 1,02^10.
    assert s.jaren[-1].reeel[1] == pytest.approx(162_889.46 / 1.02**10, abs=0.01)
    assert s.kans_minder_dan_ingelegd == 0.0


def test_zonder_volatiliteit_met_kosten_en_stortingen():
    # 0% rendement, 1% kosten per jaar, 2 jaar: 10.000 × 0,99² = 9.801.
    a = aannames(r=(0.0, 0.0), v=(0.0, 0.0))
    s = sim({"aandelen": 1.0}, a, horizon_jaren=2, inleg=10_000, kosten_pct=1.0)
    assert s.jaren[-1].nominaal[1] == pytest.approx(9_801.0)
    assert s.mediaan_zonder_kosten == pytest.approx(10_000.0)
    assert s.kosten_effect_mediaan == pytest.approx(199.0)
    # Alleen stortingen van 100 per maand, 0% rendement en geen kosten: 2.400 na 2 jaar.
    a = aannames(r=(0.0, 0.0), v=(0.0, 0.0), inflatie=0.0)
    s = sim({"aandelen": 1.0}, a, horizon_jaren=2, inleg=0, storting_per_maand=100)
    assert [j.ingelegd for j in s.jaren] == [0, 1200, 2400]
    # Zonder inflatie is ingelegd in koopkracht gelijk aan nominaal.
    assert [j.ingelegd_reeel for j in s.jaren] == pytest.approx([0, 1200, 2400])


def test_ingelegd_in_koopkracht_van_vandaag():
    # 1.000 inleg plus 24 stortingen van 100 bij 6,1678% inflatie per jaar (0,5% per maand):
    # 1.000 + Σ 100 / 1,005^m voor m = 1..24 = 1.000 + 100 × (1 − 1,005^−24) / 0,005 = 3.256,29.
    a = aannames(r=(0.0, 0.0), v=(0.0, 0.0), inflatie=1.005**12 - 1)
    s = sim({"aandelen": 1.0}, a, horizon_jaren=2, inleg=1000, storting_per_maand=100)
    assert s.jaren[2].ingelegd == 3400
    assert s.jaren[2].ingelegd_reeel == pytest.approx(3256.29, abs=0.01)


def test_stortingen_aan_het_eind_van_de_maand_groeien_mee():
    # 12% per jaar = 0,9489% per maand; storting 100 aan het eind van elke maand, 1 jaar.
    # Eindwaarde = 100 × ((1+m)^12 − 1) / m met m = 1,12^(1/12) − 1.
    a = aannames(r=(0.12, 0.12), v=(0.0, 0.0))
    s = sim({"aandelen": 1.0}, a, horizon_jaren=1, inleg=0, storting_per_maand=100)
    m = 1.12 ** (1 / 12) - 1
    assert s.jaren[-1].nominaal[1] == pytest.approx(100 * ((1 + m) ** 12 - 1) / m)


# --- statistische eigenschappen --------------------------------------------------------


def test_een_categorie_lognormaal_klopt_met_theorie():
    # Eén categorie, maandelijks herbalanceren speelt geen rol: eindwaarde is exact lognormaal.
    r, v, jaren = 0.07, 0.18, 10
    a = aannames(r=(r, 0.03), v=(v, 0.05))
    s = sim({"aandelen": 1.0}, a, horizon_jaren=jaren, paden=50_000)
    s_log = math.sqrt(math.log1p((v / (1 + r)) ** 2))
    mu = math.log1p(r) - s_log**2 / 2
    mediaan = 100_000 * math.exp(mu * jaren)
    p5 = 100_000 * math.exp(mu * jaren - 1.6449 * s_log * math.sqrt(jaren))
    p95 = 100_000 * math.exp(mu * jaren + 1.6449 * s_log * math.sqrt(jaren))
    laag, mid, hoog = s.jaren[-1].nominaal
    assert mid == pytest.approx(mediaan, rel=0.01)
    assert laag == pytest.approx(p5, rel=0.02)
    assert hoog == pytest.approx(p95, rel=0.02)


def test_spreiding_verlaagt_de_volatiliteit_van_de_mix():
    a = aannames(rho=0.1)
    r, v = portefeuillekenmerken({"aandelen": 0.6, "obligaties": 0.4}, a)
    assert r == pytest.approx(0.6 * 0.06 + 0.4 * 0.03)
    verwacht = math.sqrt(0.6**2 * 0.16**2 + 0.4**2 * 0.05**2 + 2 * 0.6 * 0.4 * 0.1 * 0.16 * 0.05)
    assert v == pytest.approx(verwacht)
    assert v < 0.6 * 0.16 + 0.4 * 0.05


def test_meer_risico_geeft_bredere_uitkomsten():
    a = aannames()
    defensief = sim({"aandelen": 0.2, "obligaties": 0.8}, a)
    offensief = sim({"aandelen": 0.9, "obligaties": 0.1}, a)
    breedte = lambda s: s.jaren[-1].nominaal[2] / s.jaren[-1].nominaal[0]
    assert breedte(offensief) > 2 * breedte(defensief)
    assert offensief.jaren[-1].nominaal[1] > defensief.jaren[-1].nominaal[1]
    assert offensief.kans_minder_dan_ingelegd > defensief.kans_minder_dan_ingelegd


def test_percentielen_oplopend_en_jaarreeks_compleet():
    s = sim({"aandelen": 0.6, "obligaties": 0.4}, aannames(), horizon_jaren=15)
    assert [j.jaar for j in s.jaren] == list(range(16))
    assert s.jaren[0].nominaal == (100_000.0, 100_000.0, 100_000.0)
    for j in s.jaren[1:]:
        assert j.nominaal[0] < j.nominaal[1] < j.nominaal[2]
        assert j.reeel[1] < j.nominaal[1]


def test_kansen_op_doelvermogen():
    a = aannames()
    s = sim({"aandelen": 0.6, "obligaties": 0.4}, a, doelvermogen=150_000)
    assert 0 < s.kans_doel_reeel < s.kans_doel_nominaal < 1
    # Een doel onder het slechte scenario wordt in vrijwel alle gevallen gehaald.
    laag = sim({"aandelen": 0.6, "obligaties": 0.4}, a, doelvermogen=s.jaren[-1].nominaal[0])
    assert laag.kans_doel_nominaal == pytest.approx(0.95, abs=0.005)
    assert sim({"aandelen": 1.0}, a).kans_doel_nominaal is None


def test_zelfde_zaad_zelfde_uitkomst_ander_zaad_dicht_bij():
    a = aannames()
    g = {"aandelen": 0.6, "obligaties": 0.4}
    assert sim(g, a) == sim(g, a)
    ander = sim(g, a, zaad=1)
    assert ander.jaren[-1].nominaal[1] == pytest.approx(sim(g, a).jaren[-1].nominaal[1], rel=0.02)


def test_kosten_drukken_het_eindvermogen_met_gelijke_toevalsgetallen():
    a = aannames()
    g = {"aandelen": 0.6, "obligaties": 0.4}
    zonder = sim(g, a)
    met = sim(g, a, kosten_pct=1.0)
    assert met.mediaan_zonder_kosten == pytest.approx(zonder.jaren[-1].nominaal[1])
    # 1% per jaar over 10 jaar kost ongeveer 1 − 0,99^10 = 9,6% van het eindvermogen.
    assert met.kosten_effect_mediaan / met.mediaan_zonder_kosten == pytest.approx(
        1 - 0.99**10, rel=0.02
    )


# --- invoercontrole --------------------------------------------------------------------


def test_onmogelijke_correlaties_worden_geweigerd():
    a = Aannames(
        categorieen=("a", "b", "c"),
        rendement={"a": 0.05, "b": 0.05, "c": 0.05},
        volatiliteit={"a": 0.1, "b": 0.1, "c": 0.1},
        # a sterk positief met b en c, maar b en c sterk negatief: kan niet.
        correlaties={
            "a": {"a": 1, "b": 0.9, "c": 0.9},
            "b": {"a": 0.9, "b": 1, "c": -0.9},
            "c": {"a": 0.9, "b": -0.9, "c": 1},
        },
        inflatie=0.02,
    )
    fouten = controleer(a)
    assert len(fouten) == 1 and "positief semidefiniet" in fouten[0]
    with pytest.raises(AannameFout):
        simuleer({"a": 1.0}, a, horizon_jaren=5, inleg=1000, storting_per_maand=0, kosten_pct=0)


@pytest.mark.parametrize(
    ("wijzig", "deel"),
    [
        (lambda a: a.rendement.update(aandelen=0.25), "buiten −5% tot 20%"),
        (lambda a: a.volatiliteit.update(aandelen=-0.01), "buiten 0% tot 60%"),
        (lambda a: a.correlaties["aandelen"].update(obligaties=0.5), "niet symmetrisch"),
        (lambda a: a.correlaties["aandelen"].update(aandelen=0.9), "met zichzelf"),
        (lambda a: a.correlaties["obligaties"].pop("aandelen"), "onvolledig"),
    ],
)
def test_ongeldige_aannames(wijzig, deel):
    a = aannames()
    wijzig(a)
    assert any(deel in f for f in controleer(a))


def test_ongeldige_simulatie_invoer():
    a = aannames()
    with pytest.raises(ValueError):
        sim({"aandelen": 0.5}, a)
    with pytest.raises(ValueError):
        sim({"aandelen": 1.0}, a, paden=1000)
    with pytest.raises(ValueError):
        sim({"vastgoed": 1.0}, a)
    with pytest.raises(ValueError):
        sim({"aandelen": 1.0}, a, horizon_jaren=0)


def test_rekentijd_bij_lange_horizon_blijft_beperkt():
    import time

    begin = time.perf_counter()
    s = sim(
        {"aandelen": 0.6, "obligaties": 0.4}, aannames(), horizon_jaren=40, storting_per_maand=500
    )
    assert time.perf_counter() - begin < 5
    assert len(s.jaren) == 41 and np.isfinite(s.jaren[-1].nominaal).all()
