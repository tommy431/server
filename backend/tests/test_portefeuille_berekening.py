import pytest

from app.models import CATEGORIEEN
from app.portefeuille import (
    STARTSELECTIE,
    TOTAAL,
    Band,
    Fonds,
    Uitsluiting,
    _verdeel,
    maak_voorstel,
    pct,
    reken_door,
)
from app.profiel import RISICOPROFIELEN, STANDAARD_ALLOCATIES

WERELD, EM, KLEIN, SRI = "IE00B4L5Y983", "IE00BKM4GZ66", "IE00BF4RFH31", "IE00BYX2JD69"
AGG, EURO_AGG, VASTGOED = "IE00BDBRDM35", "IE00B3DKXQ41", "IE00B1FZS350"
GRONDSTOF, GOUD, GELD = "DE000A0H0728", "DE000A0S9GB0", "LU0290358497"
ZORG, TECH, ENERGIE, FIN = "IE00BM67HK77", "IE00BM67HT60", "IE00BM67HM91", "IE00BM67HL84"
EURO_STAAT = "IE00B4WXJJ64"


def fonds(
    isin, categorie, regio="wereld", sector="breed", kosten=0.2, geverifieerd=True, actief=True
):
    return Fonds(isin, f"Fonds {isin[-4:]}", categorie, regio, sector, kosten, geverifieerd, actief)


FONDSEN = {
    f.isin: f
    for f in [
        fonds(WERELD, "aandelen", kosten=0.20),
        fonds(SRI, "aandelen", kosten=0.20),
        fonds(EM, "aandelen", regio="opkomende-markten", kosten=0.18),
        fonds(KLEIN, "aandelen", kosten=0.35),
        fonds(ZORG, "aandelen", sector="gezondheidszorg", kosten=0.25),
        fonds(TECH, "aandelen", sector="informatietechnologie", kosten=0.25),
        fonds(ENERGIE, "aandelen", sector="energie", kosten=0.25),
        fonds(FIN, "aandelen", sector="financiele-dienstverlening", kosten=0.25),
        fonds(AGG, "obligaties", kosten=0.10),
        fonds(EURO_AGG, "obligaties", regio="europa", kosten=0.16),
        fonds(EURO_STAAT, "obligaties", regio="europa", kosten=0.07),
        fonds(VASTGOED, "vastgoed", sector="vastgoed", kosten=0.59),
        fonds(GRONDSTOF, "grondstoffen", kosten=0.46),
        fonds(GOUD, "grondstoffen", kosten=0.0),
        fonds(GELD, "liquiditeiten", regio="europa", kosten=0.10),
    ]
}


def banden(code="neutraal"):
    return {c: Band(*STANDAARD_ALLOCATIES[code][c]) for c in CATEGORIEEN}


def codes(d, ernst=None):
    return [b.code for b in d.bevindingen if ernst is None or b.ernst == ernst]


# --- hulpfuncties ----------------------------------------------------------------------


def test_pct():
    assert (pct(6630), pct(5000), pct(10), pct(0)) == ("66,3%", "50%", "0,1%", "0%")


@pytest.mark.parametrize(
    ("totaal", "aandelen", "verwacht"),
    [
        (5000, [0.78, 0.12, 0.10], [3900, 600, 500]),
        (8500, [0.78, 0.12, 0.10], [6630, 1020, 850]),
        (1000, [1, 1, 1], [340, 330, 330]),  # rest gaat naar de eerste
        (500, [0.5, 0.5], [250, 250]),
        (10, [1, 1], [10, 0]),
    ],
)
def test_verdelen_is_exact(totaal, aandelen, verwacht):
    assert _verdeel(totaal, aandelen) == verwacht
    assert sum(verwacht) == totaal


def test_startselectie_bestaat_in_meegeleverd_universum():
    import csv
    from pathlib import Path

    pad = Path(__file__).parent.parent / "data" / "universum.csv"
    universum = {r["isin"]: r for r in csv.DictReader(pad.open(encoding="utf-8"))}
    for categorie, keuze in STARTSELECTIE.items():
        assert sum(a for _, a in keuze) == pytest.approx(1.0)
        for isin, _ in keuze:
            assert universum[isin]["categorie"] == categorie
    assert set(STARTSELECTIE) == set(CATEGORIEEN)
    assert universum[SRI]["categorie"] == "aandelen"


# --- voorstel --------------------------------------------------------------------------


def test_handmatig_nagerekend_voorstel_neutraal():
    # Neutraal: aandelen 50, obligaties 38, vastgoed 5, grondstoffen 2, liquiditeiten 5.
    # Aandelen 50% × 78/12/10 = 39 / 6 / 5. Obligaties 38% × 50/50 = 19 / 19.
    # Grondstoffen 2% × 50/50 = 1 / 1: beide onder 2%, dus alleen de eerste houdt 2%.
    posities, opmerkingen = maak_voorstel(banden(), FONDSEN, [])
    assert posities == {
        WERELD: 3900,
        EM: 600,
        KLEIN: 500,
        AGG: 1900,
        EURO_AGG: 1900,
        VASTGOED: 500,
        GRONDSTOF: 200,
        GELD: 500,
    }
    assert opmerkingen == []


@pytest.mark.parametrize("code", [c for c, _ in RISICOPROFIELEN])
def test_voorstel_voldoet_voor_elk_profiel_aan_profiel_en_beperkingen(code):
    b = banden(code)
    posities, opmerkingen = maak_voorstel(b, FONDSEN, [])
    assert opmerkingen == []
    assert sum(posities.values()) == TOTAAL
    assert min(posities.values()) >= 200
    d = reken_door(posities, FONDSEN, b, [])
    assert d.bevindingen == []
    assert d.per_categorie == {c: band.streef * 100 for c, band in b.items()}


def test_zeer_defensief_laat_kleine_aandelenposities_weg():
    posities, _ = maak_voorstel(banden("zeer-defensief"), FONDSEN, [])
    assert posities == {WERELD: 1000, AGG: 3250, EURO_AGG: 3250, GELD: 2500}


def test_uitsluiting_verdeelt_gewicht_over_de_rest():
    uit = [Uitsluiting("regio", "opkomende-markten", "wens klant")]
    posities, opmerkingen = maak_voorstel(banden(), FONDSEN, uit)
    # 50% over 78:10 → 44,3 en 5,7.
    assert (posities[WERELD], posities[KLEIN]) == (4430, 570) and EM not in posities
    assert [o.code for o in opmerkingen] == ["startselectie_aangepast"]
    assert sum(posities.values()) == TOTAAL


def test_hele_startselectie_uitgesloten_valt_terug_op_goedkoopste_breed_fonds():
    uit = [Uitsluiting("instrument", AGG), Uitsluiting("instrument", EURO_AGG)]
    posities, _ = maak_voorstel(banden(), FONDSEN, uit)
    assert posities[EURO_STAAT] == 3800
    # Een sectorfonds is nooit de terugvaloptie.
    alles = [Uitsluiting("instrument", i) for i in (WERELD, EM, KLEIN, SRI)]
    posities, opmerkingen = maak_voorstel(banden(), FONDSEN, alles)
    assert not any(FONDSEN[i].categorie == "aandelen" for i in posities)
    assert "geen_instrument" in [o.code for o in opmerkingen]
    assert "totaal" in codes(reken_door(posities, FONDSEN, banden(), alles), "fout")


def test_duurzaam_voorstel_gebruikt_duurzame_variant_als_die_beschikbaar_is():
    posities, _ = maak_voorstel(banden(), FONDSEN, [], duurzaam=True)
    assert posities[SRI] == 3900 and WERELD not in posities
    posities, _ = maak_voorstel(banden(), FONDSEN, [Uitsluiting("instrument", SRI)], duurzaam=True)
    assert posities[WERELD] == 3900


def test_inactief_fonds_komt_niet_in_voorstel():
    fondsen = FONDSEN | {GELD: fonds(GELD, "liquiditeiten", actief=False)}
    posities, opmerkingen = maak_voorstel(banden(), fondsen, [])
    assert GELD not in posities and "geen_instrument" in [o.code for o in opmerkingen]


# --- doorrekening ----------------------------------------------------------------------

NEUTRAAL = {
    WERELD: 3900,
    EM: 600,
    KLEIN: 500,
    AGG: 1900,
    EURO_AGG: 1900,
    VASTGOED: 500,
    GRONDSTOF: 200,
    GELD: 500,
}


def test_handmatig_nagerekende_verdeling_en_kosten():
    d = reken_door(NEUTRAAL, FONDSEN, banden(), [])
    assert d.totaal == TOTAAL and d.bevindingen == []
    assert d.per_categorie == {
        "aandelen": 5000,
        "obligaties": 3800,
        "vastgoed": 500,
        "grondstoffen": 200,
        "liquiditeiten": 500,
    }
    assert d.per_regio == {"wereld": 6500 + 500, "europa": 2400, "opkomende-markten": 600}
    assert d.per_sector == {"breed": 9500, "vastgoed": 500}
    assert (d.zakelijke_waarden, d.grootste_positie, d.aantal_instrumenten) == (5700, 3900, 8)
    # 39%×0,20 + 6%×0,18 + 5%×0,35 + 19%×0,10 + 19%×0,16 + 5%×0,59 + 2%×0,46 + 5%×0,10
    # = 0,078 + 0,0108 + 0,0175 + 0,019 + 0,0304 + 0,0295 + 0,0092 + 0,005 = 0,1994
    assert d.kosten_pct == pytest.approx(0.1994)
    assert d.kosten_per_positie[WERELD] == pytest.approx(0.078)
    assert sum(d.kosten_per_positie.values()) == pytest.approx(d.kosten_pct)


def test_grenzen_van_de_band_zijn_toegestaan_en_erbuiten_is_afwijking():
    # Neutraal staat 40–60% aandelen en 25–50% obligaties toe.
    op_grens = NEUTRAAL | {WERELD: 4900, AGG: 900}
    d = reken_door(op_grens, FONDSEN, banden(), [])
    assert (d.per_categorie["aandelen"], d.per_categorie["obligaties"]) == (6000, 2800)
    assert d.bevindingen == []

    net_erover = NEUTRAAL | {WERELD: 4910, AGG: 890}
    d = reken_door(net_erover, FONDSEN, banden(), [])
    assert codes(d) == ["buiten_risicoprofiel"]
    assert d.bevindingen[0].melding == (
        "Aandelen weegt 60,1%; het risicoprofiel staat 40% tot 60% toe"
    )
    assert d.afwijkingen and not d.fouten

    te_weinig = NEUTRAAL | {WERELD: 2890, AGG: 2910}
    d = reken_door(te_weinig, FONDSEN, banden(), [])
    assert [b.melding[:8] for b in d.afwijkingen] == ["Aandelen"]


def test_meerdere_categorieen_buiten_de_band_worden_elk_gemeld():
    alles_aandelen = {WERELD: 7000, EM: 1000, KLEIN: 1000, SRI: 1000}
    d = reken_door(alles_aandelen, FONDSEN, banden(), [])
    buiten = [b.melding.split()[0] for b in d.bevindingen if b.code == "buiten_risicoprofiel"]
    assert buiten == ["Aandelen", "Obligaties"]  # de overige mogen 0% zijn


def test_concentratiegrenzen_per_soort_instrument():
    b = banden("zeer-offensief")
    basis = {WERELD: 7000, EM: 1000, KLEIN: 500, AGG: 500, VASTGOED: 500, GRONDSTOF: 300, GELD: 200}
    assert reken_door(basis, FONDSEN, b, []).bevindingen == []  # precies 70% mag
    d = reken_door(basis | {WERELD: 7010, EM: 990}, FONDSEN, b, [])
    assert [x.melding for x in d.afwijkingen] == [
        "Fonds Y983 weegt 70,1%; het maximum voor één instrument is 70%"
    ]

    met_sector = basis | {WERELD: 6000, ZORG: 1000}
    assert reken_door(met_sector, FONDSEN, b, []).bevindingen == []  # precies 10% mag
    d = reken_door(basis | {WERELD: 5990, ZORG: 1010}, FONDSEN, b, [])
    assert codes(d) == ["concentratie"] and "sectorfonds" in d.bevindingen[0].melding

    goud = basis | {GOUD: 510, WERELD: 6490}
    d = reken_door(goud, FONDSEN, b, [])
    assert codes(d) == ["buiten_risicoprofiel"]  # grondstoffen 8,1% > 8%; goud zelf 5,1% mag
    veel_goud = {WERELD: 6490, EM: 1000, KLEIN: 500, AGG: 500, VASTGOED: 500, GOUD: 1010}
    d = reken_door(veel_goud, FONDSEN, b, [])
    assert codes(d) == ["concentratie", "buiten_risicoprofiel"]


def test_sectorfondsen_samen_begrensd_en_vastgoedfonds_telt_niet_als_sectorfonds():
    b = banden("zeer-offensief")
    drie = {WERELD: 5500, ZORG: 1000, TECH: 1000, ENERGIE: 1000, AGG: 500, VASTGOED: 500, GELD: 500}
    assert reken_door(drie, FONDSEN, b, []).bevindingen == []  # precies 30% mag
    vier = drie | {WERELD: 5400, FIN: 100}
    assert codes(reken_door(vier, FONDSEN, b, [])) == ["sectorfondsen"]
    assert reken_door(drie, FONDSEN, b, []).per_sector["vastgoed"] == 500


def test_minimale_spreiding():
    b = banden("zeer-defensief")
    drie = {AGG: 5000, EURO_AGG: 2500, GELD: 2500}
    assert codes(reken_door(drie, FONDSEN, b, [])) == ["spreiding"]
    vier = {AGG: 4000, EURO_AGG: 2500, GELD: 2500, WERELD: 1000}
    assert reken_door(vier, FONDSEN, b, []).bevindingen == []


@pytest.mark.parametrize(
    ("posities", "uitsluitingen", "code"),
    [
        ({}, [], "leeg"),
        (NEUTRAAL | {GELD: 490}, [], "totaal"),
        (NEUTRAAL | {GELD: 510}, [], "totaal"),
        (NEUTRAAL | {"XX0000000000": 0}, [], "onbekend"),
        (NEUTRAAL | {GOUD: 0}, [], "gewicht"),
        (NEUTRAAL | {GOUD: -5}, [], "gewicht"),
        (NEUTRAAL | {GELD: 500.0}, [], "gewicht"),
        (NEUTRAAL, [Uitsluiting("instrument", EM)], "uitgesloten"),
        (NEUTRAAL, [Uitsluiting("regio", "opkomende-markten")], "uitgesloten"),
        (NEUTRAAL, [Uitsluiting("sector", "vastgoed")], "uitgesloten"),
    ],
)
def test_fouten_blokkeren(posities, uitsluitingen, code):
    d = reken_door(posities, FONDSEN, banden(), uitsluitingen)
    assert code in codes(d, "fout")


def test_bij_fout_totaal_worden_de_banden_niet_getoetst():
    d = reken_door({WERELD: 1000, AGG: 1000, EURO_AGG: 500, GELD: 500}, FONDSEN, banden(), [])
    assert codes(d) == ["totaal"]
    assert d.bevindingen[0].melding == "De gewichten tellen op tot 30% in plaats van 100%"


def test_inactief_fonds_in_portefeuille_is_fout():
    fondsen = FONDSEN | {GELD: fonds(GELD, "liquiditeiten", actief=False)}
    assert codes(reken_door(NEUTRAAL, fondsen, banden(), []), "fout") == ["inactief"]


def test_aandachtspunten_blokkeren_niet():
    fondsen = FONDSEN | {WERELD: fonds(WERELD, "aandelen", geverifieerd=False)}
    uit = [Uitsluiting("sector", "energie")]
    d = reken_door(NEUTRAAL, fondsen, banden(), uit, "sterk", ("wapens", "tabak"))
    assert codes(d) == ["kosten_ongeverifieerd", "uitsluiting_op_label", "duurzaamheid"]
    assert not d.fouten and not d.afwijkingen
    assert "uitsluiten van wapens, tabak" in d.bevindingen[2].melding
    # Een uitsluiting op instrument geeft geen labelwaarschuwing.
    d = reken_door(NEUTRAAL, FONDSEN, banden(), [Uitsluiting("instrument", GOUD)])
    assert d.bevindingen == []


def test_valutarisico_per_soort():
    fondsen = FONDSEN | {
        WERELD: Fonds(WERELD, "W", "aandelen", "wereld", "breed", 0.2, True, valutarisico="ja"),
        AGG: Fonds(AGG, "A", "obligaties", "wereld", "breed", 0.1, True, valutarisico="nee"),
        EURO_AGG: Fonds(
            EURO_AGG, "E", "obligaties", "europa", "breed", 0.16, True, valutarisico="nee"
        ),
    }
    d = reken_door(NEUTRAAL, fondsen, banden(), [])
    assert d.valutarisico == {"ja": 3900, "deels": 0, "nee": 3800, "onbekend": 2300}
    assert sum(d.valutarisico.values()) == TOTAAL
