# Portefeuille op maat

Webapplicatie waarmee een beleggingsadviseur een portefeuille op maat samenstelt voor een klant.

## Stand van zaken

| Stap | Onderdeel | Status |
|---|---|---|
| 1 | Fundament: server, database, inloggen, logboek | klaar |
| 2 | Data: ETF-lijst, koersbronnen, kwaliteitscontroles | klaar |
| 3 | Klantprofiel en risicoprofiel | nog te bouwen |
| 4 | Portefeuilleconstructie | nog te bouwen |
| 5 | Historische analyse | nog te bouwen |
| 6 | Verwacht rendement (scenario's) | nog te bouwen |
| 7 | Rapportage | nog te bouwen |

Er is nog geen gebruikersinterface; de server is te bedienen via de API (`/docs`).

## Starten

Vereist: Python 3.12+, [uv](https://docs.astral.sh/uv/) en Docker (voor PostgreSQL).

```bash
docker compose up -d
cd backend
cp ../.env.example .env        # vul JWT_GEHEIM in
uv sync
uv run alembic upgrade head
uv run python -m app.cli adviseur-aanmaken --email jij@voorbeeld.nl --naam "Jouw Naam"
uv run python -m app.cli universum-laden
uv run python -m app.cli data-verversen
uv run uvicorn app.main:app --reload
```

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

## Nog te controleren

- De lopende kosten en ISIN-codes in `universum.csv` zijn handmatig ingevuld en staan op
  `kosten_geverifieerd = nee`. Controleer ze tegen het actuele essentiële-informatiedocument van
  elk fonds voordat ze in een advies worden gebruikt.
- De kolom `startdatum` is nog leeg.
