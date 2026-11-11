# ORDER83: samlet kandidat, net_report, kildekomplethed og godkendelser (direktørordre 83)

Skrevet 2026-11-11 kl. 17:03 lokal (16:03 UTC). Dev-only og uanvendt. `lab/`, `lab/straks.py`, `lab/pairs.py` og
`research/tools/net_report.py` (sha256 `e8cac57c…`) er uændrede. Ingen deploy, intet netværk, lab.db ikke åbnet.
**[F]** = fakta, **[V]** = vurdering.

## Tests

- `test_candidate_83,test_source_completeness_83,test_research_gates,test_note_times` i den beskyttede loader: 34 tests OK
  (22 nye: 9 + 13), 0 blokerede forsøg.
- Tre mutationer gav 4 fejl og er rullet tilbage:
  - net_report-kandidaten tæller post-terminal funding som strategi;
  - sene afregninger flages ikke;
  - kun ét marked probes.

## Kandidaten (rækkefølge i `patches/83_candidate_README.md`)

1. **`83_candidate_1_observability.diff`** er 72 og 81 observability som én diff. Den er byte-identisk med de to anvendt efter hinanden (testet).
2. **`83_candidate_2_close.diff`** er 82 plus én rettelse: en afregning, der er bogført efter terminal, men afregnet før, markeres `late_settlements`. Den tæller stadig som post-terminal, men kan nu ses. 80 og 81 v2 indgår ikke.
3. **`83_candidate_3_net_report.diff`** er net_report på en kopi:
   - post-terminal funding trækkes ud af alle funding-kolonner (til cutoff, ved mærket, efter mærket, pr. instrument);
   - den vises i et eget afsnit med `in_strategy_performance: false` og `validated: false`;
   - hver `sim_funding`-række ligger i præcis én kurv, og summen er uændret.

Testet med lukninger, en genstart og en gentagelse: hændelsernes id'er er unikke og lig rapportens liste, og rapporten er reproducerbar. For en konto, der ikke er terminal, er tallene som før. En test dokumenterer, at den pinnede net_report tæller post-terminal funding med.

## Kildekomplethed for STRAKS og PAR-BOG (design, ikke koblet ind)

`research/tools/source_completeness.py`:

- `REQUIRED` læses fra `moves.WATCH` (12) og `pairs.PAIRS` (8).
- `assess` giver `DATA_COMPLETE` kun med frisk lukket 1h-bar (≤ 2 t) og gyldig bog for hvert marked, og for STRAKS en frisk `abnormal_move/1`. Ellers `DATA_INCOMPLETE` med de manglende dele navngivet.
- `recovery` kræver 50 minutters ubrudt komplethed.
- `probes` giver samme kontrol til kandidat 1's flerkilde-`auto_resume`.
- Testet: ét forældet marked (XAU) giver `DATA_INCOMPLETE` i proben og ingen genoptagelse i 3 timer; en forældet signalkilde for STRAKS ligeså. Den frosne én-bogs-probe genoptager i samme situation.

## Resterende fejl i produktion [F]

| Fejl | Ses fra | Rettes af |
|---|---|---|
| Stopreglen kan første gang vurderes for `LANE_53058593e8` 2026-11-12 04:47 UTC; en lukning lukker perp alene (78) | ca. 12 t fra nu | 2, efter dev-motoren |
| Spot-mærkning forsøges hvert pas for de 9 konti; fejlen er tavs i produktion | nu | dev-motoren (59-D) |
| Falsk `external.recovered` for pm_lp (filalder) | nu | 1 |
| `lab/watch.py` melder "collection finished" for pm_lp fra 2026-11-28 alene på datoen | 28/11 | 1 |
| `auto_resume` for STRAKS/PAR-BOG med én BTC-bog (sovende; ingen `data_fetch`-pause sættes) | latent | kildekomplethed + ændring af pinnede moduler |
| `net_report` ville tælle post-terminal funding som strategi | når 2 er aktiv | 3 |

Kendte begrænsninger i kandidaten [V]:

- 7 døgns retry gælder også FWD/SHADOW.
- `LIKE` i `_note_close_state` behandler `_` som jokertegn (harmløst med `exp_id`-filteret).
- Spot-proben under pause kontakter fortsat den blokerede vært (kandidat 1); kildekompletheds-probes henter alle markeder hver time.
- TradFi-handelspauser er ikke verificeret.

## Deployafhængigheder [F]

- Produktion er `85db922`. Kandidat 1 kan anvendes dér (forskydninger i `risk.py` og `lane.py`). Kandidat 2 kræver dev-motoren (59-D: `mark_guarded`); 80/81/82/83-close fejler på `85db922`.
- Kandidat 3 læser hændelser fra kandidat 2.
- Ingen databasemigration.

## Godkendelser en aktivering kræver

| Trin | G12 | Ejer/direktør |
|---|---|---|
| Dev-motoren (59-D, 67/68-flag står på `legacy`/`off`) | `lab.supervisor` importerer ikke `paper_runner`; deploy genstarter flåden. Preflight `collector_restart` skal være grøn | Ordre 78: ingen deploy før 20/11; K1/K2/K3-vinduer; milepæle først |
| Kandidat 1 | **Ja:** `lab.ops` og `lab.risk` importeres af collectorens genstart (`lab.supervisor`). Ejerens særskilte tilladelse (som 72) | Ja til ændret recovered-/finished-semantik og flerkilde-`auto_resume` |
| Kandidat 2 | Nej (collectoren importerer ikke `paper_runner`) | Ja til: perp lukkes ikke ved permanent spot; terminal er låst; funding bogføres videre post-terminal; 7 døgn; ingen automatisk genoptagelse |
| Kandidat 3 | Nej | **Pin-ændring** af `NET_REPORT` (`GATE_MATRIX.json`, `NOV14_READINESS.md`) ved dateret direktørordre; ellers fejler `verify_hashes`. Brugere: `lab_qc`, `paper_chart`, `basis_ref`, dagsrapporten |
| Kildekomplethed | Nej | Ændring af pinnede `lab/straks.py` og `lab/pairs.py` (59-E, `STRAKS_CODE`/`PAIRS_CODE`), og om manglende data skal give pause (regelændring) |
| Statusregister (81) | Nej | Første rigtige række |

## Anbefaling [V]

1. Produktion forbliver frossen til efter milepælene (12/11, 14/11, 19/11, 20/11).
2. Det betyder, at et eventuelt stop fra 12/11 04:47 UTC giver en delvis lukning i produktion. Den klassificeres bagefter med `partial_close.py` (78) og fremstilles ikke som fuldstændig.
3. Efter 20/11, hvis ejeren siger ja: dev-motoren, derefter kandidat 1 (med G12-tilladelse og collector-preflight) og så kandidat 2 og 3 sammen med pin-ændringen.
4. Kildekomplethed først ved en dateret ændring af de pinnede bøger, efter PAR-BOG-rapporten 19/11.
