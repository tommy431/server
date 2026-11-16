"""Portefeuilleconstructie: startvoorstel en doorrekening van verdeling, kosten en beperkingen.

Gewichten zijn hele basispunten (10000 = 100%), zodat optellingen exact zijn.

De startselectie en de beperkingen zijn voorbeeldwaarden. Ze leggen een beleggingsvisie vast
en moeten door de adviseur worden beoordeeld voordat ze voor echt advies worden gebruikt.
"""

from dataclasses import asdict, dataclass, field

TOTAAL = 10_000
STAP = 10  # voorstellen worden afgerond op 0,1%
MIN_POSITIE_VOORSTEL = 200  # een voorstel bevat geen posities kleiner dan 2%

# Per categorie: (ISIN, aandeel binnen de categorie). Aandelen benaderen de wereldmarkt:
# ontwikkelde markten, opkomende markten en kleine bedrijven.
STARTSELECTIE: dict[str, tuple[tuple[str, float], ...]] = {
    "aandelen": (("IE00B4L5Y983", 0.78), ("IE00BKM4GZ66", 0.12), ("IE00BF4RFH31", 0.10)),
    "obligaties": (("IE00BDBRDM35", 0.50), ("IE00B3DKXQ41", 0.50)),
    "vastgoed": (("IE00B1FZS350", 1.0),),
    "grondstoffen": (("DE000A0H0728", 0.50), ("DE000A0S9GB0", 0.50)),
    "liquiditeiten": (("LU0290358497", 1.0),),
}
# Bij een sterke duurzaamheidsvoorkeur wordt het instrument vervangen door de duurzame variant.
DUURZAAM_ALTERNATIEF = {"IE00B4L5Y983": "IE00BYX2JD69"}

MAX_BREED_INSTRUMENT = 7_000
MAX_SECTORFONDS = 1_000
MAX_SECTORFONDSEN_SAMEN = 3_000
MAX_GRONDSTOF_INSTRUMENT = 1_000
MIN_INSTRUMENTEN = 4

BEPERKINGEN = {
    "max_breed_instrument": MAX_BREED_INSTRUMENT,
    "max_sectorfonds": MAX_SECTORFONDS,
    "max_sectorfondsen_samen": MAX_SECTORFONDSEN_SAMEN,
    "max_grondstof_instrument": MAX_GRONDSTOF_INSTRUMENT,
    "min_instrumenten": MIN_INSTRUMENTEN,
}

ZAKELIJKE_WAARDEN = ("aandelen", "vastgoed", "grondstoffen")


@dataclass(frozen=True)
class Fonds:
    isin: str
    naam: str
    categorie: str
    regio: str
    sector: str
    lopende_kosten: float  # procenten per jaar
    kosten_geverifieerd: bool
    actief: bool = True


@dataclass(frozen=True)
class Band:
    streef: int  # hele procenten
    minimum: int
    maximum: int


@dataclass(frozen=True)
class Uitsluiting:
    soort: str  # "instrument", "sector" of "regio"
    waarde: str
    reden: str = ""


@dataclass(frozen=True)
class Bevinding:
    # "fout": de portefeuille kan niet worden vastgelegd.
    # "afwijking": buiten het risicoprofiel of de beperkingen; vastleggen vereist een toelichting.
    # "aandachtspunt": ter informatie.
    ernst: str
    code: str
    melding: str


@dataclass(frozen=True)
class Doorrekening:
    totaal: int
    per_categorie: dict[str, int]
    per_regio: dict[str, int]
    per_sector: dict[str, int]
    zakelijke_waarden: int
    grootste_positie: int
    aantal_instrumenten: int
    kosten_pct: float  # gewogen lopende kosten in procenten per jaar
    kosten_per_positie: dict[str, float]  # bijdrage per ISIN in procentpunten
    bevindingen: list[Bevinding] = field(default_factory=list)

    @property
    def fouten(self) -> list[Bevinding]:
        return [b for b in self.bevindingen if b.ernst == "fout"]

    @property
    def afwijkingen(self) -> list[Bevinding]:
        return [b for b in self.bevindingen if b.ernst == "afwijking"]

    def als_dict(self) -> dict:
        return asdict(self)


def pct(bp: int) -> str:
    """Basispunten als leesbaar percentage: 6630 → '66,3%'."""
    return f"{bp / 100:.1f}".replace(".", ",").removesuffix(",0") + "%"


def is_uitgesloten(fonds: Fonds, uitsluitingen: list[Uitsluiting]) -> bool:
    return any(
        (u.soort == "instrument" and u.waarde == fonds.isin)
        or (u.soort == "sector" and u.waarde == fonds.sector)
        or (u.soort == "regio" and u.waarde == fonds.regio)
        for u in uitsluitingen
    )


def _verdeel(totaal: int, aandelen: list[float]) -> list[int]:
    """Verdeelt `totaal` basispunten naar rato, afgerond op STAP, met exact het juiste totaal."""
    som = sum(aandelen)
    ruw = [totaal * a / som for a in aandelen]
    delen = [int(r // STAP) * STAP for r in ruw]
    rest = totaal - sum(delen)
    volgorde = sorted(range(len(ruw)), key=lambda i: (delen[i] - ruw[i], i))
    for i in volgorde:
        if rest <= 0:
            break
        bij = min(STAP, rest)
        delen[i] += bij
        rest -= bij
    return delen


def maak_voorstel(
    banden: dict[str, Band],
    fondsen: dict[str, Fonds],
    uitsluitingen: list[Uitsluiting],
    duurzaam: bool = False,
) -> tuple[dict[str, int], list[Bevinding]]:
    """Stelt een startportefeuille voor op de streefgewichten van het risicoprofiel.

    Geeft de posities (ISIN → basispunten) en opmerkingen over wat niet volgens de
    startselectie kon. Een categorie zonder beschikbaar instrument blijft leeg; de
    doorrekening meldt dan dat het totaal geen 100% is.
    """
    posities: dict[str, int] = {}
    opmerkingen: list[Bevinding] = []

    def beschikbaar(isin: str) -> bool:
        f = fondsen.get(isin)
        return f is not None and f.actief and not is_uitgesloten(f, uitsluitingen)

    for categorie, band in banden.items():
        if band.streef == 0:
            continue
        keuze: list[tuple[str, float]] = []
        for isin, aandeel in STARTSELECTIE.get(categorie, ()):
            alternatief = DUURZAAM_ALTERNATIEF.get(isin)
            if duurzaam and alternatief and beschikbaar(alternatief):
                isin = alternatief
            if beschikbaar(isin):
                keuze.append((isin, aandeel))
        if len(keuze) < len(STARTSELECTIE.get(categorie, ())):
            opmerkingen.append(
                Bevinding(
                    "aandachtspunt",
                    "startselectie_aangepast",
                    f"{categorie.capitalize()}: niet alle instrumenten uit de startselectie zijn "
                    "beschikbaar; het gewicht is over de overige verdeeld",
                )
            )
        if not keuze:
            # Terugvallen op het goedkoopste breed gespreide instrument in de categorie.
            kandidaten = sorted(
                (
                    f
                    for f in fondsen.values()
                    if f.categorie == categorie
                    and f.sector in ("breed", "vastgoed")
                    and beschikbaar(f.isin)
                ),
                key=lambda f: (f.lopende_kosten, f.isin),
            )
            if not kandidaten:
                opmerkingen.append(
                    Bevinding(
                        "fout",
                        "geen_instrument",
                        f"{categorie.capitalize()}: geen instrument beschikbaar na de uitsluitingen",
                    )
                )
                continue
            keuze = [(kandidaten[0].isin, 1.0)]

        doel = band.streef * 100
        # Te kleine posities weglaten; het grootste aandeel blijft altijd staan.
        groot = [k for k in keuze if doel * k[1] / sum(a for _, a in keuze) >= MIN_POSITIE_VOORSTEL]
        keuze = groot or [max(keuze, key=lambda k: k[1])]
        for (isin, _), gewicht in zip(keuze, _verdeel(doel, [a for _, a in keuze]), strict=True):
            posities[isin] = posities.get(isin, 0) + gewicht
    return posities, opmerkingen


def reken_door(
    posities: dict[str, int],
    fondsen: dict[str, Fonds],
    banden: dict[str, Band],
    uitsluitingen: list[Uitsluiting],
    klant_duurzaamheid: str = "geen",
    klant_uitsluitingen: tuple[str, ...] = (),
) -> Doorrekening:
    """Berekent verdeling en kosten en toetst de portefeuille aan risicoprofiel en beperkingen."""
    bevindingen: list[Bevinding] = []
    geldig: dict[str, int] = {}
    for isin, gewicht in posities.items():
        fonds = fondsen.get(isin)
        if fonds is None:
            bevindingen.append(Bevinding("fout", "onbekend", f"Onbekend instrument {isin}"))
        elif type(gewicht) is not int or gewicht <= 0:
            bevindingen.append(
                Bevinding("fout", "gewicht", f"{fonds.naam}: het gewicht moet groter dan 0 zijn")
            )
        else:
            geldig[isin] = gewicht
            if not fonds.actief:
                bevindingen.append(
                    Bevinding("fout", "inactief", f"{fonds.naam} is niet meer beschikbaar")
                )
            if is_uitgesloten(fonds, uitsluitingen):
                bevindingen.append(
                    Bevinding("fout", "uitgesloten", f"{fonds.naam} valt onder een uitsluiting")
                )

    totaal = sum(geldig.values())
    if not geldig:
        bevindingen.append(Bevinding("fout", "leeg", "De portefeuille bevat geen posities"))
    elif totaal != TOTAAL:
        bevindingen.append(
            Bevinding(
                "fout", "totaal", f"De gewichten tellen op tot {pct(totaal)} in plaats van 100%"
            )
        )

    per_categorie = dict.fromkeys(banden, 0)
    per_regio: dict[str, int] = {}
    per_sector: dict[str, int] = {}
    kosten_per_positie: dict[str, float] = {}
    sectorfondsen = 0
    for isin, gewicht in geldig.items():
        f = fondsen[isin]
        per_categorie[f.categorie] = per_categorie.get(f.categorie, 0) + gewicht
        per_regio[f.regio] = per_regio.get(f.regio, 0) + gewicht
        per_sector[f.sector] = per_sector.get(f.sector, 0) + gewicht
        kosten_per_positie[isin] = round(gewicht / TOTAAL * f.lopende_kosten, 4)

        is_sectorfonds = f.categorie == "aandelen" and f.sector != "breed"
        if is_sectorfonds:
            sectorfondsen += gewicht
            grens, soort = MAX_SECTORFONDS, "een sectorfonds"
        elif f.categorie == "grondstoffen":
            grens, soort = MAX_GRONDSTOF_INSTRUMENT, "een grondstoffenbelegging"
        else:
            grens, soort = MAX_BREED_INSTRUMENT, "één instrument"
        if gewicht > grens:
            bevindingen.append(
                Bevinding(
                    "afwijking",
                    "concentratie",
                    f"{f.naam} weegt {pct(gewicht)}; het maximum voor {soort} is {pct(grens)}",
                )
            )

    if sectorfondsen > MAX_SECTORFONDSEN_SAMEN:
        bevindingen.append(
            Bevinding(
                "afwijking",
                "sectorfondsen",
                f"Sectorfondsen wegen samen {pct(sectorfondsen)}; "
                f"het maximum is {pct(MAX_SECTORFONDSEN_SAMEN)}",
            )
        )
    if 0 < len(geldig) < MIN_INSTRUMENTEN:
        bevindingen.append(
            Bevinding(
                "afwijking",
                "spreiding",
                f"De portefeuille bevat {len(geldig)} instrument(en); "
                f"het minimum is {MIN_INSTRUMENTEN}",
            )
        )

    # De banden toetsen heeft alleen zin als het totaal klopt.
    if geldig and totaal == TOTAAL:
        for categorie, band in banden.items():
            gewicht = per_categorie.get(categorie, 0)
            if not band.minimum * 100 <= gewicht <= band.maximum * 100:
                bevindingen.append(
                    Bevinding(
                        "afwijking",
                        "buiten_risicoprofiel",
                        f"{categorie.capitalize()} weegt {pct(gewicht)}; het risicoprofiel staat "
                        f"{band.minimum}% tot {band.maximum}% toe",
                    )
                )
        for categorie in sorted(set(per_categorie) - set(banden)):
            if per_categorie[categorie]:
                bevindingen.append(
                    Bevinding(
                        "afwijking",
                        "buiten_risicoprofiel",
                        f"{categorie.capitalize()} komt niet voor in het risicoprofiel",
                    )
                )

    ongeverifieerd = [fondsen[i].naam for i in geldig if not fondsen[i].kosten_geverifieerd]
    if ongeverifieerd:
        bevindingen.append(
            Bevinding(
                "aandachtspunt",
                "kosten_ongeverifieerd",
                f"Van {len(ongeverifieerd)} instrument(en) zijn de lopende kosten niet "
                "gecontroleerd tegen de fondsdocumentatie",
            )
        )
    # Regio en sector zijn labels van het instrument; er is geen inzicht in de onderliggende
    # beleggingen. Dat moet zichtbaar zijn waar de adviseur erop zou kunnen vertrouwen.
    if any(u.soort in ("regio", "sector") for u in uitsluitingen) and any(
        fondsen[i].categorie == "aandelen"
        and (fondsen[i].regio == "wereld" or fondsen[i].sector == "breed")
        for i in geldig
    ):
        bevindingen.append(
            Bevinding(
                "aandachtspunt",
                "uitsluiting_op_label",
                "Uitsluitingen op regio of sector werken op het label van het instrument; breed "
                "gespreide fondsen kunnen de uitgesloten regio of sector toch bevatten",
            )
        )
    if geldig and (klant_duurzaamheid != "geen" or klant_uitsluitingen):
        wensen = []
        if klant_duurzaamheid != "geen":
            wensen.append(f"voorkeur voor duurzaam beleggen ({klant_duurzaamheid})")
        if klant_uitsluitingen:
            wensen.append("uitsluiten van " + ", ".join(klant_uitsluitingen))
        bevindingen.append(
            Bevinding(
                "aandachtspunt",
                "duurzaamheid",
                f"De klant heeft duurzaamheidswensen: {'; '.join(wensen)}. Dit kan niet "
                "automatisch worden getoetst; controleer de fondsdocumentatie",
            )
        )

    return Doorrekening(
        totaal=totaal,
        per_categorie=per_categorie,
        per_regio=dict(sorted(per_regio.items(), key=lambda kv: -kv[1])),
        per_sector=dict(sorted(per_sector.items(), key=lambda kv: -kv[1])),
        zakelijke_waarden=sum(per_categorie.get(c, 0) for c in ZAKELIJKE_WAARDEN),
        grootste_positie=max(geldig.values(), default=0),
        aantal_instrumenten=len(geldig),
        kosten_pct=round(sum(kosten_per_positie.values()), 4),
        kosten_per_positie=kosten_per_positie,
        bevindingen=bevindingen,
    )
