# GO_NO_GO_RECOMMENDATION: fomo 30 s-kopi (direktørordre 56, 2026-11-08)

**Anbefaling:**
- **GO for designet** (leveret).
- **NO-GO for dataindsamling nu.** Godkendelserne mangler, og der er en regelkonflikt.
- **Betinget GO for en 7-dages fremadrettet falsifikation,** når punkterne i afsnit 3 er opfyldt.
- **Live-handel: NO-GO uanset udfald.**

## 1. Kan mekanismen testes troværdigt?

**Ja, delvist.**
- **Kan testes:** følgerbenet. Det er 30 s-forsinkelse, puljefysik (x·y=k og bonding-kurve), TP 10× på MC, 7 t-tidsstop
  og omkostninger. Testen bruger en offentligt fastlåst lederliste og on-chain-data, som en tredjepart kan genberegne
  (signaturer og reserver).
- **Kan ikke testes:**
  - fomo's egne ledere, fills og gebyrer. Det kræver en konto og login, og det er forbudt.
  - betydningen af "7:00". Den er antaget som 7 t; en klokkeslæt-læsning er UKENDT.
  - om fomo følger lederens salg (UKENDT).
- Videoen selv er ikke evidens:
  - kontoen er SIM;
  - $72 → $720 er vist uden gebyr og slippage;
  - kontoen står kun på cirka +2 % siden indbetaling;
  - selv i reklamen kom botten 4,6 % dyrere ind end lederen.

## 1a. Simulatorens hovedfund (syntetisk, SYNTHETIC_EXECUTION_TESTS.md)

Videoens handel regnet med x·y=k og LEGACY_COPYBOT_FEES (SOL $150; graduated pulje; lederen køber 1 SOL; andre køber i
de 30 s; botten køber 0,48 SOL; senere når MC præcis 10× bottens indgang):

| Scenarie | Netto |
|---|---|
| Appens visning | +900 % |
| x·y=k uden gebyrer | +874,5 % |
| x·y=k + gebyrer | **+833,4 %** |

- Ved større ordrer falder nettoen: 2 SOL giver +768 %, 5 SOL +659 %, 10 SOL +527 % og 20 SOL +366 %.
- 30 s forsinkelse med andres køb i vinduet koster meget. I eksempel A kræver følgeren et 16,5× prisløft for netto 10×,
  mens lederen kun kræver 11,5×.
- **Konklusion:** gebyrer og slippage dræber ikke en lille handel, der faktisk når 10×. Det afgørende er, **hvor ofte**
  10× nås efter 30 s (TP-raten, break-even 4,5–8,6 %). Det kan kun data svare på, ikke simulatoren.
- POWER_AND_FEASIBILITY.md bruger +850 % netto ved TP. Simulatoren giver +833 % ved 0,48 SOL. Forskellen ændrer ikke
  break-even nævneværdigt (p\* ved L −60 % er 6,6–6,7 %).

## 2. Hvad 7 dage kan bevise

| Sandt scenarie | Sandsynligt udfald med cirka 140 signaler |
|---|---|
| Kopien taber klart (TP-rate ≤ 3 %, resten ≈ −60 % eller værre) | FALSIFIED_UNDER_TESTED_CONDITIONS med sandsynlighed 0,6–1,0 |
| Tæt på break-even (TP-rate 5–8 %) | INCONCLUSIVE næsten altid |
| Kopien vinder stort (TP-rate ≥ 12 %) | PRELIMINARY_POSITIVE med sandsynlighed 0,3–0,9, aldrig VALIDATED_ALPHA |
| Videoens 4 ledere i stedet for 20 | INSUFFICIENT_DATA (cirka 7–28 signaler) |

- 7 dage kan **afvise** påstanden under de testede betingelser: én uge, ét markedsklima og én lederliste.
- 7 dage kan **ikke** bevise, at den virker.
- **Forudgående evidens:** lab'et testede samme video-mekanisme 15.–16.10 (FORSKNING.md, `8d40c9e`).
  - −15,1 % pr. handel ved 10 s.
  - Selv 0 s og 0 gebyrer gav −6,5 %.
  - Selvfundne vindertradere kopieret 2 s efter gav −7,1 %, og 10 s efter gav −18,8 %.
  - 30 s er strengere end alle disse.
- **Forventning:** FALSIFIED.

## 2a. Falsificerer oktober-resultaterne allerede påstanden? (ordre 57 P0)

Oktober-forsøgene er **historisk evidens**. De er ikke det nye forward-forsøg i protokollen, og de skal holdes adskilt
fra det.

| Spørgsmål | Svar |
|---|---|
| Samme mekanisme? | Ja: kopiér memecoin-ledere på Solana, efter forsinkelse og med omkostninger. Forskellene: 10 s (ikke 30 s); 40 % stop-loss og 24 t max hold (ikke TP 10× og 7 t); kolscan-KOL'er (ikke fomo-ledere) |
| Forudregistreret? | **Nej.** L01 og L02 var eksplorative (`NEXT_MECHANISMS.md` tabel 1, registret: "tested but no trials/alpha rows"). Kun L11 smart_v2 var forudregistreret med holdout, og den er en anden mekanisme |
| Interval? | Kan ikke beregnes. Data pr. handel ligger ikke i git; kun summer (114 handler, −15,1 %/handel, profit factor 0,33, 18 % vindere). Et formelt FALSIFIED kræver øvre CI ≤ 0, og det kan ikke dokumenteres efterfølgende |
| Konklusion | Under oktober-betingelserne (10 s, stop-loss, KOL-ledere) er kopien **negativ pr. handel i alle 10 varianter** (én variant var +$36 i uge 1, men −$337 i uge 2). Det er stærk, men ikke formel, evidens. Den falsificerer **ikke** formelt 30 s med TP 10× og 7 t. Exitreglen er anderledes, og TP 10× kan i princippet ændre fortegnet, hvis TP-raten er ≥ 4,5–8,6 % (POWER_AND_FEASIBILITY.md) |

Oktober-resultatet bruges derfor til at sætte forventningen (FALSIFIED) og prioriteten (lav). Det bruges ikke som
afgørelse.

## 3. Manglende godkendelser (ingen af dem kan Claude give)

1. **Værter:**
   - ejer-ja og en dateret PROTOCOL_V3-ændring for `solana.publicnode.com` (≤ 2 kald/s) og
     `api.mainnet-beta.solana.com` (≤ 1 kald/s, failover);
   - `api.geckoterminal.com` kun som krydstjek;
   - optagelse i `ALLOWED_HOSTS`.
2. **Regelkonflikten POST/GET:** Solana JSON-RPC kræver POST med body, men lab'ets sikkerhedstest tillader kun GET, og
   kun én body-afsender til Hyperliquid. Ejeren skal udtrykkeligt beslutte en snæver undtagelse: read-only-metoderne
   `getSignaturesForAddress`, `getTransaction`, `getMultipleAccounts` og `getSlot`, ingen signering og ingen
   `sendTransaction`. Indtil da gælder den strengeste regel.
3. **Ny stream/collector:** en separat proces uden fælles kode, budget eller unit med pm_lp. Ordre 54/55 kræver
   godkendelse af nye streams.
4. **Lederkilde:** et kolscan-billede gemt af ejeren selv og committet med hash før dag 1, eller ja til on-chain-
   kriterier.
5. **Godkendelsesniveau:**
   - Forsøget er beskrivende og falsificerende med alfa 0 og kan ikke give alfa.
   - Direktøren skal afgøre, om et dateret ejer-ja (UNVERIFIED_ORIGIN) er nok til værter og stream, eller om det
     kræver VERIFIED_OWNER_APPROVAL (ordre 53/54-A).
   - Indtil det er afgjort, gælder den strengeste fortolkning.

## 4. Hurtigste tilladte vej

1. **Nu, uden nye værter:** intet mere. Designet, simulatoren og styrken er klar, og den eneste lovlige evidens er
   lab'ets egne oktober-resultater, som allerede peger på FALSIFIED.
2. **Når punkterne 1–5 er godkendt:**
   - skriv collectoren (fremadrettet, polling, ingen websocket) med tests og en grøn suite;
   - lås protokollen med hash og commit lederlisten;
   - deploy uden for K1–K3, uden genstart af PC'en og uden at røre pm_lp;
   - kør 7 dage plus 7 t med rapporter dag 1/3 (beskrivende) og afgørelse dag 7.
3. **Tidligst:**
   - Fremadrettet indsamling er ikke en historisk forespørgsel, så 14/11-gaten blokerer den ikke.
   - Den afhænger kun af godkendelserne og af, at DNS-filtret tillader værterne. Det testes ikke af Claude.
   - Med godkendelse i dag kunne afgørelsen ligge cirka 8–9 dage efter start.

## 5. Prioritet

**Lav.** Informationsværdien er lille, fordi lab'ets egne data allerede har falsificeret varianter med kortere
forsinkelse. Et ja koster nye værter, en ny undtagelse fra sikkerhedsreglerne og en ny proces på en maskin, der har
haft 5 urene stop. Anbefalingen er at bruge W0-alfa og driftstid på igangværende spor (HFC-1 14 d 19/11, STRAKS 12/11,
S1 20/11). Fomo-testen kan tages, hvis ejeren udtrykkeligt ønsker en endelig afvisning på friske data.

Leverancer:
- `FOMO_COPY_30S_PROTOCOL_DRAFT.md`
- `DATA_SOURCE_APPROVAL_MATRIX.md`
- `SYNTHETIC_EXECUTION_TESTS.md` (+ `sim.py`, `tests/test_research_desk_fomo_sim.py`)
- `POWER_AND_FEASIBILITY.md` (+ `power.py`, `tests/test_research_desk_fomo_power.py`)
- denne fil
