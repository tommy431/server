from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.data.bronnen import (
    BronFout,
    EcbBron,
    Koerspunt,
    Koersreeks,
    YahooBron,
    haal_kortlopende_rente,
    lees_koersen_csv,
)
from app.data.kwaliteit import controleer_reeks
from app.data.universum import UniversumFout, isin_geldig, laad_universum
from app.data.verversen import ververs_alles, ververs_instrument
from app.models import Instrument, Koers, Wisselkoers
from tests.conftest import UNIVERSUM, UNIVERSUM_KOP

VANDAAG = date(2026, 11, 16)


def reeks(n=10, eind=VANDAAG, start=100.0):
    """Dagelijkse reeks die elke dag 1 stijgt en op `eind` stopt."""
    return [Koerspunt(eind - timedelta(days=n - 1 - i), start + i, start + i) for i in range(n)]


def yahoo(inhoud, status=200):
    return YahooBron(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=inhoud)))
    )


# --- universum -------------------------------------------------------------------------


def test_isin_controlecijfer():
    assert isin_geldig("IE00B4L5Y983")
    assert isin_geldig("US0378331005")
    assert not isin_geldig("IE00B4L5Y984")
    assert not isin_geldig("ie00b4l5y983")
    assert not isin_geldig("IE00B4L5Y98")


def test_meegeleverd_universum_is_geldig_en_dekt_alles(db):
    tekst = (Path(__file__).parent.parent / "data" / "universum.csv").read_text("utf-8")
    toegevoegd, _ = laad_universum(db, tekst)
    db.commit()
    instrumenten = db.scalars(select(Instrument)).all()
    assert toegevoegd == len(instrumenten) == 40
    from app.models import CATEGORIEEN, REGIOS, SECTOREN

    assert {i.categorie for i in instrumenten} == set(CATEGORIEEN)
    assert {i.regio for i in instrumenten} == set(REGIOS)
    assert {i.sector for i in instrumenten} == set(SECTOREN)


def test_universum_bijwerken_op_isin(db):
    assert laad_universum(db, UNIVERSUM) == (2, 0)
    db.commit()
    gewijzigd = UNIVERSUM.replace("0.20,nee,nee", "0.17,ja,nee")
    assert laad_universum(db, gewijzigd) == (0, 2)
    db.commit()
    wereld = db.scalar(select(Instrument).where(Instrument.isin == "IE00B4L5Y983"))
    assert wereld.lopende_kosten == 0.17 and wereld.kosten_geverifieerd
    assert wereld.startdatum == date(2009, 9, 25)


def test_universum_alles_of_niets_met_regelnummers(db):
    fout = (
        UNIVERSUM
        + "IE00B4L5Y984,X.AS,Fout controlecijfer,aandelen,wereld,breed,EUR,0.2,nee,nee,\n"
        + "IE00B5BMR087,C.AS,Onbekende regio,aandelen,mars,breed,EUR,0.2,nee,nee,\n"
        + "IE00B4L5Y983,D.AS,Dubbel,aandelen,wereld,breed,EUR,0.2,nee,nee,\n"
        + "IE00B3RBWM25,V.AS,Kosten,aandelen,wereld,breed,EUR,20,nee,nee,\n"
    )
    with pytest.raises(UniversumFout) as info:
        laad_universum(db, fout)
    db.rollback()
    assert [f.split(":")[0] for f in info.value.fouten] == [
        "Regel 4",
        "Regel 5",
        "Regel 6",
        "Regel 7",
    ]
    assert db.scalars(select(Instrument)).all() == []


def test_universum_ontbrekende_kolom_en_leeg_bestand(db):
    with pytest.raises(UniversumFout, match="Ontbrekende kolommen"):
        laad_universum(db, "isin,ticker\nIE00B4L5Y983,IWDA.AS\n")
    with pytest.raises(UniversumFout, match="geen instrumenten"):
        laad_universum(db, UNIVERSUM_KOP)


# --- kwaliteit -------------------------------------------------------------------------


def codes(punten):
    return [(b.ernst, b.code) for b in controleer_reeks(punten, VANDAAG)]


def test_schone_reeks_heeft_geen_bevindingen():
    assert codes(reeks()) == []


def test_lege_reeks_en_ongeldige_koers_zijn_fouten():
    assert codes([]) == [("fout", "geen_data")]
    punten = reeks()
    punten[3] = Koerspunt(punten[3].datum, 0.0, 0.0)
    assert codes(punten) == [("fout", "ongeldige_koers")]
    punten[3] = Koerspunt(punten[3].datum, float("nan"), 1.0)
    assert codes(punten) == [("fout", "ongeldige_koers")]


def test_gat_sprong_en_veroudering_zijn_waarschuwingen():
    punten = reeks()
    del punten[2:9]  # 8 dagen tussen twee koersen
    assert ("waarschuwing", "gat") in codes(punten)

    punten = reeks()
    punten[5] = Koerspunt(punten[5].datum, 150.0, 150.0)
    bevindingen = controleer_reeks(punten, VANDAAG)
    assert [b.code for b in bevindingen] == ["sprong"]
    assert "2 koerssprong" in bevindingen[0].melding  # omhoog en weer terug

    assert codes(reeks(eind=VANDAAG - timedelta(days=8))) == [("waarschuwing", "verouderd")]
    assert codes(reeks(eind=VANDAAG - timedelta(days=7))) == []


def test_weekend_en_grens_van_twintig_procent_geven_geen_bevinding():
    punten = [
        Koerspunt(date(2026, 11, 13), 100.0, 100.0),  # vrijdag
        Koerspunt(date(2026, 11, 16), 120.0, 120.0),  # maandag, precies +20%
    ]
    assert codes(punten) == []


# --- bronnen ---------------------------------------------------------------------------


def yahoo_antwoord(**meta):
    dag = 86400
    t0 = 1794787200  # 2026-11-16 00:00 UTC
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {"currency": "EUR", "gmtoffset": 3600, "dataGranularity": "1d", **meta},
                    "timestamp": [t0 - 3 * dag + 8 * 3600, t0 - 2 * dag + 8 * 3600, t0 + 8 * 3600],
                    "indicators": {
                        "quote": [{"close": [100.0, None, 102.0]}],
                        "adjclose": [{"adjclose": [98.0, None, 102.0]}],
                    },
                }
            ],
        }
    }


def test_yahoo_leest_dagkoersen_en_slaat_dagen_zonder_handel_over():
    uit = yahoo(yahoo_antwoord()).haal_koersen("IWDA.AS", date(2005, 1, 1))
    assert uit == Koersreeks(
        "EUR",
        [Koerspunt(date(2026, 11, 13), 100.0, 98.0), Koerspunt(date(2026, 11, 16), 102.0, 102.0)],
    )


def test_yahoo_gebruikt_lokale_beursdatum():
    antwoord = yahoo_antwoord(gmtoffset=9 * 3600)
    antwoord["chart"]["result"][0]["timestamp"] = [1794787200 - 3600] * 3  # 23:00 UTC op de 15e
    punten = yahoo(antwoord).haal_koersen("X.T", date(2005, 1, 1)).punten
    assert punten[-1].datum == date(2026, 11, 16)


@pytest.mark.parametrize(
    "inhoud",
    [
        {"chart": {"result": None, "error": {"description": "No data found"}}},
        yahoo_antwoord(dataGranularity="1mo"),
        {"onverwacht": True},
    ],
)
def test_yahoo_fouten_worden_bronfout(inhoud):
    with pytest.raises(BronFout):
        yahoo(inhoud).haal_koersen("X", date(2005, 1, 1))


def test_yahoo_onbereikbaar_en_geen_json_worden_bronfout():
    def weigert(_):
        raise httpx.ConnectError("geen verbinding")

    with pytest.raises(BronFout):
        YahooBron(httpx.Client(transport=httpx.MockTransport(weigert))).haal_koersen(
            "X", date(2005, 1, 1)
        )
    html = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>blokkade</html>"))
    )
    with pytest.raises(BronFout):
        YahooBron(html).haal_koersen("X", date(2005, 1, 1))


def ecb(tekst, status=200):
    return EcbBron(
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, text=tekst)))
    )


ECB_CSV = (
    "KEY,FREQ,CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,2026-11-13,1.0850\n"
    "EXR.D.USD.EUR.SP00.A,D,USD,EUR,2026-11-16,1.0900\n"
    "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,2026-11-16,0.8345\n"
    "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,2026-11-17,\n"
)


def test_ecb_leest_wisselkoersen():
    uit = ecb(ECB_CSV).haal_wisselkoersen(["GBP", "USD"], date(2005, 1, 1))
    assert uit == {
        "USD": {date(2026, 11, 13): 1.085, date(2026, 11, 16): 1.09},
        "GBP": {date(2026, 11, 16): 0.8345},
    }


def test_ecb_fouten_worden_bronfout():
    with pytest.raises(BronFout):
        ecb("", status=503).haal_wisselkoersen(["USD"], date(2005, 1, 1))
    with pytest.raises(BronFout, match="geen wisselkoersen voor CHF"):
        ecb(ECB_CSV).haal_wisselkoersen(["USD", "GBP", "CHF"], date(2005, 1, 1))


def test_koersen_csv():
    punten = lees_koersen_csv("datum,slot,slot_gecorrigeerd\n2026-11-16,102,101\n2026-11-13,100,\n")
    assert punten == [
        Koerspunt(date(2026, 11, 13), 100.0, 100.0),
        Koerspunt(date(2026, 11, 16), 102.0, 101.0),
    ]
    for fout in (
        "dag,prijs\n2026-11-16,1\n",
        "datum,slot\n16-11-2026,1\n",
        "datum,slot\n2026-11-16,abc\n",
        "datum,slot\n2026-11-16,1\n2026-11-16,2\n",
        "datum,slot\n",
    ):
        with pytest.raises(BronFout):
            lees_koersen_csv(fout)


# --- verversen -------------------------------------------------------------------------


class NepBron:
    naam = "nep"

    def __init__(self, reeksen):
        self.reeksen = reeksen

    def haal_koersen(self, ticker, vanaf):
        uit = self.reeksen[ticker]
        if isinstance(uit, Exception):
            raise uit
        return uit


class NepEcb:
    naam = "ecb"

    def __init__(self):
        self.gevraagd = None

    def haal_wisselkoersen(self, valuta, vanaf):
        self.gevraagd = valuta
        return {v: {VANDAAG: 1.1} for v in valuta}


@pytest.fixture
def universum(db):
    laad_universum(db, UNIVERSUM)
    db.commit()
    return {i.ticker: i for i in db.scalars(select(Instrument))}


def opgeslagen(db, instrument):
    return db.scalars(
        select(Koers).where(Koers.instrument_id == instrument.id).order_by(Koers.datum)
    ).all()


def test_verversen_vervangt_de_hele_reeks(db, universum):
    wereld = universum["IWDA.AS"]
    ververs_instrument(db, wereld, NepBron({"IWDA.AS": Koersreeks("EUR", reeks(10))}), VANDAAG)
    nieuw = reeks(5, start=50.0)
    r = ververs_instrument(db, wereld, NepBron({"IWDA.AS": Koersreeks("EUR", nieuw)}), VANDAAG)
    assert r.fout is None and r.opgeslagen == 5
    rijen = opgeslagen(db, wereld)
    assert [(k.datum, k.slot) for k in rijen] == [(p.datum, p.slot) for p in nieuw]
    assert {k.bron for k in rijen} == {"nep"}


@pytest.mark.parametrize(
    "slecht",
    [
        Koersreeks("USD", reeks(5)),  # andere valuta dan geregistreerd
        Koersreeks("EUR", []),
        Koersreeks("EUR", [Koerspunt(VANDAAG, -1.0, -1.0)]),
        BronFout("bron plat"),
    ],
)
def test_slechte_levering_laat_bestaande_koersen_staan(db, universum, slecht):
    wereld = universum["IWDA.AS"]
    ververs_instrument(db, wereld, NepBron({"IWDA.AS": Koersreeks("EUR", reeks(10))}), VANDAAG)
    r = ververs_instrument(db, wereld, NepBron({"IWDA.AS": slecht}), VANDAAG)
    assert r.fout and r.opgeslagen == 0
    assert len(opgeslagen(db, wereld)) == 10


def test_een_fout_stopt_de_rest_niet_en_euro_vraagt_geen_wisselkoers(db, universum):
    bron = NepBron({"IWDA.AS": BronFout("plat"), "IEGA.AS": Koersreeks("EUR", reeks(4))})
    ecb_bron = NepEcb()
    resultaten = {r.onderdeel: r for r in ververs_alles(db, bron, ecb_bron, VANDAAG)}
    assert resultaten["IE00B4L5Y983"].fout == "plat"
    assert resultaten["IE00B4WXJJ64"].opgeslagen == 4
    assert resultaten["wisselkoersen"].opgeslagen == 0 and ecb_bron.gevraagd is None


def test_wisselkoersen_voor_vreemde_valuta_en_pence(db, universum):
    universum["IWDA.AS"].valuta = "USD"
    universum["IEGA.AS"].valuta = "GBp"
    db.commit()
    bron = NepBron({"IWDA.AS": Koersreeks("USD", reeks(3)), "IEGA.AS": Koersreeks("GBp", reeks(3))})
    ecb_bron = NepEcb()
    resultaten = ververs_alles(db, bron, ecb_bron, VANDAAG)
    assert all(r.fout is None for r in resultaten)
    assert ecb_bron.gevraagd == ["GBP", "USD"]
    assert {w.valuta for w in db.scalars(select(Wisselkoers))} == {"GBP", "USD"}
    ververs_alles(db, bron, ecb_bron, VANDAAG)  # opnieuw verversen dupliceert niets
    assert len(db.scalars(select(Wisselkoers)).all()) == 2


def test_kortlopende_rente_eonia_tot_oktober_2019_daarna_estr():
    def antwoord(verzoek):
        if "EON/" in str(verzoek.url):
            assert verzoek.url.params["endPeriod"] == "2019-09-30"
            return httpx.Response(
                200, text="TIME_PERIOD,OBS_VALUE\n2019-09-27,-0.45\n2019-09-30,-0.46\n"
            )
        return httpx.Response(
            200, text="TIME_PERIOD,OBS_VALUE\n2019-10-01,-0.549\n2026-11-13,2.437\n"
        )

    client = httpx.Client(transport=httpx.MockTransport(antwoord))
    assert haal_kortlopende_rente(client, date(2005, 1, 1)) == [
        (date(2019, 9, 27), -0.45, "EONIA"),
        (date(2019, 9, 30), -0.46, "EONIA"),
        (date(2019, 10, 1), -0.549, "ESTR"),
        (date(2026, 11, 13), 2.437, "ESTR"),
    ]
    leeg = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="TIME_PERIOD,OBS_VALUE\n"))
    )
    with pytest.raises(BronFout):
        haal_kortlopende_rente(leeg, date(2020, 1, 1))


def test_herimport_zonder_valutakolom_laat_valutarisico_staan(db):
    kop = UNIVERSUM_KOP.strip() + ",valutarisico\n"
    rijen = "".join(r + ",ja\n" for r in UNIVERSUM.splitlines()[1:])
    laad_universum(db, kop + rijen)
    db.commit()
    laad_universum(db, UNIVERSUM)
    db.commit()
    assert {i.valutarisico for i in db.scalars(select(Instrument))} == {"ja"}
    # Een nieuw fonds zonder kolom krijgt "onbekend".
    extra = (
        UNIVERSUM_KOP
        + "IE00B5BMR087,CSPX.AS,S&P 500,aandelen,noord-amerika,breed,EUR,0.07,nee,nee,\n"
    )
    laad_universum(db, extra)
    db.commit()
    nieuw = db.scalar(select(Instrument).where(Instrument.isin == "IE00B5BMR087"))
    assert nieuw.valutarisico == "onbekend"
