# FOMO_COPY_30S_PROTOCOL_DRAFT (direktørordre 56 P0/P3/P4, udkast 2026-11-08)

**Status:**
- DRAFT. Kun design.
- DATA COLLECTION NOT AUTHORIZED. LIVE TRADING NO-GO.
- Ikke låst og ikke godkendt.
- Ingen alfa. Forsøget kan aldrig give VALIDATED_ALPHA.

Udkastet fryser påstanden, før der findes data. Ændres den efter dataadgang, bliver det et nyt forsøg med ny version og
hash.

## 1. Påstanden, ordret fra videoen (frosset)

Kilde: TikTok @trading.calls, appen "fomo". Billederne er gennemgået enkeltvis i sessionen; videoen er ikke i repo'et.

| Element | Hvad videoen viser | Status |
|---|---|---|
| Ledere | "copying 4 traders", "4 traders · 30s → Grok Bot"; ledere er fomo-brugere (fx aiwass, panceramic) | observeret |
| Forsinkelse | "30s behind", "Grok Bot copied · 30s later"; ét kort viser "AI in 26s" | observeret; 30 s er påstanden |
| Exit | Risikokortet: "TP 10× · 7:00" | TP 10× observeret; "7:00" forklares ikke |
| Eksempelhandel | Leder køber ved MC $47,6K kl. 12:19, botten 30 s senere ved $49,8K (+4,6 % dyrere). Solgt "10× take profit" kl. 3:39: $72,00 ind → $720,00 ud (+900,0 %) | observeret |
| Følger botten lederens salg? | "aiwass still holding · rule kept" efter bottens TP | botten exitter selv; om den følger salg er UKENDT |
| Konto | "SIM"; "$245.53, +$5.73 (+2%) since deposit"; et andet billede "$243.70, +$0.00 24h" | observeret: simuleret konto, cirka +2 % i alt |
| Gebyrer | ingen vist; $72 → præcis $720 betyder 0 gebyr og 0 slippage i visningen | UKENDT (botgebyr, DEX-gebyr, prioritetsgebyr) |

**"7:00":**
- Den viste handel var åben fra 12:19 til 3:39, dvs. 3 t 20 min. "7 minutter" er derfor udelukket som tidsstop for den
  handel.
- **Antagelse A (primær):** tidsstop 7 t 00 min efter følgerens indgang. Antagelsen er fastsat her, før data.
- **Antagelse B:** et klokkeslæt (07:00 i en ukendt tidszone). Den er UKENDT og testes ikke.
- Hvis ejeren eller direktøren dokumenterer en anden betydning, før dataadgang, laves en ny version. Efter dataadgang
  må tidsstoppet ikke ændres.

**Det testes ikke:**
- fomo-appens egne ledere, fills og gebyrer. Det kræver en konto og login, og det er forbudt.
- Videoens resultat i sig selv. Det er SIM og en udvalgt handel.

Det, der testes, er **mekanismen:** at kopiere offentligt kendte memecoin-ledere på Solana 30 s efter deres køb med TP 10×
og 7 t-tidsstop, efter realistiske omkostninger.

## 2. Forudgående evidens (lab'ets egne resultater, okt. 2026)

Kilde: `git show 8d40c9e:copybot/FORSKNING.md`. Det var præcis samme video-mekanisme (Grok Bot/CopyFomo).

| Test | Data | Resultat |
|---|---|---|
| L01: kopiér 8 kolscan-KOL-wallets, 10 s forsinkelse | 14 dage, 114 handler | **−15,1 %/handel**; 0 s: −14,1 %; 0 s og ingen gebyrer: −6,5 %; profit factor 0,33; hver wallet tabte som kopi; rangkorrelation uge 1→2: +0,09 |
| L01: videoens regel (2 tab → næste wallet) | 14 dage | $50 → $35,25 (−29,5 %), 0 % vindere |
| L02: selvfundne tradere (vinder selv: +23,9 %/handel i uge 2) | 98 tradere | kopi 2 s efter: **−7,1 %**; 10 s efter: **−18,8 %** |
| L11 smart_v2: tidlige køberes historik (forudregistreret holdout) | 1.200 graduations | holdout −4,7 til −25,6 % |
| L04: køb ved graduation | 443 | 60 min median −95 % |

- Lederen tjener, kopien taber. Fordelen ligger i hastighed og ses ikke ved 2–10 s, endnu mindre ved 30 s.
- Leaderboard-udvalgte wallets var valgt efter sejre. Det gjorde backtesten for optimistisk, og den tabte alligevel.

**Forudregistreret forventning (før data):** FALSIFIED_UNDER_TESTED_CONDITIONS eller INCONCLUSIVE. En positiv
forventning har ingen støtte.

## 3. Lederregel (fastsat før data)

- **Kilde:** et øjebliksbillede af kolscan.io's månedlige leaderboard.
  - Ejeren gemmer det selv; assistenten scraper ikke uden en værtsgodkendelse.
  - Det committes med sha256 **før** første observationsdag.
  - Alternativ: rene on-chain-kriterier, fastsat og committet før data.
- **Udvælgelse:**
  - de øverste 20 efter månedlig PnL på billedets tidspunkt, der opfylder alle tre krav:
    - 30–600 handler pr. måned;
    - mindst 45 % vindere;
    - højst 5.000 transaktioner pr. 14 dage (botfilter, som L01/L02);
  - lederlisten fryses for hele vinduet;
  - en leder fyres aldrig undervejs (videoens "2 tab → næste" var L01's −29,5 %; det er ikke den primære regel).
- **Signal:** hvert første køb af en mint, som en leder laver i signalvinduet.
  - Alle lederkøb registreres, også dem uden signal.
  - Gentagne køb af samme mint fra samme leder, mens følgerens position er åben, giver intet nyt signal.
  - Flere lederes køb af samme mint giver hver sit signal, men de klynges på mint i statistikken (afsnit 6).
- **Ingen filtre på likviditet, alder eller marketcap.** Videoen har ingen. Illikvide fills bliver NOT_EXECUTABLE og
  tælles som tab, jf. afsnit 5.

## 4. Følgerregel (videoens påstand, må ikke optimeres)

| Parameter | Værdi | Kilde |
|---|---|---|
| Forsinkelse | 30 s efter lederens købs blockTime | video |
| Størrelse | 0,25 SOL pr. signal, fast | video viser $38–72; fast for hele forsøget |
| Indgang | eksekverbart købsquote mod puljens tilstand ved t_leder + 30 s, efter alle swaps i mellemtiden, også lederens eget køb | fysik |
| TP | udløses, når spotprisen (MC) ≥ 10 × følgerens indgangsspotpris; fyldes til det eksekverbare salgsquote for hele positionen ved første tilstand på eller efter udløsningen | video (TP på MC) + fysik |
| Tidsstop | 7 t efter følgerens indgang; salg til det eksekverbare quote | antagelse A |
| Stop-loss | ingen | video viser kun TP og tid |
| Følger lederens salg | nej (primær) | "aiwass still holding · rule kept" |
| Slippage-tolerance | 15 %: et køb, hvis realiserede pris er mere end 15 % over quoten på signaltidspunktet, er NOT_EXECUTABLE | ANTAGELSE; fomo's indstilling er UKENDT |
| Omkostninger (primær) | LEGACY_COPYBOT_FEES: DEX 0,5 %, bot 1,0 %, MEV 0,5 % pr. side, netværk 0,0015 SOL pr. transaktion | lab'ets tidligere scenarie; fomo's gebyr er UKENDT |

**Faste regler:**
- TP, tidsstop, forsinkelse, størrelse og gebyrscenarie er låst.
- Følsomhedsberegninger er udelukkende DIAGNOSTIC_ONLY og ændrer aldrig klassifikationen:
  - forsinkelse 0/10 s;
  - TP udløst på eksekverbart quote;
  - botgebyr 0/2 %.

## 5. Udfald pr. signal (intet slettes)

Hvert signal får præcis én række. Der er seks mulige udfald:

| Udfald | Hvornår | Hvordan det tæller |
|---|---|---|
| TP_10X | TP udløst og fyldt | med det realiserede beløb |
| TIME_STOP | tidsstoppet nås | med det realiserede beløb |
| RUG / POOL_DEAD | puljen dør eller tømmes | værdien af et eksekverbart salg, ofte ≈ −100 % |
| NOT_EXECUTABLE | indgangen ligger uden for slippage-tolerancen | se nedenfor |
| MISSING_PRICE | der mangler pristilstand | se nedenfor |
| DATA_MISSING | kildesvigt, fx DNS-blokering eller 429 | se nedenfor |

- **NOT_EXECUTABLE** tæller i primæranalysen som 0 % netto minus netværksgebyr, dvs. et mislykket køb. Andelen
  rapporteres. Hvis andelen er over 20 %, markeres resultatet "ikke repræsentativt for videoens fills".
- **MISSING_PRICE:** der interpoleres ikke. Exit sker ved næste tilgængelige tilstand. Findes ingen, tæller handlen som
  −100 %.
- **DATA_MISSING** er markedsuafhængigt. Rækken bevares og rapporteres. Mere end 20 % DATA_MISSING giver
  INSUFFICIENT_DATA.

Puljetilstanden (reserver) rekonstrueres fra on-chain-transaktioner, så en tredjepart kan genberegne den. Priser fra
aggregatorer bruges kun som krydstjek, aldrig til fills.

## 6. Endepunkter og afgørelse (forudregistreret)

**Primært endepunkt:** gennemsnitligt nettoafkast pr. signal for følgeren, i procent af den SOL, der er sat ind, efter
alle omkostninger.

- **Interval:** 95 % klyngebootstrap på mint, percentilmetoden, B = 10.000, seed 56.
- **Sekundære endepunkter** (påvirker ikke afgørelsen):
  - forskellen mellem leder og følger, pr. signal og samlet. Lederens realiserede afkast er hans eget salg, eller
    mark-to-quote ved vinduets slutning, hvis han ikke har solgt;
  - TP-ramningsrate;
  - median;
  - netto uden de 3 bedste handler;
  - netto i hver halvdel (dag 1–3 og dag 4–7).

**Afgørelse, kun på dag 7:**

| Klasse | Betingelse |
|---|---|
| INSUFFICIENT_DATA | færre end 30 signaler med udfald, eller mere end 20 % DATA_MISSING |
| FALSIFIED_UNDER_TESTED_CONDITIONS | øvre 95 %-grænse ≤ 0 |
| PRELIMINARY_POSITIVE | nedre 95 %-grænse > 0 **og** positiv uden de 3 bedste **og** positiv i begge halvdele. Aldrig VALIDATED_ALPHA, aldrig grundlag for rigtige penge |
| INCONCLUSIVE | alt andet |

**Regler for vinduet:**
- Ingen tidlig stop på profit og ingen tidlig stop på tab.
- Forsøget afbrydes kun ved et sikkerhedsbrud eller et kildesvigt. Det giver INSUFFICIENT_DATA med årsag.
- Dag 1- og dag 3-rapporter er beskrivende og indeholder ingen afgørelse.

## 7. Syv-dages-plan (først efter godkendt start)

| Dag | Indhold |
|---|---|
| 0 | Designet er gjort (denne ordre). Bagefter skal der foreligge ejer-ja til værter og stream (se DATA_SOURCE_APPROVAL_MATRIX.md og GO_NO_GO_RECOMMENDATION.md), protokollen skal låses med hash, og lederlisten committes med hash. |
| 1–7 | Signalvinduet er 7 × 24 t. Observationen fortsætter 7 t efter sidste signal, så alle tidsstop når at lukke. |
| 1, 3 | Beskrivende rapport: antal signaler, udfaldsfordeling, dækning, DATA_MISSING. Ingen afgørelse. |
| 7 + 7 t | Afgørelse efter afsnit 6, commit og rapport til direktøren. |

Simulatoren til trin 5 og 6 er testet syntetisk (SYNTHETIC_EXECUTION_TESTS.md). Styrken står i POWER_AND_FEASIBILITY.md.

## 8. Beskyttelse af laboratoriet

- pm_lp, S7, F2, BIOS og DNS røres ikke.
- DNS-filtre omgås ikke.
- Ingen nøgler, ingen konti og ingen fomo-login.
- Ingen historiske forespørgsler før 14/11. Ingen genstart før 27/11.
- Deploy aldrig i K1–K3.
- En eventuel collector skal være en separat proces, der ikke deler noget med pm_lp's collector eller dens budget.
