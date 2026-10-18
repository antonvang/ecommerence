# Designgrundlag for PROTOCOL_V3 ændring 8 (hypotesefamilier)

Status: designpanel 2026-10-18 (3 uafhængige design, 2 dommere, syntese). Brugeren bekræftede de anbefalede valg samme dag. Den gældende tekst er ændring 8 i research/PROTOCOL_V3.md; dette dokument er arbejdsgrundlaget for koden (familieformat, kodeliste, tests, udkast til F1 og F2, risici).

(A) Amendment text (Danish, to be appended to `research/PROTOCOL_V3.md` after line 471, committed before any code)

---

## Ændring 8 (2026-10-18): hypotesefamilier — forhåndsregistrerede familier af ikke-prisforudsigende mekanismer, alfa-budget og fremadtest — før kode

**Beslutning:** brugeren besluttede 2026-10-18 at genstarte idégenereringen gennem forhåndsregistrerede hypotesefamilier:
- kun mekanismer, der ikke forudsiger priser: struktur, tilskud, carry, flow og likviditetsydelse. Det følger
  `research/STRATEGIC_OPPORTUNITY_REVIEW.md` afsnit 3 ("Price-prediction strategies are therefore not pursued further");
- en AI må skrive udkast til en familie, men kun brugeren godkender den, og han skriver selv godkendelsen i terminalen;
- et alfa-budget håndhæves, og en fremadtest afgør;
- registreringer, der skal hente nye data, venter til efter 2026-11-27. Indtil da bruger pm_lp netværket og DNS.

**Gælder:** kun eksperimenter, der registreres som instanser af en godkendt familie.
- Alle resultater for v1–v3 står, som de er registreret.
- MVRV's kohorte `fwd202611` (N = 1) og fremadtest-familien i ændring 7 (N = 10) ændres ikke.
- `lab/engine/catalogue.py` ændres ikke. De 3 skabelongodkendelser, der i dag er gyldige for katalogets blob
  `cfa04601fd86`, forbliver derfor gyldige: `mvrv_value`, `real_rate_filter` og `supply_dilution`.
- Ingen gate lempes, ingen tærskel ændres, og alt nyt er strengere.
- Tal mærket **[BEKRÆFT]** skal brugeren bekræfte, før koden skrives.

1. **Hvad en familie er.**
   - En familie består af to filer:
     - en committet JSON-fil `research/families/<fid>.json` (skema `lab.family/1`);
     - ét mekanismemodul `lab/families/<fid>.py` med positionsfunktioner, instrumentmodel og attribution.
   - Hver familie har ét kanonisk mekanisme-tag fra det kontrollerede ordforråd `research/families/VOCABULARY.json`.
     - Ordforrådet dækker alle eksisterende tags fra kataloget, legacy og scanneren, hver med klasse og beslægtede tags.
     - Et nyt tag kræver en ændring af ordforrådet. Ordforrådets blob er bundet i godkendelsen, så brugeren ser og godkender ændringen.
   - Instanserne hedder `E_<fid>__<instans>_a8`.

2. **Kun ikke-prisforudsigende mekanismer.**
   - Klassen skal være `carry`, `structural`, `subsidy`, `flow` eller `liquidity_provision`. Klassen `price_prediction` afvises, og alle 28 katalog-tags har den klasse.
   - Positionerne skal være afdækket i samme aktiv (`hedged_same_asset`), fx lang spot og kort perp i samme mønt. Retningsbestemte bøger og uafdækkede lange/korte bøger på tværs af mønter afvises.
   - Afkastkilden skal være en navngiven pengestrøm (funding, låst basis eller belønning). Attributionsgaten i punkt 8 tester den.
   - Denne ændring kan kun køre to instrumentmodeller: `spot_perp_ratio` og `spot_delivery_ratio`. De øvrige klasser står i ordforrådet, men kræver en senere ændring med deres egen instrumentmodel.

3. **Størrelse. [BEKRÆFT]**
   - Højst K = 3 basisinstanser. Hver har præcis 2 faste varianter, og varianten vælges på træning efter den eksisterende regel.
   - Hver basisinstans må have højst 1 forhåndsopregnet efterfølger (punkt 9). Det giver højst 12 trials pr. familie.
   - Tilbagekig er højst 14 dage. Positionerne er 0, indtil tilbagekigget er fyldt inden for vinduet (afsnit 2, "Opvarmning").
   - Beslutninger træffes kl. 01:00 UTC og bruger kun funding, der er afregnet før beslutningen.
     - Grund: motoren krediterer en afregning til positionen i den time, der starter ved afregningen (`lab/engine/data.py:158-163`, `lab/engine/backtest.py:28-38`).
     - En beslutning kl. 00:00 ville derfor give hver indgang en afregning, som den ikke ville få i virkeligheden.
   - Signaler bruger summen af afregnet funding over L dage, annualiseret (× 365/L). Det gør dem uafhængige af afregningsintervallet (8, 4 eller 2 timer).
   - Højst 2 familier pr. kanonisk tag i hele programmet. Højst 1 åben familie pr. tag ad gangen.

4. **Udkast.**
   - En AI må skrive og committe familiefil og modul som udkast (feltet `drafted_by`).
   - Udkastet må ikke beregne afkast eller signaler på data fra noget vindue.
   - Aggregerede tal, der er set under designet, skal oplyses i filen (feltet `drafting_data_access`); se punkt 20.
   - `python3 -m lab family-check FIL` er skrivebeskyttet og bruger intet netværk; alle må køre den. Den viser:
     - skema og ordforråd;
     - blobs;
     - kirkegård og beslægtede tags;
     - hvilke filer der allerede ligger i cachen;
     - budgetvirkning og styrketabel.

5. **Godkendelse — kun brugeren.**
   - Godkendelsen har to trin, som brugeren selv skriver i en interaktiv terminal:
     - `python3 -m lab approve-family <fid> --reason "..."` viser resumé, blobs, styrketabel, budgetvirkning og kirkegårdskvitteringer og giver en engangskode, der gælder i 15 minutter;
     - `python3 -m lab confirm-family` spørger om koden og om de første 8 tegn af familiefilens blob. Begge læses fra prompten, aldrig som argumenter.
   - Begge kommandoer nægter at køre, hvis stdin eller stdout ikke er en terminal, eller hvis en assistent-miljøvariabel (`CLAUDECODE`, `CLAUDE_CODE_*`) er sat. Der findes intet dashboard-endepunkt.
   - En assistent kører aldrig disse kommandoer. Mønstret "Claude bekræftede på brugerens instruks" (ændring 2, registrering) gælder ikke for familier.
   - Ærligt: koden kan ikke bevise, at et menneske skrev. Det er denne regel, der er bindende.
   - Godkendelsen (hændelsen `family.approved`) binder:
     - de committede blobs af familiefilen, modulet, `lab/families/__init__.py` og `VOCABULARY.json`;
     - de tærskler, familien bruger: `PLACEBO_P_MAX` 0,10, `DSR_MIN` 0,95, `COST_HIGH_MULT` 2,0 og bootstrap med 5 dage, 2.000 træk og seed 7.
   - Ændres noget af dette før registrering, er godkendelsen ugyldig.
   - Godkendelsen registrerer, hvilke instanser der er aktive, og hvilke der er droppet.
   - Kun et menneske kan tilbagekalde med `revoke-family`, og kun før registrering.

6. **Kirkegård og lektioner.**
   - Den eksisterende discovery-agent opdager instanserne fra committede, gyldige familiefiler, inklusive efterfølgere.
   - Kirkegården gælder som i dag: samme tag og udførelse, eller samme fingeraftryk. Et match giver SUPPRESSED.
   - Beslægtede tags fra ordforrådet tjekkes også. Hvert match på et eksperiment i REJECTED eller WITHDRAWN skal stå i `graveyard_acknowledged` med:
     - en tekst "materially different because …" på mindst 40 tegn;
     - de lektioner, teksten adresserer. Nøglerne er årsag 1–4 i `DIAGNOSE_HVORFOR_INTET_BESTAAR.md` og lektioner fra `research.diagnostic`.
   - Mangler en kvittering, nægtes godkendelse.
   - En SUPPRESSED instans genoplives kun gennem den eksisterende menneskelige overgang SUPPRESSED → DISCOVERED, med begrundelsen "materially different because …".
     - For familieinstanser kræver `lab confirm` en interaktiv terminal.
     - Genoplivning er et separat skridt og sker før `approve-family`.
   - Kirkegården tjekkes igen ved registrering. Familiens egne søskende tæller ikke som match.

7. **Registrering.**
   - Registreringen går gennem den eksisterende `register_batch`, som strategy-1 kalder i en flåde, et menneske har startet.
   - Basisinstanserne registreres én gang, som én batch: `batch.registered` med familie og trial-cutoff. Validering venter på alle medlemmers cost-trin.
   - Registrering nægtes, hvis:
     - godkendelsen er ugyldig, eller der ikke er reserveret alfa;
     - programmet er stoppet (punkt 15), eller 3 familier allerede er åbne;
     - et ikke-afsluttet eksperiment uden for familien dækker samme tag og udførelse;
     - det er før 2026-11-28 00:00 UTC, og en fil, som screeningen skal læse, ikke allerede ligger i `data/lab/market`.

8. **Screening er kun et filter.**
   - PROTOCOL v3-vinduerne og alle v2/v3-gates gælder uændret:
     - train-gaten;
     - før-validerings-gaten: eksakte look-ahead- og forgiftningstests, datakvalitet og placebo p < 0,10;
     - alle validerings-krav.
   - Ny og strengere gate, **mekanisme-attribution**: pengestrømmen minus alle omkostninger skal være > 0, og basis- og kurs-P&L skal være ≤ pengestrømmen.
   - Købe-og-holde-benchmarket er lige-vægtet købe-og-holde af de samme perps, med katalogets omkostninger.
   - DSR beregnes og registreres, men afgør intet.
   - Hver instans, der består alle andre krav, får "OBSERVE (family forward test)" og går SCREENING → OBSERVATION. Det gælder også ved DSR ≥ 0,95. En familieinstans går aldrig direkte til SCREEN_PASSED.
   - Instrumentet er én kvotientserie pr. mønt, så placebo blander begge ben samlet, og afdækningen bevares.
   - En regel, der næsten altid er aktiv, har ingen timing og fejler derfor placebo. Det er en kendt og accepteret konsekvens.

9. **Efterfølgere.**
   - Efterfølgere skal være forhåndsopregnet. De er kun én generation dybe og kan kun registreres, før kohorten lukkes.
   - En efterfølger registreres som en ekstra batch i familien, og kun hvis forælderens hash-verificerede træningsartefakter (`cost.json`, `adversarial.json`) opfylder den mekaniske udløser i familiefilen.
   - Valideringsresultater, fremaddata, slut-test og live-tal udløser aldrig noget.
   - Efterfølgere, der ikke er udløst, når kohorten lukkes, går DISCOVERED → SUPPRESSED. Det er en eksisterende automatisk kant.
   - En idé, der opstår efter resultaterne, er en ny familie med ny godkendelse og ny alfa.

10. **Kohorte. [BEKRÆFT]**
    - Kohorten lukkes ved det første strategy-pass, hvor alle registrerede medlemmer har et resultat, og ingen efterfølger længere kan udløses.
    - Hændelsen `cohort.fixed` registrerer kohorte-id, medlemmer, M, α_F, α_i = α_F/M og vinduerne. M og α_i genberegnes aldrig.
    - M ≤ 3. Overlever flere end 3, går de 3 med højest validerings-netto-Sharpe videre. Resten får "REJECTED: not selected (family cohort cap 3)".
    - Vinduet starter 00:00 UTC den 1. i måneden efter lukningen, dog aldrig før 2026-12-01, og varer 12 hele kalendermåneder.
    - Vinduet hedder `fwdYYYYMMm12`, og delvinduet hedder `fwdYYYYMMm06`.
    - Den gamle kohortetælling i `step_observe` ignorerer hændelser med en kohortenøgle, så MVRV's N forbliver 1.
    - M = 0 lukker familien som FUTILE_IN_SAMPLE.

11. **Fremadtest (den afgør).**
    - Den frosne variant genberegnes på arkivdata, tidligst 7 dage efter vinduets slutning.
    - Kravene er de samme som i ændring 2 punkt 4:
      - netto-gennemsnit pr. dag > 0;
      - ensidet 90 % nedre grænse > 0 (5-dages blokke, 2.000 træk, seed 7);
      - netto-Sharpe over lige-vægtet købe-og-holde af de samme perps;
      - netto total > 0 ved dobbelte omkostninger;
      - datakvalitet med `min_symbols`.
    - Hertil kommer mekanisme-attribution som i punkt 8.
    - Held-tjek: PSR_kons ≥ 1 − α_i. PSR_kons er den mindste af tre værdier, så den er aldrig lempeligere end i dag:
      - PSR med skævhed 0 og kurtosis 3, som i dag;
      - PSR med stikprøvens skævhed og kurtosis;
      - PSR med effektivt n = n / max(1, 1 + 2·Σ_{k=1..5}(1 − k/6)·ρ_k), aldrig over n.
    - Et symbol uden spot- eller perp-fil for vinduets første måned udelukkes før beregning (ændring 7 punkt 5).
    - PASS → SCREEN_PASSED. FAIL → REJECTED.

12. **Mellemliggende aflæsning — kan kun afvise.**
    - Delvinduet (månederne 1–6) er sit eget erklærede vindue. Det læses tidligst 7 dage efter, at det er slut.
    - Er netto-gennemsnittet pr. dag ≤ 0, eller pengestrømmen minus omkostninger ≤ 0, er udfaldet "FAIL (forward futility)" → REJECTED.
    - Ellers sættes slutevalueringen i kø.
    - Aflæsningen kan aldrig give PASS og ændrer hverken M eller α_i.

13. **Alfa-budget. [BEKRÆFT]**
    - Programformuen er W0 = 0,05 for alle fremadtests under ændring 8 tilsammen.
      - Den er adskilt fra ændring 2 (0,05 pr. vindue) og ændring 7 (0,05 ved N = 10).
      - Laboratoriets samlede fejlrisiko er derfor ikke 0,05. Det står åbent her.
    - Reglen er alfa-forbrug (Bonferroni), ikke alfa-investering.
    - α_F = 0,0125 pr. familie reserveres ved `confirm-family` som en række i `alpha_ledger` (exp_id `family:<fid>`, note "A8 reserve"). Godkendelse nægtes, hvis den resterende formue er under α_F.
    - Ved `cohort.fixed` med M ≥ 1 bruges α_F og fordeles som α_F/M pr. instans.
    - Alfa frigives (med en negativ række, "A8 release") kun, hvis familien tilbagekaldes før registrering, hvis M = 0, eller hvis familien bliver utestbar før lukning.
    - En PASS giver ingen alfa tilbage.
    - Familiefejlraten over alle ændring 8-fremadtests er ≤ 0,05 ved foreningsgrænsen, uden antagelse om uafhængighed.
    - De eksisterende rækker på 0,005 pr. eksperiment (28 rækker, 0,14 i alt) er bogføring af screening og indgår ikke i W0. Familieinstanser får en screening-række på 0.

14. **Styrkekrav før godkendelse.**
    - Godkendelse nægtes, medmindre styrken er ≥ 0,5 ved sand Sharpe 3,0 (fast, ikke selverklæret), α_F/3 og familiens vindueslængde.
    - Med α_F = 0,0125 kræver det 12 måneder: styrken er 0,63, mens 6 måneder giver 0,30.

15. **Futilitet og programstop. [BEKRÆFT]**
    - Familieniveau:
      - M = 0 → FUTILE_IN_SAMPLE.
      - For få symboler eller for lidt data → UNTESTABLE.
      - Begge frigiver alfa.
      - En permanent jobfejl standser familien uden at lukke kohorten.
    - Programmet modtager ingen nye familiegodkendelser, når et af disse gælder:
      - (a) den resterende formue er under α_F;
      - (b) 3 familier i træk er lukket uden en fremad-PASS (FUTILE, UNTESTABLE eller alle FAIL);
      - (c) der er ingen fremad-PASS pr. 2028-06-30.
    - Kun en ny dateret ændring kan genstarte programmet. Kørende fremadtests fortsætter til ende.

16. **Efter en fremad-PASS.**
    - Instansen går til SCREEN_PASSED.
    - Familier følger ikke den automatiske vej i ændring 4, fordi gaten "catalogue experiment" er lukket for dem. Slut-test 2024 og simuleret handel kræver derfor menneskelige godkendelser.
    - Slut-testen åbnes én gang som ét erklæret filsæt, der også rummer spot-filerne. Familiefilens blob er gatewayens kode-hash.
    - Uden en ren slut-test standser instansen på SCREEN_PASSED.
    - Simuleret handel for familier kræver et live spot-feed, som ikke findes i dag, og en senere ændring.

17. **Data og netværk. [BEKRÆFT]**
    - Før 2026-11-28 00:00 UTC foretager koden for ændring 8 ingen netværksforespørgsler: ingen HEAD-tjek og ingen downloads. pm_lp's opfølgning løber til 2026-11-27 (`PM_LP_START.md`).
    - Derefter hentes data kun fra `data.binance.vision`, gennem den eksisterende cache og download-kode og med flådens DNS-cache.
    - Spot-zips har samme filnavne som perp-zips. De gemmes derfor i `data/lab/market/spot_klines/`, og leveringskontrakter i `data/lab/market/cm_klines/`.
    - Hver familiefil angiver filantal og størrelse.

18. **Kode-pin.**
    - Ved registrering skriver specifikationen familiefilens blob, modulets blob og blobs for motorens filer.
    - Ændres familiefilen eller modulet efter registrering, fejler hvert senere trin lukket, også i 2027. En rettelse kræver en dateret ændring.

19. **Sikkerhed.**
    - Alt er simuleret: ingen rigtige penge, ingen nøgler, ingen ordrer.
    - Ingen autostart, cron eller timere. Alt kører i strategy-1's og discovery-agentens pass, i en flåde, som et menneske har startet.
    - Fremadjobs bruger det eksisterende felt `not_before`.

20. **Ærlig forventning og oplysning.**
    - Krævet annualiseret Sharpe (PSR med skævhed 0 og kurtosis 3):

      | Vindue | α_i 0,0125 | α_i 0,00625 | α_i 0,0042 |
      |---|---|---|---|
      | 12 måneder | 2,25 | 2,51 | 2,65 |
      | 6 måneder | 3,21 | 3,58 | 3,78 |

    - Styrke ved 12 måneder med aflæsning ved 6 måneder (simuleret):

      | Sand Sharpe | 2 | 3 | 4 |
      |---|---|---|---|
      | M = 1 | 0,40 | 0,77 | 0,96 |
      | M = 3 | 0,25 | 0,63 | 0,91 |

      Under nulhypotesen stoppes cirka 50 % ved 6 måneder.
    - Autokorrelation: med daglig AR(1), ρ = 0,3, består et nul-eksperiment dagens held-tjek med cirka 0,048 i stedet for 0,0125. PSR_kons giver cirka 0,017, men koster styrke: ved sand Sharpe 3 falder den fra 0,71 til 0,53.
    - Oplysning om data set under designet 2026-10-18:
      - Aggregerede funding-tal for de cachede filer 2022-01..2023-12 blev set: andel afregninger på præcis 0,01 % 0,44; andel negative 0,30; gennemsnit ≈ 0.
      - Der er ikke beregnet strategiafkast.
      - Familiernes gitre er taget uændret fra udkast, der blev skrevet før.
      - Screeningen er kun et filter, så fremadtestens gyldighed påvirkes ikke.

---

(B) Family file format, with the complete first family file

All paths are relative to `C:\Users\anton\ecommerence\copybot`.

**Where things live**
- `research/families/<fid>.json`: schema `lab.family/1`, committed, blob bound at approval.
- `lab/families/<fid>.py`: the mechanism module, committed, blob bound.
- `lab/families/__init__.py`: the shared adapter, blob bound.
- `research/families/VOCABULARY.json`: shape `{tag: {class, runnable, definition, related: [...]}}`, blob bound.
- `family-check` validates every rule below and works out cache status from the filesystem by itself. Any `cached` value written in the file is ignored.

**Fields**

| Field | Rule |
|---|---|
| `schema`, `family_id` | `family_id` matches `[a-z0-9]{3,12}` |
| `title`, `amendment`, `drafted_by` | required |
| `drafting_data_access` | required; disclosure only, never a licence to compute returns |
| `mechanism.tag` | must be in the vocabulary; class is not `price_prediction` |
| `mechanism.price_exposure` | must be `hedged_same_asset` |
| `mechanism.return_source`, `non_price_prediction` | required text |
| `mechanism.attribution` | `{cash_flow: funding_income \| locked_basis \| reward, rule}` |
| `mechanism.evidence` | each entry marked verified or unverified |
| `graveyard_acknowledged[]` | `{exp_id, match: exact\|related, materially_different_because (≥ 40 chars), lessons_addressed[]}` |
| `related_tags_reviewed[]` | the tags reviewed |
| `universe` | `base`, `rule`, `min_symbols` rule, `holdout_exclude`, `clean_holdout`, `forward_listing_rule` |
| `instrument_model.type` | `spot_perp_ratio` or `spot_delivery_ratio` |
| `data[]` | source, URL pattern, cache dir, splits, `files_estimate`, `mb_estimate` |
| `costs` | per unit of pair turnover; each component ≥ `catalogue.COSTS` (`catalogue.py:19-22`) |
| `decision_time_utc` | `"01:00"` |
| `windows`, `forward` | `{months: 12, interim_futility_months: 6, earliest_start: "2026-12-01"}` |
| `alpha` | `{family ≤ 0.0125}` |
| `instances[]` | 1–3 entries of `{id, function, horizon, execution: "taker", max_lookback_days ≤ 14, rule, grid: exactly 2 dicts, successor: null \| {id, function, grid, trigger{artifact ∈ {cost, adversarial}, all[]}, why}}` |
| `expected` | honest power numbers |

**Registration mapping**
- The adapter writes experiment version 2 with `spec_path` = the family JSON, `spec_commit`, and `code_hash` = the family JSON blob.
- The spec has every field in `REQUIRED_SPEC` (`registry.py:13`).
- `alpha` is written as a dict (`{in_sample: 0, forward_family: 0.0125, rule}`). It must be truthy because of the field check style at `templates.py:114-116`, and it can never go through `registry.add_version`, which does `float(spec["alpha"])` (`registry.py:123`).
- The spec also records `template = "<fid>__<inst>"`, `family`, `instance`, `protocol_version 3`, `amendment 8`, `benchmark_costs = catalogue.COSTS`, and `code_blobs` (the 4 bound files plus `ENGINE_CODE`).

**Complete example: `research/families/fcarry.json`**

```json
{
  "schema": "lab.family/1",
  "family_id": "fcarry",
  "title": "Hedged Binance funding carry: long spot / short USD-M perp in the same coin",
  "amendment": "research/PROTOCOL_V3.md Ændring 8",
  "drafted_by": "ai:claude-opus-5-5 2026-10-18",
  "drafting_data_access": {
    "strategy_returns_computed": "none",
    "disclosed": [
      "2026-10-18 design review saw the aggregate settled-funding distribution of the cached USD-M files 2022-01..2023-12: share exactly 0.0001 = 0.44, share negative = 0.30, mean ~0. No signal or return was computed. Grids are copied unchanged from drafts written before that read."
    ]
  },
  "mechanism": {
    "tag": "delta_neutral_funding_carry",
    "class": "carry",
    "price_exposure": "hedged_same_asset",
    "return_source": "settled Binance USD-M funding received by the short perp leg",
    "non_price_prediction": "Both legs are the same coin, so the price delta is ~0. P&L = funding received + change of the spot/perp ratio - costs. Signals forecast only the persistence of the funding cash flow, never price direction or relative price between coins.",
    "attribution": {
      "cash_flow": "funding_income",
      "rule": "funding_income - (fees + spread + slippage) > 0 AND gross_ratio_pnl <= funding_income; in-sample (validation) and forward"
    },
    "evidence": [
      {"ref": "Binance USD-M funding = premium + clamp(0.01%/8h - premium, +-0.05%)", "status": "unverified"},
      {"ref": "research/RESULTS_carry_v1.md: Hyperliquid carry, holdout +4.352 %, development -0.079 %, edge decaying", "status": "verified-local"},
      {"ref": "Schmeling, Schrimpf & Todorov, BIS Working Paper 1087, Crypto carry", "status": "unverified (Crossref check before approval)"}
    ]
  },
  "graveyard_acknowledged": [
    {
      "exp_id": "L13_carry_v1", "match": "exact",
      "materially_different_because": "materially different because carry_v1 ran on Hyperliquid spot pairs (19 pairs, valid only from 2024-12, survivorship on delisted spot pairs, 2.2 coins on average) with weekly top-5 re-ranking whose fees exceeded the funding in development; this family uses Binance spot/perp pairs of the 30 PROTOCOL v3 coins with point-in-time data from 2022, low-turnover filter/hysteresis/persistence rules decided at 01:00 UTC, explicit two-leg costs, an attribution gate, and is decided only by an unseen 12-month forward window",
      "lessons_addressed": ["DIAGNOSE-4 turnover x costs", "L13 weekly churn", "L13 decay"]
    },
    {
      "exp_id": "L08_funding_carry_leverage", "match": "related",
      "materially_different_because": "materially different because L08 was unhedged leveraged perp carry that failed through liquidations at 5x-10x; this family is 1x, same-coin hedged, never leveraged, and rejects profit from price moves by the attribution gate",
      "lessons_addressed": ["L08 leverage and liquidations"]
    },
    {
      "exp_id": "E_funding_contrarian_p1", "match": "related",
      "materially_different_because": "materially different because funding_contrarian was a directional tail-entry bet on 8 coins that lost to the 2023-H2 rally; this family has zero price delta per coin and is paid the funding instead of betting on a reversal",
      "lessons_addressed": ["DIAGNOSE-1 rally benchmark", "DIAGNOSE-3 regime shift"]
    },
    {
      "exp_id": "L22_m3_premium_convergence", "match": "related",
      "materially_different_because": "materially different because L22 traded minute-level premium convergence and lost 31.6-33.4 bp net to costs; this family holds for days to weeks, earns settled funding rather than premium reversion, and needs about 15 days of floor funding to repay a pair round trip",
      "lessons_addressed": ["DIAGNOSE-4 turnover x costs", "L22 costs"]
    }
  ],
  "related_tags_reviewed": ["funding_carry", "funding_carry_leverage", "funding_crowding_contrarian", "perp_premium_convergence", "dated_futures_basis_carry"],
  "universe": {
    "base": "30v3",
    "rule": "UNIVERSE_30_V3 (lab/engine/data.py:30-31); a coin whose spot or perp leg fails the existing data-quality rule in a split is excluded in that split (missing spot months fail coverage)",
    "min_symbols": 24,
    "holdout_exclude": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "clean_holdout": true,
    "forward_listing_rule": "exclude a coin with no spot or perp file for the first window month (amendment 7 section 5)"
  },
  "instrument_model": {
    "type": "spot_perp_ratio",
    "bars": "per coin and hour: (ts, spot_open / perp_open, spot_close / perp_close) on the intersection of hours",
    "funding_for_costs": "minus the settled rate, so a +1 position earns the settled rate through backtest.apply_costs",
    "position": "+1 = long 1 unit spot and short 1 unit perp, equal notional, 1x; 0 = flat; never negative",
    "benchmark": "equal-weight buy-and-hold of the same USD-M perps with catalogue costs and funding",
    "capital_per_unit_notional": 2
  },
  "data": [
    {"source": "binance_um_klines_1h", "url": "https://data.binance.vision/data/futures/um/monthly/klines/{SYM}/1h/{SYM}-1h-{YYYY}-{MM}.zip", "cache_dir": "data/lab/market/klines", "splits": ["train3", "validation3"], "files_estimate": 720, "mb_estimate": 25},
    {"source": "binance_um_fundingRate", "url": "https://data.binance.vision/data/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-{YYYY}-{MM}.zip", "cache_dir": "data/lab/market/funding", "splits": ["train3", "validation3"], "files_estimate": 720, "mb_estimate": 3},
    {"source": "binance_spot_klines_1h", "url": "https://data.binance.vision/data/spot/monthly/klines/{SYM}/1h/{SYM}-1h-{YYYY}-{MM}.zip", "cache_dir": "data/lab/market/spot_klines", "splits": ["train3", "validation3"], "files_estimate": 720, "mb_estimate": "25-50"}
  ],
  "costs": {
    "taker_fee": 0.0015, "half_spread": 0.0004, "slippage": 0.0004,
    "per": "unit of pair turnover (both legs)",
    "components": {"spot_taker": 0.0010, "perp_taker": 0.0005, "spot_half_spread": 0.0002, "perp_half_spread": 0.0002, "spot_slippage": 0.0002, "perp_slippage": 0.0002},
    "estimates": ["all half_spread and slippage values", "spot taker VIP0 0.10 % not re-verified"],
    "funding": "settled Binance funding from the data, credited to the short perp leg",
    "stress_mult": 2.0
  },
  "decision_time_utc": "01:00",
  "windows": {"train": "train3 2022-01..2023-06", "validation": "validation3 2023-07..2023-12", "holdout": "2024, sealed, human approval only, without BTC/ETH/SOL", "reserved": "2025-01-01 until the forward window start, never read"},
  "forward": {"months": 12, "interim_futility_months": 6, "earliest_start": "2026-12-01"},
  "alpha": {"family": 0.0125, "split": "alpha_F / M at cohort.fixed, M <= 3"},
  "power_check": {"true_sharpe": 3.0, "alpha": 0.0041667, "months": 12, "required": 0.5, "expected": 0.63},
  "instances": [
    {
      "id": "filt", "function": "carry_filter", "horizon": "days", "execution": "taker", "max_lookback_days": 7,
      "rule": "Daily 01:00 UTC. APR_7 = sum of funding settled in the 7 days before the decision x 365/7. Hold +1 in coin i iff APR_7 >= enter_apr, else 0. Flat until 7 days of funding exist in the window.",
      "grid": [{"lookback_days": 7, "enter_apr": 0.1095}, {"lookback_days": 7, "enter_apr": 0.219}],
      "successor": {
        "id": "filt_w", "function": "carry_filter_weekly",
        "grid": [{"lookback_days": 7, "enter_apr": 0.1095}, {"lookback_days": 7, "enter_apr": 0.219}],
        "trigger": {"artifact": "cost", "all": ["rejected_early == true", "selected.net.fees + selected.net.spread + selected.net.slippage > -selected.net.funding"]},
        "why": "Same rule decided only on Mondays 01:00 UTC; tests whether a train-gate failure was caused by churn costs rather than an absent cash flow."
      }
    },
    {
      "id": "hyst", "function": "carry_hysteresis", "horizon": "days", "execution": "taker", "max_lookback_days": 7,
      "rule": "Daily 01:00 UTC. Enter +1 when APR_7 >= 0.219; exit to 0 when APR_7 < exit_apr; otherwise keep the previous position.",
      "grid": [{"lookback_days": 7, "exit_apr": 0.0}, {"lookback_days": 7, "exit_apr": 0.1095}],
      "successor": null
    },
    {
      "id": "floor", "function": "carry_floor", "horizon": "weeks", "execution": "taker", "max_lookback_days": 14,
      "rule": "Mondays 01:00 UTC. share = fraction of the last 14 completed UTC days whose summed settled funding >= 0.0003 (the 0.01 %/8h interest floor per day). Hold +1 for the week iff share >= q.",
      "grid": [{"days": 14, "q": 0.80}, {"days": 14, "q": 0.95}],
      "successor": null
    }
  ],
  "expected": {
    "required_forward_sharpe_12m": {"M=1": 2.25, "M=2": 2.51, "M=3": 2.65},
    "forward_power_12m_with_interim": {"S=2": [0.40, 0.30, 0.25], "S=3": [0.77, 0.68, 0.63], "S=4": [0.96, 0.93, 0.91]},
    "p_at_least_one_screen_survivor": "0.25-0.45 [estimate]",
    "p_at_least_one_forward_pass": "0.04-0.12 [estimate]",
    "false_pass_under_null": "<= 0.0125 for the family"
  }
}
```

---

(C) Code changes and tests

The family layer extends the existing machinery: catalogue, approvals table, `register_batch`, the job chain and `step_observe`. There is no parallel pipeline, and nothing is injected into `catalogue.TEMPLATES`.

| # | File | Function(s) | Change | Size |
|---|---|---|---|---|
| 1 | `research/PROTOCOL_V3.md` | – | Ændring 8 as in (A); committed first | ~170 lines |
| 2 | `research/families/VOCABULARY.json` (new) | – | 28 catalogue tags (all `price_prediction`), 25 legacy tags (`legacy.py:16-100`), scanner tags (`cross_venue_perp_gap`, `perp_premium_convergence`), and the new `dated_futures_basis_carry`; each with class, `runnable`, `related` | ~150 |
| 3 | `research/families/fcarry.json` (new) | – | (B) | ~140 |
| 4 | `lab/families/__init__.py` (new) | `load/validate`, `blobs`, `power/required_sharpe` (same formula as `backtest.psr`, `backtest.py:130-135`), `budget/reserve/release/spend`, `request/confirm/revoke/approval`, `discover_all`, `template(spec)`, `instance_spec`, `transform`, `expected_paths/ready` (embargo, injectable clock as `data.CLOCK`, `data.py:37`), `guarded_get`, `registration_block`, `register_transition`, `pass_`, `psr_cons`, `attribution` | Schema/vocabulary/K/grid/lookback/months checks. Approval rows `exp_id='family:<fid>'`, `to_state='FAMILY_APPROVED'`; `lifecycle.confirm` rejects such a code as an unknown state (`lifecycle.py:71-72`). `guarded_get` is passed to `data._fetch(url, path, get)` (`data.py:95`) and raises before the embargo ends. `register_transition` mirrors `templates.register_transition` (`templates.py:105-123`). `pass_` covers waiting events, train-only successor triggers via `pipeline.frozen_artifact` (`pipeline.py:71-84`), cohort close, family close and programme stop. | L ~450 |
| 5 | `lab/families/fcarry.py` (new) | `carry_filter`, `carry_filter_weekly`, `carry_hysteresis`, `carry_floor`, `attribution` | Signal is −(cost-convention funding) summed over L days; uses only settlements before 01:00; cross-sectional calling convention, so the truncation/poison xs tests apply unchanged (`adversarial.py:60-125`) | M ~150 |
| 6 | `lab/pipeline.py` | accessors `_tpl(spec)`, `_universe(spec)`, `_min_symbols(spec)` | Replace the direct catalogue lookups at :193, :237, :311-312, :347/:372, :377, :385-394, :425-426, :485, :683, :698-699, :732, :735; `_family/_positions/_fit` take the template dict | ~+60/−30 |
| | | `_template` (:148-152) | Return `spec["template"]`; raise only if neither `template` nor `family` is present | +2 |
| | | `register_batch` (:155-172) | Split the ids. The catalogue path moves unchanged into `_batch()`. Family groups get `registration_block` → graveyard re-check (excluding own family) → `_batch(..., family=fid)`. Unapproved family ids are skipped silently. | +35 |
| | | `_register_one` (:175-188) | Family branch: version 2 from `families.instance_spec`, alpha row 0.0 with note "A8 in-sample filter", `families.register_transition` | +15 |
| | | `enqueue_pipeline` (:193) | Priority from `_tpl` (families: 120) | +2 |
| | | `_files` (:234-249), `_code_hash` (:266-267) | Spec-aware: family code hash = registered family blob; spot paths recorded in the same gateway access | +12 |
| | | `_market` (:307-331), `_benchmark` (:403-405) | Family: `families.transform` → ratio bars, cost-convention funding, plus a `FamilyData` holder with the perp bars and raw funding for the benchmark. The family function gets `extra=None`, so `adversarial.BUNDLE_KEYS` (`adversarial.py:45`) needs no change. | +30 |
| | | `step_validate` (:534-541) | Attribution gate added for families | +8 |
| | | `step_report` (:566-595) | Family: `set(failed) ⊆ {DSR}` → "OBSERVE (family forward test)" → OBSERVATION; no `observation.started` and no observe job (cohort handles both) | +12 |
| | | `step_observe` (:611-656) | Legacy count (:628-633) adds `and not p.get("cohort")`. Family branch: α_i from `cohort.fixed`, PSR_cons, attribution gate, listing exclusion, perp benchmark | +35 |
| | | `step_observe_interim` (new), `HANDLERS` (:799-801) | Months 1–6 split; reject-only; queues the final job with `not_before` | +40 |
| | | `_declare_holdout` (:695-716), `step_holdout` (:719-735) | Spot paths go into the one declared set; family blob as code hash; `spec.get("template")` for `NO_CLEAN_HOLDOUT` | +12 |
| 7 | `lab/engine/data.py` | `spot_files_for`, `expected_paths`, `forward_split` (:77-84) | Spot from `data/spot/monthly/klines/...` cached in `CACHE/spot_klines` (fixes the silent reuse of the perp zip at :96-97/:121-122). `expected_paths` builds the path list with no network. `forward_split(start, months, tagged=False)`: the default name stays `fwdYYYYMM`; `tagged` gives `fwdYYYYMMm{NN}`. | +55 |
| 8 | `lab/registry.py` | `graveyard`, `discover`, `covering` (:46-91) | `exclude=()` parameter (own family members); new `graveyard_related(db, tags, execution)` | +25 |
| 9 | `lab/fleet.py` | `strategy_pass` (:350-358), `catalogue_pass` (:417-418), `HEAVY` (:26), validation kinds (:442-445) | Call `families.pass_` (errors are contained per family) and `families.discover_all`; add `observe_interim`; no roster or timer change | +10 |
| 10 | `lab/__main__.py` | new commands; `confirm` | `family-check`, `approve-family`, `confirm-family`, `revoke-family`, `families` (TTY plus `CLAUDECODE` refusal); `confirm` requires a TTY when the approval targets a family instance | +120 |
| 11 | `lab/paper_runner.py` | `run_one` (:255) | Family instance → "unsupported" instead of a `KeyError` | +6 |
| 12 | `lab/promotion.py` | `LIVE_UNSUPPORTED` (:24) | Add "spot" and "delivery". The gate at :84 already stays closed for families (`t in catalogue.TEMPLATES` is false). | +1 |
| 13 | `lab/command.py`, `lab/web.py` | `STAGE_OF_KIND` (:22), read model | Add `observe_interim`; read-only families/budget/cohort card; deliberately no approval endpoint (unlike `web.py:385-393`) | +50 |
| 14 | `lab/engine/catalogue.py`, `lab/engine/adversarial.py` | – | No change. A test asserts the catalogue blob is `cfa04601fd86`. The per-coin ratio series makes the placebo pair-preserving with no code change. | 0 |
| 15 | Phase B | `lab/families/dbasis.py`, `research/families/dbasis.json`, `data.delivery_files_for` (`CACHE/cm_klines`), forward attribution diagnostic in `lab/diagnose.py` | After 2026-11-28 | ~240 + 120 + 40 + 30 |
| 16 | `tests/test_lab_families.py` (new); `tests/test_lab_v3.py:300` | – | Tests below; `write_market` gains spot and COIN-M writers; `_fetch` is patched to raise in every test | ~650 |

Phase A (offline, before 2026-11-28) is about 1,250 lines of code and text plus about 650 lines of tests. Phase B is about 430 lines.

Tests (run on the Linux host in a separate checkout, never against the live runtime):
1. G3.2 safety: the catalogue blob is unchanged. `templates.approval` for `mvrv_value`, `real_rate_filter` and `supply_dilution` gives the same result before and after a family approval. `catalogue.TEMPLATES` is never mutated.
2. Binding: changing any of the 4 bound files, or a bound threshold, voids the approval. Changing `catalogue.py` does not void a family approval.
3. TTY guards: refused for non-TTY stdin or stdout, `CLAUDECODE` set, wrong blob prefix, expired code, reused code, or a non-human actor. A family code given to `lab confirm` fails as an unknown state. Reviving a family instance through `lab confirm` requires a TTY. No web route exists.
4. Schema refusals: K = 4, 3 variants, lookback 30, months 9, unknown tag, class `price_prediction`, not hedged, an acknowledgement shorter than 40 characters, and a successor trigger on `validate.json`.
5. Power: 6 months at α 0.005 needs 3.69 (amendment 7's "cirka 3,7"); 12 months at 0.0125 needs 2.25. A 6-month family is refused.
6. Budget property test: random sequences of approve, revoke, cohort (M = 0..3) and close never take the A8 sum above 0.05. Releases happen only in the allowed cases. `confirm` is refused when W < α_F. The 0.005 rows are excluded.
7. Graveyard: fcarry instances are SUPPRESSED by L13 at discovery. They can only be revived by a human with "materially different". An unacknowledged related tag is refused. The registration re-check ignores siblings. `covering` ignores siblings but blocks a second open family on the same tag.
8. Embargo: with the clock at 2026-11-20 and spot files missing, nothing registers, exactly one `family.waiting` event is written, and `guarded_get` is never called. With every file present it registers. On 2026-11-28 it downloads.
9. `register_batch` with mixed catalogue and family DISCOVERED ids: no `StepError` (regression for `pipeline.py:148-152`, `:160`). The catalogue path is unchanged. Family batches are separate, with the cutoff and validate dependencies, and their priority does not use the catalogue index.
10. Spec completeness: every `REQUIRED_SPEC` field, a truthy alpha dict, `spec_path` = the family JSON, `code_hash` = the family blob.
11. Cache collision regression: with a perp `BTCUSDT-1h-2022-01.zip` in `klines/`, `spot_files_for` never returns it.
12. Transform: synthetic spot and perp with constant funding f give a +1 position +f per settlement. The ratio return is close to r_s − r_p. Microsecond spot timestamps parse. A missing spot hour lowers coverage until the coin is excluded.
13. Settlement timing: positions change only at 01:00 and use funding ≤ the decision time. Truncation and poison tests are exact for all 4 fcarry functions.
14. Placebo: a constant-exposure instance gets p = 1.0 and is REJECTED with no validation data read. A regime-timed fixture gets p < 0.10.
15. Routing: a DSR pass goes to OBSERVATION, never SCREEN_PASSED. A failure on DSR only also goes to OBSERVATION. An attribution failure goes to REJECTED. No observe job is written at report time.
16. Benchmark: uses the perp bars and `catalogue.COSTS`, not the ratio series or pair costs.
17. Lineage: a successor registers only when the parent's frozen `cost.json` meets the trigger. Never from `validate.json`, never after cohort close, no grandchild. Untriggered successors go DISCOVERED → SUPPRESSED at close.
18. Cohort: it closes only after every member and every possible trigger. `cohort.fixed` holds M and α_i with a window ≥ 2026-12-01 named `m12`/`m06`. The cap of 3 is applied by validation net Sharpe and capped-out instances get "not selected". The alpha_ledger rows are right. M = 0 gives a release and FUTILE.
19. MVRV safety: in a fixture with MVRV's `fwd202611` event plus family events, MVRV still needs 0.95. `forward_split(start, 6)` still returns `fwd202611`. Tagged and untagged splits starting in the same month do not overwrite each other in `SPLITS`.
20. Amendment 7 safety: `FORWARD_ACCOUNTS` and the `forward.*` events are untouched, and families write no `forward.*` events.
21. Interim: refused before the sub-window end + 7 days (`data.window`, `data.py:62-74`). Futility gives REJECTED and no final job. A pass queues the final job with the correct `not_before`.
22. Final: α_i comes from `cohort.fixed`. PSR_cons is never above the iid PSR, and n_eff is never above n. An AR(1) fixture has a lower false-pass rate. Delisted coins are excluded. A PASS gives SCREEN_PASSED and a VALIDATION result row.
23. Promotion: a family instance in SCREEN_PASSED gets "waiting" even with autopromote on.
24. Holdout: the family blob is the code hash, spot files are in the declared set, a catalogue change does not lock it, there is no `KeyError`, and BTC/ETH/SOL are excluded.
25. Paper: `run_one` on a family instance returns "unsupported".
26. Frozen spec: changing the family JSON or the module after registration makes the next step raise `StepError`.
27. Programme stop: 3 closed families without a PASS refuse new approvals; after 2028-06-30 approvals are refused; at most 3 families are open.
28. S7: `ROSTER` names and intervals are unchanged and there are no timers. The full existing suite, including `test_lab_v3` `ForwardEvaluation`, is green.

---

(D) First family drafts

**Data verified read-only on Linux on 2026-10-18** (`ls`/`du`, sqlite `mode=ro`; Linux HEAD 2535fe6):
- `data/lab/market/klines`: 744 zips, 25 MB. All 30 v3 symbols have 24/24 months for 2022-01..2023-12; APE and ICP have 12 each.
- `funding`: 744 zips, 3.0 MB. Header `calc_time,funding_interval_hours,last_funding_rate`. Settlements by interval: 8h 67,864, 2h 99, 4h 2. This is why the signals are interval-free day sums.
- `metrics` 211 MB, `metrics_daily` 3.2 MB, `coinmetrics` 620 KB, `dvol` 36 KB, `fred` 16 KB, `stable` 24 KB.
- No spot files, no COIN-M files, no 2024 files anywhere under `data/`. Disk has 45 GB free.
- Registry: 29 `template.approved` events across 6 blobs, 3 of them valid for `cfa04601fd86`. `alpha_ledger` has 28 rows totalling 0.14. The only `observation.started` event is `E_mvrv_value_p3`/`fwd202611`. There are 56 trials, 12 `research.diagnostic` events and 10 `forward.approved` events.
- L13_carry_v1 (`delta_neutral_funding_carry`/taker) and L08 are REJECTED; L07 is RETIRED; E_funding_contrarian_p1 is REJECTED; L22 is REJECTED; C_0755f34d6d is SUPPRESSED.

**Consequence:** no hedged family can be screened from today's cache. Both drafts register on or after 2026-11-28.

**F1 `fcarry`: hedged Binance spot/perp funding carry.** Complete file in (B).
- **Mechanism.** Funding class carry, with a structural interest-floor component. Instances `filt`, `hyst` and `floor` (K = 3); one successor, `filt_w`. That is 6–8 trials.
- **Graveyard.** An exact hit on L13: all 4 instances are created SUPPRESSED, and the user revives each one himself, or drops F1.
- **Data needed after 2026-11-28:** 720 spot zips, about 25–50 MB [estimate], via `data.binance.vision` with 8 threads. Coins with missing spot months drop out through the existing quality rule; min_symbols is 24.
- **Costs.** A pair round trip costs 0.46 % of notional. At the 1× floor of 10.95 % APR, a hold needs about 15 days to break even; at 21.9 %, about 8 days.
- **Timeline if the fleet is started on 2026-11-28 and the screen finishes by 11-30:**
  - window 2026-12-01..2027-11-30;
  - interim read ≥ 2027-06-08;
  - final read ≥ 2027-12-08;
  - about 1,080 forward zips (about 40 MB), spread across those two reads.
- **Honest power.**
  - The in-sample hurdles are severe. Aggregate 2022–23 funding was about 0 (disclosed). The validation3 buy-and-hold Sharpe is 2.02. The pair-preserving placebo removes always-on rules.
  - P(at least one screen survivor) ≈ 0.25–0.45 [estimate].
  - Forward, per instance, at 12 months with the interim look: S = 2 → 0.40 / 0.30 / 0.25 for M = 1 / 2 / 3; S = 3 → 0.77 / 0.68 / 0.63. PSR_cons lowers S = 3 to about 0.53 if the daily autocorrelation is about 0.3.
  - carry_v1's holdout active-week Sharpe was about 4.9, but its development period was −0.079 % and the edge looked like it was decaying (`RESULTS_carry_v1.md:29-30`, `:53`). Nefedov 2026 finds that carry "survives only under optimistic cost assumptions" (`STRATEGIC_OPPORTUNITY_REVIEW.md:141`).
  - P(F1 yields at least one forward PASS) ≈ 0.04–0.12. Under the null it is ≤ 0.0125.
  - Value even if it fails: the forward attribution split (funding vs basis vs costs) decides whether to retire the carry class.

**F2 `dbasis`: COIN-M quarterly cash-and-carry on altcoins.** Phase B; a draft only until it is verified.
- **Mechanism.** Long 1 coin spot and short an inverse quarterly with face F0 USD. The USD value is S_t·F0/F_t: exactly a ratio series S/F, which converges to F0 at delivery and so locks the basis.
  - New tag `dated_futures_basis_carry`, class carry. No exact graveyard hit.
  - The related tags L13, L22 and `cross_venue_perp_gap` must be acknowledged.
- **Instances (K = 3), all decided at 01:00 UTC, with B = annualised basis of the nearest quarterly with more than 3 days to expiry:**
  - `thresh`: hold when B ≥ θ; exit when B < θ/2 or 3 days before expiry; θ = 5 % / 10 %.
  - `hold2exp`: enter the day after a roll if B ≥ θ, then hold to expiry − 3 days; θ = 5 % / 10 %.
  - `xsbasis`: Mondays, hold the k coins with the highest B among those with B ≥ 5 %; k = 3 / 5.
  - Rolls are a flat bar (both legs charged twice, which is conservative). No lookback, so there is no warm-up.
- **Universe.** COIN-M coins excluding BTC/ETH/SOL (so a clean 2024 holdout exists) with continuous quarterlies 2022-01..2024-12. min_symbols = max(5, ceil(0.8n)). Fewer than 5 coins means F2 is not approved and no alpha is spent.
- **Costs.** Taker 0.15 % (COIN-M 0.05 % [U]), half-spread 0.06 % [estimate], slippage 0.06 % [estimate], no funding. USDT-spot vs USD-index basis risk remains.
- **Data.** Nothing cached. About 100 HEAD requests after 2026-11-28 to establish contract coverage [U], then about 400–600 COIN-M zips, about 20–30 MB [estimate]. Spot is shared with F1.
- **Before approval:** `dbasis.py` with roll stitching, plus a synthetic convergence test.
- **Honest power.** The P&L is low-volatility accrual while the rule is on; in a bear window the rule is mostly flat and fails "net mean > 0". P(F2 PASS) ≈ 0.03–0.10. It harvests the same leverage-demand premium as F1, so the outcomes are positively correlated: P(at least one PASS across F1 and F2) ≈ 0.06–0.18, not the sum.

**Not pursued:** reuse-first's cached cross-sectional funding long/short (F001). It is unhedged across coins, its risk is dominated by relative price moves, and it sits close to E_funding_contrarian and Nefedov's factor set. It is inconsistent with "only non-price-prediction".

---

(E) User decisions (recommended default first)

1. **Statistical core:** screen as a filter only; every survivor (including DSR ≥ 0.95) goes to a forward test; W0 = 0.05; alpha-spending with Bonferroni α_F/M. Default: **yes**. Alternative: alpha-investing (mFDR, weaker).
2. **α_F:** **0.0125** (four families that reach a forward test). Alternative 0.025: two families, S = 3 power at M = 1 rises from 0.77 to about 0.84.
3. **K and cap:** **K ≤ 3 base, ≤ 1 successor each, M ≤ 3, ≤ 3 open families, ≤ 2 families per tag.**
4. **Window:** **12 months with one reject-only look at 6.** Alternatives: 6 months (S = 3 power 0.44), or looks at 3 and 6 (about 8 pp power loss at S = 3).
5. **PSR_cons as a deciding gate:** **yes**. Under AR(1) ρ = 0.3 the iid PSR passes a null at about 0.048, not 0.0125.
6. **Attribution gate in-sample and forward:** **yes** (stricter).
7. **Families stay out of automatic promotion** (amendment 4): **yes**.
8. **F1 fcarry:** **draft now and approve after phase A.** You perform 4 revivals of the L13 tag (3 base instances plus `filt_w`) with the pre-written text. Alternative: drop F1.
9. **F2 dbasis:** **phase B only,** approved only if the HEAD check finds ≥ 5 altcoins and the convergence test passes. Alternative: defer.
10. **Successors:** **allow `filt_w` only (train-only trigger).** Alternative: none in round 1.
11. **Programme stop:** **3 families in a row without a PASS, 2028-06-30, or budget below α_F;** restart only by a new amendment.
12. **Approval friction:** **TTY, two steps, typed blob prefix, `CLAUDECODE` refusal, no web endpoint;** accepted as policy, not proof.
13. **Embargo:** **2026-11-28 00:00 UTC.** If the pm_lp tail is extended, move it by a dated amendment before 11-28.
14. **Spot cost:** **0.10 % VIP0 taker plus estimates.** Or give your real fee tier (it may only be stricter than the catalogue).
15. **Disclosure:** **accept and record** that aggregate 2022–23 funding statistics were seen during design. Alternative: replace F1 with a family drafted by someone who has not seen them.
16. **Order of work:** **amendment text → you confirm the [BEKRÆFT] values → code and tests (tests on Linux in a separate checkout) → you deploy and restart → you type the revivals and approve/confirm-family → on or after 11-28 you start the fleet by hand.**

---

(F) Risks and what remains unresolved

- **Low prior.** carry_v1's development was negative and its edge was decaying; Binance spot fees are higher than Hyperliquid's. The most likely outcome is FUTILE or a forward FAIL. That outcome is still informative because of the attribution split.
- **Gates that may reject a real carry.** The buy-and-hold gate (2.02 on validation3, and possibly more than 2 in a bull forward window) and the placebo (always-on rules) are kept unchanged by rule.
- **In-sample signal may be thin.** 2022–23 funding was near zero on average (disclosed read), so the screen may see too few "on" periods to pass. That ends as FUTILE, with the alpha refunded.
- **Model approximations:**
  - the ratio return is only about r_s − r_p (linear perp);
  - both legs fill at the hourly close;
  - the spread and slippage values are estimates;
  - margin and liquidation are not modelled for the 1× short (the ratio model has no margin call);
  - F2 has USDT/USD basis risk;
  - F2 rolls are charged conservatively.
- **Correlation and programme error.** F1 and F2 share one premium; the union bound stays valid, but the diversification is illusory. Amendments 2, 7 and 8 each control 0.05, so the lab-wide error is not 0.05; this is stated in the amendment.
- **Implementation risk.** About 20 catalogue call sites in `pipeline.py` move behind accessors. The critical invariants are MVRV N = 1, the amendment 7 family, an unchanged catalogue blob, and no injection; all are pinned by tests 1, 19 and 20.
- **New findings that the designs missed (covered by the code list):**
  - `registry.covering` would block a family's own siblings;
  - successors discovered after a sibling's rejection would be graveyard-suppressed by that sibling;
  - spot zips would silently reuse the perp zip of the same name;
  - deciding at 00:00 would credit an unearned settlement on every entry.
- **Time.** The first decision is about 2027-06 (futility) or about 2027-12 (final). A PASS cannot be paper-traded until a live spot feed exists, which is out of scope.
- **Approval friction is not a proof of a human.** A faked TTY is possible. The control is the amendment rule plus the logged actor, TTY name and typed blob prefix.
- **Holdout contamination.** It is general knowledge that 2024 funding and basis were high, so a later 2024 PASS is weak evidence; the forward test is what counts.
- **Unresolved, verified only after 2026-11-28 or at approval:**
  - Binance spot availability for all 30 v3 coins;
  - COIN-M altcoin quarterly coverage;
  - the funding formula, the fee schedules and the evidence DOIs;
  - whether the forward attribution diagnostic lands in phase A or B.
- **Deployment state.** The Linux checkout is at 2535fe6; Windows is at aae4495, two commits ahead. Testing and deploying the amendment 8 code is your step.