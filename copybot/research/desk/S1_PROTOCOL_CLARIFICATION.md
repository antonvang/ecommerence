# S1_PROTOCOL_CLARIFICATION: hvad betyder "få overgange" i S1? (direktørordre 62 P2)

**Status:** AUDIT, kun læsning. Ingen ændring af S1, pins, protokoller eller GATE_MATRIX. Intet committet.
**Skrevet:** 2026-11-09 ca. 13:25 UTC (tjekket med `date -u`).

## Kort svar

- **Der findes ingen numerisk tærskel for "få nye overgange".** Ordet er ikke kvantificeret i nogen ordre, note, kode
  eller test.
- Det eneste tal i S1 er `GAP_S` = 2 timer. Det definerer et MONITORING_GAP (tidsdækning), ikke "få" (hændelsesdækning).
- Der findes heller ikke noget krav om en mindste tidsdækning (fx en andel af timekørslerne).
- Ved **0** nye overgange er klassen entydig: INSUFFICIENT_OBSERVATION. Ved 1 eller flere afgør protokollen det ikke.

## 1. Den oprindelige tekst (i tidsorden)

Tider er commit-tider i UTC. INBOX vokser ovenfra, så linjenumrene flytter sig. Commit og citat er det faste spor.

| # | Kilde (fil:linje) | Commit | Ordret tekst |
|---|---|---|---|
| A | `research/studies/FACTORY_MIGRATION_P1_2026-11-06.md:55-57` (ordre 48 P1, plan) | `ce67d14` 2026-11-06 08:45 | "**Kriterier for at gå videre:** 14 dage i S1/S2 uden uforklarede BLOCK, uden fejl i gaten og uden forskel mellem fabrikkens og pipelinens beslutninger, som ikke falder i en dokumenteret klasse. **Tilbagerulning** ved første uforklarede BLOCK af en eksisterende proces, enhver fejl i gaten eller enhver påvirkning af papirhandlen." |
| B | `research/reviews/INBOX.md:460-461` (ordre 49 P0) | `0c902e7` 2026-11-06 09:49 | "14-dages observation starter først ved faktisk S1-start med dokumenteret baseline; rapportér præcis startdato." |
| C | `research/reviews/INBOX.md:471-473` (ordre 49 P3) | `0c902e7` 2026-11-06 09:49 | "P3 (tidligst 14 fulde døgn efter S1-start): S1-evaluering (beslutninger, ALLOW/BLOCK, årsagskoder, uforklarede forskelle, falske blokeringer, legacy-kompatibilitet, ressourcer, fejl, integritet, testdækning; **nul fejl er ikke automatisk GO uden relevante hændelser**); anbefaling. S2 kræver ny eksplicit ejerbeslutning; Claude aktiverer ikke S2." |
| D | `research/studies/FACTORY_S1_P0_2026-11-06.md:8-10` | `7a395e3` 2026-11-06 10:07 | "S1 startede 2026-11-06 kl. 09:55:07 UTC … baseline på 179 transitioner … Baseline tæller ikke som observationer. … evalueringen kan tidligst ske 2026-11-20 kl. 09:55 UTC." |
| E | `research/reviews/INBOX.md:436-440` (direktørens svar på ordre 49 P0) | `003a8a2` 2026-11-06 10:23 | "Baseline (179) er ikke evidens for fremtidig håndtering. Krav: registrér forventede og gennemførte kørsler samt længste hul; enhver periode uden kørsel = MONITORING_GAP; ved genstart indlæses alle nye overgange siden sidste behandlede id; rapportér både hændelsesdækning og tidsmæssig overvågningsdækning; **for få nye overgange → P3 konkluderer INSUFFICIENT_OBSERVATION, ikke PASS.**" |
| F | `research/tools/factory_s1.py:141` | `7a395e3` | `GAP_S = 2 * 3600  # … more than 2 h without a successful run is a MONITORING_GAP` |
| G | `research/tools/factory_s1.py:187-188` | `003a8a2` | "Event coverage: few new transitions mean INSUFFICIENT_OBSERVATION at the evaluation, never an automatic PASS." |
| H | `research/studies/FACTORY_INTEGRATION_P3_2026-11-06.md:65-66` | `497ecda` 2026-11-06 09:47 | S1: "første rapport efter 14 dage". S2 NO-GO indtil "14 dage S1 uden uforklarede BLOCK og uden gatefejl" plus nøglebinding, rollback-sikker log og en særskilt ejerbeslutning |

**Kilden til "få" er E** (direktørens svar på ordre 49 P0). Senere tekster gentager den kun:
- `research/desk/NOV14_READINESS.md:417` (§9): "Få nye overgange → INSUFFICIENT_OBSERVATION, aldrig automatisk PASS."
- `research/desk/GATE_MATRIX.json:898` (`G24_S1_EVAL.opens_by`): "few new transitions give INSUFFICIENT_OBSERVATION, never an automatic PASS".
- `research/tools/gate_status.py:95` og `research/desk/S1_READINESS_2026-11-20.md:37` og `:118-121`.

Ingen af dem tilføjer et tal.

## 2. De låste kriterier

| Kriterium | Kilde | Tal? |
|---|---|---|
| Observationsperiode: 14 fulde døgn fra den faktiske start 2026-11-06 09:55:07 UTC, dvs. tidligst 2026-11-20 09:55:07 UTC | B, C, D; G24 | ja (dato) |
| Baselinen (179 overgange, id 1-179) tæller ikke som observation | D, E | ja (id-grænse) |
| Gå videre (kun anbefaling): ingen uforklarede BLOCK, ingen gatefejl, ingen forskel uden for en dokumenteret klasse | A | nej |
| Tilbagerulning: første uforklarede BLOCK af en eksisterende proces, enhver gatefejl, enhver påvirkning af papirhandlen | A | "første" = 1 |
| Nul fejl er ikke automatisk GO uden relevante hændelser | C | nej |
| For få nye overgange → INSUFFICIENT_OBSERVATION, ikke PASS | E, G | **nej** |
| S2 kræver en ny, eksplicit ejerbeslutning. Claude aktiverer ikke S2 | C, H | – |

## 3. Krav til dækning

- **Tidsdækning:** der skal registreres forventede og gennemførte kørsler, længste hul og hvert MONITORING_GAP (E). Et
  MONITORING_GAP er mere end 2 timer uden en vellykket kørsel (F). Det skal rapporteres.
- **Der findes ikke noget minimum.** Ingen tekst siger, at et hul forlænger perioden, ugyldiggør den eller kræver en vis
  andel kørsler. Ved genstart læses alle overgange siden det sidst behandlede id (E), så et hul mister ingen overgange.
- **Hændelsesdækning:** skal rapporteres (E). Der er intet minimum ud over ordet "få".
- **Tests:** `tests/test_research_factory_s1.py` tester read-only, skriveadgang, kæde, stopfil, fejl, sidefiler og
  `coverage` (et hul over `GAP_S`). Ingen test handler om INSUFFICIENT_OBSERVATION eller et mindste antal.

## 4. Reglerne for INSUFFICIENT_OBSERVATION

Det er alt, der står:
1. "for få nye overgange → P3 konkluderer INSUFFICIENT_OBSERVATION, ikke PASS" (E).
2. "nul fejl er ikke automatisk GO uden relevante hændelser" (C). "Relevante hændelser" er ikke defineret.
3. Klassen er aldrig PASS (E, G, G24).

Hvad der **ikke** står: et tal, en andel, en minimumsvariation af årsagskoder eller en regel for 1-k overgange.

## 5. Observationsgrundlaget nu

Fra S1's egen `research/data/factory_s1/summary.md` (sidste kørsel 2026-11-09 13:08 UTC):
- 64 vellykkede kørsler ud af 76 timeslots, 0 fejlede.
- Længste hul 19,20 t. 2 MONITORING_GAP: 2026-11-07 00:19-19:31 UTC (19,2 t) og 2026-11-09 07:09-10:08 UTC (2,99 t).
- **0 nye overgange**, 0 uforklarede, 0 BLOCK. Baseline 179.

Lab'et har ikke lavet en eneste forskningsovergang siden starten. Ved 0 nye overgange 20/11 er udfaldet entydigt
INSUFFICIENT_OBSERVATION.

## 6. Hvad 20/11-rapporten må sige

Der opfindes ingen ny tærskel. Rapporten beskriver grundlaget og begrænsningen.

**Ved 0 nye overgange:**
- Klasse: **INSUFFICIENT_OBSERVATION** (E: "få" omfatter nul; C: nul fejl uden hændelser er ikke GO).
- Begrundelse: gatens reaktion på nye overgange er ikke observeret. Kun kæde, isolation, drift og dækning er vist.
- Ingen anbefaling om S2. S2 er ejerens beslutning.

**Ved 1 eller flere nye overgange:**
- Er der mindst 1 uforklaret BLOCK, en gatefejl eller påvirkning af papirhandlen, er tilbagerulningskriteriet brudt (A).
  Det gælder uanset antallet.
- Ellers rapporteres kun tallene:
  - antal nye overgange og deres id;
  - ALLOW/BLOCK pr. årsagskode, og hvilke beslutningsveje der blev brugt, og hvilke der ikke blev;
  - uforklarede forskelle og en manuel gennemgang af hver BLOCK for falske blokeringer;
  - tidsdækning (kørsler, længste hul, MONITORING_GAP) og om en overgang kom i et hul.
- Rapporten skriver ordret: "Protokollen definerer ikke 'få' (INBOX, svar på ordre 49 P0, commit `003a8a2`). Om
  grundlaget er tilstrækkeligt, afgør direktøren." Claude vælger ikke selv mellem INSUFFICIENT_OBSERVATION og
  "kriterium opfyldt".
- Selv et rent udfald giver kun en anbefaling (A, C). Det åbner ikke S2.

**Hvis direktøren vil have et tal**, skal det besluttes og dateres før 2026-11-20 09:55:07 UTC. Det må ikke vælges
efter, at tallet for nye overgange er kendt.

## 7. Afvigelser og bemærkninger

- **Ingen sikkerhedsafvigelser fundet.** Jeg har kun læst noter, kode, tests og S1's egne rapportfiler. lab.db er kun
  åbnet read-only i P1 (`datasets` og `events`) og ikke for S1.
- **Forældede linjehenvisninger (kun dokumentation):** `S1_READINESS_2026-11-20.md` henviser til "INBOX 427", "424-428",
  "459-461" og "435". `GATE_MATRIX.json` G24 `source` henviser til INBOX-linjerne "151-153" og "116-127". INBOX er vokset
  ovenfra, så linjerne passer ikke længere. I dag er det 436-440 (E), 460-461 (B) og 471-473 (C). GATE_MATRIX er pinnet
  og er ikke ændret. Fremover bør der henvises til commit og citat.
- `S1_READINESS_2026-11-20.md` punkt 7 ("Uafklaret 1") har allerede peget på, at "få" ikke er kvantificeret. Denne note
  bekræfter det efter en fuld søgning.
