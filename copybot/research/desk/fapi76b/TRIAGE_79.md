# TRIAGE_79: FAPI research triage (direktørordre 79)

**Status: UDKAST, IKKE LÅST.** Ingen lås, alfa, statusændring, ledger-række, deploy, ny indsamling eller aktivering.

**Skrevet:** 2026-11-09 kl. 23:52 lokal (22:52 UTC, læst med `date`).

**Hvad er læst:** kun kode og dokumentation (afsnit 7). `lab.db`, `pm_lp.db`, holdouts, census-rækker, karantæne og N4-filen er ikke åbnet. Ingen Binance-vært er kaldt, og der er ingen web i denne ordre. Kode: `triage_79.py`. Test: `tests/test_fapi_triage_79.py`. De committede 76-B-filer er ikke ændret; rettelser til dem står i afsnit 5.

| Design | Direktørens dom | Betydning her |
|---|---|---|
| PR1 | GO kun som `DESCRIPTIVE_ONLY` | Specifikation; ingen PASS/FAIL, ingen alfa, ingen kørsel i denne ordre |
| CB1_VOL | HOLD | Klassifikation: **`INSUFFICIENT_EVIDENCE`** (afsnit 2) |
| CB1_DIR, LD1, FL1, TS1 | NO-GO | Registreret som afviste (afsnit 3). Køres og optimeres aldrig |

## 1. P1: PR1 som `DESCRIPTIVE_ONLY`

**Den observerbare størrelse.** Pr. symbol s og timeslot h er p(s,h) = ln(markPrice/indexPrice) fra den første `census/1`-række med ts i [h, h + 10 min).
- **Hændelse:** |p| ≥ 10 bp i to på hinanden følgende slots med samme fortegn, højst én pr. mønt pr. 8 slots.
- **D:** (|p(h)| − fortegn(p(h)) · p(h + 8)) / |p(h)|, altså andelen af afstanden, der er væk 8 slots senere.
- **Grupper:** pr. UTC-døgn deles hændelserne i terciler efter `quoteVolume` (≥ 1 mio. USD). Mindst 3 hændelser pr. side.
- **Rapportering:** kun fordelinger: middel og spredning af D pr. tercil, antal hændelser og døgn, frafald pr. årsag. `pr1_decide` og ordene PASS/FALSIFIED fra 76-B bruges ikke.

**p er ikke Binances "premium index".** Det er forholdet mellem to felter i `premiumIndex`-svaret. Navnet "premium" i 76-B er en bekvemmelighed.

**Dataproveniens.**

| Led | Fakta | Kilde |
|---|---|---|
| Indsamling | premium-watch' eksisterende `premiumIndex`-svar plus én `ticker/24hr` i timen på fapi | ændring 28 punkt 2, `lab/census.py` |
| Lager | `observations`, detektor `census/1`, metric `snapshot`; manglende felt er `null`, aldrig 0 | ændring 28 punkt 3 |
| Start | 2026-10-27 15:00 UTC | `FORWARD_DATA_PLAN.md` |
| Univers | `coin_perps` pr. snapshot (ændring 28a); leveringskontrakter uden for | `lab/census.py` |
| Tid | rækken lander 0-503 s efter slot (median 34 s); kun medianen af Binance-tiderne gemmes, så det enkelte symbols tid kan ikke efterprøves | `C1_FORECAST_DESIGN.md` afsnit 2, `lab/census.py` |
| Huller | ligger i stressede timer; census manglede 17 af 52 timer 10-30..11-02 | MISSION27_3 12a og MISSION27_4, citeret i `ORIGINAL_DESIGNS_ORDER69.md` og FUNDFRAG1 |
| Brugsregel | før en dateret hypotese er låst, må kun datakvalitet rapporteres | ændring 28 punkt 6, G05 |

**Konsekvens af brugsreglen:** selv `DESCRIPTIVE_ONLY` kan ikke beregnes nu. Ændring 28 punkt 6 kræver en dateret præregistrering med falsifikation, placebo og omkostninger, og denne ordre giver ingen lås. PR1 har desuden **ingen placebo** defineret. Det er et hul i 76-B.

**Antagelser om formlen (alle UNVERIFIED; Binance-værter må ikke kaldes, og intet her er bekræftet):**

| # | Antagelse | Hvor den står | Betydning for PR1 |
|---|---|---|---|
| A1 | Funding = premium + clamp(rente − premium, ±5 bp) pr. 8 t | `families/drafts/fregime.json`, selv markeret unverified | Kun begrundelsen for 10 bp. Selve tallet er et designvalg |
| A2 | Mark = indeks + udglattet basis | `C1_FORECAST_DESIGN.md`, uden kildehenvisning | Er den rigtig, er p en udglattet størrelse, og D måler delvis udglatningsvinduet |
| A3 | Indeks er en kurv af spotbørser | samme | p er ikke afstanden til én handlebar pris |
| A4 | Funding-interval | K3-optælling, ændring 22 B: af 74 mønter med forudsagt funding ≥ 0,05 % pr. 8 t afregnede 71 hver 4. time, 2 hver time, 1 hver 8. time | 8 slots er ikke "én fundingperiode" for mange mønter. Intervallet gemmes ikke (FORWARD_DATA_PLAN fund 1) |

Funding indgår ikke i estimanden. **PR1 kan derfor ikke vise, at funding driver henfaldet.** Den kan kun beskrive henfaldet.

**Begrænsninger i statistisk styrke.**
- sd 0,25, 170 døgn og effekt 0,10 er ANTAGELSER uden kilde. MDE 0,059 gælder kun under dem (0,025-0,117 i følsomhedstabellen i 76-B). "Styrke 1,00" i 76-B må ikke citeres: den er en regnefølge af gættet.
- Antal brugbare døgn er ukendt (G05). Kravet om mindst 9 hændelser pr. døgn fravælger rolige døgn, så estimanden gælder kun de døgn, der er tilbage.
- Testen i 76-B er en almindelig klynget t uden HAC. Premium-regimer kan hænge sammen over døgn.
- Ved den registerbrede Bonferroni (N ≥ 19.439, diagnostik) kræves 0,104 og altså mere end den antagne effekt.

**Fejlkilder, som styrke ikke løser:**
- Betingelsen |p| ≥ 10 bp vælger støj, så D er positiv af sig selv (regression mod middelværdien). Tynde perps har mere støj, hvilket kan trække kontrasten begge veje.
- M3 så premier forsvinde inden for 6-75 min på BTC. D kan derfor være tæt på 1 i likvide perps (lofteffekt), og kontrasten kommer da næsten kun fra de tynde.
- Tynde perps kan have kortere funding-interval (A4), og det kan ikke kontrolleres med gemte data.
- Tick-størrelse og huller i stressede timer påvirker tynde perps mest.

**Overlap med registret** (snapshot v1, lineage `cross_venue_perp_gap`: 13 forsøg, 26 varianter).

| Post | Forhold |
|---|---|
| `L22_m3_premium_convergence` (M3) | Handlen er testet på BTC og afvist. Den viste også fortegnet på henfaldet |
| `SPOTPERP_m21i`, `FUNDING_m21h`, `E_funding_contrarian_p1`, fcarry-posterne, `CARRY_BASIS_2026-10-21`, `L08`, `L12`, `L13` | Samme slægt, andre estimander |
| `C_0755f34d6d` (`perp_premium_convergence`, PROPOSED, 0 forsøg) | Samme tag, ikke i ledgeren |
| C3, C4, FUNDFRAG1, C1 | Deler råe census-rækker, ikke estimand |

PR1 er ikke en ny, uafhængig opdagelse og får ingen ledger-række.

**Hvorfor resultater ikke kan læses som handelsafkast.**
- Hverken mark eller indeks er handlebare priser, og indekset har intet ben, man kan købe.
- Der er ingen fyld, bog, gebyr, spread eller funding i D.
- D er en andel af afstand, uvægtet, med hændelser udvalgt på størrelsen.
- En handel kræver to ben (mindst 34 bp i M3, ofte ca. 48 bp). M3 fik +0,6 til +2,4 bp brutto.
- Tallene viser kun, hvordan afstanden opfører sig i census.

## 2. P2: CB1_VOL mod F2's mekanismedefinition

**"F2" er her FACTORY F2**, ikke ændring 8's familie F2 (navnekollision AMB-01). Sammenligningen bruger kun den låste tekst, `research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md` L78-123 og L194-205, sha256 `6dd1ca82934419c0913bccb3a8962f5e5e5154d678eee59179292a7694ae5f43`, samt metadata. Ingen F2-kalibrering, ingen resultater.

**Grænsens ordlyd (L85-86):** "alle modeller, der forudsiger realiseret volatilitet ud fra fortidig realiseret volatilitet på flere horisonter (HAR-varianter, andre lags, log-HAR, GARCH-familien, regimemodeller), er samme mekanisme."

| Akse | F2 | CB1_VOL | Forhold |
|---|---|---|---|
| Udfald | realiseret volatilitet | realiseret volatilitet | Fælles |
| Nulmodel | HAR 1/7/30 d; grænsen nævner log-HAR | log-HAR 1/7/30 d | Fælles |
| Kompression | regimemodeller er inden for grænsen (også `PROTOCOL_SHORTLIST` C25) | 7 d-range under egen 90 d-fraktil, altså en tilstand af fortidig volatilitet | Fælles |
| Horisont og måling | næste døgn, 1 t-kline-lukkepriser, QLIKE mod EWMA | 3 døgn, census-mark, residual mod matchet kontrol | Forskellig |
| Ikke-RV-input | grænsen nævner ikke ekstra input | kursbrud af 20 d-kanal og volumen ≥ 2 × median | **Uafklaret** |
| Præcedens | ingen afgørelse fra direktøren | FUNDFRAG1 afsnit 8 kalder sig selv uden for grænsen, men er et ikke-godkendt udkast | **Uafklaret** |

**Klassifikation: `INSUFFICIENT_EVIDENCE`.** Reglen er fail-closed (`triage_79.classify`): en uafklaret akse afgør sagen.

- **Udelukket af dokumenterne:** `DISTINCT_MECHANISM`. Udfald, nulmodel og kompression er fælles.
- **Kan ikke afgøres:** `SAME_MECHANISM` mod `RELATED_MECHANISM`. Læses grænsen efter hele modellen, er CB1_VOL en regimemodel med ekstra input og altså inden for. Læses den efter tilvæksten (udbrud og volumen mod lige så komprimerede kontroller), er den beslægtet. Teksten skelner ikke.
- **Hvad der ville afgøre det:** en dateret afgørelse af, om ekstra ikke-RV-input fører et design ud af F2's grænse. Det er et spørgsmål om regeltolkning og kræver ikke data.

**Følger:** HOLD står. DISTINCT-gaten i 76-B bestod på FUNDFRAG1-præcedensen. Den skal nu læses som **ikke etableret**. Ingen aktivering, og `lineage` ændres ikke, før grænsen er afgjort.

## 3. P3: afviste designs

Registreret her og som V2-poster i hukommelsen (`triage_79.rejected_record`, id `TRIAGE79-<navn>`). Ingen ledger-række. V2 har intet statusfelt, så afvisningen ligger i de hashede `parameters`: `triage_status`, `never_run`, `reoptimization_allowed` falsk. Ingen genoptimering.

| Design | Lineage | Gates faldet | Begrundelse | Overlap |
|---|---|---|---|---|
| CB1_DIR | `cross_sectional_momentum` | EFFECT_REACHABLE | MDE 0,92 % pr. 3 døgn netto mod plausibel 0,14 % (antagelser); brutto krævet ca. 123 bp | L14 tsmom_v1, L03, E_oi_confirmed_return_p3, E_xs_high_volume_p2 |
| LD1 | `maker_adverse_selection_measurement` (ikke i snapshot; ingen ledger-række) | DISTINCT, EFFECT_REACHABLE | Samme rækker og hændelser som LQ1, inden for LIQREC1's grænse; MDE 8,1 bp mod plausibel 3 bp | LQ1, LIQREC1 |
| FL1 | `liquidation_cascade_reversal` | DISTINCT, VALIDATION_PLAN, EFFECT_REACHABLE | M2: alle 18 varianter netto negative; ingen fremadrettet OI; MDE 2,30 % | L21 (M2), m21c, E_daily_reversal_p1 |
| TS1 | `calendar_day_of_week` | MECHANISM, DISTINCT, EFFECT_REACHABLE | ETF-regimet ligger i forseglede vinduer; brutto krævet ca. 48 bp mod skøn 4 bp | E_hour_of_day_p1, E_day_of_week_p1, E_turn_of_month_p2 |

## 4. P4: åbne begrænsninger (bevares, lukkes ikke her)

| Id | Begrænsning |
|---|---|
| G05_CLUSTER_DAYS | Antal klyngedøgn er ukendt, indtil en tilladt lås findes. Census må ikke tælles til formålet før (G05) |
| FORWARD_OI | Fremadrettet OI er utilgængelig. Arkivet er DNS-blokeret lokalt og omgås ikke; OI fra fapi er en ugodkendt ny datalinje |
| DELISTING_PROVENANCE | Afnoteringer ses ikke i census (FORWARD_DATA_PLAN fund 2). Provenansen er uafklaret |
| BINANCE_FORMULA_UNVERIFIED | Funding-, mark- og indeksformler er UNVERIFIED; Binance-værter må ikke kaldes |
| REGISTER_N_MINIMUM | 19.438 historiske varianter er et konservativt minimum, ikke kendt N_eff. N_eff, DSR og PBO er `MISSING_INPUT` |

## 5. Rettelser til 76-B (fundet under triagen; de committede filer er ikke ændret)

1. "8 t = én standard-fundingperiode" (PR1, afsnit 2 i 76-B) holder ikke for mange mønter (A4). Læs: "en fast 8-timers horisont".
2. CB1_VOL's DISTINCT-gate er ikke etableret (afsnit 2 her).
3. CB1 bruger census' 24 t high/low som dagsinterval. `C1_FORECAST_DESIGN.md` skriver, at de "kan ikke bruges til range-estimatorer", mens LIQPROXY1 bruger 00:00-snapshottet som tilnærmet UTC-døgn. Modstriden er uafklaret og vedrører kun CB1, der står på HOLD.
4. CB1_VOL's RV på census-mark er ikke F2's måling (kline-lukkepriser) og er glattere (`C1_FORECAST_DESIGN.md`). Det er medtaget i afsnit 2.
5. PR1 mangler placebo og kan ikke beregnes uden dateret præregistrering (afsnit 1).

## 6. Tilbage for direktøren

1. Afgørelse om F2-grænsen ved ekstra ikke-RV-input (løser CB1_VOL's klassifikation).
2. Om PR1 skal have en dateret præregistrering med placebo. Denne ordre giver den ikke.

## 7. Kilder (kun lokale, read-only)

`research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`; `research/desk/F2_AMBIGUITY_RESOLUTION_PROPOSAL.md`; `research/desk/F2_CALIBRATION_SPEC_DRAFT.md`; `research/desk/C1_FORECAST_DESIGN.md`; `research/desk/PROTOCOL_SHORTLIST.md` (C24, C25, punkt 5); `research/desk/NOV14_READINESS.md` (AMB-01); `research/desk/protocols/FUNDFRAG1_v1.md`, `LIQPROXY1_v1.md`, `LIQREC1_v1.md`; `research/desk/lq1/LQ1_PROTOCOL_DRAFT.md`; `research/desk/FORWARD_DATA_PLAN.md`; `research/desk/stream_registry.json`; `research/desk/GATE_MATRIX.json` (G05, G16, G17); `research/desk/mechanism_graph.json`; `research/desk/EVIDENCE_REPORT_75.md`; `research/desk/ORIGINAL_DESIGNS_ORDER69.md`; `research/MISSION3_FAST_SCREEN.md`; `research/PROTOCOL_V3.md` (ændring 22 B, 28, 28a); `research/families/drafts/fregime.json`; `research/desk/register_snapshots/SNAPSHOT_v1.json`; `lab/census.py`; `research/desk/fapi76b/FAPI_DESIGNS_76B.md`.
