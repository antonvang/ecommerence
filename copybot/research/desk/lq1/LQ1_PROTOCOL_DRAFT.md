# LQ1_PROTOCOL_DRAFT: UDKAST, IKKE LÅST (direktørordre 70 P0)

**Skrevet:** 2026-11-09 kl. 21:55 lokal (20:55 UTC, læst med `date`).

**Status:** UDKAST, IKKE LÅST. Ingen observationer er læst, ingen alfa er opkrævet, ingen ejer har godkendt noget.
LQ1 er beskrivende forskning om handelsomkostninger og ikke en dokumenteret handelsfordel. Ingen bog, bane eller ordre
ændres af dette udkast, heller ikke ved en PASS. Alle tal for spredning og hændelsesrate er ANTAGELSER.

**Kilde:** `ORIGINAL_DESIGNS_ORDER69.md` afsnit 2. Kode: `lq1_evaluator.py`, `make_fixtures.py`, `lq1_power.py`. Tests:
`tests/test_lq1_evaluator.py`.

## 1. Hypotese

**H1:** Når 5.000-USD-rundturen gennem bogen i et af scannerens 12 markeder er mindst 3 gange sin egen 168-timers median,
er rundturen en time senere så meget lavere, at det sparer mere end ét taker-gebyr pr. side at vente én time.

- **Endepunkt:** S_i = ½ (RT_t − RT_t+1), i bp pr. side for 5.000 USD. Gebyret er det samme i begge arme og går ud.
- **Test:** ensidet t-test på UTC-døgnklyngernes middel. H0: S̄ ≤ 5 bp. α_F 0,0125, df = n − 1, eksakt t-fordeling.
- **Alfa-status:** α = 0, BESKRIVENDE, medmindre ejeren beslutter andet. Testniveauet er sat, så en senere beslutning
  ikke ændrer testen.

| Parameter | Værdi | Kilde |
|---|---|---|
| Ordrestørrelse | 5.000 USD | 21h punkt 3, 21l punkt 1 |
| Brud | RT_t ≥ 3 × baseline | H-SPR-1 punkt 5 |
| Baseline | median af højst 168 foregående brugbare timer, mindst 120, kun efter låsen | design |
| Udskydelse | én time | scannerens takt |
| Dedup | højst én hændelse pr. marked pr. 6 t | `moves.DEDUP_S` |
| Tærskel | 5 bp pr. side | 21i punkt 1 |
| Vindue | hændelser i [L + 7 d, L + 98 d), dom ved L + 99 d | design |

## 2. Præciseringer af ordre 69-teksten

Teksten lod disse punkter åbne. Evaluatoren følger nedenstående. Hvert punkt er et forslag, som direktøren skal godkende
før en lås. Alle er valgt uden data.

1. **Målingstime h** = `open_s` + 3600, altså timen, scanningen ligger i. Scanningen skal ligge i [h, h + 600 s].
2. **Baseline tælles i brugbare timer, ikke i kalendertimer.** Råvarer er lukket 49 timer om ugen. 168 kalendertimer
   giver derfor kun 119 brugbare, under minimummet på 120, og råvarerne ville aldrig kunne give en hændelse.
3. **Brugbar time:** numerisk RT, ikke EWMA, ikke første time efter genåbning, h ≥ L. Censurerede timer indgår ikke i
   baseline, hvilket trækker baseline lidt ned.
4. **Dedup:** et kandidatbrud bruger de 6 timer, også hvis t + 1 mangler. Ellers ville et hul give et nyt forsøg.
   Brud udelukket ved t (EWMA, genåbning) bruger dem ikke.
5. **Censur:** kun fejlen "book too thin for 5 000 USD". Andre scanningsfejl tæller som manglende scanning.
6. **Kun den tidligste scanning pr. (marked, time) tæller.** Er den over 10 minutter sen, er timen uden måling.
7. **Klyngedøgn** = UTC-døgnet for h. UNTESTABLE-grænsen tæller kun døgn med mindst én S-værdi.
8. **Dækning:** nævneren er markedstimer uden for EWMA i vinduet. En "for tynd"-måling tæller som scannet.
9. **Porten ved lighed:** deler flere markeder det højeste antal hændelser, bruges det laveste S̄ uden markedet.
10. **Nul spredning** (alle S = 0): p = 1, øvre grænse = middel. Giver FALSIFIED i stedet for et nedbrud.

## 3. Falsifikation og domme

Rækkefølgen er bindende, og dommene udelukker hinanden (`decide()`):

| # | Betingelse | Dom |
|---|---|---|
| – | fixture ugyldig | status ERROR, ingen dom |
| – | før L + 99 d | status NOT_DUE, kun antal |
| 1 | dækning < 90 % | INVALID |
| 2 | < 30 klyngedøgn | UNTESTABLE |
| 3 | > 20 % af hændelserne har censureret RT_t | INCONCLUSIVE_CENSORED |
| 4 | ensidet 95 %-øvre grænse for S̄ < 5 bp | FALSIFIED |
| 5 | p ≤ 0,0125, S̄ > 5 bp og robusthedsporten holder | PASS |
| 6 | ellers (også test bestået, port ikke) | INCONCLUSIVE |

**Robusthedsport:** mindst 3 markeder bidrager, og S̄ uden markedet med flest hændelser er stadig over 5 bp (punktskøn).

**Efter en dom:** FALSIFIED lukker spørgsmålet; ingen ny tærskel, størrelse eller udskydelse. Under 30 klyngedøgn
forlænges ikke uden en ny dateret ændring. En PASS giver kun lov til at foreslå en udførelsesregel for retningsneutrale
ordrer, og det kræver en ny dateret ændring med ejerens ja.

**Hvad en PASS ikke viser:** selektion på RT_t ≥ 3 × baseline giver regression mod middelværdien. Ved fuld tilbagevenden
er S = ½ (RT_t − baseline), mekanisk og uden nogen "resiliens". Ved et brud på præcis 3× baseline er det lig baseline i
bp, så et marked med en bog under 5 bp kun når over tærsklen ved langt større brud. S̄ kommer derfor fra de tynde bøger. LQ1 svarer
kun på, om det er billigere at vente, ikke hvorfor. `s_full_reversion_bp` rapporteres pr. marked som loft.

## 4. Styrke og varighed

Fra `lq1_power.py` (analytisk, ændring 32-formlen). α_F 0,0125, styrke 80 %.

**MDE over tærsklen, bp:**

| sd \ n | 30 | 60 | 91 | 120 |
|---|---|---|---|---|
| 5 | 2,8 | 2,0 | 1,6 | 1,4 |
| **10** | 5,6 | **4,0** | 3,2 | 2,8 |
| 30 | 16,9 | 11,9 | 9,7 | 8,4 |

**Klyngedøgn nødvendige for 80 % ved sand besparelse S:**

| sd \ S | 6 bp | 7 bp | 8 bp | 9 bp | 12 bp |
|---|---|---|---|---|---|
| 5 | 238 | 60 | 27 | 15 | 5 |
| **10** | 951 | 238 | 106 | **60** | 20 |
| 30 | 8.555 | 2.139 | 951 | 535 | 175 |

**Hvad vinduet på 91 dage kan nå (sd 10):**

| Andel døgn med hændelse | Klyngedøgn | Testbar | Styrke S = 8 | S = 9 | S = 12 |
|---|---|---|---|---|---|
| 25 % | 22 | nej, UNTESTABLE | – | – | – |
| 33 % | 30 | ja | 0,28 | 0,48 | 0,94 |
| 50 % | 45 | ja | 0,41 | 0,67 | 0,99 |
| 67 % (antagelsen) | 60 | ja | 0,53 | 0,80 | 1,00 |

**Varighed:**
- Testen er fast: 91 dages hændelser og dom ved L + 99 d. Ved L = 2026-11-16 (ANTAGELSE; kræver direktørbeslutning og
  dateret ejer-ja) tæller hændelser fra 2026-11-23, og dommen falder 2027-02-23. Hver dags forsinkelse af låsen flytter
  dommen en dag.
- Kun en besparelse på omkring 9 bp eller mere kan findes inden for vinduet, og kun hvis sd ≈ 10 og to af tre døgn har en
  hændelse. En besparelse på 7 bp kræver 238 klyngedøgn, over et halvt år selv med en hændelse hver dag.
- Ved sd 30 kræver 80 % styrke en sand besparelse på mindst ca. 15 bp, selv med en hændelse hvert døgn (MDE 9,7 bp ved
  n = 91).
- Hændelsesraten er ukendt. Falder under en tredjedel af døgnene en hændelse, ender testen som UNTESTABLE.

**Hele kæden, opdigtede verdener, 200 gentagelser pr. verden** (`pipeline_mc`, seeds fra 90000):

| Verden | PASS | Andre domme | Kun t-test bestået |
|---|---|---|---|
| ved tærsklen, ens bøger | 1,5 % | FALSIFIED 7,5 %, INCONCLUSIVE 91 % | 1,5 % |
| S ≈ 9 bp, ens bøger | 100 % | – | 100 % |
| **S ≈ 9 bp, blandede bøger** | **72,5 %** | INCONCLUSIVE 27,5 % | **93 %** |
| ingen tilbagevenden | 0 % | FALSIFIED 100 % | 0 % |

**Robusthedsporten koster styrke:** i verdenen med blandede bøger (2, 4, 12, 30 bp; klynge-sd 7,7 bp, ca. 50 klyngedøgn)
falder andelen af PASS fra 93 % til 72,5 %, fordi besparelsen sidder i de tynde markeder, og porten kan fjerne netop et
af dem. Det er tilsigtet som værn mod ét enkelt marked, men de 80 % i ordre 69 gælder kun t-testen og er altså et loft
for PASS. Verdenerne er ikke kalibreret efter observationer.

## 5. Databehov

Kun eksisterende felter. Intet nyt kald, ingen ny vært, ingen ny datalinje, ingen deploy. `tests/test_lq1_evaluator.py`
kontrollerer teksten i `lab/moves.py`, så beskrivelsen ikke forældes.

| Felt | Kilde (`lab/moves.py`) | Brug |
|---|---|---|
| detektor `abnormal_move/1`, metrik `book_rt` | `detect()` | rækken |
| værdi = `round_trip` (brøk af prisen, uden gebyrer) | `book_cost()` | RT |
| række-`ts` | registret | scanningens tidspunkt |
| payload `open_s` | `stats()` | h = `open_s` + 3600 |
| payload `off_hours` | `off_hours()` (ændring 21g) | EWMA-udelukkelse |
| payload `error` = "book too thin for 5 000 USD" | `book_cost()` | censur |
| de 12 markeder i `WATCH` | `moves.WATCH` | univers |

- Tynd bog: værdi `None`, `error` i payload. Andre `error`-værdier tæller som manglende scanning. En scanning med
  `history_short` eller klines-fejl giver ingen `book_rt`-række og tæller også som manglende.
- `off_hours` kendes for hver time ud fra `moves.off_hours()`, også når scanningen mangler.
- **Dækning er ikke talt:** `lab.db` er ikke åbnet. Hændelsesraten kendes derfor ikke.

**Ikke bygget:** en adapter, der læser `lab.db` (`mode=ro`, `PRAGMA query_only=ON`) og omsætter rækker til evaluatorens
format, skal skrives og committes før låsen. Evaluatoren her læser kun filer i `fixtures/`.

## 6. Overlap-audit

**Registret** (`research/data/factory/registry.json`, læst via `git show HEAD:...`, kun navn, familie og status, ingen
rækker udskrevet). 65 poster, heraf 11 med ord som liquid, spread, book, cost, maker, recover, delay, timing eller
cascade i navn eller familie; flere af dem er makro-timing uden forbindelse til LQ1.

| Familie (tag / slægt) | Status | Overlap med LQ1 |
|---|---|---|
| `maker_adverse_selection_measurement` | CLOSED | Se LIQREC1 nedenfor. Maker-fyld; LQ1 er taker-timing |
| `venue_subsidy_liquidity_rewards` (samme slægt) | EXTERNAL | pm_lp. Røres ikke |
| `liquidation_cascade_reversal` | REJECTED | Kursreversal. LQ1 har intet afkast-endepunkt |
| `short_term_reversal_liquidity` (samme slægt) | REJECTED, PROPOSED | Samme |
| `illiquidity_premium` / `high_volume_return_premium` | REJECTED | Afkastpræmie. Intet afkast i LQ1 |
| `orderflow_imbalance` | REJECTED | Andet signal |

Ingen post hedder LQ1, LIQREC eller LIQPROXY. Af 147 nøgler i hypotesepipelinen matcher ingen ordene. Af 22 off-db-studier
matcher 4 (2 i `short_term_reversal_liquidity`, 2 unclassified). Hvis LQ1 låses, tæller den som ét nyt forsøg.

**LIQREC1 er det vigtigste overlap, og ordre 69 nævnte det ikke.** `protocols/LIQREC1_v1.md` (PARKED,
INSUFFICIENT_POWER) siger i afsnit 8: "enhver måling af spread- eller dybdegenopretning efter stress (anden
hændelsesdefinition, horisont, dybdemål eller venue) er samme mekanisme".
- LQ1 er efter den tekst **samme mekanisme** i slægten `maker_adverse_selection_measurement`, med et andet hændelsesvalg
  og en anden horisont (1 time mod 7 døgn). Begge hviler på E16.
- LQ1 er derfor **ikke uafhængig** af LIQREC1, og en PASS må ikke tælle som en ny mekanisme. LQ1 ophæver ikke
  parkeringen af LIQREC1.
- **Forslag til direktøren:** LQ1 registreres i samme slægt, eller der besluttes et nyt tag før låsen. Det skal være
  afgjort, før noget låses.
- Ingen eksponering herfra: LIQREC1's sekundære analyse (`book_rt` time for time for BTC og ETH) er aldrig kørt.

| Kilde | Forhold til LQ1 |
|---|---|
| **R1** (`costreport`, 21h/21l), `flagreport` | **Samme råe rækker.** Viser niveauer. `flagreport`s "following_cost" er bog i samme scanning, ikke timen efter. Moderat eksponering for niveauer, lav for udfaldet |
| **K1/K2** (21y) | Samme `book_rt` som omkostning. Deres WEEKEND-timer er EWMA og udelukkes her. RTH-rækker deles. Ingen fælles statistik |
| **U4 / R3** (m24) | Ingen fælles observationer: 1m-zip fra 2020-21, makrotidspunkter, afkast |
| **M1F / K10** | Ingen. Monitoring Tag, altcoins, afkast; bruger ikke `book_rt` |
| H-SPR-1/2, `capacity/1` | Andre data og spørgsmål |
| LIQPROXY1 | Kursbaseret proxy mod målt spread. Andet spørgsmål, men W0-konkurrent, hvis LQ1 får alfa |
| H27-F (MISSION27, omkostningsregimer) | Kun beskrevet. Navnet bruges senere om noget andet |
| PROTOCOL_SHORTLIST C12 | Samme som LIQREC1 |

**Beskyttede holdouts:** G01 og G02 er ikke relevante (ingen historiske filer). G03 (2024) og G04 (2025+) røres ikke.
G05 er det relevante værn: egne rækker fra 2026-10-27 må ikke kalibrere eller teste før låsen og vinduet. Derfor tæller
kun rækker efter låsen, og baseline bruger kun rækker efter låsen. G07 (karantæne): bruges ikke. G12 (pm_lp): røres ikke.
Tærsklerne er lab-konventioner og er ikke valgt ud fra R1-tallene, som denne session ikke har læst.

## 7. Evaluatoren

| Regel | Dækket | Test |
|---|---|---|
| Domstræet i afsnit 3 | ja | `Decision`, `Worlds` |
| Afsnit 2's præciseringer | ja | `EventRules` |
| Null-verden, verden med effekt | ja | `Worlds` |
| Manglende felter, ugyldig værdi, forkert sti | ja, status ERROR | `BadInput` |
| Kun antal før fristen | ja | `NotDue` |
| Reproducerbarhed | ja, fixtures er byte-identiske med generatoren | `Reproducible` |
| Kun stdlib, ingen database, intet netværk | ja, kontrolleret i AST | `Boundaries` |
| **Retningsdrift** | **nej, bevidst udeladt** | – |

**Retningsdrift (s · ln(mark_t+1/mark_t)) er udeladt** fra den syntetiske evaluator:
- Den er ikke en beslutningsregel, kun en rapportlinje i ordre 69.
- Den kræver `mark` og `z_1h`, som fixtures ikke har, og et syntetisk tal siger intet om den.
- Det er afkastområdet (m21c, straks). Det hører hjemme i adapteren, hvis direktøren vil have linjen.

Konsekvensen er væsentlig: **S indeholder ikke prisrisikoen ved at vente.** En eventuel PASS gælder kun retningsneutrale
ordrer, og tærsklen på 5 bp er en designpris for den risiko, ikke et mål for den.

## 8. Åbne punkter før en lås

1. Direktørbeslutning og dateret ejer-ja; D5 for VERIFIED; ingen lås 11-14 uden et udtrykkeligt ja (order 53).
2. Slægt og tag for LQ1 (afsnit 6).
3. Godkendelse af præciseringerne i afsnit 2.
4. Adapteren skal skrives og låses sammen med teksten. Evaluatoren køres én gang ved fristen af en anden session.
5. Beslutning om, hvorvidt porten skal blive som den er, givet prisen i afsnit 4.

**Begrænsninger:** timeopløsning, så brud på få minutter ses ikke. Scanneren ser 100 niveauer, papirmotoren 20. Én
ordrestørrelse. Alle tal i afsnit 4 er syntetiske eller antagelser.
