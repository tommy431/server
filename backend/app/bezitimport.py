"""Bezit inlezen uit een export van de bank of broker (CSV).

Exports verschillen per bank. We zoeken daarom zelf de kolommen: het ISIN herkennen we aan de
vorm en het controlecijfer, het aantal aan de kolomkop. Er wordt niets opgeslagen; de adviseur
controleert het resultaat in het formulier.
"""

import csv
import io
import re
from dataclasses import dataclass, field

MAX_TEKENS = 1_000_000
_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
# Kolomkoppen voor het aantal stukken, in volgorde van voorkeur.
_AANTAL_KOPPEN = (
    "aantal",
    "aantal stuks",
    "stukken",
    "aantal stukken",
    "hoeveelheid",
    "quantity",
    "qty",
    "units",
    "nominaal",
    "positie",
)
# Kolomkoppen voor de waarde in euro's; nodig voor bezit buiten de fondsenlijst.
_WAARDE_KOPPEN = (
    "waarde",
    "waarde eur",
    "waarde (eur)",
    "waarde in eur",
    "marktwaarde",
    "actuele waarde",
    "value",
    "market value",
    "value eur",
    "value (eur)",
)


@dataclass
class Inleesresultaat:
    posities: dict[str, float] = field(default_factory=dict)
    meldingen: list[str] = field(default_factory=list)
    omschrijvingen: dict[str, str] = field(default_factory=dict)
    waarden: dict[str, float | None] = field(
        default_factory=dict
    )  # alleen als er een waardekolom is


def isin_geldig(isin: str) -> bool:
    """Controleert het ISIN-controlecijfer (Luhn over de cijferreeks, letters A=10 … Z=35)."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        return False
    cijfers = "".join(str(int(t, 36)) for t in isin)
    som = 0
    for i, c in enumerate(reversed(cijfers)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        som += d
    return som % 10 == 0


def lees_getal(tekst: str, decimaal: str = ",") -> float | None:
    """Leest een getal; `decimaal` is het decimaalteken van het bestand ("," of ".").

    Staan beide tekens in het getal, dan is het laatste het decimaalteken, wat het bestand ook
    gebruikt.
    """
    t = tekst.strip().replace("\u00a0", "").replace(" ", "").replace("'", "")
    if not t:
        return None
    if "," in t and "." in t:
        decimaal = "," if t.rfind(",") > t.rfind(".") else "."
    duizend = "." if decimaal == "," else ","
    t = t.replace(duizend, "").replace(decimaal, ".")
    if t.count(".") > 1:
        return None
    try:
        return float(t)
    except ValueError:
        return None


_ZEKER_KOMMA = re.compile(r"^-?\d{1,3}(\.\d{3})+,\d+$|^-?\d+,(\d{1,2}|\d{4,})$")
_ZEKER_PUNT = re.compile(r"^-?\d{1,3}(,\d{3})+\.\d+$|^-?\d+\.(\d{1,2}|\d{4,})$")


def _decimaalteken(rijen: list[list[str]], scheiding: str) -> str:
    """Bepaalt het decimaalteken uit getallen die geen twijfel laten, zoals '5,10' of '1,234.50'."""
    komma = punt = 0
    for rij in rijen:
        for c in rij:
            c = c.strip().replace(" ", "")
            komma += bool(_ZEKER_KOMMA.match(c))
            punt += bool(_ZEKER_PUNT.match(c))
    if komma != punt:
        return "," if komma > punt else "."
    # Geen uitsluitsel: een bestand met komma als scheidingsteken gebruikt de punt als decimaal.
    return "." if scheiding == "," else ","


def _scheidingsteken(tekst: str) -> str:
    regels = [r for r in tekst.splitlines() if r.strip()][:20]
    kandidaten = {s: sum(r.count(s) for r in regels) for s in (";", "\t", ",")}
    # Komma's komen ook in getallen voor; kies ; of tab als die voorkomen.
    for s in (";", "\t"):
        if kandidaten[s] >= len(regels) // 2 and kandidaten[s] > 0:
            return s
    return ","


def lees_bezit(tekst: str) -> Inleesresultaat:
    uit = Inleesresultaat()
    if len(tekst) > MAX_TEKENS:
        uit.meldingen.append("Het bestand is te groot (meer dan 1 MB)")
        return uit
    tekst = tekst.lstrip("\ufeff")  # byte-order mark van Excel
    scheiding = _scheidingsteken(tekst)
    rijen = [
        r for r in csv.reader(io.StringIO(tekst), delimiter=scheiding) if any(c.strip() for c in r)
    ]
    if not rijen:
        uit.meldingen.append("Het bestand is leeg")
        return uit

    # Kopregel: de eerste regel met een herkende kolomkop voor het aantal.
    kop_index, aantal_kolom = None, None
    for i, rij in enumerate(rijen[:20]):
        koppen = [c.strip().lower() for c in rij]
        for naam in _AANTAL_KOPPEN:
            if naam in koppen:
                kop_index, aantal_kolom = i, koppen.index(naam)
                break
        if kop_index is not None:
            break
    if aantal_kolom is None:
        uit.meldingen.append(
            "Geen kolom met het aantal stukken gevonden. Verwacht een kolomkop als 'Aantal', "
            "'Stukken' of 'Quantity'."
        )
        return uit

    koppen = [c.strip().lower() for c in rijen[kop_index]]
    waarde_kolom = next((koppen.index(k) for k in _WAARDE_KOPPEN if k in koppen), None)
    decimaal = _decimaalteken(rijen[kop_index + 1 :], scheiding)
    zonder_isin, ongeldig, dubbel = 0, [], set()
    for rij in rijen[kop_index + 1 :]:
        isins = [m for c in rij for m in _ISIN.findall(c.strip().upper()) if c.strip()]
        if not isins:
            zonder_isin += 1
            continue
        isin = isins[0]
        if not isin_geldig(isin):
            ongeldig.append(isin)
            continue
        aantal = lees_getal(rij[aantal_kolom], decimaal) if aantal_kolom < len(rij) else None
        if aantal is None:
            uit.meldingen.append(
                f"{isin}: aantal '{rij[aantal_kolom] if aantal_kolom < len(rij) else ''}' niet leesbaar; overgeslagen"
            )
            continue
        if aantal <= 0:
            uit.meldingen.append(f"{isin}: aantal {aantal:g} is niet positief; overgeslagen")
            continue
        if isin in uit.posities:
            dubbel.add(isin)
        uit.posities[isin] = uit.posities.get(isin, 0.0) + aantal
        if isin not in uit.omschrijvingen:
            uit.omschrijvingen[isin] = _omschrijving(rij, isin, decimaal) or isin
        if waarde_kolom is not None:
            w = lees_getal(rij[waarde_kolom], decimaal) if waarde_kolom < len(rij) else None
            vorige = uit.waarden.get(isin, 0.0)
            uit.waarden[isin] = None if w is None or vorige is None else vorige + w

    for isin in sorted(dubbel):
        uit.meldingen.append(f"{isin} kwam meerdere keren voor; de aantallen zijn opgeteld")
    if ongeldig:
        uit.meldingen.append("Ongeldig ISIN (controlecijfer klopt niet): " + ", ".join(ongeldig))
    if zonder_isin:
        uit.meldingen.append(
            f"{zonder_isin} regel(s) zonder ISIN overgeslagen, bijvoorbeeld totalen of geldsaldo"
        )
    if not uit.posities and not uit.meldingen:
        uit.meldingen.append("Geen posities gevonden")
    return uit


def _omschrijving(rij: list[str], isin: str, decimaal: str) -> str:
    """De eerste tekstcel van de regel die geen getal is, zonder het ISIN."""
    for c in rij:
        t = re.sub(r"[\s(\[]*" + isin + r"[)\]]*", " ", c.strip(), flags=re.IGNORECASE).strip(
            " -–:"
        )
        if t and lees_getal(t, decimaal) is None and not re.fullmatch(r"[\d\-/.]+", t):
            return t[:200]
    return ""
