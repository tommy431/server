"""Koersbronnen achter één interface, zodat een bron later vervangbaar is."""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import httpx


class BronFout(Exception):
    """De bron leverde geen bruikbare gegevens."""


@dataclass(frozen=True)
class Koerspunt:
    datum: date
    slot: float
    slot_gecorrigeerd: float


@dataclass(frozen=True)
class Koersreeks:
    valuta: str
    punten: list[Koerspunt]


class Koersbron(Protocol):
    naam: str

    def haal_koersen(self, ticker: str, vanaf: date) -> Koersreeks: ...


class YahooBron:
    """Dagkoersen van Yahoo Finance.

    Onofficiële interface, alleen toegestaan voor persoonlijk gebruik: geschikt voor het
    prototype, niet voor een commercieel product.
    """

    naam = "yahoo"
    _URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=30, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
        )

    def haal_koersen(self, ticker: str, vanaf: date) -> Koersreeks:
        # Expliciete periode: met range=max levert Yahoo maandkoersen in plaats van dagkoersen.
        begin = int(datetime(vanaf.year, vanaf.month, vanaf.day, tzinfo=UTC).timestamp())
        eind = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
        try:
            antwoord = self._client.get(
                self._URL.format(ticker=ticker),
                params={
                    "period1": begin,
                    "period2": eind,
                    "interval": "1d",
                    "events": "div,split",
                },
            )
            inhoud = antwoord.json()
        except (httpx.HTTPError, ValueError) as fout:
            raise BronFout(f"{ticker}: Yahoo niet bereikbaar ({fout})") from fout

        grafiek = inhoud.get("chart") or {}
        if grafiek.get("error") or not grafiek.get("result"):
            melding = (grafiek.get("error") or {}).get("description", "geen resultaat")
            raise BronFout(f"{ticker}: {melding}")
        resultaat = grafiek["result"][0]
        meta = resultaat["meta"]
        if meta.get("dataGranularity") != "1d":
            raise BronFout(f"{ticker}: geen dagkoersen ontvangen ({meta.get('dataGranularity')})")

        tijden = resultaat.get("timestamp") or []
        indicatoren = resultaat.get("indicators") or {}
        slot = (indicatoren.get("quote") or [{}])[0].get("close") or []
        gecorrigeerd = (indicatoren.get("adjclose") or [{}])[0].get("adjclose") or []
        if not (len(tijden) == len(slot) == len(gecorrigeerd)):
            raise BronFout(f"{ticker}: onvolledige reeks ontvangen")

        verschuiving = timedelta(seconds=meta.get("gmtoffset", 0))
        per_dag: dict[date, Koerspunt] = {}
        for tijd, s, g in zip(tijden, slot, gecorrigeerd, strict=True):
            if s is None or g is None:
                continue  # dag zonder handel
            dag = (datetime.fromtimestamp(tijd, UTC) + verschuiving).date()
            per_dag[dag] = Koerspunt(dag, float(s), float(g))
        return Koersreeks(
            valuta=meta.get("currency", ""), punten=sorted(per_dag.values(), key=lambda p: p.datum)
        )


class EcbBron:
    """Referentiekoersen van de ECB: eenheden vreemde valuta per 1 euro."""

    naam = "ecb"
    _URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{valuta}.EUR.SP00.A"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=60, follow_redirects=True)

    def haal_wisselkoersen(self, valuta: list[str], vanaf: date) -> dict[str, dict[date, float]]:
        try:
            antwoord = self._client.get(
                self._URL.format(valuta="+".join(valuta)),
                params={"format": "csvdata", "startPeriod": vanaf.isoformat()},
            )
            antwoord.raise_for_status()
        except httpx.HTTPError as fout:
            raise BronFout(f"ECB niet bereikbaar ({fout})") from fout

        uit: dict[str, dict[date, float]] = {v: {} for v in valuta}
        for rij in csv.DictReader(io.StringIO(antwoord.text)):
            waarde = rij.get("OBS_VALUE")
            if not waarde:
                continue
            try:
                uit[rij["CURRENCY"]][date.fromisoformat(rij["TIME_PERIOD"])] = float(waarde)
            except (KeyError, ValueError) as fout:
                raise BronFout(f"ECB: onverwachte regel {rij}") from fout
        leeg = [v for v, koersen in uit.items() if not koersen]
        if leeg:
            raise BronFout(f"ECB: geen wisselkoersen voor {', '.join(leeg)}")
        return uit


def lees_koersen_csv(tekst: str) -> list[Koerspunt]:
    """Leest een CSV met kolommen datum (JJJJ-MM-DD), slot en optioneel slot_gecorrigeerd."""
    lezer = csv.DictReader(io.StringIO(tekst))
    if not lezer.fieldnames or not {"datum", "slot"} <= set(lezer.fieldnames):
        raise BronFout("CSV moet de kolommen 'datum' en 'slot' bevatten")
    per_dag: dict[date, Koerspunt] = {}
    for nummer, rij in enumerate(lezer, start=2):
        try:
            dag = date.fromisoformat(rij["datum"].strip())
            slot = float(rij["slot"])
            gecorrigeerd = float(rij.get("slot_gecorrigeerd") or slot)
        except (ValueError, AttributeError) as fout:
            raise BronFout(f"CSV regel {nummer}: {fout}") from fout
        if dag in per_dag:
            raise BronFout(f"CSV regel {nummer}: datum {dag} komt dubbel voor")
        per_dag[dag] = Koerspunt(dag, slot, gecorrigeerd)
    if not per_dag:
        raise BronFout("CSV bevat geen koersen")
    return sorted(per_dag.values(), key=lambda p: p.datum)
