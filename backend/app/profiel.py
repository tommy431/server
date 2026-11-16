"""Vragenlijst, scores en afleiding van het risicoprofiel.

De vragen, punten, grenzen en standaardallocaties zijn voorbeeldwaarden. Ze moeten door de
adviseur en diens compliance-functie worden beoordeeld voordat ze voor echt advies worden
gebruikt.
"""

from dataclasses import dataclass

VRAGENLIJST_VERSIE = 1

# (code, naam) van defensief naar offensief; de positie + 1 is het niveau.
RISICOPROFIELEN = (
    ("zeer-defensief", "Zeer defensief"),
    ("defensief", "Defensief"),
    ("neutraal", "Neutraal"),
    ("offensief", "Offensief"),
    ("zeer-offensief", "Zeer offensief"),
)

# Per profiel en categorie: (streef, minimum, maximum) in procenten.
STANDAARD_ALLOCATIES = {
    "zeer-defensief": {
        "aandelen": (10, 0, 20),
        "obligaties": (65, 50, 80),
        "vastgoed": (0, 0, 5),
        "grondstoffen": (0, 0, 5),
        "liquiditeiten": (25, 10, 40),
    },
    "defensief": {
        "aandelen": (30, 20, 40),
        "obligaties": (55, 40, 70),
        "vastgoed": (5, 0, 10),
        "grondstoffen": (0, 0, 5),
        "liquiditeiten": (10, 0, 25),
    },
    "neutraal": {
        "aandelen": (50, 40, 60),
        "obligaties": (38, 25, 50),
        "vastgoed": (5, 0, 10),
        "grondstoffen": (2, 0, 7),
        "liquiditeiten": (5, 0, 15),
    },
    "offensief": {
        "aandelen": (70, 60, 80),
        "obligaties": (20, 10, 30),
        "vastgoed": (5, 0, 10),
        "grondstoffen": (3, 0, 8),
        "liquiditeiten": (2, 0, 10),
    },
    "zeer-offensief": {
        "aandelen": (85, 75, 95),
        "obligaties": (5, 0, 15),
        "vastgoed": (5, 0, 10),
        "grondstoffen": (3, 0, 8),
        "liquiditeiten": (2, 0, 10),
    },
}

DIMENSIES = {
    "bereidheid": "Risicobereidheid",
    "capaciteit": "Risicocapaciteit",
    "kennis": "Kennis en ervaring",
}

# Elke vraag heeft vier antwoorden; de positie (0–3) is het aantal punten.
VRAGEN = (
    {
        "code": "daling",
        "dimensie": "bereidheid",
        "tekst": "Uw beleggingen dalen binnen een jaar 20% in waarde. Wat doet u?",
        "antwoorden": (
            "Ik verkoop alles",
            "Ik verkoop een deel",
            "Ik doe niets en wacht af",
            "Ik koop bij",
        ),
    },
    {
        "code": "afweging",
        "dimensie": "bereidheid",
        "tekst": "Welke uitspraak past het best bij u?",
        "antwoorden": (
            "Behoud van mijn inleg staat voorop",
            "Ik accepteer kleine schommelingen voor iets meer rendement",
            "Ik accepteer flinke schommelingen voor een hoger rendement",
            "Ik streef naar het hoogste rendement en accepteer grote schommelingen",
        ),
    },
    {
        "code": "verlies",
        "dimensie": "bereidheid",
        "tekst": "Welk verlies in een slecht jaar vindt u nog aanvaardbaar?",
        "antwoorden": ("Tot 5%", "Tot 10%", "Tot 20%", "Meer dan 20%"),
    },
    {
        "code": "onrust",
        "dimensie": "bereidheid",
        "tekst": "Hoe ervaart u tussentijdse koersdalingen?",
        "antwoorden": (
            "Ik lig er wakker van",
            "Ik vind het vervelend en kijk vaak",
            "Ik vind het vervelend maar blijf rustig",
            "Het hoort erbij; het raakt me niet",
        ),
    },
    {
        "code": "aandeel_vermogen",
        "dimensie": "capaciteit",
        "tekst": "Welk deel van uw vrije vermogen gaat u beleggen?",
        "antwoorden": ("Meer dan 75%", "50% tot 75%", "25% tot 50%", "Minder dan 25%"),
    },
    {
        "code": "buffer",
        "dimensie": "capaciteit",
        "tekst": "Hoeveel maanden vaste lasten kunt u betalen uit spaargeld buiten deze belegging?",
        "antwoorden": ("Minder dan 3", "3 tot 6", "6 tot 12", "Meer dan 12"),
    },
    {
        "code": "afhankelijkheid",
        "dimensie": "capaciteit",
        "tekst": "In hoeverre heeft u dit vermogen nodig voor uw levensonderhoud of een vaste verplichting?",
        "antwoorden": ("Volledig", "Grotendeels", "Beperkt", "Niet"),
    },
    {
        "code": "inkomen",
        "dimensie": "capaciteit",
        "tekst": "Hoe zeker is uw inkomen de komende jaren?",
        "antwoorden": ("Onzeker", "Redelijk zeker", "Zeker", "Zeer zeker, met ruimte om te sparen"),
    },
    {
        "code": "ervaring_jaren",
        "dimensie": "kennis",
        "tekst": "Hoe lang belegt u al?",
        "antwoorden": ("Nooit belegd", "Korter dan 3 jaar", "3 tot 10 jaar", "Langer dan 10 jaar"),
    },
    {
        "code": "kennis_producten",
        "dimensie": "kennis",
        "tekst": "Hoe goed kent u aandelen, obligaties en beleggingsfondsen?",
        "antwoorden": (
            "Niet",
            "Ik ken de hoofdlijnen",
            "Ik ken de kenmerken en risico's goed",
            "Ik ben er beroepsmatig mee bezig (geweest)",
        ),
    },
    {
        "code": "meegemaakt",
        "dimensie": "kennis",
        "tekst": "Heeft u als belegger een forse koersdaling meegemaakt?",
        "antwoorden": (
            "Nee",
            "Ja, en ik heb toen verkocht",
            "Ja, en ik ben blijven zitten",
            "Ja, meerdere keren, en ik ben blijven zitten",
        ),
    },
)

# Onder deze horizon (in jaren) is het profiel hooguit het genoemde niveau.
HORIZON_GRENZEN = ((3, 1), (5, 2), (7, 3), (10, 4))
LAGE_KENNIS_GRENS = 34


@dataclass(frozen=True)
class Uitkomst:
    score_bereidheid: int
    score_capaciteit: int
    score_kennis: int
    niveau: int  # 1 (zeer defensief) t/m 5 (zeer offensief)
    bepalende_factor: str  # "bereidheid", "capaciteit" of "horizon"
    lage_kennis: bool


def _niveau_bij_score(score: int) -> int:
    """0–19 → 1, 20–39 → 2, 40–59 → 3, 60–79 → 4, 80–100 → 5."""
    return min(score // 20, 4) + 1


def _niveau_bij_horizon(jaren: int) -> int:
    for grens, niveau in HORIZON_GRENZEN:
        if jaren < grens:
            return niveau
    return 5


def bereken(antwoorden: dict[str, int], horizon_jaren: int) -> Uitkomst:
    """Leidt het risicoprofiel af. De voorzichtigste van bereidheid, capaciteit en horizon bepaalt."""
    verwacht = {v["code"] for v in VRAGEN}
    if set(antwoorden) != verwacht:
        ontbreekt = sorted(verwacht - set(antwoorden))
        onbekend = sorted(set(antwoorden) - verwacht)
        raise ValueError(f"Vragenlijst onvolledig (ontbreekt: {ontbreekt}; onbekend: {onbekend})")
    if any(type(a) is not int or not 0 <= a <= 3 for a in antwoorden.values()):
        raise ValueError("Elk antwoord moet 0, 1, 2 of 3 zijn")
    if horizon_jaren < 1:
        raise ValueError("De horizon moet minimaal 1 jaar zijn")

    scores = {}
    for dimensie in DIMENSIES:
        punten = [antwoorden[v["code"]] for v in VRAGEN if v["dimensie"] == dimensie]
        scores[dimensie] = round(100 * sum(punten) / (3 * len(punten)))

    # Bij gelijke stand wint de eerstgenoemde als bepalende factor.
    kandidaten = (
        ("bereidheid", _niveau_bij_score(scores["bereidheid"])),
        ("capaciteit", _niveau_bij_score(scores["capaciteit"])),
        ("horizon", _niveau_bij_horizon(horizon_jaren)),
    )
    factor, niveau = min(kandidaten, key=lambda k: k[1])
    return Uitkomst(
        score_bereidheid=scores["bereidheid"],
        score_capaciteit=scores["capaciteit"],
        score_kennis=scores["kennis"],
        niveau=niveau,
        bepalende_factor=factor,
        lage_kennis=scores["kennis"] < LAGE_KENNIS_GRENS,
    )


def controleer_allocatie(
    regels: dict[str, tuple[int, int, int]], categorieen: tuple[str, ...]
) -> list[str]:
    """Geeft de fouten in een modelallocatie terug; een lege lijst betekent geldig."""
    fouten = []
    if set(regels) != set(categorieen):
        return [f"De allocatie moet precies deze categorieën bevatten: {', '.join(categorieen)}"]
    for categorie, (streef, minimum, maximum) in regels.items():
        if not 0 <= minimum <= streef <= maximum <= 100:
            fouten.append(f"{categorie}: vereist is 0 ≤ minimum ≤ streefgewicht ≤ maximum ≤ 100")
    totaal = sum(streef for streef, _, _ in regels.values())
    if totaal != 100:
        fouten.append(f"De streefgewichten tellen op tot {totaal}% in plaats van 100%")
    return fouten
