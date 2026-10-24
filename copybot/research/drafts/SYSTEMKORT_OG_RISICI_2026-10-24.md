# Systemkort, verificerede påstande og åbne risici — 2026-10-24 kl. 22:10

Master mission "COMPLETE, SELF-CRITICAL MARKET RESEARCH AND EXECUTION-REALITY SYSTEM". Bygget fra koden og
registret (skrivebeskyttet). **V** = verificeret med kode, test eller registret i dag. **A** = antaget eller ikke
verificeret.

## 1. Kæden observation → signal → ordre → fill → P&L (kodestier)

| Trin | Kode | Tabel | Tidsstempler | Status |
|---|---|---|---|---|
| Data | `lab/engine/data.py` (cache, fasevagt), `hypogen.Reader`; live: `moves.detect` (fapi), `news.run`, `onchain.run` | `observations` | bar `open_s`, observation `ts`, nyhed `published_ts`/`usable_from`, on-chain `fetched_ts` | V |
| Signal (scanner) | `scanner.run` → detektorer → `opportunity.move` (deduplikeret 6 t) | `observations`, `events` | scanningstid `ts` | V |
| Signal (baner) | `lane.manage`/`lane.run_one` (fcarry-skabeloner på explore0-valgte mønter) | `events` (`lane.started`, …) | | V |
| Beslutning → ordre | `paper_runner` / `lane.run_one` → `PaperEngine.submit_taker` | `sim_orders` | ordretid `ts` | V |
| Likviditet | bog hentet lige før ordren (`Book.ts`); `risk.entry_allowed` afviser manglende, krydset eller for gammel bog (`data_max_age_s`) | `sim_fills.book_ts` | `book_ts` ≤ ordretid | V |
| Fill | bogvandring på taker-siden; `px = niveau · (1 ± extra_slippage)`; IOC-rest → `sim_cancels` | `sim_fills`, `sim_cancels` | fill `ts` = ordretid (nul latens) | V (latens: A, se risiko 3) |
| Gebyr | `taker_fee · px · q` pr. fill | `sim_fills.fee` | | V |
| Funding | `book_funding`: −qty · open-pris · rate ved hver afregning, mængden lige før afregningen, idempotent (UNIQUE) | `sim_funding` | `settle_ts`, booket `ts` | V (test_lab_paper_funding) |
| Position og P&L | `PaperEngine.ledger`/`pnl` udledes altid af fills og funding; `mark` → `sim_equity` | `sim_equity` | mark `ts` | V (orakeltest i dag) |
| Afstemning | `PaperEngine.reconcile` (overfyld, forældreløse fills, IOC, funding mod fills, kasse); `reportcheck` (natlig, uafhængig SQL) | — | | V |
| Risiko | `risk.py`: stop, pause, FAIL_CLOSED, opvarmning efter genstart, `promotion.exposure_allowed` | `risk_events` | | V (eksisterende tests) |
| Revision | alle tabeller append-only (triggere) og hash-kædede; scanneren skriver i én transaktion | alle | | V |

**Produktionens papirkonti (registret, kl. 22:10):** 20 konti med fills: 9 `FWD_`, 10 `LANE_`, 1 `SHADOW`. 1 972 fills,
alle taker. 0 IOC-rester, 1 afvist ordre. Fill-størrelser 0,5–4 129 USD.

## 2. Verificeret i dag (med bevis)

1. **Regnskab:** uafhængig orakeltest (`tests/test_lab_paper_oracle.py`) over 8 tilfældige sekvenser med vendinger:
   kasse, positioner, basis, urealiseret P&L, equity-invarianten og afstemningen stemmer efter hvert fill.
   **Fejl fundet og rettet (21s):** gebyret ved en positionsvending lå helt på den lukkede handel. 1 af 1 972 fills i
   produktionen (`FWD_E_xs_momentum_p2`, 0,58 USD forkert fordelt). Kasse og equity var uberørte.
2. **Replay:** samme ordre-id to gange ændrer intet (status "duplicate"), og fill- og ordre-id'er er UNIQUE.
3. **Banernes omkostningsopdeling:** rest-posten `price_basis` er identisk med en uafhængig, midtprisbaseret pris-P&L
   for alle 10 bane- og scannerkonti (afvigelse 0,0000). Nu en løbende kontrol (21t). Skrivebeskyttet kørsel mod
   produktionens rapport 2026-10-23: REPORT OK.
4. **Målinger:** én observation pr. markedstime i R1 (21r; genstarter havde dubleret timer). Målelogens interne
   konsistens er 24/24 (21p/21r).
5. **On-chain:** først sete værdi ændres aldrig; revisioner logges separat; `asof(db, t)` (21r).

## 3. De fem alvorligste åbne risici (rangeret)

| # | Risiko | Evidens | Hvad der ville ændre en beslutning | Kan testes nu? |
|---|---|---|---|---|
| 1 | **Ingen strategi har en dokumenteret nettofordel.** Research: 0 PASS i dag. Baner: −220,84 USD (kasseafstemt). fcarry (F1) måles fremad fra 2026-12-01, MVRV fra 2026-11-01 | registret, research-memory | en låst fremadmåling | nej (fremad) |
| 2 | **Nul latens i simuleringen:** taker-fill sker på bogen læst lige før ordren, uden forsinkelse mellem signal og fill. Bogens alder er begrænset (`data_max_age_s`), men prisbevægelsen i de sekunder er ikke modelleret | `submit_taker` | hvis signalerne lever på hurtige bevægelser | **målt kl. 22:11:** alle 1 972 fills har `book_ts`; fill-tid − `book_ts` ligger mellem −0,5 og 0 s (median −0,37 til −0,50 s pr. kontotype). Bogen er altså under 1 s gammel ved fill. Det negative fortegn skyldes, at fill-tiden gemmes afkortet til hele sekunder (`int`), mens `book_ts` er præcis; en kontrol af tidsrækkefølgen skal derfor sammenligne med floor(`book_ts`). Rest-risiko: netværks- og matchinglatens (~0,1–0,5 s) er ikke modelleret; for time- og døgnstrategier er det småt, men målbart først med rigtige ordrer (ikke tilladt) |
| 3 | **Kapacitet er ukendt:** fills er 0,5–4 129 USD; bogomkostning kun målt ved 5 000 USD (ét øjebliksbillede) og ved 160–500 USD for få mønter. Størrelse og mønt er sammenblandede (ANALYSE afsnit 10: INCONCLUSIVE) | ANALYSE afsnit 10, COSTS_2026-10-24 | om en fordel overlever ved en meningsfuld størrelse | **UNTESTABLE_CAPACITY** i dag; en fremadrettet bogkurve ved flere størrelser er mulig (forslag 5) |
| 4 | **Ingen monitor for aftagende fordel:** intet registrerer faldende nettoforventning, stigende omkostninger eller afvigelse mellem forventet og realiseret udførelse | ingen kode | at en fordel stoppes, før den taber | forslag 6 (ingen tærskler vedtaget) |
| 5 | **Omkostningsmodellen for 2020–21 er et estimat** (2026-bogdata overført bagud). R1 viser foreløbig, at målte bøger er under modellen, men data er tynde | 21i, R1 | om screeningskravene er for strenge eller for svage | R1 fra 2026-10-31 |

## 4. Kapacitet (status pr. strategi)

| Strategi | Status | Grund |
|---|---|---|
| Baner og scanner (fcarry-varianter) | **UNTESTABLE_CAPACITY** | ingen dokumenteret nettofordel at skalere; bogdata kun ved få størrelser og mønter |
| F1 fcarry (familie, fremad fra 2026-12-01) | **UNTESTABLE_CAPACITY** (endnu) | fremadmålingen er ikke startet; kræver bogdata ved flere størrelser for familiens mønter |
| MVRV (OBSERVATION) | **UNTESTABLE_CAPACITY** | ingen udførelse endnu |
| FWD_-konti (katalog-fremadtests) | **UNTESTABLE_CAPACITY** | ingen godkendt fordel; små ordrer |

Ingen break-even-størrelse angives, før der findes en fordel og bogdata ved flere størrelser.

## 5. Forslag: fremadrettet kapacitetskurve (kræver en dateret ændring før indsamling)

Én gang i døgnet: for de mønter, banerne og F1 handler, gå bogen igennem ved 500, 2 000, 5 000, 20 000 og 50 000 USD
(fapi/api depth, tilladt vært, kun GET, ~30 kald). Gem rundtur pr. størrelse og den dybde, der er tilgængelig. Det
giver en **nutidig** størrelseskurve (mærket som sådan), aldrig en historisk. Formålet er at kunne svare "ved hvilken
størrelse forsvinder en nettofordel" den dag, en fordel findes.

## 6. Forslag: monitor for aftagende fordel (ingen tærskler vedtaget)

Pr. papirkonto og fremadtest, beregnet fra registret uden nye data:

| Måling | Formel og kilde | Hyppighed | Mindste stikprøve |
|---|---|---|---|
| Nettoforventning | døgnets Δequity (`sim_equity`), døgnklynger | dagligt | ≥ 14 døgn |
| Udførelse: realiseret mod forventet | `sim_fills.slippage` mod modellens halve spread + `extra_slippage` | pr. fill, døgnaggregeret | ≥ 30 fills |
| Omkostning pr. bruttokant | (gebyrer + betalt afstand) / \|pris-P&L\| | ugentligt | ≥ 4 uger |
| Funding og basis | booket funding pr. dag; basis fra fills' midtpriser | dagligt | ≥ 14 døgn |
| Forsinkelse | ordretid − signaltid; `book_ts` − ordretid | pr. ordre | ≥ 30 |
| Datakvalitet | pauser (`data_fetch`, `data_stale`), manglende barer (målelog), on-chain-revisioner | dagligt | — |
| Koncentration | andel af nettoresultatet fra de 3 største døgn og mønter | ugentligt | ≥ 4 uger |

**Statistik (forslag):** tosidet fortegnsskift på døgnklynger mod den låste forventning, hvor en findes. Ellers kun
beskrivende. Holm over målingerne pr. konto. **Status-sprog:** "utilstrækkelige data", "forringelse mistænkt",
"fordel ikke længere støttet". Ingen automatisk handling, ingen tærskel og intet status­skift før en dateret
ændring og brugerens ja. Eksisterende livscyklus (`lifecycle.py`: OBSERVATION, PAPER_TRADING, PAUSED, REJECTED, RETIRED
m.fl.) bruges, og nye tilstande foreslås først i en ændring.

## 7. Kræver godkendelse

Deploy (21s/21t-koden), indsamling af kapacitetskurven (forslag 5), monitorens tærskler (forslag 6), LÅS, C, data
før 2026-11-14.
