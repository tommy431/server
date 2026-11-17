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
| 6 | Verwacht rendement (scenario's) | nog te bouwen |
| 7 | Rapportage | nog te bouwen |


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
  wordt gemeld welk fonds de historie beperkt. Koersen van vóór een onverklaarbare koerssprong
  van meer dan 20% worden niet gebruikt.
- De benchmark is de strategische asset allocatie van het risicoprofiel, met één breed fonds per
  categorie (`BENCHMARK_FONDSEN` in `backend/app/api/portefeuilles.py`). Het geldmarktfonds
  geldt als risicovrij rendement.
- Bij elke vastgelegde portefeuilleversie wordt de analyse bewaard zoals die toen was.

## Nog te controleren

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
