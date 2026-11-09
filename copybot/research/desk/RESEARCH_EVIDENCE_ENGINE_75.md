# Evidensmotor: Register V2 og valideringsmotor (direktørordre 75, P0/P1)

Skrevet 22:56 lokal, 2026-11-09. Kode: `research/tools/register_v2.py`, `research/tools/validation_engine.py`.
Tests: `tests/test_register_v2_75.py`, `tests/test_validation_engine_75.py`. Kun syntetiske data. Motoren afgør intet om en strategi.

## Register V2

Sidepost til fremtidige undersøgelser med egen hashkæde. Rører ikke `research/data/factory/*`, ledger-rækker eller kæden i `register_stats`.

| Felt | Indhold |
|---|---|
| `hypothesis_id`, `lineage` | etiketter |
| `trial_universe` | definition, størrelse, hash af medlemmer |
| `variants_tested` | antal + artefakt og hash |
| `parameters`, `code_hash` | værdier + deres hash; commit eller sha256 |
| `data_source`, `data_period` | navn + hash; start og slut |
| `cost_model`, `evaluation_method` | navn, hash, round-trip bps |
| `data_quality` | VERIFIED, DEGRADED, CONTAMINATED, NOT_CHECKED + evidens |
| `deviations` | liste; `[]` betyder ingen, `MISSING_INPUT` betyder ukendt |
| `register_snapshot`, `stats_ref` | valgfri pegepinde til snapshot-sha og `register_stats`-post |

- **FUTURE** skal angive alt før kørslen. Kun `variants_tested` må vente.
- **HISTORICAL** må stå som `MISSING_INPUT` i alle felter. Intet udfyldes med antagelser. Et felt skifter først, når et artefakt dokumenterer det.
- **Rettelser er nye poster.** Et låst felt ændres kun, hvis samme post tilføjer en afvigelse, der nævner feltet. Afvigelser kan kun vokse. Antal varianter kan ikke falde. CONTAMINATED kan ikke fjernes uden afvigelse. Reglerne afspilles igen i `chain_verify`.
- `historical_view` er skrivebeskyttet. Registrets eget variantantal kopieres ikke ind i V2.
- Antal testede varianter over forsøgsuniverset kræver en afvigelse.

## Statusser

| Status | Betydning |
|---|---|
| PASS | tjekket kørte og fandt intet galt, eller effekten overlevede |
| FAIL | en fejl, eller en påstand afvist med tilstrækkelig styrke |
| INCONCLUSIVE | tjekket kørte og kan ikke afgøre det |
| MISSING_INPUT | et nødvendigt input findes ikke; intet er udfyldt |
| CONTAMINATED | data må ikke bruges |

Samlet status er den værste. Rækkefølge: CONTAMINATED, FAIL, MISSING_INPUT, INCONCLUSIVE, PASS. PASS kræver, at alle krævede tjek har kørt.

## De otte tjek

| Fejltype | Metode | Udfald ved plantet fejl |
|---|---|---|
| Multiple testing | Max-t med cirkulær blok-bootstrap over hele familien. Bonferroni på største dokumenterede N, når kun en del af familien findes | Understated N: FAIL. Null med tilstrækkelig styrke: FAIL. Null uden angivet mindste effekt: INCONCLUSIVE |
| Korrelation | Parvis korrelation, klynger, max-ækvivalent N | For lavt påstået N_eff eller klonede "uafhængige bekræftelser": FAIL |
| Lookahead | Tidsstempler og afkortningsinvarians af signalberegningen | FAIL. Kun afkast: MISSING_INPUT |
| Survivorship | Point-in-time-univers mod testet og delistet | FAIL |
| Manglende observationer | Huller mod forventet akse, udfyldningsmønstre, huller efter tab | Biased eller udfyldt: FAIL. For mange huller: MISSING_INPUT |
| Datakontaminering | Beskyttede vinduer, forbudte kilder, karantæne, train/test-overlap, embargo | CONTAMINATED |
| Overfitting | PBO (CSCV) og DSR via `register_stats` | FAIL ved DSR < 0,5, eller PBO ≥ 0,5 uden høj DSR. PBO ≥ 0,5 med DSR ≥ 0,95: INCONCLUSIVE |
| Omkostninger | Antaget mod dokumenteret gulv, kant efter gulv og stress, afstemning af netto | FAIL. Marginal kant: INCONCLUSIVE |

## Formler

- t = gennemsnit / sd · √T med populations-sd.
- Bonferroni: p = min(1, N · (1 − Φ(t))), N = største dokumenterede antal; N sænkes aldrig.
- Max-t: serierne centreres om egen middelværdi. Samme blokke for alle serier, så krydskorrelation og kort autokorrelation bevares. p = (1 + antal(max* ≥ observeret)) / (B + 1). Blokstørrelse 2·T^(1/3).
- Styrke: Φ(SR_min·√T − Φ⁻¹(1 − α/N)). Uden angivet SR_min giver et nulresultat INCONCLUSIVE, aldrig FAIL.
- Max-ækvivalent N: det N, hvor E[max z] svarer til familiens egen null-max. Diagnostik, ikke dokumenteret N_eff.
- DSR og PBO er uændrede formler fra `register_stats` og `lab.engine.pbo`. De beregnes kun på poster med hashet proveniens eller eksplicit `synthetic=True`, og kun når familien er komplet. Ellers `MISSING_INPUT` uden tal.

## Max-z og registrets N

Max-z er diagnostik og ikke en kalibreret grænse. **19.438 er et konservativt minimum og ikke et endeligt N.** Værdien omkring 4,02 er E[max z] af 19.438 uafhængige normaler og bruges ikke som grænse noget sted i motoren; `max_z_diagnostic` returnerer `calibrated_threshold: None`. Ved t = 4,1 og N = 19.438 giver Bonferroni p ≈ 0,4, så tjekket består ikke; test låser dette. N_eff forbliver `MISSING_INPUT`, indtil afkastserier og en valideret metode findes.

## Målt på syntetiske null-verdener

Max-t med standardblok, α = 5 %, 10 varianter, T = 250, B = 199, 300 verdener. Standardfejl ca. 1,3 point.

| Verden | Afvisningsrate |
|---|---|
| Uafhængig | 6,7 % |
| ρ = 0,9 | 6,0 % |
| AR(1) φ = 0,3 | 6,7 % |
| AR(1) φ = 0,6 | 9,0 % |

Blokstørrelse T^(1/3) gav 8 % ved φ = 0,3 og blev derfor gjort dobbelt så lang. Alle rater ligger over 5 %, og testen er derfor lidt liberal; ved φ = 0,6 over-afviser den (9 %, ca. tre standardfejl over 5 %). Med ægte drift på SR 0,25 pr. periode: 200 af 200 afvist (før blokændringen).

## Antagelser

- Beslutningsgrænser er konventioner, angivet som parametre, ikke kalibrerede bjælker: α = 0,05, styrkemål 0,8, PBO 0,2/0,5, DSR 0,5/0,95, stress 2×, max 5 % huller, max 5 % uforklarede frafald, min. 30 perioder, klynge ved |ρ| ≥ 0,9, z-tolerance 0,25, persistensgrænse 0,5.
- t-fordelingen er tilnærmet med normalfordelingen.
- Tjek for udfyldning (mindst 5 identiske værdier i træk) er en heuristik. `flat_is_valid=True` er for bøger, der reelt står i kontanter.
- Beskyttede vinduer, forbudte kilder, karantæne og omkostningsgulv er kaldets ansvar. Motoren kender dem ikke selv.

## Resterende usikkerheder

- **Ingen ægte data er kørt.** Alle tal ovenfor er syntetiske. Størrelsen af metoden på rigtige, tunghalede afkast er ukendt.
- Lookahead kan ikke påvises af afkast alene. Uden tidsstempler eller genberegning er status `MISSING_INPUT`. Afkortningstest finder kun fejl i det, `signal_fn` faktisk beregner.
- PBO er lav ved stærk persistens uden evne (`research/studies/PBO_PERSISTENCE_2026-10-21.md`), derfor INCONCLUSIVE over grænsen. PBO måler selektion inden for familien, ikke effektens niveau: 20 syntetiske familier med ens ægte drift gav gennemsnitlig PBO 0,56 (spænd 0,00 til 0,94), og derfor giver PBO ≥ 0,5 ved høj DSR INCONCLUSIVE og ikke FAIL. Det betyder "valget af variant bærer ikke", ikke "ingen effekt".
- DSR bruger N = antal testede varianter og sænker det ikke med en korrelationsrabat.
- Bonferroni-grenen med kun `best_t` antager, at t-tallet er korrekt beregnet, og tager ikke højde for autokorrelation.
- Survivorship dækker ikke sidste tab ved delisting. Der tjekkes kun, at medlemmet er med.
- Register V2 gemmer ikke sig selv. `render_jsonl` giver tekst; placering og commit er ikke afgjort, og `deviations` påvirker ikke motorens status endnu.
- Litteraturhenvisninger er fra hukommelsen og ikke slået op (intet netværk): Bailey & López de Prado 2014 (DSR); Bailey, Borwein, López de Prado & Zhu 2014 (PBO/CSCV); White 2000 og Romano & Wolf 2005 (max-t-familien); Politis & Romano 1992 (cirkulær blok); Hall, Horowitz & Jing 1995 (blokstørrelsens orden).
