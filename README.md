# Portefeuille op maat

Webapplicatie waarmee een beleggingsadviseur een portefeuille op maat samenstelt voor een klant.

## Stand van zaken

| Stap | Onderdeel | Status |
|---|---|---|
| 1 | Fundament: server, database, inloggen, logboek | klaar |
| 2 | Data: ETF-lijst, koersbronnen, kwaliteitscontroles | klaar |
| 3 | Klantprofiel, vragenlijst, risicoprofielen en eerste schermen | klaar |
| 4 | Portefeuilleconstructie: voorstel, uitsluitingen, toetsing, versies | klaar |
| 5 | Historische analyse met benchmark en grafiek | klaar |
| 6 | Verwacht rendement: Monte Carlo-scenario's en instelbare aannames | klaar |
| 7 | Adviesrapport als PDF per vastgelegde versie | klaar |


## Starten

Vereist: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ en Docker (voor PostgreSQL).

```bash
docker compose up -d
cd backend
cp ../.env.example .env        # vul JWT_GEHEIM en VERSLEUTELSLEUTEL in
uv sync
uv run alembic upgrade head
uv run python -m app.cli adviseur-aanmaken --email jij@voorbeeld.nl --naam "Jouw Naam"
uv run python -m app.cli universum-laden
uv run python -m app.cli data-verversen
uv run uvicorn app.main:app --reload
```

In een tweede venster de schermen:

```bash
cd frontend
npm install
npm run dev
```

Open daarna http://localhost:5173 en log in met het aangemaakte account.

Bewaar `VERSLEUTELSLEUTEL` veilig en apart van de database: zonder die sleutel zijn de
klantgegevens niet meer te lezen.

Tests: `uv run pytest` (SQLite in het geheugen; zet `TEST_DATABASE_URL` om tegen PostgreSQL te testen).

## Data

- **ETF-lijst:** `backend/data/universum.csv`, 40 ETF's. Aanpassen en opnieuw laden met
  `universum-laden`, of uploaden via `POST /instrumenten/import`.
- **Koersen:** Yahoo Finance (dagkoersen, gecorrigeerd voor dividend). Dit is een onofficiële bron
  die alleen voor persoonlijk gebruik is toegestaan: geschikt voor het prototype, niet voor een
  commercieel product. De bron zit achter de interface `Koersbron` in `backend/app/data/bronnen.py`
  en is daar te vervangen.
- **Wisselkoersen:** ECB-referentiekoersen.
- **Eigen koersen:** CSV met kolommen `datum,slot,slot_gecorrigeerd` via
  `POST /instrumenten/{id}/koersen/import`.
- **Kwaliteit:** `GET /data/status` toont per instrument de periode, de bron en bevindingen
  (gaten, koerssprongen van meer dan 20%, verouderde koersen). Bevindingen worden gemeld, niet
  stil gecorrigeerd.

## Klantprofiel

- Naam, e-mailadres, geboortedatum, beleggingsdoel en toelichtingen staan versleuteld in de
  database. Een adviseur ziet alleen zijn eigen klanten.
- Het risicoprofiel volgt uit de vragenlijst en de horizon: de voorzichtigste van
  risicobereidheid, risicocapaciteit en horizon bepaalt. De adviseur mag een defensiever
  profiel kiezen (met toelichting), nooit een offensiever.
- Elke wijziging van een profiel is een nieuwe versie; eerdere versies blijven bewaard.
- De modelallocaties per risicoprofiel zijn te beheren in het scherm Modelallocaties.

## Portefeuille

- Het startvoorstel volgt de streefgewichten van het risicoprofiel en vult elke categorie met de
  startselectie uit `backend/app/portefeuille.py`.
- Na elke wijziging wordt de portefeuille opnieuw doorgerekend: verdeling naar categorie, regio en
  sector, lopende kosten en toetsing aan de bandbreedtes en concentratiegrenzen.
- Een fout (bijvoorbeeld geen 100%) blokkeert vastleggen. Een afwijking van het risicoprofiel of
  de beperkingen vereist een toelichting, die versleuteld wordt bewaard.
- Elke vastgelegde versie bewaart een momentopname van banden en doorrekening, zodat het advies
  later te reconstrueren is.
- Het valutarisico per fonds (`valutarisico` in `universum.csv`) is door mij ingevuld op basis
  van de fondsnaam en het beleggingsgebied; controleer het tegen de fondsdocumentatie.
- Regio en sector zijn labels van het instrument. Van breed gespreide fondsen is de onderliggende
  verdeling niet bekend; uitsluitingen op regio of sector en duurzaamheidswensen kunnen daarom
  niet op het niveau van de onderliggende beleggingen worden getoetst.

## Historische analyse

- Rendement per jaar, volatiliteit, grootste daling, Sharpe-ratio en vergelijking met een
  benchmark over 1, 3, 5 en 10 jaar en sinds start, plus rendement per kalenderjaar.
- Totaalrendement in euro, inclusief dividend en na lopende fondskosten (die zitten in de koers).
  Transactiekosten en advieskosten zijn niet meegerekend.
- De portefeuille wordt jaarlijks op de eerste handelsdag teruggebracht naar de gewichten.
- Een periode is alleen beschikbaar als elk fonds over de hele periode koersen heeft; anders
  wordt gemeld welk fonds de historie beperkt. Op verzoek wordt een korte fondshistorie aangevuld
  met het rendement van een fonds met dezelfde categorie, regio en sector. Zulke perioden worden
  als gesimuleerd gemarkeerd.
- Koersen van vóór een onverklaarbare koerssprong van meer dan 20% worden niet gebruikt.
- Risicovrij rendement voor de Sharpe-ratio: de kortlopende eurorente van de ECB (€STR, vóór
  oktober 2019 EONIA).
- Stresstest: de huidige samenstelling in de kredietcrisis (2008–2009), de Europese
  schuldencrisis (2011), de coronacrash (2020) en het jaar 2022, voor zover er koersen zijn.
- Bij elke vastgelegde portefeuilleversie wordt de analyse bewaard zoals die toen was.

## Verwacht rendement

- 10.000 gesimuleerde verlopen over de horizon van de klant, met maandelijkse rendementen per
  beleggingscategorie (lognormaal, met correlaties), jaarlijks herbalanceren, de inleg, de
  maandelijkse stortingen, de lopende fondskosten, eventuele overige kosten en een optionele
  vermogensheffing als benadering van box 3. Met een vast startgetal, zodat dezelfde invoer
  dezelfde uitkomst geeft.
- Getoond worden een slecht, verwacht en goed scenario (5e, 50e en 95e percentiel), de kans op het
  doelvermogen (nominaal of in koopkracht van vandaag, zoals vastgelegd in het profiel), de kans
  op minder dan ingelegd en het effect van kosten, heffing en inflatie.
- Een hypothetische zware crisis met een instelbare schok per categorie laat zien wat een daling
  buiten het slechte scenario zou betekenen.
- De aannames (rendement, volatiliteit, correlaties, inflatie, bron en peildatum) zijn te beheren
  in het scherm Aannames. Elke wijziging is een nieuwe versie; elke vastgelegde portefeuille
  bewaart haar scenario en de gebruikte aannames.

## Adviesrapport

- Bij elke vastgelegde portefeuilleversie kan een adviesrapport (PDF) worden opgesteld: situatie
  en wensen, risicoprofiel, portefeuille, onderbouwing, kosten, resultaten uit het verleden met
  stresstest, scenario's met de gebruikte aannames, en risico's.
- Het rapport wordt opgebouwd uit de momentopname van de versie en verandert dus niet als koersen,
  aannames of modelallocaties later wijzigen.
- Elk rapport wordt versleuteld bewaard met datum, opsteller en SHA-256-vingerafdruk. Opstellen en
  downloaden worden vastgelegd in het logboek.
- Zolang er voorbeeldaannames of ongecontroleerde fondskosten in zitten, staat op de eerste pagina
  dat het een concept is.
- Het lettertype DejaVu Sans staat in `backend/app/lettertypen` (vrije licentie, zie
  `LICENTIE-DejaVu.txt`).

## Klantgegevens verwijderen

Een gearchiveerde klant kan worden geanonimiseerd zodra de bewaartermijn van vijf jaar na het
laatste advies is verstreken (MiFID II). Naam, e-mailadres, geboortedatum, doel en
toelichtingen worden dan gewist, net als de PDF-rapporten (hun vingerafdruk blijft bewaard); de
cijfers blijven bewaard. Laat de termijn toetsen door een
jurist: die kan langer zijn als de AFM daarom vraagt.

## Nog te controleren

- De vaste teksten in het adviesrapport (risico's, toelichtingen) zijn een eerste opzet. Laat ze
  door compliance beoordelen, en ook of het rapport voldoet als geschiktheidsverklaring.

- **De meegeleverde aannames zijn voorbeeldwaarden zonder gepubliceerde bron.** Vervang ze door
  aannames uit een erkende bron voordat de scenario's in een advies worden gebruikt. Het scherm
  toont een waarschuwing zolang de voorbeeldwaarden gelden.

- De benchmarkfondsen zijn een voorbeeldkeuze. Voor een eerlijke vergelijking is een index of een
  breed geaccepteerde mixbenchmark beter; daarvoor is een andere databron nodig.
- De startselectie en de concentratiegrenzen in `backend/app/portefeuille.py` zijn
  voorbeeldwaarden en leggen een beleggingsvisie vast. Laat ze beoordelen door de adviseur.

- De vragenlijst, de puntentelling, de grenzen per risicoprofiel en de standaardallocaties in
  `backend/app/profiel.py` zijn voorbeeldwaarden. Laat ze beoordelen door de adviseur en
  compliance voordat ze voor echt advies worden gebruikt.

- De lopende kosten en ISIN-codes in `universum.csv` zijn handmatig ingevuld en staan op
  `kosten_geverifieerd = nee`. Controleer ze tegen het actuele essentiële-informatiedocument van
  elk fonds voordat ze in een advies worden gebruikt.
- De kolom `startdatum` is nog leeg.
