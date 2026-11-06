# LIQREC1 v1: to-regime-genopretning af likviditet efter markedsstress (direktørordre 51 P2, udkast)

**Status: UDKAST, beslutning PARKED (INSUFFICIENT_POWER).** Intet er godkendt, ingen skabelon er godkendt, ingen alfa er
opkrævet, og ingen data er åbnet eller testet. Skrevet 2026-11-06 ca. kl. 14:55 lokal (13:55 UTC) i dev-worktree.
Udkastet er skrevet færdigt, så mekanismen ikke senere foreslås igen uden styrkeberegningen; det går ikke til
ejergodkendelse i denne form.

## 1. Mekanisme og litteratur

- **E16** (Lim, *Journal of FinTech and Digital Assets* 1(2), 2026; fagfællebedømt, uafhængig forfatter, **én
  hændelse**): efter likvidationskaskaden 10-10-2025 på Hyperliquid (BTC, ETH, SOL, XRP, DOGE) normaliseredes quoted
  spreads hurtigt (puljet median top 9,4 bp, p95 87,5 bp; tilbage inden for 1,2 × niveauet før hændelsen inden for 23
  dage), mens **dybden efter 23 dage stadig lå på 66–79 %** af niveauet før for 4 af 5 mønter. Kursreversal er ikke
  undersøgt.
- **E04, E03:** arbitrage- og likviditetskapital er knap; marginspidser og likvidationer gør den dyr at stille.
- **Mekanisme, der testes:** en market maker kan stille en tæt top-of-book med lille størrelse næsten med det samme,
  men dyb likviditet kræver lager og risikokapital, som stresshændelsen har brugt op eller fået risikogrænser til at
  stramme. Derfor to regimer: spread kommer hurtigt tilbage, dybde langsomt.
- **Hvorfor det er et spørgsmål for lab'et:** omkostningsmodellen og papirmotoren (20 niveauer) antager samme dybde
  efter en hændelse som før. Straks-bogen (ændring 41) handler netop usædvanlige bevægelser; R1/costreport og
  straks-fyldene måler kun omkostningen i samme time, ikke over de følgende dage.

## 2. Primær hypotese, estimand, retning og falsifikator

- **H1:** 7 døgn efter en markedsstressdag er top-of-book-dybden på tværs af Binance USDT-krypto-perps lavere end
  niveauet før hændelsen, ud over den ændring, der ses over samme afstand på ikke-hændelsesdage.
- **Primær estimand:** E[L_j], gennemsnittet over hændelser j af
  L_j = middel_i ln(dep_i(D+7) / dep_i(base)) − median over placebodage D′ af middel_i ln(dep_i(D′+7) / dep_i(base′)).
- **Retning:** negativ (ensidet; H0: E[L] ≥ 0).
- **Falsifikator:** gennemsnittet af L ≥ 0 (ingen vedvarende dybdesvækkelse).

## 3. Primær test (K = 1)

1. **Stressdag D:** |ln(BTCUSDT-mark ved D+1 00:00 / mark ved D 00:00)| (census) ≥ 3 × sd af de foregående 60 daglige
   log-afkast (mindst 55). Afklynget: ingen ny hændelse inden for 21 døgn efter den forrige (så basis- og udfaldsvinduer
   ikke overlapper en anden hændelse).
2. **Dybde pr. perp og døgn:** dep_i(d) = median over døgnets timerækker i fwd_tob_universe af
   (bidQty·bid + askQty·ask) / 2 i USD (top-of-book-notional; gyldighed som i LIQPROXY1 afsnit 3). Mindst 20 af 24
   timer.
3. **Basis:** dep_i(base) = median af dep_i(d) for d i [D − 14, D − 2] (D − 1 udelades mod foregribelse). Udfald ved
   D + 7.
4. **Placebo:** dagene D′ i [D − 60, D − 22] uden hændelse i [D′ − 14, D′ + 7], samme konstruktion; medianen over
   placebodagene trækkes fra.
5. **Test:** ensidet t på {L_j} med t(n − 1), n = antal hændelser. Beslutning ved α_F = 0,0125.
6. **Afgørelser:** PASS (middel < 0 og p ≤ 0,0125), REJECT (middel ≥ 0), INCONCLUSIVE (ellers eller ved for få hændelser).

## 4. Univers (point-in-time)

Ved D − 14 00:00: census `coin_perps` (USDT-krypto, TRADING), `quoteVolume` ≥ 1 mio. USD, first_seen ≥ 30 døgn, ikke
tick-bundet (tickSize/mark < 8 bp, fwd_spec_journal). Perps, der forlader universet før D + 7, udgår af hændelsen
(tælles; intet udfyldes).

## 5. Data og vindue

| Rolle | Strøm | Status 2026-11-06 |
|---|---|---|
| stressdag, univers | `bn_census` | EXISTING_ACTIVE |
| top-of-book-dybde og spread | `fwd_tob_universe` | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| tickSize | `fwd_spec_journal` | PROPOSED_NEEDS_SEPARATE_APPROVAL |
| sekundært: dyb bog | `bn_capacity` (rt_20000, depth_usd; universet skifter med papirhandlen), `bn_abnormal_move` (book_rt, 12 WATCH) | EXISTING_ACTIVE |

Kun fremad. Planlægningsdato 2026-12-07 00:00 UTC, længde 365 døgn (slut 2027-12-07). Ingen historik: E16's egen
hændelse (10-10-2025) ligger i den reserverede periode og læses aldrig.

## 6. Omkostninger, kapital og kapacitet

Ikke relevant (måling uden ordrer). En PASS ville give lov til at skrive en dateret ændring om en dybdestress i
omkostningsmodellen i dagene efter en stressdag.

## 7. Effektstørrelse og styrke

- **Registret:** E16 angiver dybde på 66–79 % efter 23 dage, dvs. ln-forhold −0,42 til −0,24, for den største
  kaskade i markedets historie. Det er ikke en plausibel størrelse for en typisk 3σ-dag. **Antagelse:** ln-forhold
  −0,10 ved D + 7 og sd 0,15 pr. hændelse (gennemsnit over mange perps, men med en fælles likviditetskomponent), dvs.
  e = 0,67.
- **Antal hændelser:** antagelse ca. **6 pr. 12 måneder** (3σ-dage i BTC efter afklyngning på 21 døgn). Frekvensen er
  ikke beregnet, fordi historikken ligger i den reserverede periode eller kræver en historisk forespørgsel.
- Styrke = `p2_power.sr_power(e, n, 1, α_F)`. Ved så små n overvurderer normalapproksimationen styrken; en t-test med
  5 frihedsgrader er svagere.

| Hændelser (≈ måneder) | e 0,5 | **e 0,67 (plausibel)** | e 1,0 | MDE e ved 80 % |
|---|---|---|---|---|
| 6 (12 mdr.) | 0,139 | **0,224** | 0,405 | 2,76 |
| 8 (16 mdr.) | 0,182 | 0,298 | 0,527 | 1,71 |
| 12 (24 mdr.) | 0,271 | 0,443 | 0,721 | 1,15 |
| 20 (40 mdr.) | 0,447 | 0,680 | 0,921 | 0,79 |
| 24 (48 mdr.) | 0,527 | 0,766 | 0,961 | 0,70 |

Styrke 0,8 ved e 0,67 kræver 26 hændelser, ca. 4,3 år ved den antagne frekvens (43 hændelser ved e 0,5).

## 8. Familie, slægt og alfabudget

- **Slægt:** `maker_adverse_selection_measurement` (klasse liquidity_provision), som E16's kobling i registret angiver.
  Beslægtet legacy-tag `liquidation_cascade_reversal` gælder kursreversalen, som ikke testes her (og som er F1's slægt i
  FACTORY_P2). Beslægtet måling: R1/costreport (samme time), H27-F's omkostningsregimer (MISSION27, kun beskrevet).
- **Mekanismegrænse:** enhver måling af spread- eller dybdegenopretning efter stress (anden hændelsesdefinition,
  horisont, dybdemål eller venue) er samme mekanisme.
- **Alfa:** ville trække α_F = 0,0125 fra W0. **Ikke opkrævet** og ikke reserveret, fordi udkastet er parkeret.

## 9. Eksponering

R1/costreport og straks-fyldene har vist omkostninger i samme time omkring flagede bevægelser; capacity/1-kørsler
findes siden 10-24. Ingen dybdegenopretning over dage er beregnet. `fwd_tob_universe` findes ikke endnu.

## 10. Sekundære analyser (hvis udkastet nogensinde aktiveres)

Spread ved D + 1 og D + 7 (E16's første regime); capacity/1 rt_20000 for de bøger, der findes på begge dage;
abnormal_move book_rt time for time for BTC og ETH.

## 11. Afgørelse for udkastet

**PARKED (INSUFFICIENT_POWER):** styrke 0,224 ved den plausible effekt inden for 12 måneder, MDE e 2,76. Desk-fabrikken
parkerer det selv (`check_power` < 0,8).

**Redesign-muligheder (hver kræver et nyt, versionsstyret udkast før data):**
1. Beskrivende sporing uden alfa: når `fwd_tob_universe` og `fwd_quality_monitor` kører, kan dybde og spread omkring
   stressdage rapporteres som R1 gør, uden test. **Anbefalet.**
2. En bredere hændelsesdefinition (fx C3's halebredde over sin 95 %-fraktil) giver flere hændelser, men mindre effekt pr.
   hændelse; det er ikke på forhånd bedre.
3. En 48-måneders forudregistrering (styrke 0,77 ved e 0,67), næppe nyttig i tide.

**Værdi ved et negativt resultat:** middel. Det ville sige, at omkostningsmodellen ikke behøver en dybdestress efter
stressdage, men med 6 hændelser kan et negativt resultat ikke skelnes fra lav styrke.

## 12. Felter til desk-fabrikken (`desk_factory.PROTOCOL_FIELDS`)

| Felt | Værdi |
|---|---|
| primary_hypothesis | 7 døgn efter en BTC-3σ-stressdag er top-of-book-dybden på tværs af Binance USDT-krypto-perps under niveauet før, ud over placebodage. |
| estimand | E[L_j] = middel_i ln(dep(D+7)/dep(base)) minus placebo-median |
| direction | negative (ensidet) |
| universe_rule | PIT ved D − 14: census coin_perps, quoteVolume ≥ 1 mio. USD, first_seen ≥ 30 d, tickSize/mark < 8 bp |
| window_start | 1796601600 (2026-12-07 00:00 UTC, planlægningsdato) |
| window_end | 1828137600 (2027-12-07 00:00 UTC; 365 døgn) |
| cost_model | n/a (måling uden ordrer) |
| data_streams | bn_census, fwd_tob_universe, fwd_spec_journal |
| alpha_f | 0.0125 (ikke opkrævet, ikke reserveret) |
| plausible_sr | 0.67 (standardiseret effekt pr. hændelse; antagelse ud fra E16's −0,42..−0,24 for den største kaskade) |
| per_year | 1 |
| n_planned | 6 (hændelser på 12 måneder, antagelse) |
