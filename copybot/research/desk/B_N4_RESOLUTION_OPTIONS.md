# B n4: løsningsmuligheder (direktørordre 53 P1; højst to)

Skrevet 2026-11-06 kl. 16:20 lokal (15:20 UTC). Bygger på `B_N4_QUARANTINE_AUDIT.md`. Dette er forslag og ikke en
lås. Intet er ændret, og ingen data er åbnet. En tekstpakke er ikke en signatur (ordre 53).

**Udgangspunkt:**
- Ingen præcisering bevarer B n4's identitet. Universet indgår i fingeraftrykket (`factory.fingerprint`), og den eneste
  liste, der bevarer det, er den karantænerede (audit §6).
- **I begge muligheder forbliver B n4 (6c som skrevet) BLOCKED.** Teksten kan ikke indsættes ordret (AMB-18), og
  `n4_kimchi.py` får ingen lås med "metode n4".

## Mulighed A (anbefalet): B n4 lukkes før lås; ny, separat protokol N4b med point-in-time-univers

**Indhold:**
1. **B n4** lukkes som `WITHDRAWN_BEFORE_LOCK`:
   - ingen dataadgang og intet alfaforbrug (der er aldrig testet);
   - 6c, parfilen og QUARANTINE står uændret som dokumentation.
2. **N4b** er en ny protokolfil, fx `research/desk/protocols/N4B_v1.md`. Den skrives og committes før enhver
   dataadgang og indsættes ved låsen ordret som næste ledige ændring "metode n4b".
   - **Mekanisme, signal, udfald, portefølje, afgørelse og konsekvens** (6c punkt 2-6 og 9) kan genbruges ordret. Ifølge
     MISSION27_4 1c er de ikke afledt af afvigelsen.
   - **Universregel**, skrevet før data og i stedet for 6c punkt 1:
     - Mønt c er medlem på dag d, hvis dens Upbit-KRW-marked havde første handel ≤ d − 30 dage og ikke var afnoteret
       før d. Kilde: CoinMetrics `catalog-all/markets?exchange=upbit&type=spot`, kvote `krw`, afnoterede med.
     - Samme mønt skal have en Binance USD-M USDT-perp, der findes i data.binance.vision-arkivets filindeks med første
       fil ≤ d − 30 dage og en 1h-klinefil for d. Afnoterede symboler skal med.
     - Parring sker på samme basissymbol efter fjernelse af et numerisk multiplikatorpræfiks (1000/1000000).
     - BTC og fiat-stablecoins udelades efter en navngiven regel i teksten, ikke efter en liste afledt af nogen data.
   - **As-of:** kataloget og indekset hentes én gang hver efter låsen og hashes ved hentning. De får status
     RECONSTRUCTED, ikke LOCKED (`factory_security.universe`), fordi indekset hentes efter låsen. Det skal stå i
     resultatet.
   - **Censur:** sidste-handelsdatoer efter 2021-12-31 gemmes kun som "levende gennem explore0" og udskrives aldrig.
     Det er 2024+-metadata.
   - **Restskævhed:** medlemmer, som Upbit ikke leverer candles for (fx afnoterede), tælles og rapporteres for sig. Er
     andelen af medlems-dage uden Upbit-pris over en grænse, der fastsættes i teksten (forslag 20 %), kan udfaldet højst
     blive INCONCLUSIVE.
   - **Styrke** (ændring 32, før data): MIN_COINS og n udledes igen af medlemstallene pr. dag fra indekset. Det er kun
     metadata, efter låsen og før priser. Er MDE > 2 × gulvet (0,46 %/dag), stopper N4b som INSUFFICIENT_POWER uden
     at hente priser. Det står i teksten, før indekset ses.
   - **Fabrikken:** `factory.py` kræver `universe_asof` ≤ vinduets start. Et dagligt rullende point-in-time-medlemskab
     kræver, at teksten udtrykkeligt definerer `universe_asof` pr. dag (medlemskab på d kun ud fra information ≤ d).
     Ellers skal man vælge en fast liste pr. 2020-03-01, som sandsynligvis fejler MIN_COINS. Valget træffes i teksten.
   - **Alfa:** egen test, 1 ved α 0,005, +1 forsøg til DSR, uden for W0. Slægt `cross_venue_perp_gap` som i
     NOV14_READINESS. Det upræcise tag er et åbent punkt; ordre 53 tillader ingen nye familier.
   - **Eksponering** (erklæres i teksten): forfatteren og auditøren har set nutidens Upbit-navne og overlap-tallene
     299/231/232 (MISSION27_4 1c; audit §7).

**Ejerens tekst** (skal dateres og nævne version og hash; udfyldes, når N4B_v1.md er committet):

> "Jeg godkender [dato]:
> (1) B n4 (MISSION27_3 6c, commit `586a34d`, sha256 `103fd0af…`) låses ikke og lukkes uden dataadgang.
> (2) N4b-protokollen `research/desk/protocols/N4B_v1.md`, commit `<hash>`, sha256 `<sha256>`, må indsættes ordret som
> næste ledige ændring 'metode n4b' tidligst 2026-11-14 00:00 UTC.
> (3) Ændring 38 B's Upbit-tilladelse (`candles/days`, samme begrænsninger: 1 samtidig, ≥ 0,2 s, kun explore0-rækker,
> kun efter låsen) gælder også N4b's research-værktøj.
> (4) Efter låsen må CoinMetrics' `catalog-all`-katalog for Upbit og data.binance.vision-arkivets filindeks (inkl. den
> S3-liste, der viser det) hentes én gang hver til universet."

**Hvorfor punkt 3 og 4 er nødvendige:**
- 38 B er skrevet "kun til N4's research-værktøj". Om N4b er N4, er en fortolkning, så jeg læser det fail-closed.
- S3-listeværten står ikke udtrykkeligt i nogen gate.

**Risici:**
- Upbit leverer måske ikke candles for afnoterede markeder. Så består der en restskævhed, som rapporteres, men ikke
  repareres.
- CoinMetrics' første handel har dækningsartefakter (17h punkt 2).
- Styrken kan falde under kravet. Så får vi et tidligt stop uden resultat.
- Ticker-kollisioner og omdøbninger kan give forkerte par.
- Mere kode: universbygger, indlæser og syntetiske tests.
- Fabrikkens per-dag-fortolkning skal skrives uden at svække survivorship-checket.

**Tidligste lovlige datoer:**
- Teksten kan skrives og committes nu (et udkast, ingen data).
- Låsen kræver ejerens daterede ja ovenfor, med virkning tidligst 2026-11-14 00:00 UTC.
- Katalog- og indekshentning, styrkekontrol og candles først efter låsecommitten og tidligst 2026-11-14.
- Kørslen sker efter en testet indlæser og grøn suite. Realistisk tidligst 11-14 og sandsynligvis senere.

**Fortsat blokeret:**
- B n4 og enhver lås med "metode n4".
- Brug af parfilen og den rå Upbit-fil til noget som helst.
- `api.upbit.com` for andet end N4/N4b's værktøj og før låsen.
- U1F (17i) er uændret og bruger fortsat CoinMetrics.
- 2024+-holdoutet.
- `n4_kimchi.py run`, som forbliver afvisende. N4b får sit eget værktøj eller en ny metode-regex, skrevet efter teksten.

## Mulighed B (ikke anbefalet): 38 B-vejen som skrevet, men som ny hypotese med erklæret overlevelsesskævhed

**Indhold:**
- 6c genbruges, men punkt 1 erstattes af ejerens formulering: "universet er Upbit KRW-markederne fra ét nyt
  `market/all`-kald efter låsen (38 B punkt 4), krydset med Binance USD-M-perps fra `<angivet kilde og as-of>` (AMB-19);
  BTC og stablecoins udeladt".
- Det er protokollens egen foreskrevne vej (38 B punkt 4, 40 punkt 5, OWNER_DECISIONS D2).

**Ærlig vurdering:**
- **Det er ikke en identitetsbevarende præcisering.** Listen og `universe_asof` (2026-11-14) adskiller sig fra 6c's
  liste, så fingeraftrykket er nyt. Det skal derfor registreres som en ny hypotese (fx N4-cur) og ikke som "B n4".
- **Fabrikken afviser det.** `factory.py` linje 225-226 afviser FROZEN, fordi `universe_asof` ligger efter vinduets
  start. Det kan kun køre uden for fabrikken som et PROTOCOL_V3-værktøj, i modstrid med ordre 49's point-in-time-krav.
- **Karantænen er kun opfyldt formelt.** Et nyt kald 12 dage senere giver med stor sandsynlighed næsten samme liste,
  som forfatteren allerede har set. **[I]**
- **Overlevelsesskævheden er strukturel.** FACTORY_MIGRATION_P1 (der citerer P3) målte +6 til +12 bp/dag i syntetiske
  verdener for tværsnit. Det svarer til 13-26 % af gulvet, i en anden sammenhæng.
- **Konsekvensen er begrænset** af 6c punkt 9: en PASS giver kun en ny dateret fremadhypotese. Det er den eneste grund
  til, at muligheden er medtaget.

**Ejerens tekst:**

> "Jeg godkender [dato]: N4-cur = MISSION27_3 6c (commit `586a34d`, sha256 `103fd0af…`) med punkt 1 erstattet af
> `<ordret formulering inkl. Binance-kilde og as-of>`, indsat ordret som næste ledige ændring 'metode n4' tidligst
> 2026-11-14 00:00 UTC. Universet er ikke point-in-time; resultatet mærkes SURVIVORSHIP_KNOWN og kan højst give en ny
> dateret fremadhypotese. Fabrikkens survivorship-gate gælder ikke for denne PROTOCOL_V3-test."

Den sidste sætning er en undtagelse fra en gate, altså en sikkerhedssvækkelse. Den skal stå på ejerens
"spørg først"-liste.

**Risici:**
- En falsk ledetråd på grund af overlevelsesskævhed.
- Præcedens for at omgå fabrikkens point-in-time-krav.
- Navneforvirring med B n4.
- Upbit-historikkens længde er ukontrolleret (AMB-20).

**Tidligste lovlige dato:** låsen 2026-11-14 00:00 UTC efter ejerens daterede ja. `market/all` og candles kommer
derefter.

**Fortsat blokeret:**
- B n4 med 6c punkt 1 som skrevet.
- Parfilen.
- `api.upbit.com` før låsen.
- Fabriksregistrering som FROZEN.

## Anbefaling

**Mulighed A.**
- B n4 forbliver BLOCKED og lukkes før lås uden alfaforbrug.
- N4b skrives som ny protokol med point-in-time-regel, egen alfa og tidligste data 2026-11-14 efter lås og ejerens
  daterede ja med version og hash.
- Mulighed B er kun med for fuldstændighedens skyld. Den er lovlig efter 38 B's ordlyd, men bryder fabrikkens
  point-in-time-krav og bevarer heller ikke identiteten.
- Uden et ejer-ja til én af dem sker der intet med B/N4 den 14/11, og Upbit-gaten forbliver lukket
  (OWNER_DECISIONS D2).
