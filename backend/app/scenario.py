"""Verwacht rendement: Monte Carlo-simulatie van de vermogensontwikkeling.

Model:
- Per beleggingscategorie een verwacht rekenkundig rendement per jaar en een volatiliteit,
  plus correlaties tussen categorieën. Dit zijn aannames, geen voorspellingen.
- Maandrendementen zijn lognormaal verdeeld, gezamenlijk normaal in logaritmen. De parameters
  zijn zo gekozen dat het rekenkundig jaarrendement en de jaarvolatiliteit per categorie
  overeenkomen met de aannames.
- Extreme crises komen in werkelijkheid vaker voor dan dit model aanneemt. Dikkere staarten per
  maand helpen daar niet tegen: over jaren middelen ze uit. Staartrisico wordt daarom apart
  getoond met historische en hypothetische stresstests.
- De portefeuille wordt eens per jaar teruggebracht naar de gewichten per categorie; daartussen
  lopen de gewichten met de koersen mee, net als in de historische analyse.
- Kosten (lopende fondskosten plus eventuele overige kosten) en een eventuele vermogensheffing
  als percentage van het vermogen gaan er elke maand naar rato af.
- De inleg wordt aan het begin belegd, stortingen aan het eind van elke maand volgens de
  gewichten.
- Bedragen in koopkracht van vandaag zijn teruggerekend met een vaste inflatie.
"""

from dataclasses import asdict, dataclass

import numpy as np

STANDAARD_PADEN = 10_000
MIN_PADEN = 5_000
MAX_PADEN = 50_000
STANDAARD_ZAAD = 20_261_117  # vast, zodat dezelfde invoer dezelfde uitkomst geeft
PERCENTIELEN = (5, 50, 95)


class AannameFout(ValueError):
    def __init__(self, fouten: list[str]) -> None:
        super().__init__("; ".join(fouten))
        self.fouten = fouten


@dataclass(frozen=True)
class Aannames:
    categorieen: tuple[str, ...]
    rendement: dict[str, float]  # verwacht rekenkundig rendement per jaar, bijv. 0.065
    volatiliteit: dict[str, float]  # per jaar, bijv. 0.16
    correlaties: dict[str, dict[str, float]]  # symmetrisch; diagonaal 1
    inflatie: float  # per jaar

    def matrix(self) -> np.ndarray:
        c = self.categorieen
        return np.array([[self.correlaties[a][b] for b in c] for a in c])


def controleer(a: Aannames) -> list[str]:
    """Geeft de fouten in een aannameset terug; een lege lijst betekent geldig."""
    fouten = []
    for c in a.categorieen:
        r, v = a.rendement.get(c), a.volatiliteit.get(c)
        if r is None or v is None:
            fouten.append(f"{c}: rendement en volatiliteit zijn verplicht")
            continue
        if not -0.05 <= r <= 0.20:
            fouten.append(f"{c}: verwacht rendement {r:.1%} valt buiten −5% tot 20%")
        if not 0 <= v <= 0.60:
            fouten.append(f"{c}: volatiliteit {v:.1%} valt buiten 0% tot 60%")
    if not -0.02 <= a.inflatie <= 0.10:
        fouten.append(f"Inflatie {a.inflatie:.1%} valt buiten −2% tot 10%")
    try:
        m = a.matrix()
    except KeyError:
        return fouten + ["De correlatiematrix is onvolledig"]
    if not np.allclose(m, m.T):
        fouten.append("De correlatiematrix is niet symmetrisch")
    if not np.allclose(np.diag(m), 1):
        fouten.append("De correlatie van een categorie met zichzelf moet 1 zijn")
    if np.any(m < -1) or np.any(m > 1):
        fouten.append("Correlaties moeten tussen −1 en 1 liggen")
    if not fouten and np.linalg.eigvalsh(m).min() < -1e-10:
        fouten.append(
            "De correlaties zijn onderling niet mogelijk (de matrix is niet positief "
            "semidefiniet); pas een of meer correlaties aan"
        )
    return fouten


def portefeuillekenmerken(gewichten: dict[str, float], a: Aannames) -> tuple[float, float]:
    """Verwacht rekenkundig jaarrendement en jaarvolatiliteit van de mix, vóór kosten."""
    w = np.array([gewichten.get(c, 0.0) for c in a.categorieen])
    r = np.array([a.rendement[c] for c in a.categorieen])
    v = np.array([a.volatiliteit[c] for c in a.categorieen])
    cov = np.outer(v, v) * a.matrix()
    return float(w @ r), float(np.sqrt(max(w @ cov @ w, 0.0)))


@dataclass(frozen=True)
class Jaarpunt:
    jaar: int
    ingelegd: float
    # Inleg plus stortingen, elke storting teruggerekend naar koopkracht van vandaag.
    ingelegd_reeel: float
    nominaal: tuple[float, float, float]  # 5e, 50e, 95e percentiel
    reeel: tuple[float, float, float]


@dataclass(frozen=True)
class Scenario:
    paden: int
    zaad: int
    horizon_jaren: int
    inleg: float
    storting_per_maand: float
    doelvermogen: float | None
    kosten_pct: float  # totaal per jaar, in procenten
    belasting_pct: float  # vermogensheffing per jaar als percentage van het vermogen
    verwacht_rendement: float  # vóór kosten
    verwachte_volatiliteit: float
    jaren: list[Jaarpunt]
    kans_doel_nominaal: float | None
    kans_doel_reeel: float | None
    kans_minder_dan_ingelegd: float
    mediaan_zonder_kosten: float
    kosten_effect_mediaan: float  # mediaan eindvermogen zonder kosten min met kosten
    belasting_effect_mediaan: float  # mediaan eindvermogen zonder heffing min met heffing
    inflatie_effect_mediaan: float  # mediaan nominaal min mediaan in koopkracht van vandaag

    def als_dict(self) -> dict:
        return asdict(self)


def simuleer(
    gewichten: dict[str, float],
    aannames: Aannames,
    *,
    horizon_jaren: int,
    inleg: float,
    storting_per_maand: float,
    kosten_pct: float,
    belasting_pct: float = 0.0,
    doelvermogen: float | None = None,
    paden: int = STANDAARD_PADEN,
    zaad: int = STANDAARD_ZAAD,
) -> Scenario:
    """Simuleert de vermogensontwikkeling. `gewichten` per categorie tellen op tot 1."""
    if not MIN_PADEN <= paden <= MAX_PADEN:
        raise ValueError(f"Het aantal paden moet tussen {MIN_PADEN} en {MAX_PADEN} liggen")
    if horizon_jaren < 1:
        raise ValueError("De horizon moet minimaal 1 jaar zijn")
    if not 0 <= kosten_pct < 100 or not 0 <= belasting_pct < 100:
        raise ValueError("Kosten en heffing moeten tussen 0% en 100% liggen")
    if abs(sum(gewichten.values()) - 1) > 1e-9:
        raise ValueError("De gewichten tellen niet op tot 100%")
    onbekend = set(gewichten) - set(aannames.categorieen)
    if onbekend:
        raise ValueError(f"Geen aannames voor: {', '.join(sorted(onbekend))}")
    fouten = controleer(aannames)
    if fouten:
        raise AannameFout(fouten)

    cats = aannames.categorieen
    w = np.array([gewichten.get(c, 0.0) for c in cats])
    r = np.array([aannames.rendement[c] for c in cats])
    v = np.array([aannames.volatiliteit[c] for c in cats])

    # Lognormaal per jaar: E[1+R] = 1+r en Var[1+R] = v². Daaruit volgen per jaar de
    # verwachting (mu) en standaarddeviatie (s) van ln(1+R); per maand gedeeld door 12 en √12.
    s = np.sqrt(np.log1p((v / (1 + r)) ** 2))
    mu = np.log1p(r) - s**2 / 2
    cov_log = np.outer(s, s) * aannames.matrix() / 12
    # Cholesky werkt niet bij een semidefiniete matrix (bijv. volatiliteit 0); eigenwaarden wel.
    eigen, vectoren = np.linalg.eigh(cov_log)
    factor = vectoren * np.sqrt(np.clip(eigen, 0, None))

    maanden = horizon_jaren * 12
    rng = np.random.default_rng(zaad)
    kostenfactor = (1 - kosten_pct / 100) ** (1 / 12)
    heffingfactor = (1 - belasting_pct / 100) ** (1 / 12)

    # Drie varianten met dezelfde toevalsgetallen, zodat het effect van kosten en heffing zuiver
    # te meten is: alles, zonder kosten, zonder heffing. Bezit per pad en per categorie.
    factoren = {
        "alles": kostenfactor * heffingfactor,
        "zonder_kosten": heffingfactor,
        "zonder_heffing": kostenfactor,
    }
    bezit = {k: np.outer(np.full(paden, float(inleg)), w) for k in factoren}
    jaar_nominaal = [bezit["alles"].sum(axis=1)]
    for maand in range(1, maanden + 1):
        z = rng.standard_normal((paden, len(cats)))
        groei = np.exp(mu / 12 + z @ factor.T)  # per categorie
        for k, f in factoren.items():
            bezit[k] = bezit[k] * groei * f + storting_per_maand * w
            if maand % 12 == 0:  # jaarlijks herbalanceren
                bezit[k] = np.outer(bezit[k].sum(axis=1), w)
        if maand % 12 == 0:
            jaar_nominaal.append(bezit["alles"].sum(axis=1))
    zonder_kosten = bezit["zonder_kosten"].sum(axis=1)
    zonder_heffing = bezit["zonder_heffing"].sum(axis=1)

    maandinflatie = (1 + aannames.inflatie) ** (1 / 12)
    jaren = []
    for jaar, waarden in enumerate(jaar_nominaal):
        deflator = (1 + aannames.inflatie) ** jaar
        stortingen_reeel = sum(
            storting_per_maand / maandinflatie**m for m in range(1, 12 * jaar + 1)
        )
        p = np.percentile(waarden, PERCENTIELEN)
        jaren.append(
            Jaarpunt(
                jaar=jaar,
                ingelegd=float(inleg + storting_per_maand * 12 * jaar),
                ingelegd_reeel=float(inleg + stortingen_reeel),
                nominaal=tuple(float(x) for x in p),
                reeel=tuple(float(x) / deflator for x in p),
            )
        )

    eind = jaar_nominaal[-1]
    eind_reeel = eind / (1 + aannames.inflatie) ** horizon_jaren
    ingelegd = jaren[-1].ingelegd
    mediaan = float(np.median(eind))
    mediaan_zonder = float(np.median(zonder_kosten))
    rendement_mix, volatiliteit_mix = portefeuillekenmerken(gewichten, aannames)
    return Scenario(
        paden=paden,
        zaad=zaad,
        horizon_jaren=horizon_jaren,
        inleg=float(inleg),
        storting_per_maand=float(storting_per_maand),
        doelvermogen=doelvermogen,
        kosten_pct=kosten_pct,
        belasting_pct=belasting_pct,
        verwacht_rendement=rendement_mix,
        verwachte_volatiliteit=volatiliteit_mix,
        jaren=jaren,
        kans_doel_nominaal=float(np.mean(eind >= doelvermogen)) if doelvermogen else None,
        kans_doel_reeel=float(np.mean(eind_reeel >= doelvermogen)) if doelvermogen else None,
        kans_minder_dan_ingelegd=float(np.mean(eind < ingelegd)),
        mediaan_zonder_kosten=mediaan_zonder,
        kosten_effect_mediaan=mediaan_zonder - mediaan,
        belasting_effect_mediaan=float(np.median(zonder_heffing)) - mediaan,
        inflatie_effect_mediaan=mediaan - float(np.median(eind_reeel)),
    )
