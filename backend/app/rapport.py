"""Adviesrapport als PDF.

Het rapport wordt opgebouwd uit de momentopname van een vastgelegde portefeuilleversie, zodat het
altijd laat zien waarop het advies op dat moment was gebaseerd.

De vaste teksten (risico's, waarschuwingen) zijn een eerste opzet. Laat ze beoordelen door
compliance voordat het rapport aan klanten wordt verstrekt.
"""

import io
from datetime import date
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.fonts import addMapping  # noqa: F401
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

_MAP = Path(__file__).parent / "lettertypen"
pdfmetrics.registerFont(TTFont("DejaVu", _MAP / "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Vet", _MAP / "DejaVuSans-Bold.ttf"))
# Zodat <b> in tekst het vette lettertype gebruikt.
registerFontFamily(
    "DejaVu", normal="DejaVu", bold="DejaVu-Vet", italic="DejaVu", boldItalic="DejaVu-Vet"
)

TEKST = colors.HexColor("#1b2330")
ZACHT = colors.HexColor("#5b6676")
RAND = colors.HexColor("#d9dee6")
VLAK = colors.HexColor("#f5f6f8")
BLAUW = colors.HexColor("#2a78d6")
ORANJE = colors.HexColor("#eb6834")
WAAIER = colors.HexColor("#b7d3f6")
ROOD = colors.HexColor("#a4262c")
OKER = colors.HexColor("#8a5300")

BREEDTE = A4[0] - 40 * mm


def _stijl(naam: str, vet: bool = False, grootte: float = 10, regel: float = 14.5, **extra):
    return ParagraphStyle(
        naam,
        fontName="DejaVu-Vet" if vet else "DejaVu",
        fontSize=grootte,
        leading=regel,
        textColor=extra.pop("textColor", TEKST),
        **extra,
    )


_S = {
    "titel": _stijl("titel", True, 22, 27),
    "h1": _stijl("h1", True, 15, 19, spaceBefore=12, spaceAfter=6),
    "h2": _stijl("h2", True, 11.5, 15, spaceBefore=9, spaceAfter=4),
    "p": _stijl("p", spaceAfter=5),
    "opsom": _stijl("opsom", spaceAfter=3, leftIndent=12, bulletIndent=0),
    "klein": _stijl("klein", grootte=8.5, regel=11.5, textColor=ZACHT),
    "cel": _stijl("cel", grootte=9, regel=12),
    "cel_r": _stijl("cel_r", grootte=9, regel=12, alignment=TA_RIGHT),
    "kop": _stijl("kop", True, 8.5, 11, textColor=ZACHT),
    "kop_r": _stijl("kop_r", True, 8.5, 11, textColor=ZACHT, alignment=TA_RIGHT),
    "waarschuwing": _stijl("waarschuwing", True, spaceBefore=6),
    "samenvatting": _stijl("samenvatting", spaceAfter=6, leftIndent=12, bulletIndent=0),
}

NAMEN = {
    "zeer-defensief": "Zeer defensief",
    "defensief": "Defensief",
    "neutraal": "Neutraal",
    "offensief": "Offensief",
    "zeer-offensief": "Zeer offensief",
    "bereidheid": "risicobereidheid",
    "capaciteit": "risicocapaciteit",
    "horizon": "beleggingshorizon",
    "aandelen": "Aandelen",
    "obligaties": "Obligaties",
    "vastgoed": "Vastgoed",
    "grondstoffen": "Grondstoffen",
    "liquiditeiten": "Liquiditeiten",
    "geen": "geen voorkeur",
    "enigszins": "enige voorkeur",
    "sterk": "sterke voorkeur",
    "wereld": "Wereldwijd gespreid",
    "noord-amerika": "Noord-Amerika",
    "europa": "Europa",
    "opkomende-markten": "Opkomende markten",
    "azie-pacific": "Azië-Pacific",
    "breed": "Breed gespreid",
    "energie": "Energie",
    "materialen": "Materialen",
    "industrie": "Industrie",
    "duurzame-consumptiegoederen": "Duurzame consumptiegoederen",
    "dagelijkse-consumptiegoederen": "Dagelijkse consumptiegoederen",
    "gezondheidszorg": "Gezondheidszorg",
    "financiele-dienstverlening": "Financiële dienstverlening",
    "informatietechnologie": "Informatietechnologie",
    "communicatiediensten": "Communicatiediensten",
    "nutsbedrijven": "Nutsbedrijven",
    "fossiele-brandstoffen": "fossiele brandstoffen",
    "kernenergie": "kernenergie",
}
CATEGORIEEN = ("aandelen", "obligaties", "vastgoed", "grondstoffen", "liquiditeiten")
MAANDEN = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
MAANDEN_LANG = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)


def naam(code: str) -> str:
    return NAMEN.get(code, code)


def _getal(x: float, decimalen: int = 0) -> str:
    tekst = f"{abs(x):,.{decimalen}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("−" if x < 0 and round(abs(x), decimalen) > 0 else "") + tekst


def eur(x: float) -> str:
    """Bedrag in hele euro's; negatief als −€ 1.234."""
    if round(x) < 0:
        return f"−€\u00a0{_getal(-x)}"
    return f"€\u00a0{_getal(x)}"


def bp(x: int) -> str:
    """Basispunten als percentage: 6630 → 66,3%."""
    return _getal(x / 100, 1).removesuffix(",0") + "%"


def pct(x: float, decimalen: int = 1, teken: bool = False) -> str:
    """Fractie als percentage: 0.0453 → 4,5%."""
    tekst = _getal(x * 100, decimalen) + "%"
    return ("+" + tekst) if teken and round(x * 100, decimalen) > 0 else tekst


def datum_lang(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.day} {MAANDEN_LANG[d.month - 1]} {d.year}"


def _esc(tekst: str) -> str:
    return tekst.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(tekst: str, stijl: str = "p") -> Paragraph:
    return Paragraph(tekst, _S[stijl])


def _tabel(
    kop: list[str],
    rijen: list[list[str]],
    breedtes: list[float],
    rechts: set[int] = frozenset(),
    nadruk: set[int] = frozenset(),
) -> Table:
    """Tabel met kopregel; kolommen in `rechts` worden rechts uitgelijnd (getallen)."""

    def cel(tekst: str, i: int, is_kop: bool) -> Paragraph:
        stijl = ("kop" if is_kop else "cel") + ("_r" if i in rechts else "")
        return Paragraph(tekst, _S[stijl])

    data = [[cel(t, i, True) for i, t in enumerate(kop)]]
    data += [[cel(t, i, False) for i, t in enumerate(rij)] for rij in rijen]
    t = Table(data, colWidths=[b * BREEDTE for b in breedtes], repeatRows=1, hAlign="LEFT")
    stijl = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RAND),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RAND),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in nadruk:
        stijl.append(("BACKGROUND", (0, r + 1), (-1, r + 1), VLAK))
    t.setStyle(TableStyle(stijl))
    return t


def _gegevens(paren: list[tuple[str, str]]) -> Table:
    data = [[Paragraph(k, _S["kop"]), Paragraph(v, _S["cel"])] for k, v in paren]
    t = Table(data, colWidths=[0.30 * BREEDTE, 0.70 * BREEDTE], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return t


def _kader(tekst: str, kleur=OKER, achtergrond="#fff4e0") -> Table:
    t = Table(
        [[Paragraph(tekst, ParagraphStyle("k", parent=_S["cel"], textColor=kleur))]],
        colWidths=[BREEDTE],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(achtergrond)),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


# --- grafieken -------------------------------------------------------------------------


def _stap(bereik: float) -> float:
    ruw = bereik / 5
    macht = 10 ** int(f"{ruw:e}".split("e")[1])
    return next((f * macht for f in (1, 2, 2.5, 5, 10) if f * macht >= ruw), ruw)


class _Grafiek(Flowable):
    def __init__(self, tekening: Drawing) -> None:
        super().__init__()
        self.tekening = tekening
        self.width, self.height = tekening.width, tekening.height

    def draw(self) -> None:
        self.tekening.drawOn(self.canv, 0, 0)


def _as_tekst(x: float, y: float, tekst: str, anker: str = "end") -> String:
    return String(x, y, tekst, fontName="DejaVu", fontSize=6.5, fillColor=ZACHT, textAnchor=anker)


def waardegrafiek(punten: list) -> Flowable | None:
    """Waardeontwikkeling van portefeuille (blauw) en benchmark (oranje), beginwaarde 100."""
    if len(punten) < 2:
        return None
    b, h = BREEDTE, 52 * mm
    links, rechts, onder, boven = 26, 28, 14, 6
    tijden = [date.fromisoformat(p[0]).toordinal() for p in punten]
    met_bm = all(p[2] is not None for p in punten)
    waarden = [p[1] for p in punten] + ([p[2] for p in punten] if met_bm else [])
    s = _stap(max(waarden) - min(waarden) or 1)
    y0 = (min(waarden) // s) * s
    y1 = -(-max(waarden) // s) * s

    def x(t: int) -> float:
        return links + (t - tijden[0]) / (tijden[-1] - tijden[0]) * (b - links - rechts)

    def y(w: float) -> float:
        return onder + (w - y0) / (y1 - y0) * (h - onder - boven)

    d = Drawing(b, h)
    w = y0
    while w <= y1 + 1e-9:
        d.add(Line(links, y(w), b - rechts, y(w), strokeColor=RAND, strokeWidth=0.4))
        d.add(_as_tekst(links - 4, y(w) - 2, _getal(w)))
        w += s
    eerste_jaar = date.fromordinal(tijden[0]).year + 1
    laatste_jaar = date.fromordinal(tijden[-1]).year
    jaarstap = max(1, -(-(laatste_jaar - eerste_jaar + 1) // 9))
    for jaar in range(eerste_jaar, laatste_jaar + 1, jaarstap):
        d.add(_as_tekst(x(date(jaar, 1, 1).toordinal()), 3, str(jaar), "middle"))
    for kolom, kleur in ((2, ORANJE), (1, BLAUW)) if met_bm else ((1, BLAUW),):
        lijn = []
        for t, p in zip(tijden, punten, strict=True):
            lijn += [x(t), y(p[kolom])]
        d.add(PolyLine(lijn, strokeColor=kleur, strokeWidth=1.3, strokeLineJoin=1))
        d.add(
            String(
                b - rechts + 4,
                y(punten[-1][kolom])
                - 2
                + (4 if kolom == 1 and met_bm and punten[-1][1] > punten[-1][2] else 0)
                - (4 if kolom == 1 and met_bm and punten[-1][1] <= punten[-1][2] else 0),
                _getal(punten[-1][kolom]),
                fontName="DejaVu-Vet",
                fontSize=6.5,
                fillColor=TEKST,
            )
        )
    return _Grafiek(d)


def waaiergrafiek(jaren: list[dict], doel: float | None, reeel: bool) -> Flowable:
    """Scenario's: vlak van slecht tot goed, verwacht scenario (blauw) en de inleg (grijs)."""
    b, h = BREEDTE, 55 * mm
    links, rechts, onder, boven = 34, 8, 14, 6
    kolom = "reeel" if reeel else "nominaal"
    inleg = "ingelegd_reeel" if reeel and "ingelegd_reeel" in jaren[0] else "ingelegd"
    n = len(jaren) - 1
    hoogste = max(max(j[kolom][2] for j in jaren), doel or 0)
    s = _stap(hoogste or 1)
    y1 = -(-hoogste // s) * s

    def x(jaar: int) -> float:
        return links + jaar / n * (b - links - rechts)

    def y(w: float) -> float:
        return onder + w / y1 * (h - onder - boven)

    d = Drawing(b, h)
    w = 0.0
    while w <= y1 + 1e-6:
        d.add(Line(links, y(w), b - rechts, y(w), strokeColor=RAND, strokeWidth=0.4))
        label = (
            "€ 0"
            if w == 0
            else (f"€ {_getal(w / 1000)}k" if w < 1_000_000 else f"€ {_getal(w / 1e6, 1)} mln")
        )
        d.add(_as_tekst(links - 4, y(w) - 2, label))
        w += s
    jaarstap = max(1, -(-n // 8))
    for j in range(0, n + 1, jaarstap):
        d.add(_as_tekst(x(j), 3, "nu" if j == 0 else f"{j} jr", "middle"))
    vlak = [c for j in jaren for c in (x(j["jaar"]), y(j[kolom][2]))]
    vlak += [c for j in reversed(jaren) for c in (x(j["jaar"]), y(j[kolom][0]))]
    d.add(Polygon(vlak, fillColor=WAAIER, strokeColor=None))
    d.add(
        PolyLine(
            [c for j in jaren for c in (x(j["jaar"]), y(j[inleg]))],
            strokeColor=ZACHT,
            strokeWidth=1,
        )
    )
    if doel:
        d.add(Line(links, y(doel), b - rechts, y(doel), strokeColor=TEKST, strokeWidth=0.8))
        d.add(
            String(
                links + 4,
                y(doel) + 3,
                f"Doel {eur(doel)}",
                fontName="DejaVu-Vet",
                fontSize=6.5,
                fillColor=TEKST,
            )
        )
    d.add(
        PolyLine(
            [c for j in jaren for c in (x(j["jaar"]), y(j[kolom][1]))],
            strokeColor=BLAUW,
            strokeWidth=1.4,
        )
    )
    return _Grafiek(d)


def _legenda(items: list[tuple[str, object, str]]) -> Paragraph:
    """items: (tekst, kleur, soort 'lijn' of 'vlak')."""
    delen = []
    for tekst, kleur, soort in items:
        teken = "━━" if soort == "lijn" else "███"
        delen.append(f'<font color="{kleur.hexval().replace("0x", "#")}">{teken}</font> {tekst}')
    return Paragraph("&nbsp;&nbsp;&nbsp;".join(delen), _S["klein"])


# --- teksten ---------------------------------------------------------------------------

PROFIELUITLEG = {
    "zeer-defensief": "Zeer defensief: vooral obligaties en spaarachtige beleggingen, weinig aandelen. "
    "De waarde schommelt weinig, het verwachte rendement is laag.",
    "defensief": "Defensief: meer obligaties dan aandelen. Beperkte schommelingen, een bescheiden "
    "verwacht rendement.",
    "neutraal": "Neutraal: ongeveer evenveel aandelen als obligaties en andere beleggingen. Een "
    "evenwicht tussen schommelingen en verwacht rendement.",
    "offensief": "Offensief: vooral aandelen. Flinke schommelingen, een hoger verwacht rendement.",
    "zeer-offensief": "Zeer offensief: bijna alleen aandelen. Grote schommelingen, het hoogste "
    "verwachte rendement.",
}

CATEGORIE_UITLEG = {
    "aandelen": "Aandelen: een stukje eigendom van bedrijven. Op lange termijn het hoogste verwachte "
    "rendement, maar de waarde schommelt het sterkst.",
    "obligaties": "Obligaties: leningen aan overheden en bedrijven, die rente opleveren. Meestal "
    "minder schommelingen dan aandelen.",
    "vastgoed": "Vastgoed: aandelen in vastgoedbedrijven, zoals kantoren, winkels en woningen.",
    "grondstoffen": "Grondstoffen: bijvoorbeeld olie, metalen en landbouwproducten, of goud. Bewegen "
    "vaak anders dan aandelen en obligaties.",
    "liquiditeiten": "Liquiditeiten: een spaarachtige belegging in euro's met een rente die de "
    "geldmarkt volgt.",
}

BEGRIPPEN = (
    (
        "Aandelen, obligaties, vastgoed, grondstoffen, liquiditeiten",
        "De beleggingscategorieën; zie hoofdstuk 2.",
    ),
    (
        "Indexfonds (ETF)",
        (
            "Een beursgenoteerd fonds dat een hele markt volgt, bijvoorbeeld alle grote "
            "bedrijven wereldwijd. Goedkoop en breed gespreid."
        ),
    ),
    (
        "Lopende kosten",
        "Kosten die het fonds jaarlijks inhoudt. U betaalt ze niet apart; ze zitten in de koers.",
    ),
    ("Rendement per jaar", "Gemiddelde waardegroei per jaar, inclusief dividend en rente."),
    ("Grootste daling", "Het grootste verlies van een hoogste punt naar het laagste punt daarna."),
    (
        "Herbalanceren",
        (
            "De portefeuille terugbrengen naar de afgesproken verdeling, door wat gestegen is "
            "deels te verkopen en wat gedaald is bij te kopen."
        ),
    ),
    (
        "Koopkracht van vandaag",
        "Een bedrag in de toekomst omgerekend naar wat u er nu voor kunt kopen.",
    ),
    ("Risicoprofiel", "De mate van risico die bij u past, van zeer defensief tot zeer offensief."),
    ("Scenario", "Een mogelijke uitkomst, berekend met een rekenmodel. Geen voorspelling."),
    (
        "Standaardmix",
        (
            "De verdeling die hoort bij uw risicoprofiel, ingevuld met één breed fonds per "
            "categorie. Dient ter vergelijking."
        ),
    ),
    (
        "Swap",
        (
            "Een contract waarmee een fonds een rendement afspreekt met een bank in plaats van zelf te "
            "beleggen. Brengt een klein risico mee dat die bank haar afspraak niet nakomt."
        ),
    ),
    (
        "Valutarisico",
        "Het risico dat een andere munt, zoals de dollar, minder waard wordt ten opzichte van de euro.",
    ),
    ("Volatiliteit", "Een maat voor hoe sterk de waarde schommelt. Hoe hoger, hoe onrustiger."),
)


def _score_tekst(soort: str, score: int) -> str:
    laag, hoog = score < 34, score >= 67
    teksten = {
        "bereidheid": (
            "U wilt liever weinig schommelingen, ook als dat rendement kost.",
            "U accepteert schommelingen als daar een redelijk rendement tegenover staat.",
            "U accepteert flinke schommelingen voor een hoger verwacht rendement.",
        ),
        "capaciteit": (
            "Uw financiële situatie laat weinig ruimte om verliezen op te vangen.",
            "Uw financiële situatie laat ruimte om tijdelijke verliezen op te vangen.",
            "Uw financiële situatie laat ruimte om ook flinke tijdelijke verliezen op te vangen.",
        ),
        "kennis": (
            "U heeft beperkte kennis van en ervaring met beleggen.",
            "U heeft redelijke kennis van en ervaring met beleggen.",
            "U heeft goede kennis van en ervaring met beleggen.",
        ),
    }[soort]
    return teksten[0] if laag else teksten[2] if hoog else teksten[1]


def _oordeel(kans: float) -> str:
    if kans >= 0.85:
        return "zeer waarschijnlijk haalbaar"
    if kans >= 0.65:
        return "goed haalbaar"
    if kans >= 0.35:
        return "onzeker: ongeveer even grote kans op wel als niet halen"
    return "waarschijnlijk niet haalbaar met de huidige inleg en storting"


def _fondsomschrijving(p: dict) -> str:
    regio = {
        "wereld": "wereldwijd",
        "noord-amerika": "in Noord-Amerika",
        "europa": "in Europa",
        "opkomende-markten": "in opkomende landen",
        "azie-pacific": "in Azië en de Pacific",
    }.get(p["regio"], "")
    basis = {
        "aandelen": f"Aandelen van bedrijven {regio}",
        "obligaties": f"Obligaties {regio}",
        "vastgoed": f"Vastgoedbedrijven {regio}",
        "grondstoffen": "Goud" if "Gold" in p["naam"] else "Een mix van grondstoffen",
        "liquiditeiten": "Spaarachtig, rente van de geldmarkt in euro",
    }[p["categorie"]]
    extra = []
    if p["sector"] not in ("breed", "vastgoed"):
        extra.append(f"sector {naam(p['sector']).lower()}")
    if "Small Cap" in p["naam"]:
        extra.append("kleinere bedrijven")
    if "Govt" in p["naam"] or "Government" in p["naam"] or "Treasury" in p["naam"]:
        extra.append("van overheden")
    if "Corp" in p["naam"]:
        extra.append("van bedrijven")
    if "High Yield" in p["naam"]:
        extra.append("met hogere rente en hoger risico")
    if "Inflation" in p["naam"]:
        extra.append("met inflatiebescherming")
    if "Hedged" in p["naam"]:
        extra.append("valutarisico afgedekt")
    if "ESG" in p["naam"] or "SRI" in p["naam"]:
        extra.append("met duurzaamheidscriteria")
    if "Swap" in p["naam"]:
        extra.append("werkt met swaps")
    return basis + (f" ({', '.join(extra)})" if extra else "")


def _opsom(tekst: str, stijl: str = "opsom") -> Paragraph:
    return Paragraph(tekst, _S[stijl], bulletText="•")


def _watermerk(canvas) -> None:
    canvas.saveState()
    canvas.setFont("DejaVu-Vet", 80)
    canvas.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.10))
    canvas.translate(A4[0] / 2, A4[1] / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, "CONCEPT")
    canvas.restoreState()


def _kop_en_voet(canvas, doc, titel: str, concept: bool) -> None:
    if concept:
        _watermerk(canvas)
    canvas.saveState()
    canvas.setFont("DejaVu", 7.5)
    canvas.setFillColor(ZACHT)
    canvas.drawString(
        20 * mm, 12 * mm, titel + (" · CONCEPT, niet voor de klant" if concept else "")
    )
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Pagina {doc.page}")
    canvas.setStrokeColor(RAND)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
    canvas.restoreState()


def _samenvattingskader(regels: list[Paragraph]) -> Table:
    t = Table([[regels]], colWidths=[BREEDTE], hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4fc")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return t


# --- rapport ---------------------------------------------------------------------------


def maak_rapport(g: dict) -> bytes:
    """Bouwt het adviesrapport. `g` bevat de gegevens zoals `rapportgegevens` ze samenstelt."""
    klant, profiel, pf = g["klant"], g["profiel"], g["portefeuille"]
    d = pf["doorrekening"]
    analyse = (pf.get("analyse") or {}).get("analyse")
    benchmark_fondsen = (pf.get("analyse") or {}).get("benchmark") or []
    su = pf.get("scenario") or {}
    sc = su.get("scenario")
    varianten = su.get("varianten") or {}
    concept = bool(g.get("concept"))
    reeel = bool(profiel.get("doel_in_koopkracht"))
    kolom = "reeel" if reeel else "nominaal"
    maatstaf = "in koopkracht van vandaag" if reeel else "in euro's van dat moment"
    prof = naam(pf["risicoprofiel"])
    posities = sorted(
        g["posities"], key=lambda p: (CATEGORIEEN.index(p["categorie"]), -p["gewicht"])
    )
    overig = su.get("overige_kosten_pct") or 0
    kosten_totaal = d["kosten_pct"] + overig
    stortingen_jaar1 = profiel["storting_per_maand_eur"] * 6  # gemiddeld half jaar belegd
    kosten_jaar1 = (profiel["inleg_eur"] + stortingen_jaar1) * kosten_totaal / 100
    aandelen = d["per_categorie"].get("aandelen", 0)
    eind = sc["jaren"][-1] if sc else None
    kans_doel = None
    if sc and sc.get("doelvermogen"):
        kans_doel = sc["kans_doel_reeel"] if reeel else sc["kans_doel_nominaal"]
    slecht_jaar = su.get("slecht_jaar")
    inhoud: list = []

    # Voorblad en samenvatting -------------------------------------------------------------
    inhoud += [
        _p("Uw beleggingsadvies", "titel"),
        Spacer(1, 2 * mm),
        _p(
            f"{_esc(klant['naam'])} · {datum_lang(pf['vastgelegd_op'])} · adviseur {_esc(g['adviseur'])}",
            "klein",
        ),
        Spacer(1, 5 * mm),
    ]
    kort = [_p("<b>In het kort</b>", "h2")]
    kort.append(
        _opsom(
            f"<b>Ons advies:</b> beleggen met risicoprofiel <b>{prof.lower()}</b>: ongeveer "
            f"{bp(aandelen)} in aandelen en de rest vooral in "
            + (
                "obligaties"
                if d["per_categorie"].get("obligaties", 0) >= 1000
                else "andere beleggingen"
            )
            + f", verdeeld over {d['aantal_instrumenten']} breed gespreide fondsen.",
            "samenvatting",
        )
    )
    if kans_doel is not None:
        kort.append(
            _opsom(
                f"<b>Uw doel:</b> {eur(sc['doelvermogen'])} over {profiel['horizon_jaren']} jaar, {maatstaf}. "
                f"De kans daarop is {round(kans_doel * 100)}%: {_oordeel(kans_doel)}."
                + (" Zie hoofdstuk 5 voor wat helpt." if kans_doel < 0.65 else ""),
                "samenvatting",
            )
        )
    if eind:
        w = eind[kolom]
        kort.append(
            _opsom(
                f"<b>Wat u kunt verwachten</b> na {profiel['horizon_jaren']} jaar, {maatstaf}: "
                f"ergens tussen {eur(w[0])} en {eur(w[2])}, met {eur(w[1])} als middelste uitkomst. "
                f"U legt in totaal {eur(eind['ingelegd_reeel'] if reeel and 'ingelegd_reeel' in eind else eind['ingelegd'])} in.",
                "samenvatting",
            )
        )
    if slecht_jaar is not None:
        kort.append(
            _opsom(
                f"<b>In een slecht jaar</b> (1 op de 20 jaren) kan uw vermogen meer dan "
                f"{pct(-slecht_jaar, 0)} dalen; op uw inleg is dat ongeveer "
                f"{eur(-slecht_jaar * profiel['inleg_eur'])}. Bij een zware crisis kan het meer zijn.",
                "samenvatting",
            )
        )
    kort.append(
        _opsom(
            f"<b>Kosten:</b> {pct(kosten_totaal / 100, 2)} per jaar, in het eerste jaar ongeveer "
            f"{eur(kosten_jaar1)}.",
            "samenvatting",
        )
    )
    inhoud += [_samenvattingskader(kort), Spacer(1, 5 * mm)]
    inhoud += [
        _p("<b>Inhoud</b>"),
        _p(
            "1. Uw situatie en wensen · 2. Ons advies · 3. Waarom dit advies bij u past · 4. Kosten · "
            "5. Uw doel: wat kunt u verwachten? · 6. Wat kan er misgaan? · 7. Resultaten uit het verleden · "
            "8. Volgende stappen · Bijlage A: begrippen · Bijlage B: technische toelichting",
            "klein",
        ),
    ]

    # 1. Situatie en wensen ----------------------------------------------------------------
    doelregel = (
        f"{eur(profiel['doelvermogen_eur'])} {maatstaf}"
        if profiel.get("doelvermogen_eur")
        else "Geen bedrag opgegeven"
    )
    duurzaam = naam(profiel["duurzaamheid"]).capitalize()
    if profiel.get("uitsluitingen"):
        duurzaam += "; u wilt niet beleggen in " + ", ".join(
            naam(u) for u in profiel["uitsluitingen"]
        )
    inhoud += [
        _p("1. Uw situatie en wensen", "h1"),
        _gegevens(
            [
                ("Uw doel", _esc(profiel["doel"])),
                ("Looptijd", f"{profiel['horizon_jaren']} jaar"),
                ("Inleg", eur(profiel["inleg_eur"])),
                ("Storting per maand", eur(profiel["storting_per_maand_eur"])),
                ("Gewenst vermogen", doelregel),
                ("Duurzaamheid", _esc(duurzaam)),
            ]
        ),
        _p("Wat wij uit het gesprek en de vragenlijst opmaken", "h2"),
        _opsom(_score_tekst("bereidheid", profiel["score_bereidheid"])),
        _opsom(_score_tekst("capaciteit", profiel["score_capaciteit"])),
        _opsom(_score_tekst("kennis", profiel["score_kennis"])),
        _p("Uw risicoprofiel", "h2"),
    ]
    afgeleid = naam(profiel["afgeleid_risicoprofiel"])
    if profiel["risicoprofiel"] == profiel["afgeleid_risicoprofiel"]:
        inhoud.append(
            _p(
                f"Daarbij past het risicoprofiel <b>{prof.lower()}</b>. Het voorzichtigste van uw "
                f"risicobereidheid, uw financiële ruimte en uw looptijd bepaalt het profiel; bij u is dat "
                f"uw {naam(profiel['bepalende_factor'])}."
            )
        )
    else:
        inhoud.append(
            _p(
                f"Uit de vragenlijst volgt het profiel {afgeleid.lower()}. In overleg is gekozen voor het "
                f"voorzichtigere profiel <b>{prof.lower()}</b>. Reden: {_esc(profiel.get('afwijking_toelichting') or '')}"
            )
        )
        alt = next((v for v in varianten.get("profielen", []) if v.get("afgeleid")), None)
        if alt and sc:
            midden_nu = eind[kolom][1]
            inhoud.append(
                _p(
                    f"Wat betekent die keuze? Met {afgeleid.lower()} zou de middelste uitkomst ongeveer "
                    f"{eur(alt['midden'])} zijn in plaats van {eur(midden_nu)}"
                    + (
                        f", en de kans op uw doel {round(alt['kans_doel'] * 100)}% in plaats van {round(kans_doel * 100)}%"
                        if kans_doel is not None and alt.get("kans_doel") is not None
                        else ""
                    )
                    + f". In een slecht jaar zou u dan wel meer dan {pct(-alt['slecht_jaar'], 0)} kunnen verliezen, "
                    f"tegen {pct(-slecht_jaar, 0)} nu."
                )
            )
    inhoud.append(_p(PROFIELUITLEG.get(pf["risicoprofiel"], ""), "klein"))
    if profiel["score_kennis"] < 34:
        inhoud.append(
            _kader(
                "Omdat u nog weinig ervaring heeft met beleggen, raden we u aan hoofdstuk 6 (wat kan er misgaan) "
                "extra aandachtig te lezen. Stel gerust vragen als iets niet duidelijk is."
            )
        )

    # 2. Ons advies -------------------------------------------------------------------------
    rijen = [
        [
            f"{_esc(p['naam'])}<br/><font color='#5b6676'>{_esc(_fondsomschrijving(p))}</font>",
            naam(p["categorie"]),
            bp(p["gewicht"]),
        ]
        for p in posities
    ]
    rijen.append(["<b>Totaal</b>", "", f"<b>{bp(d['totaal'])}</b>"])
    inhoud += [
        CondPageBreak(90 * mm),
        _p("2. Ons advies", "h1"),
        _p(
            f"Wij adviseren u te beleggen in de onderstaande {d['aantal_instrumenten']} indexfondsen. Elk fonds "
            "volgt een brede markt en belegt in honderden tot duizenden bedrijven of leningen tegelijk."
        ),
        _tabel(
            ["Fonds en waarin het belegt", "Soort", "Deel van uw vermogen"],
            rijen,
            [0.62, 0.18, 0.20],
            {2},
        ),
        _p("Zo is uw vermogen verdeeld", "h2"),
        _tabel(
            ["Soort belegging", "Uw portefeuille", "Toegestaan bij uw profiel"],
            [
                [
                    naam(c),
                    bp(d["per_categorie"].get(c, 0)),
                    f"{pf['banden'][c]['minimum']}% tot {pf['banden'][c]['maximum']}%",
                ]
                for c in CATEGORIEEN
                if c in pf["banden"]
                and (d["per_categorie"].get(c, 0) or pf["banden"][c]["maximum"])
            ],
            [0.40, 0.25, 0.35],
            {1, 2},
        ),
        Spacer(1, 2 * mm),
    ]
    inhoud += [
        _opsom(CATEGORIE_UITLEG[c], "klein") for c in CATEGORIEEN if d["per_categorie"].get(c, 0)
    ]
    if pf.get("uitsluitingen"):
        inhoud.append(
            _p(
                "Op uw verzoek beleggen we niet in: "
                + "; ".join(
                    _esc(
                        g["fondsnamen"].get(u["waarde"], u["waarde"])
                        if u["soort"] == "instrument"
                        else naam(u["waarde"]).lower()
                    )
                    for u in pf["uitsluitingen"]
                )
                + ". Breed gespreide fondsen kunnen daar via een klein deel toch in beleggen.",
            )
        )

    # 3. Waarom past dit ----------------------------------------------------------------------
    afwijkingen = [b for b in d["bevindingen"] if b["ernst"] == "afwijking"]
    inhoud += [CondPageBreak(60 * mm), _p("3. Waarom dit advies bij u past", "h1")]
    if afwijkingen:
        inhoud.append(
            _opsom(
                f"<b>Risicoprofiel:</b> de verdeling wijkt op deze punten af van wat bij {prof.lower()} hoort: "
                + "; ".join(_esc(b["melding"]) for b in afwijkingen)
                + (f". Waarom: {_esc(pf['toelichting'])}" if pf.get("toelichting") else ".")
            )
        )
    else:
        inhoud.append(
            _opsom(
                f"<b>Risicoprofiel:</b> elke soort belegging blijft binnen de grenzen van het profiel {prof.lower()}, "
                "en het vermogen is over meerdere fondsen gespreid."
            )
        )
        if pf.get("toelichting"):
            inhoud.append(_opsom(f"<b>Toelichting van uw adviseur:</b> {_esc(pf['toelichting'])}"))
    if kans_doel is not None:
        inhoud.append(
            _opsom(
                f"<b>Uw doel:</b> de kans op {eur(sc['doelvermogen'])} is {round(kans_doel * 100)}%, "
                f"{_oordeel(kans_doel)}."
                + (
                    " Dit advies past bij uw risicoprofiel, maar haalt uw doel waarschijnlijk niet; in hoofdstuk 5 staat wat helpt."
                    if kans_doel < 0.35
                    else ""
                )
            )
        )
    else:
        inhoud.append(
            _opsom(
                f"<b>Uw looptijd:</b> {profiel['horizon_jaren']} jaar; een eventuele daling heeft tijd om te herstellen."
                if profiel["horizon_jaren"] >= 10
                else f"<b>Uw looptijd:</b> {profiel['horizon_jaren']} jaar; daarom is het risico beperkt gehouden."
            )
        )
    if slecht_jaar is not None:
        inhoud.append(
            _opsom(
                f"<b>Verliezen opvangen:</b> in een slecht jaar kan uw vermogen ongeveer "
                f"{eur(-slecht_jaar * profiel['inleg_eur'])} dalen. {_score_tekst('capaciteit', profiel['score_capaciteit'])}"
            )
        )
    if profiel["duurzaamheid"] != "geen" or profiel.get("uitsluitingen"):
        inhoud.append(
            _opsom(
                "<b>Duurzaamheid:</b> uw wensen zijn meegenomen bij de keuze van de fondsen"
                + (" en de uitsluitingen" if pf.get("uitsluitingen") else "")
                + ". Bij brede indexfondsen is niet volledig uit te sluiten dat een klein deel in ongewenste bedrijven belegt."
            )
        )
    inhoud += [
        _p("De nadelen van dit advies", "h2"),
        _opsom("De waarde van uw beleggingen schommelt en kan lager uitkomen dan uw inleg."),
        _opsom("Er is geen garantie op rendement of op het halen van uw doel."),
        _opsom("Kosten verlagen uw rendement elk jaar, ook als de beurs daalt."),
    ]

    # 4. Kosten -----------------------------------------------------------------------------
    kostenrijen = [
        [
            "Lopende kosten van de fondsen",
            pct(d["kosten_pct"] / 100, 2),
            eur((profiel["inleg_eur"] + stortingen_jaar1) * d["kosten_pct"] / 100),
        ],
    ]
    if overig:
        kostenrijen.append(
            [
                "Kosten advies, beheer en bewaring",
                pct(overig / 100, 2),
                eur((profiel["inleg_eur"] + stortingen_jaar1) * overig / 100),
            ]
        )
    kostenrijen.append(
        ["<b>Totaal</b>", f"<b>{pct(kosten_totaal / 100, 2)}</b>", f"<b>{eur(kosten_jaar1)}</b>"]
    )
    inhoud += [
        CondPageBreak(60 * mm),
        _p("4. Kosten", "h1"),
        _tabel(
            ["Soort kosten", "Per jaar", "In het eerste jaar"],
            kostenrijen,
            [0.50, 0.22, 0.28],
            {1, 2},
        ),
    ]
    if sc:
        inhoud.append(
            _p(
                f"Over de hele looptijd van {profiel['horizon_jaren']} jaar verlagen de kosten uw verwachte "
                f"eindvermogen met ongeveer {eur(sc['kosten_effect_mediaan'])} (nominaal). Kosten tellen elk jaar "
                "op, en ook over het rendement dat u door die kosten misloopt."
            )
        )
    inhoud.append(
        _p(
            "De kosten in het eerste jaar zijn berekend over uw inleg plus de helft van de stortingen in dat jaar. "
            "De lopende kosten van de fondsen zitten in de koers; u betaalt ze niet apart. Kosten bij aan- en "
            "verkoop zijn hier niet meegerekend. U ontvangt van elk fonds het essentiële-informatiedocument.",
            "klein",
        )
    )

    # 5. Uw doel ----------------------------------------------------------------------------
    inhoud += [CondPageBreak(120 * mm), _p("5. Uw doel: wat kunt u verwachten?", "h1")]
    if not sc:
        inhoud.append(_p("Voor dit advies zijn geen toekomstscenario's berekend."))
    else:
        ingelegd = (
            eind["ingelegd_reeel"] if reeel and "ingelegd_reeel" in eind else eind["ingelegd"]
        )
        gerekend = [f"kosten van {pct(sc['kosten_pct'] / 100, 2)} per jaar"]
        if sc.get("belasting_pct"):
            gerekend.append(
                f"een vermogensheffing van ongeveer {pct(sc['belasting_pct'] / 100, 2)} per jaar"
            )
        if reeel:
            gerekend.append(f"inflatie van {pct(su['aannames']['inflatie'])} per jaar")
        inhoud += [
            _p(
                f"Niemand weet hoe de beurs zich ontwikkelt. Daarom hebben we {_getal(sc['paden'])} mogelijke "
                f"verlopen doorgerekend. Alle bedragen in dit hoofdstuk zijn <b>{maatstaf}</b>"
                + (", zodat u ze kunt vergelijken met wat u er nu voor kunt kopen" if reeel else "")
                + ". Gerekend met "
                + ", ".join(gerekend[:-1])
                + (" en " if len(gerekend) > 1 else "")
                + gerekend[-1]
                + "."
            ),
            _tabel(
                [f"Na {sc['horizon_jaren']} jaar", "Uw vermogen", "Verschil met wat u inlegt"],
                [
                    [
                        "Goed scenario: 1 op 20 kans op meer",
                        eur(eind[kolom][2]),
                        eur(eind[kolom][2] - ingelegd),
                    ],
                    [
                        "<b>Middelste scenario</b>: even grote kans op meer als op minder",
                        f"<b>{eur(eind[kolom][1])}</b>",
                        eur(eind[kolom][1] - ingelegd),
                    ],
                    [
                        "Slecht scenario: 1 op 20 kans op minder",
                        eur(eind[kolom][0]),
                        eur(eind[kolom][0] - ingelegd),
                    ],
                    ["Wat u in totaal inlegt", eur(ingelegd), ""],
                ],
                [0.52, 0.22, 0.26],
                {1, 2},
                {1},
            ),
            Spacer(1, 3 * mm),
            KeepTogether(
                [
                    _legenda(
                        [
                            ("9 op de 10 uitkomsten", WAAIER, "vlak"),
                            ("Middelste scenario", BLAUW, "lijn"),
                            ("Wat u inlegt", ZACHT, "lijn"),
                        ]
                    ),
                    waaiergrafiek(sc["jaren"], sc.get("doelvermogen"), reeel),
                ]
            ),
        ]
        verlies = (
            sc.get("kans_minder_dan_ingelegd_reeel") if reeel else sc["kans_minder_dan_ingelegd"]
        )
        if verlies is None:
            verlies = sc["kans_minder_dan_ingelegd"]
        regels = []
        if kans_doel is not None:
            regels.append(
                (
                    "Kans op uw doel",
                    f"<b>{round(kans_doel * 100)}%</b> dat u {eur(sc['doelvermogen'])} haalt: {_oordeel(kans_doel)}.",
                )
            )
        regels.append(
            (
                "Kans op minder dan u inlegt",
                f"{round(verlies * 100)}% na {sc['horizon_jaren']} jaar.",
            )
        )
        inhoud += [Spacer(1, 2 * mm), _gegevens(regels)]

        opties = []
        if varianten.get("storting_voor_kans") and kans_doel is not None and kans_doel < 0.75:
            st = varianten["storting_voor_kans"]
            for k, label in (("0.5", "1 op 2"), ("0.75", "3 op 4")):
                if k in st and (kans_doel < float(k)):
                    opties.append(
                        [
                            f"Maandelijks {eur(st[k])} storten in plaats van {eur(profiel['storting_per_maand_eur'])}",
                            f"{round(float(k) * 100)}% ({label})",
                            "",
                        ]
                    )
        if varianten.get("langer"):
            lg = varianten["langer"]
            opties.append(
                [
                    f"{lg['horizon_jaren'] - profiel['horizon_jaren']} jaar langer beleggen ({lg['horizon_jaren']} jaar)",
                    f"{round(lg['kans_doel'] * 100)}%" if lg.get("kans_doel") is not None else "—",
                    eur(lg["midden"]),
                ]
            )
        for v in varianten.get("profielen", []):
            opties.append(
                [
                    f"Risicoprofiel {naam(v['code']).lower()}"
                    + (" (volgt uit de vragenlijst)" if v.get("afgeleid") else "")
                    + f"; in een slecht jaar meer dan {pct(-v['slecht_jaar'], 0)} verlies",
                    f"{round(v['kans_doel'] * 100)}%" if v.get("kans_doel") is not None else "—",
                    eur(v["midden"]),
                ]
            )
        if opties:
            inhoud += [
                CondPageBreak(45 * mm),
                _p(
                    "Wat als u iets anders kiest?"
                    if kans_doel is None or kans_doel >= 0.65
                    else "Wat helpt om uw doel te halen?",
                    "h2",
                ),
                _tabel(
                    ["Keuze", "Kans op uw doel", "Middelste scenario"],
                    [
                        [
                            f"Dit advies; in een slecht jaar meer dan {pct(-slecht_jaar, 0)} verlies"
                            if slecht_jaar is not None
                            else "Dit advies",
                            f"{round(kans_doel * 100)}%" if kans_doel is not None else "—",
                            eur(eind[kolom][1]),
                        ]
                    ]
                    + opties,
                    [0.56, 0.20, 0.24],
                    {1, 2},
                    {0},
                ),
                _p(
                    "Bij een hogere storting is de middelste uitkomst ook hoger; die staat niet in de tabel. "
                    "Een ander risicoprofiel kiest u alleen samen met uw adviseur, als het bij u past.",
                    "klein",
                ),
            ]
        inhoud.append(
            _p(
                "Dit zijn berekeningen op basis van aannames, geen voorspelling. De werkelijke uitkomst kan "
                "hoger of lager zijn, ook lager dan het slechte scenario.",
                "waarschuwing",
            )
        )

    # 6. Wat kan er misgaan ------------------------------------------------------------------
    inhoud += [CondPageBreak(80 * mm), _p("6. Wat kan er misgaan?", "h1")]
    if slecht_jaar is not None:
        inhoud.append(
            _p(
                f"<b>Een slecht jaar.</b> Gemiddeld eens in de twintig jaar daalt een portefeuille als deze met "
                f"meer dan {pct(-slecht_jaar, 0)}. Op uw inleg van {eur(profiel['inleg_eur'])} is dat ongeveer "
                f"{eur(-slecht_jaar * profiel['inleg_eur'])}."
            )
        )
    if su.get("crisis_rendement") is not None and su["crisis_rendement"] < 0:
        inhoud.append(
            _p(
                f"<b>Een zware crisis.</b> In een crisis zoals die van 2008 kan de waarde in korte tijd met "
                f"ongeveer {pct(-su['crisis_rendement'], 0)} dalen, ongeveer {eur(-su['crisis_rendement'] * profiel['inleg_eur'])} "
                "op uw inleg. Zo'n crisis is zeldzaam, maar kan voorkomen. Na eerdere crises herstelden de "
                "markten, maar dat duurde soms jaren."
            )
        )
    stress = [s for s in (analyse or {}).get("stressperioden") or [] if s["beschikbaar"]]
    if stress:
        inhoud.append(
            _p(
                "<b>In eerdere onrustige perioden</b> zou deze portefeuille zo zijn bewogen: "
                + "; ".join(
                    f"{s['naam'].split(' (')[0].lower()} {pct(s['rendement'], 0, teken=True)}"
                    for s in stress
                )
                + "."
            )
        )
    risicos = []
    zakelijk = d["zakelijke_waarden"]
    if zakelijk:
        risicos.append(
            (
                "Koersdalingen",
                f"{bp(zakelijk)} van uw vermogen zit in aandelen, vastgoed en grondstoffen. Die kunnen in korte tijd flink in waarde dalen.",
            )
        )
    obligaties = d["per_categorie"].get("obligaties", 0)
    if obligaties:
        risicos.append(
            (
                "Rentestijging",
                f"{bp(obligaties)} zit in obligaties. Als de rente stijgt, dalen obligaties in waarde, zoals in 2022.",
            )
        )
        risicos.append(
            (
                "Wanbetaling",
                "Een overheid of bedrijf kan een lening niet terugbetalen. Door de spreiding over veel leningen is het effect per geval klein.",
            )
        )
    vr = (d.get("valutarisico") or {}).get("ja", 0) + (d.get("valutarisico") or {}).get("deels", 0)
    if vr:
        afgedekt = [p["naam"] for p in posities if "Hedged" in p["naam"]]
        risicos.append(
            (
                "Wisselkoersen",
                f"Ongeveer {bp(vr)} van uw vermogen belegt (deels) buiten de euro. Als bijvoorbeeld de dollar daalt, "
                "daalt de waarde, ook al noteren de fondsen in euro's."
                + (
                    " Bij het wereldwijde obligatiefonds is dit risico afgedekt."
                    if afgedekt
                    else ""
                ),
            )
        )
    swaps = [p["naam"] for p in posities if "Swap" in p["naam"]]
    if swaps:
        risicos.append(
            (
                "Swaps",
                ("Eén fonds" if len(swaps) == 1 else f"{len(swaps)} fondsen")
                + " in uw portefeuille "
                + ("werkt" if len(swaps) == 1 else "werken")
                + " met swaps: afspraken met een bank. Als die bank haar afspraak niet nakomt, kan het fonds een deel van de waarde verliezen. Dat risico is wettelijk begrensd.",
            )
        )
    grootste = max(posities, key=lambda p: p["gewicht"]) if posities else None
    if grootste:
        risicos.append(
            (
                "Afhankelijkheid",
                f"Het grootste fonds, {_esc(grootste['naam'])}, is {bp(grootste['gewicht'])} van uw vermogen. Het belegt zelf wel breed gespreid.",
            )
        )
    risicos += [
        ("Inflatie", "Prijsstijgingen verminderen wat u met uw vermogen kunt kopen."),
        (
            "Verkopen in onrustige tijden",
            "Als de beurs onrustig is, kan verkopen tegen een goede prijs lastiger zijn. Bij brede indexfondsen is dat meestal beperkt.",
        ),
        (
            "Rekenmodel",
            "De scenario's berusten op aannames. Extreme gebeurtenissen komen vaker voor dan het model aanneemt.",
        ),
    ]
    inhoud += [_p("De risico's van uw portefeuille", "h2")] + [
        _opsom(f"<b>{k}.</b> {t}") for k, t in risicos
    ]

    # 7. Verleden -------------------------------------------------------------------------
    inhoud += [CondPageBreak(110 * mm), _p("7. Resultaten uit het verleden", "h1")]
    if not analyse or not analyse.get("peildatum"):
        inhoud.append(_p("Voor dit advies was geen historische analyse beschikbaar."))
    else:
        beschikbaar = [p for p in analyse["perioden"] if p["beschikbaar"] and p.get("portefeuille")]
        inhoud.append(
            _p(
                "Hoe zou deze verdeling het in het verleden hebben gedaan? De standaardmix is de verdeling die "
                "bij uw risicoprofiel hoort, met één breed fonds per soort belegging. Rendementen na fondskosten, "
                f"inclusief dividend, tot en met {datum_lang(analyse['peildatum'])}."
            )
        )
        titel = lambda p: (
            {
                "1j": "Afgelopen jaar",
                "3j": "Afgelopen 3 jaar",
                "5j": "Afgelopen 5 jaar",
                "10j": "Afgelopen 10 jaar",
            }.get(p["code"], f"Sinds {datum_lang(p['van'])}")
            + (" †" if p.get("gesimuleerd") else "")
        )
        inhoud.append(
            _tabel(
                ["Periode", "Gemiddeld per jaar", "Grootste daling", "Standaardmix per jaar"],
                [
                    [
                        titel(p),
                        pct(p["portefeuille"]["rendement_per_jaar"], teken=True),
                        pct(p["portefeuille"]["max_daling"], 0),
                        pct(p["benchmark"]["rendement_per_jaar"], teken=True)
                        if p.get("benchmark")
                        else "—",
                    ]
                    for p in beschikbaar
                ],
                [0.34, 0.22, 0.20, 0.24],
                {1, 2, 3},
            )
        )
        ontbreekt = [p for p in analyse["perioden"] if not p["beschikbaar"]]
        if ontbreekt:
            inhoud.append(
                _p(
                    "Over langere perioden zijn niet van alle fondsen koersen beschikbaar; die laten we daarom weg.",
                    "klein",
                )
            )
        if any(p.get("gesimuleerd") for p in beschikbaar):
            inhoud.append(
                _p(
                    "† Deels berekend met een vergelijkbaar fonds, omdat een fonds nog niet zo lang bestaat. Geen werkelijk behaald resultaat.",
                    "klein",
                )
            )
        grafiek = waardegrafiek(analyse.get("waardeverloop") or [])
        if grafiek:
            met_bm = all(p[2] is not None for p in analyse["waardeverloop"])
            inhoud += [
                Spacer(1, 3 * mm),
                KeepTogether(
                    [
                        _legenda(
                            [("Deze portefeuille", BLAUW, "lijn")]
                            + ([("Standaardmix", ORANJE, "lijn")] if met_bm else [])
                        ),
                        grafiek,
                        _p(
                            f"Wat € 100 vanaf {datum_lang(analyse['waardeverloop'][0][0])} waard zou zijn geworden.",
                            "klein",
                        ),
                    ]
                ),
                Spacer(1, 3 * mm),
            ]
        jaren = analyse.get("kalenderjaren") or []
        if jaren:
            beste = max(jaren, key=lambda j: j["portefeuille"])
            slechtste = min(jaren, key=lambda j: j["portefeuille"])
            inhoud.append(
                _p(
                    f"Het beste kalenderjaar was {beste['jaar']} ({pct(beste['portefeuille'], 0, teken=True)}), het "
                    f"slechtste {slechtste['jaar']} ({pct(slechtste['portefeuille'], 0, teken=True)}). Alle jaren staan in bijlage B."
                )
            )
        inhoud.append(
            _p(
                "In het verleden behaalde resultaten bieden geen garantie voor de toekomst.",
                "waarschuwing",
            )
        )

    # 8. Volgende stappen --------------------------------------------------------------------
    inhoud += [
        CondPageBreak(60 * mm),
        _p("8. Volgende stappen", "h1"),
        _opsom("<b>Akkoord:</b> als u met dit advies instemt, bespreken we de uitvoering met u."),
        _opsom(
            "<b>Jaarlijkse evaluatie:</b> we bekijken minstens eens per jaar met u of de portefeuille nog past en "
            "brengen de verdeling zo nodig terug naar de afspraak (herbalanceren)."
        ),
        _opsom(
            "<b>Neem eerder contact op</b> als uw situatie verandert, bijvoorbeeld bij een andere baan, een "
            "verhuizing, een erfenis, een scheiding, of als u het geld eerder nodig heeft."
        ),
        _opsom(
            "<b>Bij onrust op de beurs:</b> verkoop niet overhaast. Bel ons gerust om de situatie te bespreken."
        ),
    ]

    # Bijlagen ------------------------------------------------------------------------------
    inhoud += [PageBreak(), _p("Bijlage A: begrippen", "h1")]
    inhoud += [_p(f"<b>{_esc(k)}.</b> {_esc(v)}") for k, v in BEGRIPPEN]

    inhoud += [CondPageBreak(80 * mm), _p("Bijlage B: technische toelichting", "h1")]
    inhoud.append(_p("Fondsen", "h2"))
    inhoud.append(
        _tabel(
            ["Fonds", "ISIN", "Lopende kosten", "Gewicht"],
            [
                [_esc(p["naam"]), p["isin"], pct(p["lopende_kosten"] / 100, 2), bp(p["gewicht"])]
                for p in posities
            ],
            [0.52, 0.20, 0.14, 0.14],
            {2, 3},
        )
    )
    if analyse and analyse.get("peildatum"):
        inhoud += [
            CondPageBreak(55 * mm),
            _p("Resultaten uit het verleden, uitgebreid", "h2"),
            _tabel(
                [
                    "Periode",
                    "Per jaar",
                    "Volatiliteit",
                    "Grootste daling",
                    "Sharpe-ratio",
                    "Standaardmix",
                ],
                [
                    [
                        titel(p),
                        pct(p["portefeuille"]["rendement_per_jaar"], teken=True),
                        pct(p["portefeuille"]["volatiliteit"]),
                        pct(p["portefeuille"]["max_daling"]),
                        _getal(p["portefeuille"]["sharpe"], 2)
                        if p["portefeuille"].get("sharpe") is not None
                        else "—",
                        pct(p["benchmark"]["rendement_per_jaar"], teken=True)
                        if p.get("benchmark")
                        else "—",
                    ]
                    for p in analyse["perioden"]
                    if p["beschikbaar"] and p.get("portefeuille")
                ],
                [0.26, 0.13, 0.14, 0.16, 0.14, 0.17],
                {1, 2, 3, 4, 5},
            ),
        ]
        if analyse.get("kalenderjaren"):
            inhoud += [Spacer(1, 3 * mm), _p("Per kalenderjaar", "h2")]
            inhoud.append(
                _tabel(
                    ["Jaar", "Portefeuille", "Standaardmix"],
                    [
                        [
                            str(j["jaar"]),
                            pct(j["portefeuille"], teken=True),
                            pct(j["benchmark"], teken=True)
                            if j.get("benchmark") is not None
                            else "—",
                        ]
                        for j in reversed(analyse["kalenderjaren"])
                    ],
                    [0.2, 0.2, 0.2],
                    {1, 2},
                )
            )
        uitleg = [
            "Volatiliteit: standaarddeviatie van de dagrendementen, omgerekend naar een jaar.",
            "Sharpe-ratio: rendement boven de risicovrije rente, gedeeld door de volatiliteit"
            + (
                f"; risicovrije rente: {_esc(pf['analyse'].get('risicovrij'))}."
                if pf["analyse"].get("risicovrij")
                else "."
            ),
            "De portefeuille wordt jaarlijks op de eerste handelsdag teruggebracht naar de gewichten.",
        ]
        if benchmark_fondsen:
            uitleg.append(
                "Standaardmix: "
                + ", ".join(f"{b['gewicht']}% {_esc(b['naam'])}" for b in benchmark_fondsen)
                + "."
            )
        inhoud += [_p(u, "klein") for u in uitleg]
        for w in analyse.get("waarschuwingen") or []:
            inhoud.append(_p(_esc(w), "klein"))
    aannames = su.get("aannames") or {}
    if sc and aannames:
        inhoud += [
            _p("Rekenmodel voor de toekomst", "h2"),
            _p(
                f"{_getal(sc['paden'])} gesimuleerde verlopen met maandelijkse rendementen per soort belegging, "
                "lognormaal verdeeld met onderlinge samenhang, jaarlijks herbalanceren, stortingen aan het eind van "
                "elke maand. Het slechte en goede scenario zijn het 5e en 95e percentiel.",
                "klein",
            ),
            _tabel(
                ["Soort", "Verwacht rendement per jaar", "Volatiliteit per jaar", "Zware crisis"],
                [
                    [
                        naam(c),
                        pct(aannames["categorieen"][c]["rendement"]),
                        pct(aannames["categorieen"][c]["volatiliteit"]),
                        pct((aannames.get("stress") or {}).get(c, 0), 0)
                        if aannames.get("stress")
                        else "—",
                    ]
                    for c in CATEGORIEEN
                    if c in aannames.get("categorieen", {})
                ],
                [0.28, 0.26, 0.24, 0.22],
                {1, 2, 3},
            ),
            _p(
                f"Inflatie {pct(aannames['inflatie'])} per jaar. Aannames van {datum_lang(aannames['peildatum'])}; "
                f"bron: {_esc(aannames['bron'])}",
                "klein",
            ),
        ]
    inhoud += [
        _p("Verantwoording", "h2"),
        _p(
            f"Opgesteld op {datum_lang(g['opgesteld_op'])} uit portefeuilleversie {pf['versie']} (klantprofiel versie "
            f"{profiel['versie']}), vastgelegd op {datum_lang(pf['vastgelegd_op'])} door {_esc(g['adviseur'])}. De "
            "cijfers zijn een momentopname van dat moment. " + _esc(g.get("databron") or ""),
            "klein",
        ),
    ]

    buffer = io.BytesIO()
    titel_doc = f"Beleggingsadvies {klant['naam']} · {datum_lang(pf['vastgelegd_op'])}"
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=titel_doc,
        author=g["adviseur"],
        subject="Beleggingsadvies",
        creator="Portefeuille op maat",
        lang="nl-NL",
    )

    def voet(canvas, doc):
        _kop_en_voet(canvas, doc, titel_doc, concept)

    doc.build(inhoud, onFirstPage=voet, onLaterPages=voet)
    return buffer.getvalue()
