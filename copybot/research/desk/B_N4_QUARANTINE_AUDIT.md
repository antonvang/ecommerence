# B n4: audit af universet og den karantænerede parliste (direktørordre 53 P1)

Skrevet 2026-11-06 kl. 16:20 lokal (15:20 UTC). Kun repoet er læst: ingen netværk, ingen Upbit- eller børskald, ingen
markedsdata. Intet er ændret: B n4, låsetekst 6c, QUARANTINE.json, PROTOCOL_V3 og værktøjerne er urørte. Intet er låst.
Den karantænerede fil er kun brugt til at forklare karantænen og ikke til at vælge eller forme et univers.

Mærkning: **[F]** betyder fakta med kilde (fil og linje eller commit). **[I]** betyder min slutning.
Lokal tid = UTC+1. Commit-tiderne er git-tider (`git log --date=iso`).

Identiteter, som de blev læst:

| Fil | Seneste commit | sha256 (start) |
|---|---|---|
| `research/PROTOCOL_V3.md` | `ec91280` | `0a09b3e954d92c82` |
| `research/studies/MISSION27_3_2026-11-02.md` | `586a34d` | `103fd0afe3e2fd47` |
| `research/data/QUARANTINE.json` | `8fac269` | `7e98e1b38c552ef9` |
| `research/data/N4_KIMCHI_PAIRS_2026-11-02.json` | `b971d56` | `36a8e82be90a5483` (= QUARANTINE-posten) |
| `research/tools/n4_kimchi.py` | `8fac269` | `c0e42309017725ae` |
| `research/tools/factory.py` | `70856c5` | `3d07716e87776a1e` |

---

## 1. Den oprindelige universregel og dens commit

**[F]** Låsetekst B, MISSION27_3 punkt 6c punkt 1, blev tilføjet i `b971d56` (2026-11-02 10:14:43 lokal) og står
uændret (linje 346-350):

> Upbit-dagscandles (`candles/days`, `KRW-<mønt>`) for de 232 par i
> `research/data/N4_KIMCHI_PAIRS_2026-11-02.json`. Parlisten er dagens Upbit-liste, hentet 08:08 UTC, krydset med
> Binance-perps; BTC og stablecoins er udeladt.

Samme punkt erklærer en **kendt skævhed** (linje 354-355): "mønter, der blev afnoteret fra Upbit før 11-02, mangler
(overlevelsesskævhed). Det kan ikke repareres og rapporteres."

- **[F]** Universet er altså en **fast liste**, ikke en regel. Listen er dateret til 2026-11-02, mens perioden er
  explore0 (2020-03-01..2021-12-31; 6a).
- **[F]** Der findes ingen anden universformulering for B. NOV14_READINESS §5 siger: "En erstatningsformulering af punkt
  1 findes ingen steder" (AMB-18).
- **[F]** `n4_kimchi.py` blev oprettet i `7012c2b` (10:20:52 lokal) med konstanten
  `PAIRS = …/N4_KIMCHI_PAIRS_2026-11-02.json` (linje 23) og testen `test_pair_file`. Konstanten blev fjernet i
  `8fac269`. Testen læser stadig filen for at kontrollere `overlap == len(pairs)` og at BTC ikke er med. Det er tilladt,
  fordi ændring 40 punkt 2 lader registret og testene nævne filen.
- **[F]** Ingen version af 6c er låst. `n4_kimchi.py run` nægter at køre uden en `## Ændring … metode n4` og før
  2026-11-14 (READINESS §6, `EARLIEST`).

## 2. Hvornår listen blev bygget, af hvad og med hvilken kode

| UTC (11-02) | Hændelse | Kilde |
|---|---|---|
| 2026-10-24 00:43 | Ændring 17h punkt 1: "Upbits egen vært (`api.upbit.com`) er en handelsvært og bruges ikke" | `d0c80c3`; PROTOCOL_V3 linje 2106-2109 |
| 08:08:29-31 | Ét GET: `curl -s --max-time 20 'https://api.upbit.com/v1/market/all?isDetails=false'` | MISSION27_4 1a (transskriptets tidsstempel og filens mtime) |
| 08:09 | Punkt 5 committet med tallene "299 KRW-markeder … 231 af dem har en Binance USDT-perp" | `2ae6226` |
| 09:14 | Parfilen (232 par) og låsetekst 6c, som nævner den | `b971d56` |
| 09:20 | `n4_kimchi.py` med `PAIRS`-konstanten | `7012c2b` |
| 09:47 | Punkt 7a/7b: afvigelsen erkendes. Værten er forbudt, og listen bruges "ikke til en lås". B blokeres af datagaten | `7ee4799` |
| 14:02 | Ændring 38 (brugerens "Begge"). B punkt 4: parlisten bruges ikke, og universet bygges igen ved låsen med et nyt `market/all` | `7e3ee44` |
| 22:30 | Ændring 40 (karantæne) | `4ef7ef8` |
| 22:32 | MISSION27_4 1a-1d: audit af afvigelsen | `4731127` |
| 22:41 | `QUARANTINE.json`, gate-tests, `PAIRS` fjernet | `8fac269` |

**Data brugt ved konstruktionen** (parfilens metadata, kun nøgler, tællinger og metadatafelter; se §7 om læsningen):
- **[F]** `sources.upbit` = "api.upbit.com/v1/market/all fetched 2026-11-02 08:08 UTC (file time; current list)".
- **[F]** `sources.binance` = "fapi exchangeInfo snapshot 2026-11-01". Det er sandsynligvis samme øjebliksbillede som
  H27A-universet, exchangeInfo 2026-11-01 kl. 22:13 UTC (PROTOCOL_V3 linje 3971-3972). **[I]**: filen siger ikke, hvilket
  af dagens svar den bruger.
- **[F]** `written` = "2026-11-02 kl. 10:14 lokal", `rule` = "current lists only, no historical data".
- **[F]** Tællinger: `upbit_krw_markets` 299, `overlap` 232, `pairs` 232 poster (felterne `perp` og `multiplier`;
  multiplikator 1 for 229 og 1000 for 3), `excluded` 12 strenge (indholdet er ikke læst).
- **[F]** Upbit-svaret indeholdt 875 markeder med felterne `market`, `korean_name` og `english_name`, 67.961 bytes.
  "Ingen priser, volumen eller historik" (MISSION27_4 1a). Den rå fil ligger kun i en sessions-scratchpad uden for
  repoet. Den er hash-registreret i QUARANTINE (`upbit-raw-2026-11-02`, sha256 `bbdc54fd…`).

**Kode:**
- **[F]** Intet script i repoet har bygget listen. `git log -S N4_KIMCHI_PAIRS` viser kun `b971d56`, `7012c2b`, `7ee4799`,
  `4731127` og `8fac269`, og ingen af dem tilføjer en konstruktionskode.
- **[I]** Krydsningen blev lavet ad hoc i sessionen. Den kan ikke reproduceres fra repoet.
- **[F]** Afvigelse mellem tallene: punkt 5 (08:09 UTC) siger 231 med perp, filen (09:14 UTC) siger 232. Årsagen er ikke
  dokumenteret. **[I]** Den skyldes sandsynligvis en anden optælling, fx om BTC er med eller ej. Det ændrer ikke dommen.

## 3. Hvorfor listen er i karantæne (regel og post ordret)

**Reglen**, PROTOCOL_V3 ændring 40 (linje 4290-4307):
- Punkt 1: filerne "må ikke slettes, overskrives eller bruges af noget værktøj til lås, univers eller analyse".
- Punkt 5: "Udkast B's (n4) punkt 1 og MISSION27_3 punkt 5's tal "299 / 231" mærkes som afledt af afvigelsen; B's
  univers bygges kun fra kaldet under 38 B efter låsen."

**Ændring 38 B punkt 4** (linje 4267-4268): "Afvigelsen kl. 09:08 lokal … er ikke godkendt med tilbagevirkende kraft.
Parlisten fra den bruges ikke. N4's univers bygges igen ved låsen med et nyt `market/all`-kald under denne ændring."

**Posten** i `QUARANTINE.json` (`upbit-pairs-2026-11-02`):
- `source`: "one GET https://api.upbit.com/v1/market/all?isDetails=false at 2026-11-02 08:08:29-31 UTC, before amendment
  38 B; banned then by amendment 17h point 1"
- `forbidden`: "N4's universe, any lock text, any analysis; N4 builds its universe from a new market/all call under 38 B
  after its lock"

**Begrundelsen er procesmæssig.** **[F]** Listen kommer fra en vært, som på det tidspunkt var forbudt (17h punkt 1), og
38 B godkender ikke kaldet bagudrettet. Karantænen skyldes altså ikke, at listen rummer udfaldsdata.

**[F] Fejlcitat:** 7a, 38 B punkt 3 og ændring 40's baggrund kalder forbuddet "17i punkt 1". MISSION27_4 1a retter det
til 17h punkt 1 og lader de gamle tekster stå. QUARANTINE-posten citerer korrekt 17h.

## 4. Så konstruktionen beskyttede data?

| Spørgsmål | Svar | Type |
|---|---|---|
| Priser, afkast eller udfald (s, y, r_d)? | Nej. Upbit-svaret indeholdt kun navne (MISSION27_4 1a). 6-overskriften siger "ingen historiske data læst", og 6e siger "ingen data læst" | [F] |
| 2024+-holdout (priser, news-titler)? | Ikke i konstruktionen. Holdout-bruddet samme dag gjaldt news/1-titler (QUARANTINE post 3) og er en anden sag | [F] |
| Upbit-candles eller explore0-klines for N4? | Nej. `n4_kimchi.py` er skrevet "before any Upbit candle or explore0 kline was read" (docstring), og der findes ingen indlæser | [F] |
| Data efter vinduets start? | **Ja, som tilstand.** Begge lister er dagens (2026-11-01/02), altså efter explore0 og efter 2024-holdoutet | [F] |
| Er overlevelse gennem 2022-2026 kodet ind i universet? | Ja. At en mønt er noteret på Upbit KRW og har en Binance-perp i 11-2026, er en funktion af hændelser i 2022-2026, også i holdout-årene (afnoteringer, nye noteringer). Det er ikke en udfaldsværdi, men det er information fra efter vinduet, og den korrelerer med afkast (overlevere) | [I] |
| Påvirkede listen forskningsretningen? | Ja. "299/231" blev brugt til at prioritere N4 som nr. 2 ("et tværsnit er muligt"). MISSION27_4 1c kalder det "påvirket (forskningsretning, ikke data)" | [F] |
| Påvirkede listen styrkeberegningen? | MISSION27_4 1c siger nej: k følger af MIN_COINS 40, n af explore0-dage. Men antagelsen "n ≈ 550 … over 40 mønter i overlap fra cirka midten af 2020" (6c punkt 7) blev skrevet 09:14 UTC, efter at nutidens overlap var set. Den er ikke kontrolleret og skal udledes igen af en point-in-time-kilde | [F]/[I] |

**Konklusion:**
- Konstruktionen så ingen priser, ingen udfald og intet holdout-indhold.
- Den er et brud på en værtsgate. Universet er betinget af en tilstand fra 2026, altså af post-vindue-information,
  hvilket er overlevelsesskævhed.
- Det sidste gælder også den erstatning, som 38 B punkt 4 foreskriver (et nyt `market/all` ved låsen). Det er heller
  ikke en point-in-time-liste (AMB-19).

## 5. Kan et gyldigt point-in-time-univers bygges uden at se beskyttede resultater?

**Kravet** (FACTORY_SECURITY P1 komponent 5 og FACTORY_MIGRATION_P1 "Krav til nye screeninger" punkt 2):
- Universet skal være en regel fastlagt før data, med senere afnoterede inkluderet.
- Reglen anvendes på et arkivindeks.
- Indeks og medlemsliste hashes ved låsen.
- Et indeks hentet efter låsen giver status RECONSTRUCTED (`factory_security.universe`, linje 187-198).
- **[F]** `factory.py` linje 225-226 afviser FROZEN, hvis `universe_asof` mangler eller ligger efter vinduets start
  ("survivorship: the universe must be fixed as of the window start").

**Kilder, der kan give point-in-time-medlemskab uden priser** (**[I]** for egnetheden, **[F]** for værtsstatus):

| Ben | Kilde | Værtsstatus i dag | Hvad den kan give | Ukontrolleret |
|---|---|---|---|---|
| Upbit KRW-medlemskab | `community-api.coinmetrics.io/v4/catalog-all/markets?exchange=upbit&type=spot` | Tilladt vært ([F] 17h punkt 1; brugt af `upbit/1`) | Første og sidste handel pr. marked, også afnoterede (`catalog-all`) | Dækningsartefakter i første handel (17h punkt 2: 2019-03-15, 187 markeder). Om sidste handel er pålidelig for afnoterede |
| Binance USD-M-perp-medlemskab | data.binance.vision-arkivets filindeks (månedlige og daglige 1h-klines pr. symbol, også afnoterede) | data.binance.vision er tilladt. Indekset læses via S3-listen `s3-ap-northeast-1.amazonaws.com/data.binance.vision?…` (brugt i `research/tsmom_v2_feasibility.py` linje 12) | Første og sidste fil pr. symbol, dvs. eksistens på dag d | Om S3-listeværten er dækket af den samme tilladelse, skal stå udtrykkeligt i teksten (gate-grep før kald) |
| Upbit-priser (signalet) | `api.upbit.com/v1/candles/days` | [F] Kun "til N4's research-værktøj", tidligst 11-14 efter N4's lås (38 B punkt 1-2) | KRW-close pr. dag | [F] Historikkens længde er ukontrolleret (AMB-20). **[I]** Om afnoterede markeder overhovedet har candles. Hvis ikke, består der en restskævhed i prisbenet, selv med point-in-time-medlemskab |
| Alternativ Upbit-pris | CoinMetrics community market-candles | Tilladt vært | Muligvis Upbit-candles | [F] Ukontrolleret. 7d: "kontrolleres med ét katalog-GET tidligst 11-14" |

**Datogrænser** ([F]):
- Historiske forespørgsler tidligst 2026-11-14 og kun efter låsen (38 B punkt 2; Mission 27.2/27.3).
- Kun explore0-rækker.
- Intet 2024+.
- COIN-M er ikke relevant.

**[I] Holdout-forsigtighed:** et katalog med "sidste handel" kan rumme afnoteringsdatoer i 2024-2025. Det er
holdout-periodens metadata (jf. reglen om news-titler). En lovlig indlæser skal censurere ved indlæsning, så sidste
handel efter 2021-12-31 kun gemmes som "levende gennem explore0". Datoen udskrives og gemmes ikke.

**Dom:**
- **[I]** Et point-in-time-medlemskab er muligt fra tilladte kilder uden at se priser eller udfald, tidligst 2026-11-14
  og efter en lås.
- **[I]** Fuld eliminering af overlevelsesskævhed er usikker, fordi Upbit-prisbenet for afnoterede markeder er
  ukontrolleret. Medlemmer uden pris skal tælles og rapporteres for sig, aldrig tavst udelades.
- **[I]** Styrken er åben. En fast liste pr. 2020-03-01 (som `factory.py` kræver bogstaveligt) er sandsynligvis for lille
  til MIN_COINS 40. Cachens filnavne viser 15-66 USD-M-mønter pr. måned i explore0 (MISSION27_3 7c), før krydsningen
  med Upbit. Et dagligt rullende point-in-time-medlemskab (medlem på dag d efter information ≤ d) passer bedre, men
  kræver, at fabrikkens survivorship-check udtrykkeligt læses pr. dag. Det skal skrives i teksten og ikke antages.

## 6. Ændrer en ny universregel eksperimentets identitet?

- **[F]** `factory.fingerprint()` (linje 156-159) er `sha([mechanism_tag, direction, sorted(universe), estimand])`, og
  "A new name with the same fingerprint is the same hypothesis". Omvendt giver et andet univers et andet fingeraftryk,
  altså en ny hypotese. `Register.propose` afviser kun ens fingeraftryk.
- **[F]** B n4's univers er de 232 par i den karantænerede fil (6c punkt 1).
- **[I]** Alle lovlige universer har derfor et andet fingeraftryk:
  - et point-in-time-regelunivers;
  - det nye `market/all`-kald under 38 B punkt 4. Upbits liste ændrer sig mellem 11-02 og 11-14, og selv en identisk
    liste ville have `universe_asof` 2026-11-14 og ikke vinduets start.
- **[I]** Ingen identitetsbevarende præcisering findes. At bevare identiteten kræver netop den forbudte liste.
- **[I]** 38 B punkt 4 og 40 punkt 5 foreskriver allerede et andet univers end 6c. Protokollen accepterede altså den
  11-02, før fabrikken fandtes, i praksis allerede et nyt univers for "N4".
- **[F]** Fabrikkens point-in-time-krav (ordre 49, FACTORY_SECURITY P1) kom senere end 38 B. De to tekster er ikke
  forenet: 38 B kræver et nutidigt `market/all`, mens fabrikken afviser et univers med `universe_asof` efter vinduets
  start.
- **[F] Konsekvensbegrænsning:** 6c punkt 9 siger, at "en PASS giver kun lov til en ny dateret fremadhypotese på census
  og upbit, ingen bane". En skæv PASS koster derfor højst en fremadtest.

**Mekanisme-tag** ([F]): NOV14_READINESS §5 placerer N4 i slægten `cross_venue_perp_gap`. VOCABULARY.json definerer
den som "scanner: Hyperliquid vs Binance perp mid gap". **[I]** Upbit-KRW-præmien passer ikke præcist ind. Et nyt tag
er en familiebeslutning, som ordre 53 ikke åbner ("ingen nye familier"), så det er et åbent punkt.

## 7. Denne audits egen eksponering (ærligt)

- **[F]** Ved strukturinspektionen af parfilen udskrev mit Python-kald ved en fejl hele nøglelisten under `pairs`, altså
  møntsymbolerne, i terminalen. Opgaven bad kun om nøgler, tællinger og metadata.
- Symbolerne står ikke i noget dokument og bruges ikke til noget. Listen indeholder ingen priser.
- Feltet `excluded` er kun talt (12), ikke læst.
- Ingen sha256 af indholdet er beregnet ud over at bekræfte filens hash mod QUARANTINE-posten (match).
- **[I]** Eksponeringen er af samme art som den, MISSION27_4 1c allerede erklærer for forfatteren af 6c (nutidens
  navne). Et nyt N4-udkast skal erklære den.

## 8. Opsummering

1. **[F]** Universet er en fast liste med 232 par: nutidens Upbit `market/all` (08:08 UTC 11-02, forbudt vært ifølge
   17h punkt 1) krydset med Binance exchangeInfo 2026-11-01. Listen blev committet i `b971d56` sammen med 6c, uden
   konstruktionskode i repoet.
2. **[F]** Den er i karantæne for en procesafvigelse (ændring 40 punkt 1/5, 38 B punkt 4, QUARANTINE
   `upbit-pairs-2026-11-02`). Det er ikke fordi den indeholder udfald.
3. **[F]/[I]** Konstruktionen så ingen priser, udfald eller holdout-indhold. Men universet er betinget af en tilstand fra
   2026 og har derfor overlevelsesskævhed. Det gælder også 38 B's erstatning.
4. **[I]** Et point-in-time-univers kan bygges fra tilladte kilder (CoinMetrics-katalog og Binance-arkivindeks) tidligst
   11-14 efter en lås. Upbit-prisbenet for afnoterede markeder og styrken er ukontrollerede.
5. **[F]/[I]** Ethvert lovligt univers giver et nyt fingeraftryk og dermed en ny hypotese. **B n4 kan ikke gøres
   lovlig med bevaret identitet og forbliver BLOCKED.** Mulighederne står i `B_N4_RESOLUTION_OPTIONS.md`.
