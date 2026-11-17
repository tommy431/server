import pytest

from app.bezitimport import isin_geldig, lees_bezit, lees_getal

WERELD, OBL = "IE00B4L5Y983", "IE00B4WXJJ64"


def test_isin_controlecijfer():
    assert isin_geldig(WERELD) and isin_geldig(OBL) and isin_geldig("US0378331005")
    assert not isin_geldig("IE00B4L5Y984")
    assert not isin_geldig("IE00B4L5Y98")


@pytest.mark.parametrize(
    ("tekst", "decimaal", "getal"),
    [
        ("1.234,56", ",", 1234.56),
        ("1,234.56", ",", 1234.56),
        ("1234,5", ",", 1234.5),
        ("1 234", ",", 1234),
        ("12", ",", 12),
        ("1.234.567", ",", 1234567),
        ("0,0123", ",", 0.0123),
        ("1.250", ",", 1250),
        ("1.250", ".", 1.25),
        ("1,250", ".", 1250),
        ("1.2.3", ".", None),
        ("", ",", None),
        ("abc", ",", None),
    ],
)
def test_getallen(tekst, decimaal, getal):
    assert lees_getal(tekst, decimaal) == getal


def test_nederlandse_export_met_puntkomma():
    tekst = (
        "﻿Portefeuilleoverzicht per 14-11-2026\n"
        "\n"
        "Product;ISIN;Aantal;Koers;Waarde\n"
        f"iShares Core MSCI World;{WERELD};1.250;98,12;122.650,00\n"
        f"iShares Euro Govt Bond;{OBL};300,5;5,10;1.532,55\n"
        "Geldsaldo;;;;1.000,00\n"
        "Totaal;;;;125.182,55\n"
    )
    r = lees_bezit(tekst)
    # '1.250' met punt zonder komma: duizendtalscheiding in een Nederlandse export.
    assert r.posities == {WERELD: 1250, OBL: 300.5}
    assert r.meldingen == ["2 regel(s) zonder ISIN overgeslagen, bijvoorbeeld totalen of geldsaldo"]


def test_engelse_export_met_komma_en_isin_in_omschrijving():
    tekst = (
        "Instrument,Quantity,Value\n"
        f'"iShares World ({WERELD})",10,"1,234.50"\n'
        f'"iShares World ({WERELD})",5,"600.00"\n'
    )
    r = lees_bezit(tekst)
    assert r.posities == {WERELD: 15}
    assert r.meldingen == [f"{WERELD} kwam meerdere keren voor; de aantallen zijn opgeteld"]


def test_decimaalteken_volgt_uit_het_bestand():
    # Een Engelse export met puntkomma: '1.250' is hier 1,25 stuk, want '98.12' laat geen twijfel.
    tekst = f"ISIN;Quantity;Price\n{WERELD};1.250;98.12\n"
    assert lees_bezit(tekst).posities == {WERELD: 1.25}
    # Zonder uitsluitsel bij puntkomma: Nederlands.
    assert lees_bezit(f"ISIN;Aantal\n{WERELD};1.250\n").posities == {WERELD: 1250}


def test_fouten_worden_gemeld():
    tekst = f"ISIN;Aantal\nIE00B4L5Y984;10\n{WERELD};onbekend\n{OBL};-3\n"
    r = lees_bezit(tekst)
    assert r.posities == {}
    assert any("niet leesbaar" in m for m in r.meldingen)
    assert any("niet positief" in m for m in r.meldingen)
    assert any("controlecijfer" in m for m in r.meldingen)


def test_zonder_aantalkolom():
    r = lees_bezit(f"ISIN;Waarde\n{WERELD};100\n")
    assert r.posities == {} and "Geen kolom met het aantal" in r.meldingen[0]


def test_leeg_en_te_groot():
    assert lees_bezit("").meldingen == ["Het bestand is leeg"]
    assert "te groot" in lees_bezit("x" * 1_000_001).meldingen[0]
