# FOMO Copybot 30 s · datakilde-matrix (direktørordre 56, P1)

Skrevet 2026-11-08 22:37 UTC (23:37 CET). Kun design.
**Status: DATAINDSAMLING IKKE GODKENDT · LIVE-HANDEL NO-GO.**

Påstanden: fomo-appens "Grok Bot" kopierer top-memecoin-traderes Solana-køb 30 s senere, med TP 10× og tidsstop.

Sådan er dokumentet lavet:
- Kun offentlige dokumentations- og prissider er læst (WebFetch/WebSearch). Ingen data-endpoint er kaldt.
- Ingen konti, ingen login, ingen nøgler. fomo-appen er ikke åbnet.
- Sider, der ikke kunne nås, står som "UNVERIFIED (blokeret/ikke nået)". Der er ikke prøvet omveje.
- Et lokalt DNS-filter (192.168.1.3) blokerer nogle værter. Det er ikke testet. Tilgængelighed er ikke garanteret.
  Under læsningen gav `developers.jup.ag` og `www.quicknode.com` DNS-fejl (EAI_AGAIN).
- "Lab målt" betyder tal fra den gamle CopyBot (15.–16.10.2026, commits `586fcbb`, `8d40c9e`). De er ikke dokumentation.

## 1. Lokale regler, der gælder for alle kilder

| Regel | Kilde | Betydning her |
|---|---|---|
| Kun værter på `ALLOWED_HOSTS` | `tests/test_lab_safety.py` l. 19-42 | Ingen Solana- eller memecoin-vært står på listen. |
| Ny vært kræver ejer-ja + dateret ændring | `research/PROTOCOL_V3.md` ændring 11 punkt 8 (l. 968-973) | Mønstret: vært, metode, formål, "kun med brugerens godkendelse". |
| Kun GET, ingen signering, ingen nøgler | samme ændring; `SECRET_ENV`, `FORBIDDEN_TEXT` i testen | Nøgle-kilder er udelukket. |
| Kun én funktion må sende en body, og kun til Hyperliquid /info | `BODY_SENDERS`, `BODY_TARGETS` i testen | Solana JSON-RPC (POST) er i strid med dette i dag. |
| `websocket`/`websockets` må ikke importeres | `FORBIDDEN_IMPORTS` i testen | Ingen `logsSubscribe`; kun polling. |
| Ingen historiske forespørgsler før 2026-11-14 | PROTOCOL_V3 ændring 24a (l. 3575) | Ingen tilbagefyldning nu. Fremad-only. |
| 2024 er holdout, 2025+ reserveret | PROTOCOL_V3 l. 702, 1363 | Gælder lab'ens markedsdata; berører ikke 2026-memecoins direkte, men ingen læsning af 2024-filer. |
| COIN-M fra 2026-11-28; `api.upbit.com` kun N4 fra 11-14 | PROTOCOL_V3 l. 648, 4260-4265 | Ikke relevant for Solana; ingen undtagelse at låne. |

`grep` i PROTOCOL_V3 efter solana, helius, publicnode, geckoterminal, dexscreener, kolscan, jupiter, birdeye, pump.fun,
memecoin og fomo giver **0 træf**. Ingen af kilderne herunder har en gate. Status for alle er derfor:
**IKKE PÅ TILLADT LISTE — kræver ejer-ja + dateret ændring.**

## 2. Datakrav

| # | Behov | Hvorfor |
|---|---|---|
| 1 | Leder-identitet og alle lederens swaps (signatur, slot/blockTime, mint, side, mængder) | Lederreglen og hver kopi. |
| 2 | Token/pool (mint → pool, venue: pump.fun-kurve, PumpSwap, Raydium, Meteora; ruter via Jupiter) | Rigtig pool til prisimpact. |
| 3 | Poolreserver/likviditet ved leder-tid og leder+30 s | x·y=k-impact for følgeren. |
| 4 | Priser langs holdeperioden (1 s, 1 min) | TP 10× og tidsstop. |
| 5 | Omkostninger: DEX-gebyr, pump.fun-gebyr, priority fee/Jito-tip, netværksgebyr, bot-gebyr | Netto. fomo's bot-gebyr er **UKENDT**. |
| 6 | Døde pools, rugs, migrering (pump.fun → PumpSwap), ikke-eksekverbare fills | Ingen overlevelsesbias. |

## 3. Matrix A · hvad hver kilde dækker

| # | Kilde (vært) | Behov 1-6 | Felter | Tidsopløsning |
|---|---|---|---|---|
| 1 | Offentlig Solana RPC (`api.mainnet-beta.solana.com`) | 1 ✓ 2 ✓ 3 ✓ (fra tx-saldi) 4 ◐ (rekonstrueret) 5 ✓ (undtagen bot) 6 ✓ | `getSignaturesForAddress`, `getTransaction` (pre/postTokenBalances, fee, logs), `getAccountInfo`/`getMultipleAccounts` | slot (~0,4 s), blockTime i sekunder |
| 2 | PublicNode (`solana.publicnode.com`) | som 1, men kort historik | samme JSON-RPC | som 1; lab målt: kun ~1 dags historik |
| 3 | Helius (`*.helius-rpc.com`) | 1-6 som RPC + `getTransactionsForAddress` (hele tx, 1000 pr. kald) | JSON-RPC + egne API'er | slot |
| 4 | Triton One (`*.rpcpool.com/<NØGLE>`) | som RPC | JSON-RPC, gRPC | slot |
| 5 | QuickNode | som RPC | JSON-RPC | slot |
| 6 | Shyft (`*.shyft.to`) | som RPC + indekserede tx | JSON-RPC, REST, gRPC | slot |
| 7 | GeckoTerminal (`api.geckoterminal.com`) | 2 ✓ 3 ◐ (kun nu) 4 ✓ (OHLCV) 6 ◐ | pool, reserve_in_usd, OHLCV | min. 1 min |
| 8 | DexScreener (`api.dexscreener.com`) | 2 ✓ 3 ◐ (kun nu) 4 ✗ 6 ◐ | pairAddress, dexId, priceNative, liquidity.base/quote, pairCreatedAt | øjebliksbillede |
| 9 | Birdeye (`public-api.birdeye.so`) | 1 ◐ 2 ✓ 4 ✓ 6 ◐ | trades, OHLCV, token-info | ned til sekunder (påstået) |
| 10 | Solscan Pro API (`pro-api.solscan.io`) | 1 ✓ 2 ✓ 5 ◐ | konto-tx, defi-aktivitet | blockTime |
| 11 | Bitquery (GraphQL) | 1 ✓ 2 ✓ 3 ◐ 4 ✓ | `Solana.DEXTrades` på tværs af DEX'er | blok |
| 12 | Dune (`api.dune.com`) | 1 ✓ 2 ✓ 4 ✓ (SQL) | dex_solana.trades m.m. | blok, forsinket indeksering |
| 13 | Jupiter (`api.jup.ag`, tidl. `lite-api.jup.ag`) | 2 ◐ (rute) 3 ◐ (quote nu) 4 ◐ (pris nu) | quote: outAmount, priceImpactPct, routePlan | kun nu |
| 14 | pump.fun frontend-API (uofficiel) | 2 ◐ 6 ◐ (graduation-flag) | coin-data, kurve-status | øjebliksbillede |
| 15 | kolscan.io (scrape) | kun lederudvælgelse | rangliste, PnL, vinderandel | dag/uge/måned |
| 16 | fomo-appen | påstået: lederliste og botens handler | ukendt | ukendt |

✓ dækker · ◐ delvist · ✗ nej.

## 4. Matrix B · grænser, PIT, reproduktion og anbefaling

| # | Gratis/grænse (dokumenteret, URL) | Nøgle? | PIT ved leder-tid og +30 s | Reproducerbar? | PROTOCOL_V3 | Anbefaling |
|---|---|---|---|---|---|---|
| 1 | 100 kald/10 s pr. IP, 40/10 s pr. metode (https://solana.com/docs/references/clusters; kun set i søgeuddrag, siden gav HTTP 429 → delvist UNVERIFIED). Lab målt: 1 kald/s stabilt, 429 fra ~1,5-3/s | Nej | Ja. Reserver efter hver tx ligger i `postTokenBalances`/lamports. +30 s: reserver efter sidste tx med blockTime ≤ t+30, eller live-aflæsning fremad | Ja (signaturer) | IKKE PÅ TILLADT LISTE — kræver ejer-ja + dateret ændring | TILLAD-KANDIDAT |
| 2 | UNVERIFIED (ingen grænse på https://www.publicnode.com/). Lab målt: ~10× hurtigere end 1 | Nej | Ja fremad (live-aflæsning ved +30 s); kort historik | Ja (signaturer) | IKKE PÅ TILLADT LISTE — kræver ejer-ja + dateret ændring | TILLAD-KANDIDAT |
| 3 | Free: 1M credits/md., 10 req/s (https://www.helius.dev/pricing). `getTransactionsForAddress` fra Developer-plan (https://docs.helius.xyz/docs/billing/credits.md, søgeuddrag) | Ja (konto) | Ja (on-chain) | Ja | IKKE PÅ TILLADT LISTE | AFVIS (nøgle) |
| 4 | Tilmelding og $125-indskud (https://triton.one/pricing, søgeuddrag); ingen gratis grænse fundet → UNVERIFIED | Ja (i URL) | Ja | Ja | IKKE PÅ TILLADT LISTE | AFVIS (nøgle, betaling) |
| 5 | UNVERIFIED (blokeret/ikke nået: `www.quicknode.com/pricing`, EAI_AGAIN) | Ja (endpoint-token) | Ja | Ja | IKKE PÅ TILLADT LISTE | AFVIS (nøgle) |
| 6 | Free 10 RPC req/s, 1 index req/s; anden kopi siger 20 RPC req/s (https://shyft.to/solana-rpc-grpc-pricing, søgeuddrag, modstridende) → UNVERIFIED | Ja | Ja | Ja | IKKE PÅ TILLADT LISTE | AFVIS (nøgle) |
| 7 | 30 kald/min offentligt (https://support.coingecko.com/hc/en-us/articles/22612838274841-Does-GeckoTerminal-have-an-API, søgeuddrag; apiguide.geckoterminal.com viderestiller til docs.coingecko.com) | Nej | Nej for reserver (kun nu). OHLCV er efterfølgende aggregat, ikke eksekverbar pris | Delvist (aggregat, kan revideres) | IKKE PÅ TILLADT LISTE | KUN DOKUMENTATION / krydstjek |
| 8 | 60 req/min for profil-/meta-endpoints (https://docs.dexscreener.com/api/reference). Pair-endpoints: 300/min kun i tredjepartskilder → UNVERIFIED | Nej | Nej (kun nu; ingen historik/OHLCV på siden) | Nej | IKKE PÅ TILLADT LISTE | KUN DOKUMENTATION |
| 9 | Wallet-API 30 rpm (https://docs.birdeye.so/docs/rate-limiting, søgeuddrag); plantal UNVERIFIED | Ja | Delvist (egen indeksering) | Nej (lukket) | IKKE PÅ TILLADT LISTE | AFVIS (nøgle) |
| 10 | Lite: 1.000 req/60 s, 20M CU, $49/md. (https://docs.solscan.io/api-access/solscan-api-lite-plan); gratis niveau UNVERIFIED | Ja (`token`-header) | Delvist | Delvist | IKKE PÅ TILLADT LISTE | AFVIS (nøgle) |
| 11 | Prøve: 1.000 punkter, 7 dage; Personal 30 req/min (https://bitquery.io/pricing) | Ja | Delvist (egen indeksering) | Delvist | IKKE PÅ TILLADT LISTE | AFVIS (nøgle, betaling) |
| 12 | Free: "API access Not available" (https://docs.dune.com/api-reference/overview/rate-limits) | Ja + betaling | Delvist | Ja for SQL, men data er Dunes | IKKE PÅ TILLADT LISTE | AFVIS |
| 13 | Nøglefri 0,5 req/s; free med nøgle 1 req/s; `lite-api` udfases 2026-01-31 (https://developers.jup.ag/docs/portal/rate-limits, søgeuddrag; siden selv: UNVERIFIED (blokeret/ikke nået)) | Nu: ja | Nej (kun nu, ingen historik) | Nej | IKKE PÅ TILLADT LISTE | AFVIS (nøgle; kun nu) |
| 14 | Ingen officiel dokumentation → UNVERIFIED | Nej (uofficiel) | Nej | Nej | IKKE PÅ TILLADT LISTE | AFVIS (uofficiel, kan ændres) |
| 15 | Ingen officiel API-dokumentation → UNVERIFIED | Nej (scrape) | Nej (rangliste er efterfølgende) | Kun via committet snapshot | IKKE PÅ TILLADT LISTE | KUN DOKUMENTATION (lederkilde, se afsnit 5) |
| 16 | Ingen dokumentation | Konto + login | Nej | Nej | IKKE PÅ TILLADT LISTE | AFVIS (konto/login; ordre 56) |

Kendte faldgruber fra den gamle CopyBot (gælder kilde 1-2):
- Spam: ~1.000 transaktioner/dag pr. KOL-wallet; én wallet ("Jijo") havde 60.000/dag og blev udelukket.
  Ved 1 kald/s kan én wallet ikke følges. Lederreglen skal derfor have et loft over tx/dag, fastsat før data.
- Version-1-transaktioner manglede, indtil `maxSupportedTransactionVersion` blev hævet (fejlkode -32015).
- Forkert poolstørrelse ved ruter: sidste led kan være en stor SOL/USDC-pool. Reserven skal tages fra en konto, der
  også holder memecoinen (`swaps.py` i `586fcbb`).
- Koncentreret likviditet (Orca Whirlpool, Raydium CLMM, Meteora DLMM) følger ikke x·y=k. Disse fills er ikke
  modelbare med x·y=k og skal mærkes, ikke gættes.
- Lab målt gebyr i PumpSwap-pools: 0,274-0,275 % (`FORSKNING.md` afsnit 12). pump.fun-kurvens gebyr: UNVERIFIED.

## 5. Lederudvælgelse (særskilt problem)

- Videoens "top traders" er ikke offentlig og ikke point-in-time. Listen kan være valgt efter, at de vandt.
- Lederreglen skal derfor låses **før** data. To mulige veje:
  1. Et kolscan-snapshot, som ejeren selv gemmer manuelt. Filen committes med SHA-256 og tidsstempel før første
     udfald. Lab'en henter ikke kolscan. Snapshot-tid er grænsen: kun handler efter den tæller.
  2. On-chain kriterier, fx købere i nye PumpSwap-pools med ≥ N handler og ≤ M tx/dag. Reglen skrives før data og
     anvendes kun på perioden efter låsen.
- Lab-forhistorie (ikke evidens for denne test): kolscan-KOL'er kopieret 10 s senere gav −15 %/handel; selv 0 s og
  uden gebyrer −6,5 % (`FORSKNING.md` test 1).
- kolscan skulle ifølge tredjepart være opkøbt af pump.fun. UNVERIFIED.

## 6. Minimal tilladt sti

Kun fremad. Kun nøglefri, læse-only JSON-RPC. Alt kan efterregnes fra on-chain signaturer.

| Vært | Metoder | Dækker | Foreslået loft |
|---|---|---|---|
| `solana.publicnode.com` | `getSignaturesForAddress`, `getTransaction`, `getMultipleAccounts`, `getSlot` | 1-6 (fremad) | ≤ 2 kald/s (ingen dokumenteret grænse; skal sættes lavt) |
| `api.mainnet-beta.solana.com` | samme | reserve, failover og 1-2 dages efterkontrol | ≤ 1 kald/s (lab målt; under dokumenteret 100/10 s) |

Sådan dækkes behovene:
- 1: poll hver leders signaturer; hent hver tx. Lederens tid = blockTime/slot.
- 2-3: pool og reserver læses fra lederens egen tx. Ved +30 s: `getMultipleAccounts` på pool-kontiene, og gem slot.
- 4: poll pool-konti fremad (fx hvert 5.-10. s inden for loftet). 1 s-opløsning er ikke mulig ved 1-2 kald/s for
  flere åbne positioner; det skal stå som begrænsning i protokollen.
- 5: netværks- og priority fee fra tx-meta; Jito-tip som overførsel til tip-konto; DEX-gebyr fra reserveændring.
  Bot-gebyr: scenarie (0 %, 1 %, ...) fastsat før data, fordi fomo's er ukendt.
- 6: pool uden handler, tom reserve eller migrering ses on-chain. Køb, der ikke kan fyldes inden for impactloftet,
  tælles som "ikke eksekverbar", ikke slettes.

Valgfrit krydstjek: `api.geckoterminal.com` (GET, ≤ 10 kald/min, under dokumenteret 30/min) for 1 min-priser.
Bruges aldrig til fills.

Ejergodkendelser, der skal til (hver for sig):
1. `solana.publicnode.com`: JSON-RPC, de fire metoder ovenfor, loft ≤ 2 kald/s, ingen nøgle, kun læsning.
2. `api.mainnet-beta.solana.com`: samme metoder, loft ≤ 1 kald/s, ingen nøgle, kun læsning.
3. (Valgfri) `api.geckoterminal.com`: GET pool/OHLCV, loft ≤ 10 kald/min.
4. Hver godkendelse skal ind som en **dateret PROTOCOL_V3-ændring** (mønster: ændring 11 punkt 8) og derefter i
   `ALLOWED_HOSTS` i `tests/test_lab_safety.py`.
5. Dataindsamling i det hele taget (ordre 56 siger NO-GO indtil protokol og kilder er godkendt).

**Regelkonflikt:** Solana JSON-RPC bruger HTTP POST med en body. Lab'ens sikkerhedstest tillader kun GET, og kun
`scanner.py http_post` til Hyperliquid /info må sende en body (`BODY_SENDERS`, `BODY_TARGETS`). Det er en
regelkonflikt, som ejeren skal afgøre. Indtil da gælder den strengeste regel: **ingen POST til Solana RPC, og dermed
ingen Solana-data.** Websocket er også forbudt (`FORBIDDEN_IMPORTS`), så kun polling er mulig.

## 7. Hvad der IKKE kan lade sig gøre under gældende regler

- Helius, Triton, QuickNode, Shyft, Birdeye, Solscan, Bitquery, Dune, Jupiter: alle kræver nøgle og/eller konto.
- `getTransactionsForAddress` (den hurtige historik) findes kun hos Helius og kræver betalt plan.
- Tilbagefyldning (backtest af fortiden) før 2026-11-14. Også derefter kræver det en godkendt vært.
- fomo-appens egen lederliste og botens egne handler: kræver konto og login. Påstandens "+900 %" kan derfor ikke
  efterregnes direkte, kun påstandens regel.
- Historiske poolreserver fra REST-aggregatorer (GeckoTerminal, DexScreener): de giver kun "nu".
- 1 s-prissti for mange samtidige positioner ved 1-2 kald/s.
- Følge wallets med tusindvis af tx/dag på gratis RPC.
- Enhver Solana-forespørgsel overhovedet, så længe POST-konflikten ikke er afgjort.

## 8. Åbne spørgsmål til ejer/direktør

1. Må lab'en sende JSON-RPC POST (kun læse-metoder) til Solana-værter? Hvis ja: skal sikkerhedstesten udvides med en
   lukket liste af metoder, og hvem godkender teksten?
2. Hvilke værter: kun PublicNode, eller PublicNode + offentlig Solana RPC? Og med hvilke lofter?
3. Lederkilde: manuelt kolscan-snapshot (ejeren gemmer, vi committer hash), eller on-chain kriterier? Hvor mange
   ledere, og hvilket loft over tx/dag?
4. Bot-gebyr: hvilke scenarier låses (fx 0 %, 1 %, 2 %), når fomo's gebyr er ukendt?
5. Hvordan behandles koncentreret likviditet (CLMM/DLMM): udeluk fra primær analyse, eller mærk som ikke-modelbar?
6. Er GeckoTerminal-krydstjek ønsket, eller skal stien være ren on-chain?
7. Startdato for fremad-indsamling, og forholdet til driftsregel B (ingen genstart før 11-28) og K3-vinduer.
8. Skal "7:00" fra videoen (tidsstop?) verificeres via en offentlig kilde, eller markeres UKENDT i protokollen?
