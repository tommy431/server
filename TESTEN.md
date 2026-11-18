# Testhandleiding

Deze handleiding is voor wie het programma gaat testen. U installeert het op uw eigen computer,
richt het in en loopt de testscenario's door. Wat niet klopt, onduidelijk is of beter kan, meldt u
volgens het formulier onderaan.

**Gebruik in de testfase geen echte klantgegevens.** Verzin namen en bedragen.

## 1. Installeren

Nodig: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, Mac of Linux)
en de broncode van dit project. Alle opdrachten hieronder typt u in een terminal, in de map van het
project.

1. Maak de geheime sleutels aan en zet ze in `backend/.env`:

   ```bash
   docker build -t portefeuille .
   docker run --rm portefeuille python -m app.cli sleutels-maken > backend/.env
   ```

   Het bouwen duurt de eerste keer enkele minuten.

   **Windows (PowerShell):** gebruik voor de tweede regel

   ```powershell
   docker run --rm portefeuille python -m app.cli sleutels-maken | Out-File -Encoding ascii backend/.env
   ```

   Met `>` schrijft PowerShell het bestand in een codering die Docker niet leest.

2. Start de database en het programma:

   ```bash
   docker compose --profile app up -d
   ```

3. Maak twee beheerders aan. U kiest bij elk een wachtwoord van minstens 12 tekens:

   ```bash
   docker compose exec app python -m app.cli adviseur-aanmaken --email beheerder1@test.nl --naam "Eerste Beheerder" --rol beheerder
   ```

   ```bash
   docker compose exec app python -m app.cli adviseur-aanmaken --email beheerder2@test.nl --naam "Tweede Beheerder" --rol beheerder
   ```

   Twee beheerders zijn nodig vanwege het vier-ogenprincipe: een wijziging van de
   modelallocaties, de aannames of de ondernemingsgegevens gaat pas in als een tweede beheerder
   haar goedkeurt. Test u alleen, zet dan `VIER_OGEN=false` in `backend/.env` en herstart met
   `docker compose --profile app up -d`.

4. Laad de fondsenlijst en haal de koersen op (dit duurt een paar minuten):

   ```bash
   docker compose exec app python -m app.cli universum-laden
   ```

   ```bash
   docker compose exec app python -m app.cli data-verversen
   ```

5. Open http://localhost:8000 en log in.

**Stoppen** met `docker compose --profile app down`. De gegevens blijven bewaard; met
`docker compose --profile app up -d` gaat u verder waar u was. **Opnieuw beginnen** met een lege
database: `docker compose --profile app down -v` en daarna vanaf stap 2.

## 2. Eerste inrichting

1. **Tweestapsverificatie.** Een beheerder moet die eerst aanzetten, onder *Mijn account*. U heeft
   een authenticator-app op uw telefoon nodig (bijvoorbeeld Microsoft Authenticator of Google
   Authenticator). Wilt u dit tijdens het testen overslaan, zet dan
   `TWEESTAPS_VERPLICHT_BEHEERDER=false` in `backend/.env`.
2. **Onderneming.** Vul de gegevens van uw onderneming in. Zolang die ontbreken, is elk
   adviesrapport een concept met watermerk. Log daarna in als de tweede beheerder en keur het
   voorstel goed.
3. **Een adviseur.** Maak onder *Gebruikers* een account aan met de rol adviseur. Het tijdelijke
   wachtwoord ziet u eenmalig; de adviseur kiest bij de eerste keer inloggen een eigen wachtwoord.
4. **Lopende kosten.** Controleer onder *Data* de lopende kosten van de fondsen die u adviseert,
   tegen het essentiële-informatiedocument (EID) van het fonds, en klik op *Controleren*. Zolang een
   fonds in het advies niet gecontroleerd is, blijft het rapport een concept.
5. **Aannames.** De aannames voor het verwachte rendement zijn voorbeeldwaarden. Zolang ze niet
   vervangen zijn door aannames met een bron, blijft het rapport een concept. Voor het testen mag
   u ze laten staan.

## 3. Testscenario's

Werk de scenario's in volgorde af; ze bouwen op elkaar voort. Vink af wat klopt en meld wat niet
klopt.

### A. Klant en profiel (als adviseur)

- [ ] Maak een klant aan en leg een profiel vast: doel, horizon, inleg, maandelijkse storting en
      de vragenlijst. *Verwacht:* een afgeleid risicoprofiel met uitleg welke factor het bepaalt.
- [ ] Kies bewust een offensiever profiel dan afgeleid. *Verwacht:* dat mag niet. Een
      defensiever profiel mag wel, met een verplichte toelichting.
- [ ] Herzie het profiel later. *Verwacht:* een nieuwe versie; de oude blijft zichtbaar.

### B. Portefeuille en advies

- [ ] Open *Portefeuille samenstellen*. *Verwacht:* een startvoorstel dat binnen de bandbreedtes van
      het profiel past, met historische analyse, stresstest en scenario's.
- [ ] Pas gewichten aan, voeg een fonds toe en sluit een sector of regio uit. *Verwacht:* de
      verdeling, kosten, analyse en scenario's werken direct bij.
- [ ] Zet een categorie buiten de bandbreedte. *Verwacht:* vastleggen kan alleen met een
      toelichting.
- [ ] Vul de overige kosten in (bijvoorbeeld 0,5%) en leg de portefeuille vast. Download het rapport.
      *Verwacht:* een begrijpelijk rapport voor de klant; zonder ondernemingsgegevens met
      watermerk *Concept*.
- [ ] Geef een klant duurzaamheidswensen. *Verwacht:* bij het vastleggen vraagt het programma hoe
      u de fondsen daaraan hebt getoetst; zonder die toelichting blijft het rapport een concept.
- [ ] Lees het rapport als klant. Is het duidelijk, eerlijk over risico's en kosten, en vindt u de
      antwoorden op uw vragen?

### C. Opvolging

- [ ] Ga naar *Opvolging* en leg het werkelijke bezit vast, met handmatige aantallen. *Verwacht:*
      de waarde, de vergelijking met het advies en, als het afwijkt, een herbalanceringsvoorstel.
- [ ] Lees een depotoverzicht in (CSV-export van uw bank of broker). *Verwacht:* de fondsen en
      aantallen staan in het formulier, ter controle vóór het opslaan.
- [ ] Voeg overig bezit toe, bijvoorbeeld een los aandeel met ISIN en aantal. *Verwacht:* de actuele
      koers wordt opgehaald en omgerekend naar euro's. Vink *Behouden* aan en kijk wat er met het
      voorstel gebeurt.
- [ ] Leg een evaluatie vast. *Verwacht:* de volgende evaluatie staat twaalf maanden later.
- [ ] Bekijk *Signalen*. *Verwacht:* per klant wat aandacht vraagt, het dringendste bovenaan.

### D. Beheer (als beheerder)

- [ ] Wijzig een modelallocatie of de aannames. *Verwacht:* een voorstel dat pas ingaat na
      goedkeuring door de tweede beheerder; u kunt uw eigen voorstel niet goedkeuren.
- [ ] Draag de klanten van een adviseur over aan een ander en blokkeer daarna die adviseur.
- [ ] Controleer het logboek met *Keten controleren*. *Verwacht:* "Het logboek is ongewijzigd".
- [ ] Anonimiseer een gearchiveerde klant. *Verwacht:* naam en persoonlijke gegevens zijn weg, de
      cijfers van het advies blijven bewaard.

### E. Algemeen

- [ ] Gebruik het programma op een telefoon of smal venster. Is alles leesbaar en bruikbaar?
- [ ] Log vijf keer in met een verkeerd wachtwoord. *Verwacht:* tijdelijk geblokkeerd voor die
      combinatie van account en computer.
- [ ] Probeer de adresbalk te gebruiken om bij een klant van een andere adviseur te komen.
      *Verwacht:* "Klant niet gevonden".

## 4. Bekende beperkingen

- **Koersen** komen van Yahoo Finance, een onofficiële bron die alleen voor persoonlijk gebruik is
  toegestaan. Voor commercieel gebruik is een betaalde gegevensleverancier nodig.
- **Aannames** voor het verwachte rendement zijn voorbeeldwaarden zonder bron.
- **Lopende kosten** in de meegeleverde fondsenlijst zijn niet gecontroleerd; dat doet de
  beheerder zelf onder *Data*.
- Het programma verstuurt geen e-mail; een tijdelijk wachtwoord geeft u zelf door.
- Het herbalanceringsvoorstel rekent zonder transactiekosten, spreads en belastingen.
- Een fonds buiten de fondsenlijst kan niet in een advies worden opgenomen, alleen als overig
  bezit bij de opvolging.

## 5. Bevindingen melden

Meld per bevinding:

- **Waar:** het scherm of het hoofdstuk van het rapport.
- **Wat u deed:** de stappen, zo precies mogelijk.
- **Wat u verwachtte** en **wat er gebeurde.** Een schermafdruk helpt.
- **Ernst:** *blokkerend* (u kunt niet verder), *fout* (iets klopt niet), *onduidelijk* (u begrijpt
  het niet) of *wens* (het kan beter).
