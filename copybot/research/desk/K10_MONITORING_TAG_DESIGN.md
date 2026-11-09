# K10 netto-short efter Binance' Monitoring Tag: design (direktørordre 61, arbejdsspor 4)

Skrevet 2026-11-09 (ca. 12:10–13:30 UTC). **Kun design. Ingen short-positioner eller nye datafeeds nu.**

- Ingen data er hentet. Ingen kald til Binance' API'er eller andre API'er. Ingen streams, lås, alfa, nøgler eller handel.
- `python3 -m lab` er ikke kørt. lab.db er ikke åbnet. Derfor kendes M1F's aktuelle kandidattal ikke (sidst noteret 0
  af 20 den 2026-10-26, `research/studies/MISSION22_SPOR_2026-10-26.md` linje 28). N4-filen og karantænemappen er ikke
  læst.
- Web er kun brugt til Binance' FAQ og meddelelser (søgemaskinens uddrag) og til artikler. `www.binance.com` svarer
  normalt i den lokale DNS (`getent hosts`, 2026-11-09 12:10 UTC). Én meddelelsesside gav kun navigation, ingen tekst.
- Mærker: **DOK** = læst i Binance' egne sider eller deres søgeuddrag i dag. **ART** = artikel. **UNVERIFIED** = ikke
  bekræftet. **ANTAGELSE** = eget skøn. **Lokal** = lab'ets egne filer.
- Dette er ikke en låsetekst. M1S-skitsen og PKT-M1S i `PROFIT_SEARCH_2026-11-09.md` (linje 154–174) er stadig kun
  illustrative.

## 0. Konklusion først

| Spørgsmål | Svar |
|---|---|
| Er K10 bare en aflæsning af M1F? | **Nej.** M1F's låste udfald er spot-`sar_7d` minus medianen af 29 altcoins, brutto, uden omkostninger. M1F's tekst siger "Ingen short-handel" (punkt 7). K10 har et andet udfald (perp, BTC-hedge, gebyrer, funding, likvidationsloft). K10 er derfor en **separat hypotese med egen α**. M1F's lås ændres ikke. |
| Er signalet testbart uden look-ahead? | Ja, hvis t = news-watch' `usable_from`, indgang ≥ t + 1 t, og perpens eksistens afgøres af arkivdata fra før t. Universet bygges kun af meddelelser i tidsrækkefølge (afsnit 2–4). |
| Survivorship | Håndterbar fremad: afnoterede mønter bliver i stikprøven. Exit ved afnotering = sidste handlede pris før stop (afsnit 3). |
| Styrke | Lav. MDE ca. 9–13 % over 7 døgn ved 20 mønter mod et omkostningsgulv på ca. 0,7–1,7 %. "Kan kun finde store effekter (32)". |
| Hændelsesrate | ca. 1 meddelelse pr. måned i 2026 med 3–4 mønter (lokale titeltal og søgeuddrag). PROFIT_SEARCH's "ca. 5 hændelser pr. md." og "ca. 2027-04" er for optimistisk (afsnit 8). |
| Anbefaling | **NO-GO nu** for lås og alfa. Betinget: en beskrivende nettoaflæsning (α = 0) af M1F's egne mønter kan låses før M1F kører. K10 som bekræftende test genovervejes først efter M1F's kørsel. Afsnit 11. |

**Ingen short-positioner eller nye datafeeds nu.** Alt herunder er papir, og kun efter en dateret lås.

## 1. Forholdet til den låste M1F (ændring 17j)

### 1.1 Hvad M1F's lås siger (ordret kontrolleret i dag)

Låst tekst: `research/drafts/M1F_MONITORING_FREMAD.md`. Git-blob `dccceba6181520d49ca16adc7e28998dac402a15` og sha256
`db9924c4…cb48b` stemmer med PROTOCOL_V3 ændring 17j punkt 1 (genberegnet i dag med `git hash-object` og `sha256sum`).

| M1F-punkt | Indhold |
|---|---|
| 1 Påstand | Mønten klarer sig dårligere end de øvrige altcoins de næste 7 døgn: gennemsnit Y < 0 |
| 2 Begivenhed | news-watch-titel, der matcher `Extend the Monitoring Tag to (?:Include )?(.+?)(?:,? and Remove|,? Remove| on \d{4}-\d{2}-\d{2}|$)`, med `usable_from` ≥ 2026-10-25 00:00 UTC. t = `usable_from` |
| 3 Udelukket | (a) gentaget tag, (b) afnotering annonceret før t (16e), (c) stablecoins og BTC, (d) ingen Binance-spotpris inden for 72 t |
| 4 Udfald | Y = `sar_7d`(mønt) − median `sar_7d` over `UNIVERSE_30_V3` uden BTC og mønten. Spot fra `data.binance.vision`. Start ved første time ≥ t med spotpris |
| 5 Stikprøve | De første 20 mønter. Én kørsel. Frist 2027-06-30. Under 12 mønter eller 6 meddelelser: UNTESTABLE |
| 6 Test | Fortegnsskift pr. meddelelse, ensidet, egen α 0,05 uden for alle budgetter |
| 7 Betydning | "kun at faldet findes fremad. En risikoregel … kræver sin egen daterede ændring. **Ingen short-handel.**" |

### 1.2 Hvorfor K10 ikke er en aflæsning af M1F's udfald

| Element | M1F | K10 |
|---|---|---|
| Instrument | Spot | USD-M-perp `<MØNT>USDT` |
| Reference | Median af 29 altcoins (ikke handelbar billigt) | Lang BTCUSDT-perp 1:1 (handelbar) |
| Omkostninger | Ingen | 0,12 % pr. side og ben (lab-modellen) |
| Funding | Ingen | Realiseret, begge ben |
| Tabsloft | Intet | −100 % af marginen ved 2× kursstigning |
| Start | Første time ≥ t med spotpris | Første hele time ≥ t + 1 t |
| Begivenheder | Fra 2026-10-25 | Kun fra K10's egen lås |
| Udelukket | 3a–3d | 3a–3c + ingen perp før t, TradFi, futures-afnotering før t |

K10's brutto er ca. −(`sar_7d` mod BTC), ikke M1F's Y. Et M1F-PASS kan altså falde sammen med et K10-FALSIFIED, fx
hvis hele altcoin-markedet falder mod BTC, eller hvis funding æder faldet.

### 1.3 Følger

- **Egen hypotese og egen α.** En handelsgevinst er en hypotese, ikke en måling. Ordre 52 og G20 forbyder at
  omklassificere en hypotese som måling for at undgå multipel-test-korrektion. En bekræftende K10 skal derfor have
  α_F 0,0125 fra W0. W0 er fuldt optaget (afsnit 10).
- **M1F's lås røres ikke.** K10 får sin egen fil, sin egen ændring og sin egen kode. M1F's stikprøve, kørselstidspunkt,
  kode og rapport ændres ikke. K10 rapporteres aldrig før M1F's egen kørsel. Overlap i mønter rapporteres.
- **Mulig beskrivende variant K10-D (α = 0):** de samme nettoregler anvendt på M1F's egne 20 mønter, kørt lige efter
  M1F. Den afgør intet. Den svarer kun på, om et eventuelt M1F-fald er stort nok til at overleve omkostninger. Den skal
  låses, før M1F's priser læses.

## 2. Point-in-time-univers

### 2.1 Hvordan tag-listen ændrer sig

| Fakta | Status | Kilde |
|---|---|---|
| Monitoring Tag og Seed Tag blev indført 2023-07-26 (Seed Tag afløste Innovation Zone) | DOK (uddrag) | binance.com "Introducing Seed Tags & Monitoring Tags …" |
| Tagget markerer tokens med højere volatilitet og risiko; de kan afnoteres, hvis de ikke opfylder kravene | DOK (uddrag) | academy.binance.com/en/glossary/monitoring-tag |
| Handel kræver en risikoquiz hvert 90. døgn på Spot og/eller Margin | DOK (uddrag) | samme |
| Binance gennemgår periodisk og tilføjer eller fjerner tags. Kriterier: team, udvikling, volumen og likviditet, netværkssikkerhed, kommunikation, due diligence, svindel | DOK (uddrag) | samme |
| Tagget vises på Spot-, Margin- og Markets-siderne. Om det gælder futures: UNVERIFIED (intet uddrag nævner futures) | UNVERIFIED | – |
| Ændringer sker via meddelelser: "Binance Will Extend the Monitoring Tag to Include X, Y … on YYYY-MM-DD", ofte med "and Remove the Monitoring Tag for …" | DOK (titler) | binance.com-meddelelser 2023-10-04, 2024-01-04, 2024-07-01 |
| Lokale titeltal (ingen priser): 2023 1, 2024 2, 2025 6, 2026 10 meddelelser (til 10-24) | Lokal | `research/studies/ANALYSE_2026-10-24.md` linje 124 |
| 2026-eksempler: FLOW, ACA, D, DATA (01-02); ACT, BLUR, PIVX, QKC (06-18); AEUR, PYR, SCRT, VANRY (07-03); ACX, LSK, STX (07-24); STORJ m.fl. (05-22) | ART (søgeuddrag) | coinfomania, fxnewsgroup, storj-forum |

**Der findes ingen tilladt, point-in-time liste over taggede mønter.** Binance' nuværende liste er et øjebliksbillede.
Den har survivorship (afnoterede mønter er væk) og look-ahead (den kender fremtidige tilføjelser og fjernelser). Universet
skal derfor bygges **kun** af meddelelserne i den rækkefølge, de blev set.

### 2.2 Kilde til tidspunktet

- Kilden er news-watch (ændring 16): Binance' CMS-artikelliste på `www.binance.com` (tilladt vært, GET), kategorierne
  48, 161 og 49, hentet hvert 10. minut. Den kører allerede. **Intet nyt feed.**
- t = `usable_from`. For live-poster er det indsamlingstiden (ændring 16 punkt 3). Det er højst ca. 10 min efter
  udgivelsen (`releaseDate`, Binance' eget tidsstempel).
- Backfill-poster bruges ikke. De ligger alle før K10's lås og må ikke være evidens (ændring 16 punkt 5).
- Gentagne tags (M1F 3a) afgøres af news-watch' arkiv med titler før t. Det er point-in-time.
- Mønterne findes med M1F's regex og opdeling, uændret (`lab/coverage.py` linje 227 og 263–268). Samme regel giver
  samme mønter i begge studier.

## 3. Afnotering og survivorship

Taggede mønter afnoteres ofte. Det er netop mekanismen. Reglerne skal derfor sikre, at de "bedste" og de "værste"
udfald begge bliver i stikprøven.

| Situation | Regel |
|---|---|
| Spot afnoteres, perp handler videre | Ingen ændring. K10 bruger kun perps |
| Futures-afnotering annonceret før t (16e's titelregel) | Udelukket (tælles med årsag). Positionen ville ikke kunne holdes 7 døgn |
| Futures-afnotering annonceret under holdet | Ingen ændring i exit-reglen. Holdet slutter ved planlagt exit eller ved handelsstop, hvad der kommer først |
| Perp stopper handel før exit | Exit = sidste 1m-close i arkivet før stop. Binance afregner til gennemsnittet af indeksprisen pr. sekund over de sidste 30 min (1.800 værdier) og opkræver handelsgebyr (DOK (uddrag), FAQ "Delisting of Futures Contracts"; ændret fra 1 t til 30 min 2024-11-11). Afregningsprisen findes ikke sikkert i arkiverne: UNVERIFIED. Følsomhed: det højeste 1m-high i de sidste 30 min (værst for en short) |
| 30 min før stop | Kun reduce-only. K10 åbner aldrig nye positioner i den periode (DOK (uddrag)) |
| Kurshul i arkivet efter indgang | Exit ved sidste tilgængelige 1t-close før hullet, markeret. Følsomhed: −100 % for disse |
| Ingen perpdata efter indgang overhovedet | Talt som datafejl. Er > 20 % af de gyldige mønter ramt, er studiet INVALID (datatab er ikke tilfældigt) |
| Mønt fjernet fra tag-listen under holdet | Ingen ændring |
| Om `data.binance.vision` beholder klines for afnoterede perps | ANTAGELSE (ja); kontrolleres i arkivets fillister ved målingen, ikke nu |

## 4. Testbar uden look-ahead?

| Risiko | Regel i K10 |
|---|---|
| Meddelelsestid mod ikrafttræden | Titlen giver en dato ("on 2026-07-24"). Klokkeslættet er UNVERIFIED. K10 bruger t = `usable_from`, altså det tidspunkt, en lille aktør kunne have handlet på. Sekundært (afgør intet): indgang ved første hele time ≥ ikrafttrædelsesdatoen 00:00 UTC + 1 t |
| Tidszone | `releaseDate` og `usable_from` er epoch-sekunder (UTC). Datoen i titlen antages at være UTC (UNVERIFIED) |
| Fandtes perpen ved meddelelsen? | Kun hvis `data.binance.vision` har en 1t-kline for `<MØNT>USDT` (USD-M) i timen før t. Ikke dagens `exchangeInfo` (den kender fremtiden og mangler afnoterede). En perp, der listes efter t, tæller ikke |
| TradFi-perps | Udelukket som i præciseringen af 16d/16f |
| Funding | Kun realiseret funding efter hver afregning bruges, og kun som omkostning. Aldrig som signal |
| Indgangspris | Åbningen af 1t-kline h, hvor h er første hele time ≥ t + 1 t. Hastighed betyder intet |
| Universmedianen | Bruges ikke. Ingen fremtidig information om andre mønter indgår |
| Stikprøvens rækkefølge | Efter t, derefter alfabetisk (som M1F 5). Fastlagt før data |

Konklusion: signalet er testbart uden look-ahead fremad. Historisk er det ikke: news-watch' backfill har forbeholdet om
rettede titler, og 2024-backfill er holdout (G03, G06).

## 5. Omkostninger for en short-perp

| Post | Værdi i modellen | Status |
|---|---|---|
| Taker-gebyr og slippage | 0,10 % + 0,02 % pr. side og ben (PROTOCOL_V3 ændring 42 punkt 2). Short mønt + lang BTC = 4 × 0,12 % = **0,48 %** pr. rundtur | Lokal model. Binance' basis-taker på USD-M er lavere (FAQ 360033544231, citeret i PROFIT_SEARCH; ikke genlæst i dag) |
| Slippage i tynde bøger | Taggede perps har ofte tynde bøger. Følsomhed: 3× omkostninger | ANTAGELSE |
| Funding, short-ben | Realiseret, fra `data.binance.vision` funding-arkiver. Er funding negativ, betaler shorten | Retningen for taggede mønter er **UNVERIFIED**. Lab'et har ingen tal (H4/H5 målte nye listninger, ikke tags). Ved −0,01 % til −0,05 % pr. 8 t koster 7 døgn 0,21–1,05 % (egen regning) |
| Funding, BTC-ben | Realiseret. Ved +0,01 % pr. 8 t betaler den lange ca. 0,21 % på 7 døgn | ANTAGELSE om niveau |
| Fundinginterval | Binance skifter interval (4 t eller 1 t) for urolige perps. Lokale titeltal: 30 `funding_interval`-meddelelser i 2025 | Lokal. Modellen bruger de faktiske afregninger, uanset interval |
| Lån | **Irrelevant for perps.** Ingen lånerente, ingen recall. Spot-short via margin bruges ikke | – |
| Likvidation | 1× margin. Når et 1t-high ≥ 2 × indgangsprisen, regnes shorten som −100 % af marginen, og BTC-benet lukkes ved timens close | Forenklet (vedligeholdelsesmargin ignoreres). Som PKT-M1S |
| Afregningsgebyr ved afnotering | Handelsgebyr opkræves (DOK (uddrag)). Modellen trækker 0,12 % | – |

**Omkostningsgulv:** ca. 0,7–1,7 % pr. hændelse (0,48 % + funding på begge ben; ANTAGELSE om funding). PROFIT_SEARCH
brugte ≈ 0,6 %. Det er i den lave ende.

## 6. Hypotese, enhed og endpoint

### 6.1 Hypotese H-M1S (falsificerbar)

> En short af USD-M-perpen for en mønt, der får et nyt Monitoring Tag, hedget 1:1 med en lang BTCUSDT-perp, åbnet ved
> første hele time ≥ t + 1 t og holdt 168 timer, giver **i middel en nettogevinst > 0** efter gebyr, slippage,
> realiseret funding på begge ben og likvidationsloftet.

### 6.2 Definitioner

| Begreb | Definition |
|---|---|
| Begivenhed | M1F punkt 2's titelregel, men kun `usable_from` ≥ K10's låsetidspunkt |
| Udelukket (tælles) | M1F 3a–3c; ingen USD-M-perp før t (afsnit 4); TradFi; futures-afnotering annonceret før t |
| **Enhed** | Mønt. Klyngeenhed for testen: meddelelsen |
| Netto pr. mønt | Y_net = −ln(P_exit/P_entry) + ln(B_exit/B_entry) − 4 × 0,0012 + Σ funding modtaget af shorten − Σ funding betalt af den lange. P = mønt-perp, B = BTCUSDT-perp. Gulv: −100 % (afsnit 5) |
| **Primært endpoint** | Gennemsnit af Y_net over de første 20 mønter |
| Sekundære (afgør intet) | Median; andel > 0; Y_net ved 3× omkostninger; Y_net uden funding; brutto; indgang ved ikrafttrædelsesdato; andel ramt af −100 %-loftet; andel afnoteret under holdet |

### 6.3 Test

Ensidet fortegnsskift-permutation, hvor alle mønter i samme meddelelse vender fortegn samtidig (som M1F punkt 6),
eksakt over 2^k. Bekræftende: α_F 0,0125 fra W0. Beskrivende (K10-D eller en fase A): α = 0, afgør intet.

## 7. Uafhængig validering

| Element | Indhold |
|---|---|
| To evaluatorer | Claude skriver `m1s_eval`; Codex skriver en blind reference ud fra spec'en. 100 % ens på fixtures før første kørsel |
| Fixtures (syntetiske) | MS-F01 perp listet 2 t efter t (udelukket); MS-F02 kurs ×2,1 på dag 3 (−100 %); MS-F03 perp stopper på dag 4 (exit ved sidste 1m-close; følsomhed 30-min-high); MS-F04 tre mønter i én meddelelse (én klynge); MS-F05 gentaget tag; MS-F06 fundinginterval skifter fra 8 t til 4 t midt i holdet; MS-F07 TradFi-perp; MS-F08 kurshul i arkivet; MS-F09 futures-afnotering før t; MS-F10 backfill-post (ignoreres) |
| Mutationstest | Mindst 15 mutationer (fx funding med forkert fortegn, BTC-ben glemt, indgang ved t i stedet for t + 1 t, exchangeInfo brugt i stedet for arkiv) |

## 8. Statistisk styrke

Kilde til sd (ændring 32 punkt 1): explore0's ubetingede sd for alt mod BTC over 7 døgn er **16,85 %** (median;
PROTOCOL_V3 ændring 32 punkt 4, beregnet med `power_plan.py` 2026-10-28). Taggede mønter svinger formentlig mere, så den
reelle MDE er højere. MDE = (z_α + 0,842) · sd / √n.

| α (ensidet) | sd | n | MDE over 7 døgn |
|---|---|---|---|
| 0,0125 | 16,85 % | 20 mønter | 11,6 % |
| 0,0125 | 16,85 % | 40 mønter | 8,2 % |
| 0,0125 | 12 % (klyngemiddel, ANTAGELSE) | 8 meddelelser | 13,1 % |
| 0,05 | 16,85 % | 20 mønter | 9,4 % |
| 0,05 | 12 % | 8 meddelelser | 10,5 % |

- **MDE/gulv ≈ 7–19.** K10 står som "kan kun finde store effekter (32)". En SCREEN_FAIL er da "lav styrke".
- **Hændelsesrate (ANTAGELSE ud fra lokale titeltal og søgeuddrag):** ca. 10–12 meddelelser pr. år med 3–4 mønter.
  Efter gentagne tags, mønter uden USD-M-perp og TradFi skønnes 15–25 brugbare mønter pr. år. 20 mønter tager altså ca.
  10–16 måneder og kun ca. 6–8 klynger.
- **Rettelse til PROFIT_SEARCH (linje 79 og 226):** "ca. 5 hændelser pr. md." og "ca. 2027-04" svarer ikke til de
  lokale tal. Realistisk kommer 20 mønter efter en lås 11-14 tidligst ca. 2027-09, sandsynligvis senere.
- Et fald på 10 % eller mere efter et tag ville være meget stort. Lab'ets nabo-resultat L06 (short af nye HL-listninger
  −5,6 %, n 23, 7 af 23 fordoblede sig) viser, at halen på shortsiden er tung.

## 9. Stopregler og kill-regler

| Regel | Tidspunkt | Udløser | Følge |
|---|---|---|---|
| K1 kill | Ved 20 mønter (eller fristen) | Gennemsnit Y_net ≤ 0 | FALSIFIED |
| K2 futilitet fra M1F | Når M1F har kørt | M1F's gennemsnit Y ≥ 0 (intet relativt fald) | K10 stoppes uden kørsel: STOPPED_FUTILE. Ingen brutto-effekt, ingen netto-effekt. Kan kun stoppe, aldrig give PASS, så α påvirkes ikke |
| K3 hale | Ved 10 mønter | ≥ 3 af 10 ramt af −100 %-loftet | KILL_TAIL: stop og rapport |
| K4 data | Ved kørslen | > 20 % af gyldige mønter uden perpdata efter indgang | INVALID |
| K5 frist | 2028-06-30 | Under 12 mønter eller under 6 meddelelser | UNTESTABLE |
| S1 én kørsel | – | Koden skrives først ved 20 mønter (som M1F). Ingen mellemopgørelser | – |
| S2 rækkefølge | – | K10 rapporteres aldrig før M1F's egen kørsel | – |

Ingen ændring af observationstid, stikprøve eller acceptkriterier efter låsen.

## 10. Godkendelser og datoer

| Krav | Hvad | Status |
|---|---|---|
| Data | news-watch (kører), `data.binance.vision` klines 1m/1t og funding-arkiver (tilladt, læses én gang ved målingen). Ingen ny vært, intet nyt feed, ingen collector | Tilgængeligt, men arkivlæsning er historisk og må først ske efter 2026-11-14 og efter låsen (G01) |
| Lås | Dateret lås af `research/desk/protocols/M1S_v1.md` (eller K10-D) som næste ændring i PROTOCOL_V3 | Mangler. Ordre 53: ingen A/B-låse 11-14 uden ejerens eksplicitte, daterede ja |
| VERIFIED_OWNER_APPROVAL | Ejernøglen D5. Uden den bliver et chat-ja UNVERIFIED_ORIGIN og resultatet kun beskrivende | Mangler (G15 CLOSED) |
| α | Bekræftende: α_F 0,0125 fra W0. Beskrivende: α = 0 | W0 har 0,0375 tilbage, og F2, F3, LIQPROXY1 og FUNDFRAG1 gør krav på det (G20, D6). Egen α uden for W0 som M1F er ikke tilladt for en handelshypotese (ordre 52) |
| M1F | Uændret | Ændring 17j, sha256 kontrolleret i dag |
| Programmets tal | Fremadtests med egen α (H5F, H5X, U1F, M1F) nævnes ved hvert resultat (17j punkt 2) | K10 skal nævne dem og sin egen W0-plads |

Tidligste datoer (kun hvis alle krav nås):

| Dato (UTC) | Trin |
|---|---|
| 2026-11-14 → | Låsetekst (M1S_v1 eller K10-D) kan tidligst committes, med ejerens daterede ja |
| ca. 2027-05 (ANTAGELSE) | M1F's 20. mønt + 10 døgn: M1F kører. K10-D kan køre straks efter. K2-futilitet afgøres |
| ca. 2027-09 til 2028-03 (ANTAGELSE) | 20 K10-mønter efter en lås 11-14, + 7 døgn + arkivforsinkelse: tidligste K10-dom |
| 2028-06-30 | K10's frist (forslag; M1F's frist er 2027-06-30) |

## 11. Anbefaling

**NO-GO nu for lås og alfa. Ingen short-positioner eller nye datafeeds nu.**

For:
- Data kører allerede. Intet nyt feed og ingen ny vært.
- Mekanismen er plausibel (afnoteringsrisiko, quizkrav, færre købere).
- K10 svarer på det, M1F ikke kan: overlever et fald omkostninger, funding og squeezes?

Imod:
- Styrken er lav: MDE 9–13 % mod et gulv på 0,7–1,7 %.
- 20 mønter tager 10–16 måneder med kun 6–8 uafhængige klynger.
- W0 er fuldt optaget. En bekræftende K10 ville fortrænge en anden kandidat.
- M1F måler allerede brutto-effekten. Uden et M1F-fald er K10 død på forhånd (K2).
- Funding for shorts på taggede mønter er ukendt og kan være dyr. Halen på shortsiden er tung (L06).

Betinget anbefaling (kræver alle punkter):
1. **K10-D (α = 0):** en beskrivende nettoaflæsning af M1F's egne 20 mønter med reglerne i afsnit 3–6 kan låses før
   M1F's priser læses. Den kræver ejerens daterede ja og VERIFIED_OWNER_APPROVAL. Den afgør intet.
2. **K10 bekræftende:** genovervejes først, når M1F har kørt og viser et fald på mindst ca. 10 %, og når ejerens
   W0-rangering (D6) giver plads.
3. Ingen kode før 20 mønter. M1F's lås, kode og rapport røres ikke.

## 12. Række til falsifikationsmatricen

| Hypotese | Primært endpoint | Kill-regel | Data tilgængelige? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| K10 H-M1S: short USD-M-perp efter nyt Binance Monitoring Tag, BTC-hedget 1:1, indgang ≥ t + 1 t, 168 t, netto > 0 | Gennemsnit af Y_net over de første 20 mønter efter låsen (0,12 %/side/ben, realiseret funding begge ben, −100 %-loft); ensidet fortegnsskift pr. meddelelse | Gennemsnit ≤ 0 → FALSIFIED; M1F's Y ≥ 0 → STOPPED_FUTILE; ≥ 3 af 10 ramt af −100 % → KILL_TAIL; < 12 mønter eller < 6 meddelelser ved 2028-06-30 → UNTESTABLE | **Delvis.** Hændelser: ja (news-watch kører). Priser og funding: tilladte arkiver, læses først efter 11-14 og efter låsen. Intet nyt feed | Dateret lås + VERIFIED_OWNER_APPROVAL (D5) + W0-α (fuldt optaget, D6); K10-D kun lås + D5, α = 0 | K10-D ca. 2027-05 (ved M1F's kørsel); K10 ca. 2027-09 til 2028-03 (ANTAGELSE) | **NO-GO nu** (lås/alfa). Betinget: K10-D (α = 0) før M1F kører; genovervej K10 efter M1F. Ingen short-positioner eller nye datafeeds nu |

## 13. Kilder og verifikationsstatus

| Påstand | Status | Kilde |
|---|---|---|
| M1F's låste tekst og hashes | Lokal, kontrolleret i dag | `research/drafts/M1F_MONITORING_FREMAD.md`; `research/PROTOCOL_V3.md` ændring 17j |
| M1F's regex og kandidattælling | Lokal | `lab/coverage.py` linje 225–297 |
| news-watch, `usable_from`, backfill-regel | Lokal | `research/PROTOCOL_V3.md` ændring 16 punkt 1–5 |
| Afnoteringstitler (16e) | Lokal | `research/PROTOCOL_V3.md` ændring 16e |
| TradFi-udelukkelse | Lokal | Præcisering af 16d/16f |
| sd 16,85 % og styrkeregel | Lokal | `research/PROTOCOL_V3.md` ændring 32 |
| Omkostningsmodel 0,10 % + 0,02 % | Lokal | `research/PROTOCOL_V3.md` ændring 42 punkt 2 |
| Titeltal 2023–2026; 30 `funding_interval`-meddelelser i 2025 | Lokal | `research/studies/ANALYSE_2026-10-24.md` linje 124 |
| L06 −5,6 %, 7 af 23 fordoblede | Lokal | `research/desk/PROFIT_SEARCH_2026-11-09.md` linje 60 |
| Tagget indført 2023-07-26; quiz hvert 90. døgn; kriterier; vist på Spot/Margin | DOK (uddrag) | https://academy.binance.com/en/glossary/monitoring-tag ; https://www.binance.com/en/support/announcement/introducing-seed-tags-monitoring-tags-for-tokens-with-high-volatility-and-risks-b0f241491d0e4d75aa2f8752b7bf8af5 |
| Titelformat og eksempler 2023–2024 | DOK (titler) | binance.com-meddelelser 2023-10-04, 2024-01-04, 2024-07-01 |
| 2026-batches (3–4 mønter) | ART (søgeuddrag) | https://coinfomania.com/binance-expands-monitoring-tag-to-include-acx-lsk-and-stx/ ; fxnewsgroup.com; forum.storj.io |
| Ikrafttrædelsens klokkeslæt | UNVERIFIED | – (meddelelsessiden gav ingen tekst; artiklen nævner kun datoen) |
| Gælder tagget futures? | UNVERIFIED | – |
| Futures-afnotering: 30-min-gennemsnit af indeks (1.800 værdier), fra 2024-11-11; reduce-only de sidste 30 min; afregning med gebyr | DOK (uddrag) | https://www.binance.com/en/support/faq/delisting-of-futures-contracts-dd60dfbf654d4055aa6b217ea6d5ddba ; https://www.binance.com/en/support/announcement/updates-on-binance-futures-settlement-price-calculation-4bcabddf0e81423ebca242e185bf157d |
| Afregningspris i arkiverne; arkiver for afnoterede perps | UNVERIFIED / ANTAGELSE | – |
| Funding-retning for taggede mønter | UNVERIFIED | – |
| Hændelsesrate, klynge-sd, fundingniveauer, gulv | ANTAGELSE | Egne skøn |
