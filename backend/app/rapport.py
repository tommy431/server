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

_S = {
    "titel": ParagraphStyle(
        "titel", fontName="DejaVu-Vet", fontSize=20, leading=25, textColor=TEKST
    ),
    "h1": ParagraphStyle(
        "h1",
        fontName="DejaVu-Vet",
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=6,
        textColor=TEKST,
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName="DejaVu-Vet",
        fontSize=10.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
        textColor=TEKST,
    ),
    "p": ParagraphStyle(
        "p", fontName="DejaVu", fontSize=9, leading=13, textColor=TEKST, spaceAfter=4
    ),
    "klein": ParagraphStyle("klein", fontName="DejaVu", fontSize=7.5, leading=10, textColor=ZACHT),
    "cel": ParagraphStyle("cel", fontName="DejaVu", fontSize=8, leading=10, textColor=TEKST),
    "cel_r": ParagraphStyle(
        "cel_r", fontName="DejaVu", fontSize=8, leading=10, textColor=TEKST, alignment=TA_RIGHT
    ),
    "kop": ParagraphStyle("kop", fontName="DejaVu-Vet", fontSize=7.5, leading=10, textColor=ZACHT),
    "kop_r": ParagraphStyle(
        "kop_r",
        fontName="DejaVu-Vet",
        fontSize=7.5,
        leading=10,
        textColor=ZACHT,
        alignment=TA_RIGHT,
    ),
    "waarschuwing": ParagraphStyle(
        "waarschuwing",
        fontName="DejaVu-Vet",
        fontSize=9,
        leading=13,
        textColor=TEKST,
        spaceBefore=6,
    ),
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
    return f"€ {_getal(x)}"


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


# --- rapport ---------------------------------------------------------------------------

RISICOS = (
    (
        "Marktrisico",
        (
            "De waarde van beleggingen kan dalen door ontwikkelingen op de financiële markten. Vooral "
            "aandelen, vastgoed en grondstoffen kunnen in korte tijd sterk in waarde dalen."
        ),
    ),
    (
        "Valutarisico",
        (
            "Fondsen die beleggen buiten de eurozone zijn gevoelig voor veranderingen in wisselkoersen, "
            "ook als het fonds zelf in euro noteert."
        ),
    ),
    (
        "Renterisico",
        "Als de rente stijgt, daalt de waarde van obligaties; hoe langer de looptijd, hoe sterker.",
    ),
    (
        "Kredietrisico",
        "Uitgevende instellingen van obligaties kunnen hun verplichtingen niet nakomen.",
    ),
    (
        "Inflatierisico",
        (
            "Inflatie vermindert de koopkracht van het vermogen. Een nominaal behaald doel kan in "
            "koopkracht tegenvallen."
        ),
    ),
    (
        "Concentratierisico",
        (
            "Een groot deel van het vermogen in één fonds, sector of regio maakt de portefeuille "
            "gevoeliger voor ontwikkelingen daarin."
        ),
    ),
    (
        "Liquiditeitsrisico",
        "In onrustige markten kan het moeilijker zijn fondsen tegen een redelijke prijs te verkopen.",
    ),
    (
        "Modelrisico",
        (
            "Scenario's berusten op aannames en een rekenmodel. Extreme gebeurtenissen komen in "
            "werkelijkheid vaker voor dan het model aanneemt."
        ),
    ),
)


def _kop_en_voet(canvas, doc, titel: str) -> None:
    canvas.saveState()
    canvas.setFont("DejaVu", 7)
    canvas.setFillColor(ZACHT)
    canvas.drawString(20 * mm, 12 * mm, titel)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Pagina {doc.page}")
    canvas.setStrokeColor(RAND)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
    canvas.restoreState()


def maak_rapport(g: dict) -> bytes:
    """Bouwt het adviesrapport. `g` bevat de gegevens zoals `rapportgegevens` ze samenstelt."""
    klant, profiel, pf = g["klant"], g["profiel"], g["portefeuille"]
    d = pf["doorrekening"]
    analyse = (pf.get("analyse") or {}).get("analyse")
    scenario_uit = pf.get("scenario") or {}
    scenario = scenario_uit.get("scenario")
    inhoud: list = []

    # Voorblad --------------------------------------------------------------------------
    inhoud += [
        _p("Adviesrapport beleggingsportefeuille", "titel"),
        Spacer(1, 4 * mm),
        _gegevens(
            [
                ("Klant", _esc(klant["naam"])),
                ("Adviseur", _esc(g["adviseur"])),
                ("Datum advies", datum_lang(pf["vastgelegd_op"])),
                ("Portefeuilleversie", f"{pf['versie']} (klantprofiel versie {profiel['versie']})"),
                ("Risicoprofiel", naam(pf["risicoprofiel"])),
                ("Rapport opgesteld", datum_lang(g["opgesteld_op"])),
            ]
        ),
        Spacer(1, 4 * mm),
        _p(
            "Dit rapport legt het beleggingsadvies vast: uw situatie en wensen, de voorgestelde "
            "portefeuille en waarom die bij u past, de kosten, de historische resultaten van deze "
            "samenstelling, mogelijke toekomstige uitkomsten en de risico's."
        ),
    ]
    if g.get("waarschuwingen_vooraf"):
        inhoud += [
            Spacer(1, 2 * mm),
            _kader("<br/>".join(_esc(w) for w in g["waarschuwingen_vooraf"])),
        ]

    # 1. Klantprofiel -------------------------------------------------------------------
    doel = profiel.get("doelvermogen_eur")
    doelregel = "Geen doelvermogen opgegeven"
    if doel:
        doelregel = eur(doel) + (
            " in koopkracht van vandaag"
            if profiel.get("doel_in_koopkracht")
            else " (in euro's van dat moment)"
        )
    duurzaam = naam(profiel["duurzaamheid"]).capitalize()
    if profiel.get("uitsluitingen"):
        duurzaam += "; uitsluiten: " + ", ".join(naam(u) for u in profiel["uitsluitingen"])
    inhoud += [
        _p("1. Uw situatie en wensen", "h1"),
        _gegevens(
            [
                ("Beleggingsdoel", _esc(profiel["doel"])),
                ("Beleggingshorizon", f"{profiel['horizon_jaren']} jaar"),
                ("Inleg", eur(profiel["inleg_eur"])),
                ("Storting per maand", eur(profiel["storting_per_maand_eur"])),
                ("Doelvermogen", doelregel),
                ("Risicobereidheid", f"{profiel['score_bereidheid']} van 100"),
                ("Risicocapaciteit", f"{profiel['score_capaciteit']} van 100"),
                ("Kennis en ervaring", f"{profiel['score_kennis']} van 100"),
                ("Duurzaamheid", _esc(duurzaam)),
            ]
        ),
        _p("Uw risicoprofiel", "h2"),
        _p(
            f"Op basis van de vragenlijst en uw beleggingshorizon past het risicoprofiel "
            f"<b>{naam(profiel['afgeleid_risicoprofiel']).lower()}</b> bij u. Het voorzichtigste van "
            f"risicobereidheid, risicocapaciteit en horizon bepaalt het profiel; bij u is dat de "
            f"{naam(profiel['bepalende_factor'])}."
        ),
    ]
    if profiel["risicoprofiel"] != profiel["afgeleid_risicoprofiel"]:
        inhoud.append(
            _p(
                f"In overleg is gekozen voor het defensievere profiel <b>{naam(profiel['risicoprofiel']).lower()}</b>. "
                f"Toelichting: {_esc(profiel.get('afwijking_toelichting') or '')}"
            )
        )
    if profiel["score_kennis"] < 34:
        inhoud.append(
            _kader(
                "Uw kennis en ervaring met beleggen zijn beperkt. Lees de beschrijving van de risico's in "
                "hoofdstuk 7 extra aandachtig en stel vragen als iets niet duidelijk is."
            )
        )

    # 2. Portefeuille ------------------------------------------------------------------
    posities = sorted(
        g["posities"], key=lambda p: (CATEGORIEEN.index(p["categorie"]), -p["gewicht"])
    )
    rijen = [
        [
            f"{_esc(p['naam'])}<br/><font color='#5b6676' size='6.5'>{p['isin']} · {naam(p['regio'])}"
            + (f" · {naam(p['sector'])}" if p["sector"] not in ("breed", "vastgoed") else "")
            + "</font>",
            naam(p["categorie"]),
            pct(p["lopende_kosten"] / 100, 2),
            bp(p["gewicht"]),
        ]
        for p in posities
    ]
    rijen.append(
        [
            "<b>Totaal</b>",
            "",
            f"<b>{pct(d['kosten_pct'] / 100, 2)}</b>",
            f"<b>{bp(d['totaal'])}</b>",
        ]
    )
    inhoud += [
        PageBreak(),
        _p("2. De voorgestelde portefeuille", "h1"),
        _tabel(
            ["Fonds", "Categorie", "Lopende kosten", "Gewicht"],
            rijen,
            [0.56, 0.18, 0.14, 0.12],
            {2, 3},
        ),
        _p("Verdeling over beleggingscategorieën", "h2"),
        _tabel(
            ["Categorie", "Gewicht", "Toegestaan bij uw risicoprofiel", "Streefgewicht"],
            [
                [
                    naam(c),
                    bp(d["per_categorie"].get(c, 0)),
                    f"{pf['banden'][c]['minimum']}% – {pf['banden'][c]['maximum']}%",
                    f"{pf['banden'][c]['streef']}%",
                ]
                for c in CATEGORIEEN
                if c in pf["banden"]
            ],
            [0.30, 0.20, 0.30, 0.20],
            {1, 2, 3},
        ),
    ]
    regio = ", ".join(f"{naam(r)} {bp(w)}" for r, w in d["per_regio"].items())
    sector = ", ".join(f"{naam(s)} {bp(w)}" for s, w in d["per_sector"].items())
    kenmerken = [
        ("Naar regio", regio),
        ("Naar sector", sector),
        ("Zakelijke waarden", bp(d["zakelijke_waarden"])),
        ("Grootste positie", bp(d["grootste_positie"])),
        ("Aantal fondsen", str(d["aantal_instrumenten"])),
    ]
    if d.get("valutarisico"):
        v = d["valutarisico"]
        tekst = f"{bp(v.get('ja', 0))} met blootstelling aan vreemde valuta"
        if v.get("deels"):
            tekst += f", {bp(v['deels'])} gedeeltelijk"
        kenmerken.append(("Valutarisico", tekst))
    if pf.get("uitsluitingen"):
        kenmerken.append(
            (
                "Uitgesloten",
                "; ".join(
                    _esc(
                        (
                            g["fondsnamen"].get(u["waarde"], u["waarde"])
                            if u["soort"] == "instrument"
                            else naam(u["waarde"])
                        )
                        + (f" ({u['reden']})" if u.get("reden") else "")
                    )
                    for u in pf["uitsluitingen"]
                ),
            )
        )
    inhoud += [
        _p("Kenmerken", "h2"),
        _gegevens(kenmerken),
        _p(
            "Regio en sector zijn kenmerken van het fonds zelf. Breed gespreide fondsen beleggen in veel "
            "regio's en sectoren tegelijk; uitsluitingen op regio of sector gelden voor het fonds, niet "
            "voor alle onderliggende bedrijven.",
            "klein",
        ),
    ]

    # 3. Onderbouwing --------------------------------------------------------------------
    afwijkingen = [b for b in d["bevindingen"] if b["ernst"] == "afwijking"]
    aandacht = [b for b in d["bevindingen"] if b["ernst"] == "aandachtspunt"]
    inhoud += [CondPageBreak(50 * mm), _p("3. Waarom deze portefeuille bij u past", "h1")]
    inhoud.append(
        _p(
            f"De portefeuille volgt de strategische verdeling die hoort bij het risicoprofiel "
            f"{naam(pf['risicoprofiel']).lower()}. Elke beleggingscategorie blijft binnen de bandbreedte "
            "van dat profiel, en de spreiding over fondsen voldoet aan de beperkingen die voor elk "
            "advies gelden."
            if not afwijkingen
            else f"De portefeuille wijkt op de volgende punten af van het risicoprofiel "
            f"{naam(pf['risicoprofiel']).lower()} of van de beperkingen die voor elk advies gelden:"
        )
    )
    for b in afwijkingen:
        inhoud.append(_p(f"• {_esc(b['melding'])}"))
    if pf.get("toelichting"):
        inhoud.append(_p(f"<b>Toelichting van de adviseur:</b> {_esc(pf['toelichting'])}"))
    if aandacht:
        inhoud.append(_p("Aandachtspunten", "h2"))
        inhoud += [_p(f"• {_esc(b['melding'])}") for b in aandacht]

    # 4. Kosten --------------------------------------------------------------------------
    inhoud += [CondPageBreak(45 * mm), _p("4. Kosten", "h1")]
    kostenparen = [
        ("Lopende fondskosten", f"{pct(d['kosten_pct'] / 100, 2)} per jaar"),
        (
            "Op uw inleg",
            (
                f"circa {eur(profiel['inleg_eur'] * d['kosten_pct'] / 100)} per jaar bij een inleg van "
                f"{eur(profiel['inleg_eur'])}"
            ),
        ),
    ]
    if scenario_uit:
        overig = scenario_uit.get("overige_kosten_pct") or 0
        if overig:
            kostenparen.append(
                ("Overige kosten", f"{pct(overig / 100, 2)} per jaar (advies, beheer, bewaring)")
            )
        if scenario:
            kostenparen.append(
                (
                    "Effect over de looptijd",
                    (
                        f"De kosten van samen {pct(scenario['kosten_pct'] / 100, 2)} per jaar verlagen het "
                        f"verwachte eindvermogen na {scenario['horizon_jaren']} jaar met circa "
                        f"{eur(scenario['kosten_effect_mediaan'])}."
                    ),
                )
            )
    inhoud += [
        KeepTogether(
            [
                _gegevens(kostenparen),
                _p(
                    "De lopende fondskosten worden door de fondsen zelf ingehouden en zitten in de koers. "
                    "Transactiekosten bij aan- en verkoop zijn hier niet meegerekend. Een volledig overzicht van "
                    "alle kosten en de essentiële-informatiedocumenten van de fondsen ontvangt u apart.",
                    "klein",
                ),
            ]
        ),
    ]

    # 5. Historische analyse ------------------------------------------------------------
    inhoud += [CondPageBreak(110 * mm), _p("5. Resultaten uit het verleden", "h1")]
    if not analyse or not analyse.get("peildatum"):
        inhoud.append(
            _p(
                "Voor deze portefeuille was op het moment van het advies geen historische analyse beschikbaar."
            )
        )
    else:
        inhoud.append(
            _p(
                f"Hoe zou de huidige samenstelling het in het verleden hebben gedaan? Gerekend met koersen "
                f"tot en met {datum_lang(analyse['peildatum'])}, inclusief dividend, na lopende fondskosten, "
                "in euro, met jaarlijkse herbalancering. De benchmark is de strategische verdeling van uw "
                "risicoprofiel, ingevuld met één breed fonds per categorie."
            )
        )
        rijen = []
        for p in analyse["perioden"]:
            titel = {"1j": "1 jaar", "3j": "3 jaar", "5j": "5 jaar", "10j": "10 jaar"}.get(
                p["code"], f"Sinds {datum_lang(p['van'])}" if p.get("van") else "Sinds start"
            ) + (" †" if p.get("gesimuleerd") else "")
            if not p["beschikbaar"] or not p.get("portefeuille"):
                rijen.append([titel, "—", "—", "—", "—", "—"])
                continue
            k, bm = p["portefeuille"], p.get("benchmark")
            rijen.append(
                [
                    titel,
                    pct(k["rendement_per_jaar"], teken=True),
                    pct(k["volatiliteit"]),
                    pct(k["max_daling"]),
                    _getal(k["sharpe"], 2) if k.get("sharpe") is not None else "—",
                    pct(bm["rendement_per_jaar"], teken=True) if bm else "—",
                ]
            )
        inhoud += [
            _tabel(
                [
                    "Periode",
                    "Rendement per jaar",
                    "Volatiliteit",
                    "Grootste daling",
                    "Sharpe-ratio",
                    "Benchmark per jaar",
                ],
                rijen,
                [0.26, 0.16, 0.14, 0.15, 0.13, 0.16],
                {1, 2, 3, 4, 5},
            ),
        ]
        niet = [p for p in analyse["perioden"] if not p["beschikbaar"]]
        if niet:
            inhoud.append(
                _p(
                    "— Niet beschikbaar: " + "; ".join(_esc(p["reden"] or "") for p in niet) + ".",
                    "klein",
                )
            )
        if any(p.get("gesimuleerd") for p in analyse["perioden"]):
            inhoud.append(
                _p(
                    "† Deels gesimuleerd: voor fondsen met een kortere historie is gerekend met een "
                    "vergelijkbaar fonds. Dit zijn geen werkelijk behaalde resultaten.",
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
                            [("Portefeuille", BLAUW, "lijn")]
                            + ([("Benchmark", ORANJE, "lijn")] if met_bm else [])
                        ),
                        grafiek,
                        _p("Waardeontwikkeling, beginwaarde 100, maandwaarden.", "klein"),
                    ]
                ),
            ]
        if analyse.get("kalenderjaren"):
            jaren = analyse["kalenderjaren"]
            beste = max(jaren, key=lambda j: j["portefeuille"])
            slechtste = min(jaren, key=lambda j: j["portefeuille"])
            inhoud += [
                CondPageBreak(60 * mm),
                _p("Per kalenderjaar", "h2"),
                _tabel(
                    ["Jaar", "Portefeuille", "Benchmark"],
                    [
                        [
                            str(j["jaar"]),
                            pct(j["portefeuille"], teken=True),
                            pct(j["benchmark"], teken=True)
                            if j.get("benchmark") is not None
                            else "—",
                        ]
                        for j in reversed(jaren)
                    ],
                    [0.2, 0.2, 0.2],
                    {1, 2},
                ),
                _p(
                    f"Beste jaar: {beste['jaar']} ({pct(beste['portefeuille'], teken=True)}). "
                    f"Slechtste jaar: {slechtste['jaar']} ({pct(slechtste['portefeuille'], teken=True)})."
                ),
            ]
        stress = analyse.get("stressperioden") or []
        if stress:
            inhoud += [
                CondPageBreak(45 * mm),
                _p("In eerdere crises", "h2"),
                _tabel(
                    ["Periode", "Portefeuille", "Grootste daling"],
                    [
                        [
                            s["naam"] + (" †" if s.get("gesimuleerd") else ""),
                            pct(s["rendement"], teken=True),
                            pct(s["max_daling"]),
                        ]
                        if s["beschikbaar"]
                        else [s["naam"], "—", "—"]
                        for s in stress
                    ],
                    [0.55, 0.2, 0.25],
                    {1, 2},
                ),
            ]
            ontbreekt = [s for s in stress if not s["beschikbaar"]]
            if ontbreekt:
                inhoud.append(
                    _p(
                        "— Niet beschikbaar: "
                        + "; ".join(
                            f"{_esc(s['naam'])}: {_esc(s.get('reden') or '')}" for s in ontbreekt
                        )
                        + ". Zie voor een zware crisis hoofdstuk 6.",
                        "klein",
                    )
                )
        if analyse.get("waarschuwingen"):
            inhoud += [_p("Opmerkingen bij de gegevens", "h2")] + [
                _p(f"• {_esc(w)}", "klein") for w in analyse["waarschuwingen"]
            ]
        inhoud.append(
            _p(
                "In het verleden behaalde resultaten bieden geen garantie voor de toekomst.",
                "waarschuwing",
            )
        )

    # 6. Scenario's -----------------------------------------------------------------------
    inhoud += [CondPageBreak(130 * mm), _p("6. Mogelijke uitkomsten in de toekomst", "h1")]
    if not scenario:
        inhoud.append(_p("Voor deze portefeuille zijn bij het advies geen scenario's berekend."))
    else:
        reeel = bool(profiel.get("doel_in_koopkracht"))
        kolom = "reeel" if reeel else "nominaal"
        eind = scenario["jaren"][-1]
        ingelegd = eind.get("ingelegd_reeel", eind["ingelegd"]) if reeel else eind["ingelegd"]
        aannames = scenario_uit.get("aannames") or {}
        inhoud += [
            _p(
                f"Op basis van {_getal(scenario['paden'])} gesimuleerde verlopen over {scenario['horizon_jaren']} jaar, "
                f"met uw inleg van {eur(scenario['inleg'])} en {eur(scenario['storting_per_maand'])} per maand. "
                + (
                    "Bedragen in koopkracht van vandaag, zoals uw doelvermogen is afgesproken."
                    if reeel
                    else "Bedragen in euro's van dat moment."
                )
            ),
            _tabel(
                [f"Na {scenario['horizon_jaren']} jaar", "Vermogen", "Ten opzichte van ingelegd"],
                [
                    [
                        "Goed scenario (1 op 20 kans op meer)",
                        eur(eind[kolom][2]),
                        eur(eind[kolom][2] - ingelegd),
                    ],
                    ["Verwacht scenario", eur(eind[kolom][1]), eur(eind[kolom][1] - ingelegd)],
                    [
                        "Slecht scenario (1 op 20 kans op minder)",
                        eur(eind[kolom][0]),
                        eur(eind[kolom][0] - ingelegd),
                    ],
                    [
                        "Totaal ingelegd" + (" (in koopkracht van vandaag)" if reeel else ""),
                        eur(ingelegd),
                        "",
                    ],
                ],
                [0.5, 0.25, 0.25],
                {1, 2},
                {1},
            ),
            Spacer(1, 3 * mm),
            KeepTogether(
                [
                    _legenda(
                        [
                            ("90% van de uitkomsten", WAAIER, "vlak"),
                            ("Verwacht", BLAUW, "lijn"),
                            ("Ingelegd", ZACHT, "lijn"),
                        ]
                    ),
                    waaiergrafiek(scenario["jaren"], scenario.get("doelvermogen"), reeel),
                ]
            ),
        ]
        kansen = []
        if scenario.get("doelvermogen"):
            k = scenario["kans_doel_reeel"] if reeel else scenario["kans_doel_nominaal"]
            kansen.append(
                (
                    "Kans op uw doelvermogen",
                    f"{round(k * 100)}% dat {eur(scenario['doelvermogen'])} wordt gehaald",
                )
            )
        kansen.append(
            (
                "Kans op minder dan ingelegd",
                f"{round(scenario['kans_minder_dan_ingelegd'] * 100)}% (nominaal)",
            )
        )
        if scenario_uit.get("crisis_rendement") is not None:
            kansen.append(
                (
                    "Bij een zware crisis",
                    (
                        f"Een crisis zoals in de aannames beschreven zou de waarde direct met "
                        f"{pct(scenario_uit['crisis_rendement'])} veranderen; op uw inleg circa "
                        f"{eur(max(scenario_uit.get('crisis_verlies_eur') or 0, 0))} verlies. Dat valt buiten het "
                        "slechte scenario."
                    ),
                )
            )
        kansen.append(
            (
                "Effect van inflatie",
                f"Het verwachte eindvermogen is in koopkracht van vandaag circa {eur(scenario['inflatie_effect_mediaan'])} minder waard.",
            )
        )
        if scenario.get("belasting_pct"):
            kansen.append(
                (
                    "Vermogensheffing",
                    (
                        f"Gerekend met {pct(scenario['belasting_pct'] / 100, 2)} per jaar, als benadering: circa "
                        f"{eur(scenario.get('belasting_effect_mediaan') or 0)} lager verwacht eindvermogen."
                    ),
                )
            )
        else:
            kansen.append(("Belasting", "Belastingen zijn niet meegerekend."))
        inhoud += [Spacer(1, 3 * mm), _gegevens(kansen)]
        if aannames:
            regels = [
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
            ]
            inhoud += [
                CondPageBreak(55 * mm),
                _p("Gebruikte aannames", "h2"),
                _tabel(
                    [
                        "Categorie",
                        "Verwacht rendement per jaar",
                        "Volatiliteit per jaar",
                        "Zware crisis",
                    ],
                    regels,
                    [0.28, 0.26, 0.24, 0.22],
                    {1, 2, 3},
                ),
                _p(
                    f"Inflatie {pct(aannames['inflatie'])} per jaar. Aannames van {datum_lang(aannames['peildatum'])}. "
                    f"Bron: {_esc(aannames['bron'])}",
                    "klein",
                ),
            ]
        inhoud.append(
            _p(
                "Dit zijn scenario's op basis van aannames, geen voorspelling. De werkelijke uitkomst kan "
                "hoger of lager zijn, ook lager dan het slechte scenario.",
                "waarschuwing",
            )
        )

    # 7. Risico's en verklaring ----------------------------------------------------------
    inhoud += [CondPageBreak(90 * mm), _p("7. Risico's", "h1")]
    inhoud += [_p(f"<b>{k}.</b> {t}") for k, t in RISICOS]
    inhoud += [
        _p("Gegevens en verantwoording", "h2"),
        _p(
            f"Rapport gegenereerd op {datum_lang(g['opgesteld_op'])} uit portefeuilleversie {pf['versie']}, "
            f"vastgelegd op {datum_lang(pf['vastgelegd_op'])} door {_esc(g['adviseur'])}. De cijfers in dit "
            "rapport zijn een momentopname van dat moment en veranderen niet als koersen, aannames of "
            "modelallocaties later wijzigen.",
            "klein",
        ),
    ]
    if g.get("databron"):
        inhoud.append(_p(_esc(g["databron"]), "klein"))

    buffer = io.BytesIO()
    titel = (
        f"Adviesrapport {klant['naam']} · versie {pf['versie']} · {datum_lang(pf['vastgelegd_op'])}"
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=titel,
        author=g["adviseur"],
        subject="Adviesrapport beleggingsportefeuille",
        creator="Portefeuille op maat",
    )
    voet = lambda canvas, doc: _kop_en_voet(canvas, doc, titel)
    doc.build(inhoud, onFirstPage=voet, onLaterPages=voet)
    return buffer.getvalue()
