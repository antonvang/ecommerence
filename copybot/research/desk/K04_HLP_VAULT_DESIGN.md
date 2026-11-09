# K04 HLP-vault som pooled maker mod 3-måneders T-bill: design (direktørordre 61, arbejdsspor 4)

Skrevet 2026-11-09 (ca. 12:10–13:30 UTC). **Kun design. Ingen kapitalallokering.**

- Ingen data er hentet. Ingen kald til Hyperliquid `/info` eller andre API'er, selv om værten er tilladt. Ingen
  streams, lås, alfa, nøgler eller handel.
- `python3 -m lab` er ikke kørt. lab.db er ikke åbnet. N4-filen og karantænemappen er ikke læst.
- Web er kun brugt til dokumentation og artikler (Hyperliquid-docs, The Block, Arkham, CoinGecko, eco.com,
  tradingstrategy.ai). `hyperliquid.gitbook.io` svarer normalt i den lokale DNS (`getent hosts`, 2026-11-09 12:10 UTC).
- `earnpark.com` blev omdirigeret af DNS-filteret (joindns4.eu-certifikat). Siden er ikke åbnet, og filteret er ikke
  omgået. Tal derfra står som **UNVERIFIED**.
- Mærker: **DOK** = læst i officiel dokumentation i dag. **ART** = læst i en artikel i dag (sekundær kilde).
  **UNVERIFIED** = ikke bekræftet. **ANTAGELSE** = eget skøn.
- Dette er ikke en låsetekst. HLP1-skitsen og PKT-HLP1 i `PROFIT_SEARCH_2026-11-09.md` (linje 128–152) er stadig kun
  illustrative.

## 0. Konklusion først

| Spørgsmål | Svar |
|---|---|
| Hvad er K04? | En målehypotese: slår HLP-vaultens afkast den risikofri rente (DTB3) fremad? HLP laver market making og backstop-likvidationer på Hyperliquid og får en del af gebyrerne (DOK). |
| Kan lab'et teste det ærligt? | Ja, teknisk. Én `vaultDetails`-POST pr. døgn gennem den eksisterende HL-afsender giver vaultens egen PnL og egenkapital. |
| Kan testen give en dom? | **Næsten ikke.** Ved σ_d 20 bp (ANTAGELSE) er MDE ca. 17–22 % p.a. over T-bill på 182 døgn. Styrken mod et realistisk merafkast på 6 % p.a. er ca. 0,08. PROFIT_SEARCH's 0,41 er for optimistisk (afsnit 8). |
| Halerisiko | Dokumenteret: ETH-hval 03-2025 (ca. −$4 mio.), JELLY 03-2025 (op til ca. −$12–13,5 mio. urealiseret, reddet af en validator-afstemning), POPCAT 11-2025 (ca. −$4,9 mio.). 6–12 måneder kan ikke prisfastsætte den. |
| Anbefaling | **NO-GO for alfa og for en bekræftende test.** En beskrivende log (α = 0) er billig, men giver ikke et profit-bevis. Den parkeres og startes kun på ejerens eksplicitte, daterede ja. Afsnit 11. |

**Ingen kapitalallokering.** Intet i denne note er en anbefaling om at indskyde penge i HLP. Lab'et indskyder
aldrig, og en "hypotetisk indskyder" er kun en regnestørrelse.

## 1. Hypotese, falsifikation, enhed og endpoint

### 1.1 Hypotese H-HLP1 (falsificerbar)

> HLP's tidsvægtede daglige afkast, målt fremad på vault-niveau fra Hyperliquids egne tal og fratrukket en
> hypotetisk indskyders ind- og udbetalingsomkostning, er i middel **større end DTB3-renten** over de samme døgn.

### 1.2 Falsifikation

| Udfald | Regel |
|---|---|
| FALSIFIED | Middel af det daglige merafkast er ≤ 0 ved slutningen (punktestimat). |
| PASS (kun bekræftende fase B) | Ensidet Newey-West-t over merafkastet ≥ 2,24 (α_F 0,0125). |
| INCONCLUSIVE | Middel > 0, men t < 2,24. Det er det mest sandsynlige udfald (afsnit 8). |
| KILL_TAIL | En stopregel i afsnit 9 udløses. Rapporteres som halehændelse, ikke som et nej til middelafkastet. |
| INVALID | Datadækning under kravet i afsnit 9. Datatab er ikke et nej. |

### 1.3 Definitioner

| Begreb | Definition |
|---|---|
| Vault | HLP's moder-vault `0xdfc24b077bc1425ad1dea75bcb6f8158e10df303` (ART: tradingstrategy.ai, CoinGecko; DOK bruger adressen som eksempel i `userVaultEquities`). Kontrolleres igen i dokumentationen før låsen. |
| Snapshot | Ét svar på `{"type": "vaultDetails", "vaultAddress": <HLP>}` kl. 00:05 UTC (± 10 min). |
| **Enhed** | Ét UTC-døgn d med et gyldigt snapshot i begge ender. |
| Dagens PnL | ΔPnL_d = sidste punkt i `portfolio["day"].pnlHistory` minus første punkt i samme bucket. Kun punkter med tidsstempel ≥ låsetidspunktet og ≥ nu − 26 t bruges (afsnit 6). |
| Egenkapital | A_d = første punkt i `portfolio["day"].accountValueHistory` (start af døgnet). |
| Dagsafkast | r_d = ΔPnL_d / A_d. PnL er uafhængig af ind- og udbetalinger, så r_d er tidsvægtet. Det er en tilnærmelse: strømme midt i døgnet flytter nævneren lidt. |
| Risikofri dagsrente | rf_d = ln(1 + i_d) / 365, hvor i_d er DTB3 omregnet fra diskontobasis til investeringsrente: i = 365·d / (360 − d·91). Ved d = 3,75 % er i = 3,84 % (egen regning). Følsomhed: DTB3 uomregnet som ændring 42 punkt 5. |
| **Primært endpoint** | e_d = ln(1 + r_d) − rf_d. Middel af e_d over alle gyldige døgn. |
| Hypotetisk indskyder | 10.000 USDC på papir, ind på dag 0, ud på sidste dag. Omkostning c = 2 USDC i alt (ANTAGELSE: bro og gas; HL's udbetalingsgebyr er UNVERIFIED), fordelt jævnt over døgnene. |

### 1.4 Sekundære endpoints (afgør intet)

| Endpoint | Formel |
|---|---|
| E2 kumulativt merafkast | Σ e_d i procent |
| E3 største fald | Største fald i indekset Π(1 + r_d) fra en tidligere top |
| E4 værste døgn og CVaR 5 % | Laveste r_d; middel af de 5 % laveste |
| E5 beta til BTC | OLS af r_d på BTC's daglige log-afkast (lab'ets egen `mark` for BTCUSDT, kun rækker efter låsen) |
| E6 annonceret APR | Feltet `apr` logges, men bruges aldrig til en dom (afsnit 2.3) |
| E7 TVL-strøm | Ændring i A_d minus ΔPnL_d (ind- og udbetalinger netto) |

## 2. Afkast: observeret og hypotetisk holdes adskilt

### 2.1 Fire størrelser, der aldrig blandes

| Størrelse | Hvad det er | Kilde | Bruges til |
|---|---|---|---|
| **O1 observeret, vault-niveau** | HLP's egen PnL og egenkapital, som protokollen rapporterer dem | `vaultDetails` (DOK: felterne `portfolio`, `accountValueHistory`, `pnlHistory`) | Primært endpoint |
| **H1 hypotetisk indskyder** | O1 pro rata minus ind- og udbetalingsomkostning | Beregnet | Primært endpoint (efter fradrag) |
| H2 kontrafaktisk uden indgreb | Hvad HLP ville have tabt uden validatorernes JELLY-afgørelse | Kan ikke beregnes fremad | Kun omtalt (afsnit 3) |
| A annonceret APR | Feltet `apr` og tal på tredjepartssider | `vaultDetails.apr`; eco.com; DefiLlama | Aldrig et endpoint |

### 2.2 Hvad der er dokumenteret om HLP's afkast

| Påstand | Værdi | Kilde | Status |
|---|---|---|---|
| Kumulativ PnL siden lancering (05-2023) | ca. $136,9 mio. | CoinGecko (forespurgt 2026-06-30 via `vaultDetails`, `allTime`-bucket, ca. 93 punkter) | ART |
| Kumulativ PnL har aldrig været negativ | – | CoinGecko | ART |
| PnL kan stå stille i uger eller måneder | – | CoinGecko | ART |
| Enkelthændelser | 10-10-2025 ca. +10 % på under 48 t; 31-01-2026 ca. +5,8 % | CoinGecko | ART |
| "ca. 15–30 % APR i de fleste kvartaler" og fald på 5–12 % | – | eco.com (2026-09-15), med DefiLlama som kilde | UNVERIFIED (eco.com forklarer ikke DefiLlamas metode) |
| APR ca. 3,5 % på ca. $178 mio. i oktober 2026 | – | earnpark.com via søgeuddrag; siden er DNS-blokeret | UNVERIFIED |
| TVL top ca. $603,9 mio. (09-2025), ca. $268,6 mio. (06-2026) | fald > 55 % | CoinGecko | ART |
| Ingen performance fee; overskud og tab går fuldt til indskyderne | – | CoinGecko; tradingstrategy.ai | ART. Docs-eksemplet har `leaderCommission` 0 (DOK), men eksemplets vault er ikke navngivet |

Grov egen regning (ANTAGELSE): $136,9 mio. over ca. 3,1 år på en gennemsnitlig TVL på ca. $350 mio. svarer til ca.
12–13 % p.a. Tallet er ikke tidsvægtet og må ikke bruges som forventning.

### 2.3 Er HLP's egen PnL og APR netto, og netto for hvad?

| Post | Indeholdt i O1 (vaultens PnL)? | Status |
|---|---|---|
| Market making-resultat (spread, inventar, adverse selection) | Ja | DOK: "multiple market making strategies" |
| HLP's andel af handelsgebyrer | Ja, men andelen er ikke offentliggjort | DOK: "accrues a portion of trading fees"; gebyrsiden siger kun, at gebyrer går til "HLP, the assistance fund, and deployers" |
| Backstop-likvidationer (beholdt vedligeholdelsesmargin) | Ja | DOK: likvidator-vaulten er en del af HLP; margin returneres ikke |
| Funding på HLP's positioner | Ja, formodentlig | UNVERIFIED |
| Renter fra "USDC in Earn" | Muligvis | DOK nævner det; om det indgår i moder-vaultens PnL: UNVERIFIED |
| Underliggende vaults (`relationship.childAddresses`) | Om moderens `accountValue` og `pnl` inkluderer børnene: **UNVERIFIED** | Skal afklares før låsen. Ellers skal hvert barn hentes |
| Performance fee til en leder | Nej (0) | ART |
| Indskyderens bro-, gas- og udbetalingsomkostning | **Nej** | Trækkes fra i H1 |
| Kapitalbinding i lockup | Nej | Se afsnit 4 |
| USDC's kreditrisiko mod USD | Nej | Rapporteres, trækkes ikke fra |
| Indgreb (JELLY-afgørelse, Hyper Foundation-refusion) | Indgrebets virkning er med i O1 | Gør O1 bedre end en ren markedsrisiko |

Feltet `apr` er ikke defineret i dokumentationen (DOK: enhed og periode står ikke). En tredjepart siger, at det kun
bygger på de seneste 30 døgn (Growi.fi via søgeuddrag, UNVERIFIED). Derfor bruges `apr` aldrig til en dom.

## 3. Halerisiko

### 3.1 Dokumenterede hændelser

| Dato | Hændelse | Virkning for HLP | Kilde |
|---|---|---|---|
| 2025-03-12 | ETH-hval: lang ca. 160.234 ETH (ca. $307 mio.), trak urealiseret gevinst ud, blev likvideret | HLP tabte "~$4M over the past 24h", ca. 1 % af en TVL på ca. $451 mio. Max gearing sat ned til 40x (BTC) og 25x (ETH) | The Block 345866 (ART) |
| 2025-03-26 | JELLY: en kort position blev likvideret og overført til HLP. Kursen blev presset op | Urealiseret tab op til ca. $10–13,5 mio. (kilderne er uenige). Validatorerne afnoterede JELLY og lukkede til $0,0095. HLP endte med ca. +$0,7 mio. Hyper Foundation lovede at holde brugerne skadesløse | Arkham (ART); The Block 348314, CoinDesk og Blockworks via søgeuddrag (UNVERIFIED for præcise tal) |
| 2025-07 | TST-hændelse | Ukendt størrelse | Kun nævnt i søgeuddrag (UNVERIFIED) |
| 2025-10-10 | Markedsbredt krak | Ingen tab; ca. +10 % | CoinGecko (ART) |
| 2025-11-12 | POPCAT: ca. $3 mio. i 19 tegnebøger byggede en lang på $20–30 mio. og trak købsvæggen | HLP tabte ca. $4,9 mio. (under 1 % af TVL). Ind- og udbetalinger blev sat på pause i ca. en time | The Block 378606 (ART); Cointelegraph via søgeuddrag |
| 2026-01-31 | Stor ETH-lang likvideret | Ingen tab; ca. +5,8 % | CoinGecko (ART) |
| 2026-04 | Fartcoin-hændelse | Ingen tal | CoinGecko (ART) |

### 3.2 Hvad hændelserne betyder for designet

- **Backstop-eksponering er strukturel.** Når en bog-likvidation fejler, overtager HLP positionen (DOK: under 2/3 af
  vedligeholdelsesmarginen). HLP sælger altså en slags option på markedets likviditet. Gevinsten er lille og ofte. Tabet
  er sjældent og stort.
- **Manipulation af små perps rammer HLP direkte** (JELLY, POPCAT). Det er ikke et markedsfald. Det er et angreb på
  backstoppen.
- **"Validator-put".** JELLY-tabet forsvandt ved en afstemning (Blockworks' udtryk via søgeuddrag). O1 er derfor betinget
  af diskretionære indgreb. H2 (uden indgreb) ville have været værre. En fremadmåling kan ikke vide, om næste indgreb
  kommer.
- **Positive spring findes også** (10-10-2025, 31-01-2026). Afkastet er ikke bare negativt skævt. Det har tunge haler
  begge veje. Det gør σ_d stor og styrken lav.
- **Driftsrisiko uden for markedet:** USDC (Circle), Hyperliquids L1 og bro, og en validatorgruppe, hvor fem
  Foundation-validatorer har over halvdelen af stake (søgeuddrag, UNVERIFIED). Ingen af dem er i T-billen.
- **6–12 måneder kan ikke prisfastsætte halen.** Tre tabshændelser på ca. 20 måneder (03-2025 til 11-2025) giver en
  rate på ca. 1,8 pr. år (egen regning). Et vindue på 182 døgn ser 0, 1 eller 2. Det siger intet om halens størrelse.

## 4. Likviditet: lockup og udbetaling

| Regel | Værdi | Kilde |
|---|---|---|
| HLP-lockup | 4 døgn efter seneste indskud. Eksempel: indskud 14/9 08:00 → udbetaling tidligst 18/9 08:00 | DOK (protocol-vaults; for-vault-depositors) |
| Bruger-vaults | 1 døgn | DOK |
| Glidning ved udbetaling | "There may be some slippage as you withdraw and open positions are closed" (gælder vaults generelt; for HLP: UNVERIFIED) | DOK |
| Platformen kan pause udbetalinger | Ja, i ca. en time under POPCAT | ART |
| Udbetalingsloft | Feltet `maxWithdrawable` findes pr. vault | DOK |
| Udbetaling fra Hyperliquid til en anden kæde | "small gas fees"; et fast gebyr på 1 USDC er ikke bekræftet | DOK / UNVERIFIED |

Konsekvens for designet: en hypotetisk indskyder med 182 døgns hold mærker ikke lockup'en i det normale tilfælde.
I en krise kan den dog binde kapitalen netop, når tabet sker. Det modelleres ikke. Det rapporteres som
likviditetsforbehold.

## 5. Sammenlignelighed med den risikofri reference (DTB3)

Lab'et bruger allerede DTB3 som målestok (PROTOCOL_V3 ændring 42 punkt 5; `fred.stlouisfed.org` er tilladt). K04
bruger den samme serie med disse forskelle:

| Spørgsmål | Valg i K04 | Grund |
|---|---|---|
| Rentebasis | DTB3 omregnes fra diskontobasis til investeringsrente (afsnit 1.3) | Diskontobasis undervurderer renten med ca. 9 bp ved 3,75 %. Primært er den strengere (højere) målestok. Ændring 42's uomregnede tal er følsomhed |
| Dage uden værdi | Seneste offentliggjorte værdi føres frem (højst 4 døgn) | Weekender og helligdage. HLP har afkast alle 7 dage |
| Periode | Præcis de døgn, der har et gyldigt HLP-snapshot | Samme døgn i tæller og nævner |
| Valuta | USD mod USDC; ingen korrektion | USDC-afvigelser rapporteres |

**Hvorfor APR mod T-bill ikke er like-for-like:**
1. **Forskellig måling.** `apr` er udefineret, bagudskuende og formentlig 30-dages (UNVERIFIED). DTB3 er en notering af
   en 91-dages statsobligation på diskontobasis. De to tal har hverken samme periode eller samme rentebasis.
2. **Forskellig kreditrisiko.** T-billen er et krav på den amerikanske stat. HLP er et krav på USDC, en L1, en bro og
   en validatorgruppe, der kan stemme om afgørelser.
3. **Forskellig likviditet.** T-billen kan sælges dagligt. HLP har 4 døgns lockup og kan pauses.
4. **Forskellig fordeling.** HLP's afkast er en backstop- og market making-præmie med spring begge veje (afsnit 3).
   T-billen har næsten ingen varians. Et merafkast er kun en præmie for den risiko, ikke alfa.
5. **Overlevelse.** HLP's historik findes, fordi HLP overlevede. Én hændelse blev reddet af et indgreb. Andre
   puljede likviditetspuljer indgår ikke i sammenligningen (ingen kilde er læst; ANTAGELSE om at skævheden findes).
6. **Markedsbeta.** HLP kan have netto-eksponering mod markedet. E5 (beta til BTC) rapporteres, så et merafkast ikke
   forveksles med en lang markedsposition.

**Risikojustering i K04:** det primære endpoint er merafkastet e_d. Det fortolkes kun sammen med E3–E5 (fald, hale,
beta). En PASS på e_d med et fald ≥ 10 % er ikke en "bedre T-bill". Den er en risikopræmie, der blev betalt.

## 6. Point-in-time-data

### 6.1 Hvad lab'et har i dag

| Kilde | Indhold | Brugbart? |
|---|---|---|
| `lab/hlcensus.py` (ændring 38 A) | Hver times `metaAndAssetCtxs`-snapshot af alle HL-perps (funding, mark, OI, volumen) | **Nej** til HLP-afkast. Kan bruges som kontekst (fx store likvidationer) efter en lås |
| `lab/scanner.py` `http_post(HL_INFO, …)` (linje 46, 60) | Den eksisterende, read-only afsender til `/info` | Ja, som transport. En ny body `vaultDetails` er en ny datalinje, ikke en ny vært |
| `research/RESULTS_carry_v1.md` | HL-funding og spot-par (FAIL) | Nej. Anden mekanisme |
| HLP-vault-data | Ingen | **Lab'et har ingen HLP-data.** |

### 6.2 Findes en historisk serie?

**Ja.** Hvert `vaultDetails`-svar indeholder historik (DOK): `portfolio` har buckets `day`, `week`, `month`, `allTime`
og perp-varianter, hver med `accountValueHistory` og `pnlHistory` som lister af [tidsstempel, værdi]. CoinGecko fik ca.
93 punkter tilbage i `allTime` for perioden 05-2023 til 06-2026 (ART). Serien er altså tynd langt tilbage og tættere i
de korte buckets.

**Regel for historikken (fail-closed):**
- Før 2026-11-14 00:00 UTC læses intet historisk (G01). Det gælder også et enkelt svar, fordi svaret selv indeholder
  historik.
- Efter 11-14 må en historisk læsning kun ske efter en dateret lås, der nævner den (G01: "the date alone opens
  nothing").
- Punkter fra 2024 (G03 holdout) og fra 2025 og frem (G04 reserveret) læses aldrig. Den eneste tilladte historiske
  del ville være 2023-05..2023-12, og den er kort og tynd. **Designet bruger derfor ingen historik.**
- Fremad: ved indlæsning kasseres alle punkter med tidsstempel < låsetidspunktet eller < nu − 26 t, **før** noget gemmes
  eller beregnes. Samme præcedens som DefiLlama-reglen (PROTOCOL_V3 linje 69). En test med et syntetisk svar skal vise,
  at intet gammelt punkt når lab.db.

### 6.3 Hvad der skal registreres fremad

| Felt | Kilde | Kadence |
|---|---|---|
| `day`-bucket: punkter i `accountValueHistory` og `pnlHistory` efter filteret | `vaultDetails` | Dagligt 00:05 UTC |
| `apr`, `maxWithdrawable`, `maxDistributable`, `isClosed`, `allowDeposits`, `relationship` | `vaultDetails` | Dagligt |
| Lokal modtagetid, HTTP-status, svartid, svarets sha256 | Processen | Hver anmodning |
| DTB3 | FRED (tilladt) | Ved opgørelse |
| BTC-referencepris | Lab'ets eksisterende `mark` for BTCUSDT | Eksisterer allerede |

`followers` gemmes ikke. Listen indeholder andre brugeres adresser og beløb, og K04 har ikke brug for den.

Budget: 1 POST pr. døgn (plus 1 pr. barn, hvis børnene ikke er med i moderens tal). Svaret er af ukendt størrelse
(ANTAGELSE: under 1 MB). Det måles i en tørkørsel efter godkendelse, ikke nu.

## 7. Uafhængig validering

| Element | Indhold |
|---|---|
| To evaluatorer | Claude skriver `hlp1_eval`. Codex skriver en blind reference ud fra spec'en (som K05 og evaluator v1.1.1). Krav: 100 % ens på alle fixtures før første rigtige kørsel |
| Mutationstest | Mindst 15 mutationer (fx DTB3 uomregnet, historik ikke kasseret, flow regnet som PnL, NW-lags forkert) |

| Fixture | Plantet situation | Forventet |
|---|---|---|
| HLP-F01 | Svar med `allTime`-punkter fra 2024 og 2025 | Kasseret ved indlæsning; intet gemt |
| HLP-F02 | Indskud på 20 % af TVL midt i døgnet, PnL 0 | r_d = 0 (ikke +20 %) |
| HLP-F03 | Manglende snapshot i 2 døgn | 2 døgn ugyldige; ingen interpolation |
| HLP-F04 | Fald på 11 % fra top | KILL_TAIL |
| HLP-F05 | `isClosed` sand | Stop |
| HLP-F06 | DTB3 3,75 % diskonto | i = 3,8385 % |
| HLP-F07 | Weekend uden DTB3 | Fredagens værdi føres frem |
| HLP-F08 | Moderens PnL uden børn / med børn | Begge stier testet; låsen vælger én |

## 8. Statistisk styrke

Test: ensidet Newey-West-t på e_d med 5 lags. α_F = 0,0125 (z = 2,24). 80 % styrke (z = 0,84). σ_d er ukendt;
20 bp og 40 bp er ANTAGELSER (springene i afsnit 3 taler for den høje). NW-inflation 1,0–1,3 (ANTAGELSE).

| σ_d | n døgn | MDE pr. døgn | MDE p.a. over T-bill |
|---|---|---|---|
| 20 bp | 182 | 4,6–5,9 bp | 16,7–21,7 % |
| 20 bp | 365 | 3,2–4,2 bp | 11,8–15,3 % |
| 40 bp | 182 | 9,1–11,9 bp | 33,4–43,4 % |
| 40 bp | 365 | 6,5–8,4 bp | 23,6–30,6 % |

Styrke (NW 1,3) mod et sandt merafkast:

| σ_d | n | 3 % p.a. | 6 % p.a. | 10 % p.a. |
|---|---|---|---|---|
| 20 bp | 182 | 0,03 | 0,08 | 0,21 |
| 20 bp | 365 | 0,05 | 0,15 | 0,41 |
| 40 bp | 182 | 0,02 | 0,03 | 0,06 |
| 40 bp | 365 | 0,03 | 0,05 | 0,11 |

- **Rettelse til PROFIT_SEARCH (linje 78):** "styrken er 0,41 på 6 mdr." holder ikke med σ_d 20 bp. 0,41 nås først ved
  365 døgn og et sandt merafkast på 10 % p.a. På 182 døgn er styrken 0,03–0,21.
- **Ændring 8 punkt 14:** en familie kræver styrke ≥ 0,5 ved sand Sharpe 3,0 og α_F/3. Med 182 døgn er den 0,30
  (teksten selv). K04 som ændring 8-familie kræver derfor 12 måneder.
- **Ændring 32:** MDE/gulv er meget større end 2. K04 står som "kan kun finde store effekter (32)".
- Konklusion: en PASS kræver et merafkast på mindst ca. 17 % p.a. over T-bill på 6 måneder. Det er over de tal, der er
  rapporteret for HLP de seneste måneder (afsnit 2.2, UNVERIFIED).

## 9. Stopregler og kill-regler

| Regel | Tidspunkt | Udløser | Følge |
|---|---|---|---|
| S1 dækning | Løbende | Under 90 % gyldige døgn i en 28-døgns periode | INVALID for perioden; > 30 % ugyldige døgn i alt → studiet INVALID (udsat), ikke FALSIFIED |
| S2 hale | Løbende | Fald ≥ 10 % i indekset Π(1 + r_d) fra en top | KILL_TAIL: stop og rapport |
| S3 platform | Løbende | Udbetalinger pauset > 24 t, `isClosed` sand, eller en validator-afstemning om en HLP-position | Stop og rapport. Data efter hændelsen fortolkes ikke |
| S4 futilitet | Dag 91 | Kumulativt merafkast ≤ −2 % | FALSIFIED-tidligt (beskrivende). Kan kun stoppe, aldrig give PASS |
| S5 slut | Dag 182 (primær) | – | Dom efter afsnit 1.2 |
| S6 forlængelse | Kun hvis låst på forhånd | Dag 365 | Ingen forlængelse efter at have set data |
| K1 kill | Dag 182 | Middel e_d ≤ 0 | FALSIFIED |
| K2 materialitet | Dag 182 | Kumulativt merafkast under 1 % (ANTAGELSE; direktøren kan sætte et andet tal før låsen) | NOT MATERIAL |

Ingen tidlig evaluering ud over S4. Ingen ændring af observationstid, stikprøve eller acceptkriterier efter låsen.

## 10. Godkendelser og datoer

| Krav | Hvad | Status |
|---|---|---|
| Dokumentationstjek | Moder/barn i `accountValue` og `pnl`; betydningen af `pnlHistory` (kumulativ inden for bucket?); udbetalingsgebyr; HLP-adressen | Kan gøres i docs uden datakald. Ikke gjort færdigt |
| Ny datalinje | `info:vaultDetails` til `api.hyperliquid.xyz` gennem `scanner.http_post(HL_INFO)`. Ingen ny vært, ingen ny afsender, aldrig `/exchange` | Mangler; ét dateret ejer-ja |
| Lås | Dateret lås af `research/desk/protocols/HLP1_v1.md` som næste ændring i PROTOCOL_V3 | Mangler. Ordre 53: ingen A/B-låse 11-14 uden ejerens eksplicitte, daterede ja |
| VERIFIED_OWNER_APPROVAL | Ejernøglen D5 (`OWNER_KEY_GUIDE_D5.md`). Uden den bliver et chat-ja UNVERIFIED_ORIGIN, og resultatet kan kun være beskrivende | Mangler (G15 CLOSED) |
| W0-alfa | α_F 0,0125 fra W0, kun for en bekræftende fase B | W0 har 0,0375 tilbage, og F2, F3, LIQPROXY1 og FUNDFRAG1 gør krav på det (G20; D6). K04 ville være nr. 5 |
| G10 | Er K04 en ændring 8-familie, må koden ikke gå på nettet før 2026-11-28 | Gælder ved familie-status |
| G11/G12 | Ingen genstart af værten til og med 11-27; pm_lp røres aldrig | Deploy af datalinjen kræver ingen værtsgenstart |
| Deploy-vindue | Uden for K1–K3 (K3: ±35 min om 00/04/08/12/16/20 UTC) | 01:00–03:20 UTC er K3-frit |

Tidligste datoer (kun hvis alle krav nås):

| Dato (UTC) | Trin |
|---|---|
| 2026-11-14 → | Låsetekst kan tidligst committes, med ejerens daterede ja |
| 2026-11-28 | COIN-M, pm_lp's egne trin og en mulig genstart kommer først |
| 2026-11-30 (man) 01:00–03:20 | Tidligste deploy af datalinjen. Dag 0 |
| 2027-03-01 | S4 futilitet (dag 91) |
| **2027-05-31** | Dom ved 182 døgn. Mest sandsynligt INCONCLUSIVE |
| 2027-11-30 | Dom ved 365 døgn, kun hvis låst på forhånd |

PROFIT_SEARCH's 11-23 forudsatte deploy før 11-28. Det er muligt for en ren måling uden familie-status, men det
lægger en deploy midt i 11-19/11-20-beskyttelsen og op til 11-28. Denne note anbefaler 11-30.

## 11. Anbefaling

**NO-GO for alfa og for en bekræftende test. Beskrivende log parkeret. Ingen kapitalallokering.**

For:
- Den eneste kandidat, der angriber lab'ets robuste negative fund om gebyrtrin direkte (K12).
- Teknisk billig: én POST pr. døgn gennem en eksisterende afsender til en tilladt vært.
- Mekanismen er dokumenteret (DOK): market making, gebyrandel og backstop-likvidationer.

Imod:
- Styrken er 0,03–0,21 på 182 døgn (afsnit 8). Et nej og et ja ser næsten ens ud.
- Halen kan ikke prisfastsættes på 6–12 måneder. Den største kendte hale blev fjernet af et indgreb.
- Et merafkast er en risikopræmie for backstop- og platformrisiko, ikke en fordel, lab'et selv skaber.
- Rapporterede nyere tal (APR ca. 3,5 %, TVL faldet > 55 %) peger på et afkast nær T-bill (UNVERIFIED).
- W0 er fuldt optaget. K04 kan ikke få bekræftende status uden at fortrænge en anden kandidat.
- En PASS kan ikke bruges: lab'et indskyder ikke, og denne note anbefaler det heller ikke.

Hvis ejeren alligevel vil have en beskrivende log (α = 0), gælder alle disse betingelser:
1. Docs-punkterne i afsnit 10 er afklaret uden datakald.
2. Historikfilteret i afsnit 6.2 er bevist med en syntetisk test før første kald.
3. Dateret lås med VERIFIED_OWNER_APPROVAL; α = 0; ingen W0.
4. Deploy tidligst 2026-11-30 01:00–03:20 UTC; pm_lp og værten røres ikke.
5. Codex-referencen og fixtures er 100 % ens før første opgørelse.

## 12. Række til falsifikationsmatricen

| Hypotese | Primært endpoint | Kill-regel | Data tilgængelige? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| K04 H-HLP1: HLP's tidsvægtede dagsafkast (vault-niveau, minus hypotetisk ind- og udbetaling) > DTB3 (omregnet), fremad | Middel af e_d = ln(1 + r_d) − rf_d over 182 gyldige døgn; ensidet NW-t (5 lags), α_F 0,0125 | Middel ≤ 0 ved dag 182 → FALSIFIED; fald ≥ 10 % fra top eller udbetalingspause > 24 t → KILL_TAIL; kumulativt ≤ −2 % ved dag 91 → stop; dækning < 90 % → INVALID | **Nej.** Ingen HLP-data i lab'et. Ny datalinje (1 POST/døgn via eksisterende HL-afsender). Historik findes i svaret, men kasseres (G01, G03, G04) | Dateret lås + VERIFIED_OWNER_APPROVAL (D5) + ejer-ja til datalinjen + W0-α (fuldt optaget, D6) | 2027-05-31 (182 d); 2027-11-30 (365 d) | **NO-GO** for alfa/bekræftende test (styrke 0,03–0,21; hale uprissat). Beskrivende log (α = 0) kun på ejerens eksplicitte ja. Ingen kapitalallokering |

## 13. Kilder og verifikationsstatus

| Påstand | Status | Kilde |
|---|---|---|
| HLP laver market making og likvidationer, får en del af gebyrerne, leverer USDC i Earn; lockup 4 døgn | DOK | https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/protocol-vaults |
| HLP 4 døgn, bruger-vaults 1 døgn; glidning ved udbetaling; 10 % til leder i eksemplet; "past performance …" | DOK | https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-depositors |
| `vaultDetails`-felter (`portfolio`, `accountValueHistory`, `pnlHistory`, `apr`, `followers`, `lockupUntil`, `maxWithdrawable`, `isClosed`, `relationship`); `apr` udefineret | DOK | https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint |
| Gebyrer går til HLP, assistance fund og deployers; basis 0,045 % taker / 0,015 % maker | DOK | https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees |
| Backstop under 2/3 af vedligeholdelsesmargin; likvidator-vault er en del af HLP | DOK | https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations |
| Udbetalingsgebyr "small gas fees"; fast 1 USDC | DOK / UNVERIFIED | https://hyperliquid.gitbook.io/hyperliquid-docs/onboarding/how-to-start-trading |
| HLP-adresse 0xdfc2…f303 | ART | https://tradingstrategy.ai/trading-view/vaults/address/0xdfc24b077bc1425ad1dea75bcb6f8158e10df303 ; CoinGecko |
| ETH-hval 2025-03-12, ca. $4 mio., TVL ca. $451 mio., gearing 40x/25x | ART | https://www.theblock.co/post/345866/hype-drop-hlp-vault-loss-hyperliquid-whale-liquidation |
| JELLY 2025-03-26, lukket til $0,0095, HLP ca. +$0,7 mio. | ART | https://info.arkm.com/research/jellyjelly-exploit-on-hyperliquid |
| JELLY-top $10–13,5 mio. urealiseret; validator-afstemning; Foundation-refusion | UNVERIFIED (søgeuddrag) | The Block 348314; CoinDesk; Blockworks "validator put" |
| POPCAT 2025-11-12, ca. $4,9 mio.; pause i ca. 1 t | ART | https://www.theblock.co/post/378606/hyperliquid-pauses-deposits-withdrawals-popcat-trading-scheme-speculation |
| Kumulativ PnL $136,9 mio.; TVL-top og -fald; hændelser 10-2025, 01-2026, 04-2026; 93 punkter i `allTime` | ART | https://www.coingecko.com/learn/hyperliquid-hlp-vault-analysis |
| 15–30 % APR i de fleste kvartaler; fald 5–12 % | UNVERIFIED | https://eco.com/support/en/articles/15197987-hyperliquid-vault-strategies-2026-hlp-and-user-vaults-explained |
| APR ca. 3,5 % i 10-2026 | UNVERIFIED (DNS-blokeret, ikke omgået) | earnpark.com |
| `apr` = seneste 30 døgn | UNVERIFIED | Growi.fi via søgeuddrag |
| DTB3 som lab'ets målestok, diskontobasis | Lokal | `research/PROTOCOL_V3.md` ændring 42 punkt 5 |
| Historikfilter-præcedens (DefiLlama) | Lokal | `research/PROTOCOL_V3.md` linje 69 |
| W0, styrkekrav, familiekrav | Lokal | `research/PROTOCOL_V3.md` ændring 8 punkt 13–15; ændring 32; `research/desk/GATE_MATRIX.json` G01, G03, G04, G10, G15, G20 |
| HL-afsender og census | Lokal | `lab/scanner.py` linje 46 og 60; `lab/hlcensus.py` |
| σ_d, NW-faktor, bro-omkostning, materialitetsgulv, gennemsnitlig TVL | ANTAGELSE | Egne skøn |
