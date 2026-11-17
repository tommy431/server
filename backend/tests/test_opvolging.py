from datetime import date

import pytest

from app.opvolging import _plus_maanden, herbalanceer, signalen, waardeer
from app.portefeuille import Fonds

D = date(2026, 11, 17)
A, O, X = "IE00B4L5Y983", "IE00BDBRDM35", "IE00BM67HT60"
FONDSEN = {
    A: Fonds(A, "Aandelen Wereld", "aandelen", "wereld", "breed", 0.2, True),
    O: Fonds(O, "Obligaties Wereld", "obligaties", "wereld", "breed", 0.1, True),
    X: Fonds(X, "Tech", "aandelen", "wereld", "informatietechnologie", 0.25, True),
}
KOERSEN = {A: (D, 100.0), O: (D, 50.0), X: (D, 200.0)}
ADVIES = {A: 6000, O: 4000}
BANDEN = {
    "aandelen": {"streef": 60, "minimum": 50, "maximum": 70},
    "obligaties": {"streef": 40, "minimum": 30, "maximum": 50},
    "liquiditeiten": {"streef": 0, "minimum": 0, "maximum": 10},
}


def test_waardering_handmatig_nagerekend():
    # 800 × 100 = 80.000 aandelen, 300 × 50 = 15.000 obligaties, 5.000 geld: totaal 100.000.
    w = waardeer({A: 800, O: 300}, 5000, KOERSEN, ADVIES, FONDSEN)
    assert w.totaal == 100_000
    assert {p.isin: (p.waarde, p.gewicht, p.advies) for p in w.posities} == {
        A: (80_000, 8000, 6000),
        O: (15_000, 1500, 4000),
    }
    assert w.per_categorie == {"aandelen": 8000, "obligaties": 1500, "liquiditeiten": 500}


def test_herbalancering_handmatig_nagerekend():
    # Doel: 60.000 aandelen en 40.000 obligaties.
    # Verkoop 20.000 / 100 = 200 aandelen. Geld: 5.000 + 20.000 = 25.000.
    # Koop 25.000 / 50 = 500 obligaties. Daarna: 600 × 100 = 60.000 en 800 × 50 = 40.000.
    w = waardeer({A: 800, O: 300}, 5000, KOERSEN, ADVIES, FONDSEN)
    h = herbalanceer(w, ADVIES)
    assert [(t.isin, t.actie, t.aantal, t.bedrag) for t in h.transacties] == [
        (A, "verkoop", 200, 20_000),
        (O, "koop", 500, 25_000),
    ]
    assert h.kas_na == 0 and h.gewichten_na == {A: 6000, O: 4000}


def test_fonds_buiten_advies_wordt_volledig_verkocht_ook_gebroken_aantal():
    w = waardeer({A: 600, O: 700, X: 10.5}, 0, KOERSEN, ADVIES, FONDSEN)
    h = herbalanceer(w, ADVIES)
    verkoop = [t for t in h.transacties if t.isin == X]
    assert verkoop and verkoop[0].aantal == 10.5 and verkoop[0].actie == "verkoop"
    assert X not in h.gewichten_na


def test_te_weinig_geld_verkleint_alle_aankopen_naar_rato():
    # Alles in geld behalve een klein beetje: aankopen in hele stukken, nooit meer dan het saldo.
    w = waardeer({}, 10_000, KOERSEN, ADVIES, FONDSEN)
    h = herbalanceer(w, ADVIES)
    assert [(t.isin, t.aantal) for t in h.transacties] == [(A, 60), (O, 80)]
    assert h.kas_na == pytest.approx(0) and h.kas_na >= 0


def test_kleine_afwijkingen_leiden_niet_tot_transacties():
    w = waardeer({A: 601, O: 798}, 0, KOERSEN, ADVIES, FONDSEN)
    assert herbalanceer(w, ADVIES).transacties == []


def test_zonder_koers_geen_voorstel():
    w = waardeer({A: 10}, 0, {}, ADVIES, FONDSEN)
    assert w.zonder_koers == ["Aandelen Wereld"]
    with pytest.raises(ValueError):
        herbalanceer(w, ADVIES)


# --- signalen --------------------------------------------------------------------------


def codes(**kw):
    basis = {
        "vandaag": D,
        "heeft_profiel": True,
        "advies_datum": date(2026, 6, 1),
        "profiel_na_advies": False,
        "laatste_evaluatie": None,
        "bezit_peildatum": date(2026, 11, 1),
        "waardering": waardeer({A: 600, O: 800}, 0, KOERSEN, ADVIES, FONDSEN),
        "banden": BANDEN,
    }
    return [s.code for s in signalen(**(basis | kw))]


def test_alles_in_orde_geeft_geen_signalen():
    assert codes() == []


def test_buiten_bandbreedte_en_afwijkingen():
    w = waardeer({A: 800, O: 300, X: 10}, 0, KOERSEN, ADVIES, FONDSEN)
    c = codes(waardering=w)
    assert c[0] == "buiten_bandbreedte" and "niet_in_advies" in c
    # Afwijkingen per fonds vallen dan onder het herbalanceringsvoorstel en worden niet herhaald.
    assert "afwijking_positie" not in c
    # Binnen de bandbreedtes wordt een flinke afwijking per fonds wel gemeld.
    assert "afwijking_positie" in codes(waardering=w, banden={})


def test_evaluatie_verlopen_binnenkort_en_na_evaluatie_weer_in_orde():
    assert codes(advies_datum=date(2025, 11, 17)) == ["evaluatie_verlopen"]
    assert codes(advies_datum=date(2025, 12, 10)) == ["evaluatie_binnenkort"]
    assert codes(advies_datum=date(2025, 1, 1), laatste_evaluatie=date(2026, 10, 1)) == []


def test_ontbrekend_of_verouderd_bezit_en_herzien_profiel():
    assert codes(bezit_peildatum=None, waardering=None) == ["geen_bezit"]
    assert codes(bezit_peildatum=date(2026, 6, 1)) == ["bezit_verouderd"]
    assert codes(profiel_na_advies=True) == ["profiel_herzien"]
    assert codes(heeft_profiel=False) == ["geen_profiel"]
    assert codes(advies_datum=None) == ["geen_advies"]


def test_plus_maanden_aan_het_eind_van_de_maand():
    assert _plus_maanden(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _plus_maanden(date(2026, 11, 17), 12) == date(2027, 11, 17)
    assert _plus_maanden(date(2026, 12, 17), -1) == date(2026, 11, 17)
