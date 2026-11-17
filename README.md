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
| 8 | Opvolging: werkelijk bezit, herbalanceren, signalen en evaluaties | klaar |


## Starten

Vereist: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ en Docker (voor PostgreSQL).

```bash
docker compose up -d
cd backend
cp ../.env.example .env        # vul JWT_GEHEIM en VERSLEUTELSLEUTEL in
uv sync
uv run alembic upgrade head
uv run python -m app.cli adviseur-aanmaken --email jij@voorbeeld.nl --naam "Jouw Naam" --rol beheerder
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

Tests:

- Backend: `cd backend && uv run pytest` (SQLite in het geheugen; zet `TEST_DATABASE_URL` om tegen
  PostgreSQL te testen).
- Browsertests: `cd frontend && npm run e2e`. Start zelf de server en de schermen tegen een aparte
  SQLite-testdatabase (`backend/e2e-test.db`) met gegenereerde koersen; er is geen internet of
  PostgreSQL nodig. Eenmalig: `npx playwright install chromium`, of wijs met `CHROMIUM_PAD` een
  bestaande Chromium aan.

## Productie

- `backend/app/productie.py` levert de API onder `/api` en de gebouwde schermen op één poort,
  met beveiligingsheaders (Content-Security-Policy, HSTS, geen framing) en zonder openbare
  API-documentatie. Zet er een proxy met HTTPS voor.
- Docker: `docker build -t portefeuille .` en daarna
  `docker run -p 8000:8000 --env-file backend/.env portefeuille`. De container migreert de
  database bij het starten en draait niet als root.
- Verplicht: `DATABASE_URL`, `JWT_GEHEIM` (minstens 32 tekens) en `VERSLEUTELSLEUTEL`; de server
  weigert te starten met een zwak of ongeldig geheim.
- Zet `FORWARDED_ALLOW_IPS` op het IP-adres van de proxy (standaard alleen `127.0.0.1`). Alleen
  dan gebruikt de server het echte IP-adres van de bezoeker voor de inlog- en verzoeklimieten,
  zonder dat iemand een vals adres kan meesturen.

## Beveiliging tegen misbruik

- Na 5 mislukte inlogpogingen in 15 minuten wordt de combinatie van IP-adres en account
  geblokkeerd. Een aanvaller elders kan de gebruiker dus niet buitensluiten.
- Een IP-adres met 20 mislukte pogingen, over alle accounts samen, wordt geblokkeerd.
- Alleen bij een grootschalige aanval (50 mislukte pogingen op één account vanaf veel adressen)
  gaat dat account tijdelijk dicht.
- Algemene limiet van 1200 verzoeken per minuut per IP-adres (`LIMIET_VERZOEKEN_PER_MINUUT`).
  Deze teller staat in het geheugen van elk serverproces; bij meerdere processen geldt hij per
  proces.
- Maak dagelijks een back-up van de database, en bewaar de `VERSLEUTELSLEUTEL` apart en veilig:
  zonder die sleutel zijn klantgegevens en rapporten in de back-up onleesbaar.

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

Bij elke vastgelegde portefeuilleversie kan een adviesrapport (PDF) worden opgesteld, geschreven
voor de klant:

- **In het kort** op de eerste pagina: het advies, de haalbaarheid van het doel, de bandbreedte van
  de uitkomsten, het verlies in een slecht jaar en de kosten in euro's.
- **Hoofdstukken:** situatie en wensen (scores in woorden), het advies met per fonds waarin het
  belegt, waarom het past (inclusief nadelen), kosten, uw doel met wat helpt om het te halen,
  wat er mis kan gaan (toegesneden op de portefeuille), resultaten uit het verleden en volgende
  stappen.
- **Bijlagen:** begrippenlijst en technische toelichting (volatiliteit, Sharpe-ratio, aannames,
  ISIN's, verantwoording).
- **Wat helpt:** bij vastleggen worden vergelijkingen berekend en bewaard: de maandelijkse storting
  voor 50% en 75% kans op het doel, vijf jaar langer beleggen, het profiel uit de vragenlijst en
  één profiel defensiever.
- **Concept of definitief:** zolang er voorbeeldaannames, ongecontroleerde fondskosten of
  ongetoetste duurzaamheidswensen zijn, is het rapport een concept met watermerk. De redenen staan
  in het klantscherm, niet in de PDF.
- Elk rapport wordt versleuteld bewaard met datum, opsteller, status en SHA-256-vingerafdruk, en is
  een momentopname van de versie.
- Het lettertype DejaVu Sans staat in `backend/app/lettertypen` (vrije licentie, zie
  `LICENTIE-DejaVu.txt`).

## Opvolging na het advies

Via **Opvolging** bij een klant, en het overzicht **Signalen** in het menu.

- **Werkelijk bezit:** de adviseur neemt de aantallen stukken en het geldsaldo over van het
  depotoverzicht van de klant, met een peildatum. Elke opgave is een nieuwe versie. De waarde wordt
  berekend tegen de laatst bekende slotkoers (euro-fondsen).
- **Vergelijking met het advies:** per fonds het werkelijke gewicht naast het geadviseerde, en per
  beleggingscategorie het gewicht tegen de bandbreedtes van de laatst vastgelegde portefeuilleversie.
- **Herbalanceringsvoorstel:** terug naar de gewichten van het advies, in hele stukken. Eerst
  verkopen (fondsen buiten het advies helemaal), dan kopen met het geldsaldo en de opbrengst; bij te
  weinig geld worden de aankopen naar rato verkleind. Afwijkingen onder € 250 blijven staan.
  Transactiekosten, spreads en belastingen zijn niet meegerekend: het is een hulpmiddel, geen order.
- **Evaluaties:** datum, uitkomst en een versleutelde notitie. De volgende evaluatie is twaalf
  maanden na het laatste advies of de laatste evaluatie.
- **Signalen**, de meest dringende eerst: evaluatie verlopen of binnen een maand, profiel herzien na
  het advies, categorie buiten de bandbreedte, fonds in bezit maar niet in het advies, een afwijking
  per fonds van meer dan 5 procentpunt, geen koers, bezit ouder dan drie maanden, of nog geen
  profiel, advies of bezit.
- Vastleggen van bezit en evaluaties komt in het logboek.

## Rollen en vier-ogenprincipe

- Er zijn twee rollen: **adviseur** en **beheerder**. Iedereen kan modelallocaties en aannames
  inzien; alleen een beheerder kan ze wijzigen, en alleen een beheerder kan de fondslijst en
  koersbestanden importeren.
- Een wijziging van modelallocaties of aannames is eerst een **voorstel**. Een tweede beheerder
  keurt het goed of wijst het af (met reden); de indiener kan het intrekken. Alle stappen staan in
  het logboek.
- Is er maar één beheerder, zet dan `VIER_OGEN=false`; wijzigingen worden dan direct doorgevoerd.
- Iemand beheerder maken, of een beheerder blokkeren of adviseur maken, gaat via een voorstel in het
  scherm Gebruikers. Er blijven altijd minstens twee actieve beheerders over (één zonder
  vier-ogenprincipe).
- Beheerders kunnen adviseurs aanmaken (met een tijdelijk wachtwoord dat bij de eerste keer
  inloggen moet worden vervangen), blokkeren en hun wachtwoord of tweestapsverificatie resetten.
  Voor een beheerder kan dat alleen op de server: `uv run python -m app.cli tweestaps-resetten
  --email ...`, zodat niemand via een reset de rol van een andere beheerder kan overnemen.
- De eerste beheerder maakt u op de server aan:
  `uv run python -m app.cli adviseur-aanmaken --email ... --naam ... --rol beheerder`.

## Inloggen en tweestapsverificatie

- Tweestapsverificatie met een authenticator-app (bijvoorbeeld Google of Microsoft
  Authenticator), in te stellen onder Mijn account. Voor beheerders verplicht om beheertaken te
  doen (`TWEESTAPS_VERPLICHT_BEHEERDER`, standaard aan). Een code kan maar één keer worden
  gebruikt; foute codes tellen mee voor de blokkade na vijf mislukte pogingen.
- Na een wachtwoordwijziging, reset of blokkade worden bestaande sessies van dat account ongeldig.

## Logboek

- Alle wijzigingen en inlogpogingen staan in het logboek. Elke regel bevat een SHA-256-vingerafdruk
  van zichzelf en van de vorige regel; achteraf wijzigen, invoegen of verwijderen verbreekt de keten.
- Controleren: in het scherm Logboek (beheerders) of op de server met
  `uv run python -m app.cli logboek-controleren`.
- Bewaar de laatste vingerafdruk regelmatig buiten het systeem (bijvoorbeeld maandelijks per
  e-mail). Iemand met volledige toegang tot de database kan de keten anders in theorie helemaal
  opnieuw opbouwen.

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
