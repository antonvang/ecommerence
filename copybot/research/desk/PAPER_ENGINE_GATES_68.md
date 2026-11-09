# Papirmotoren: korrekthedsporte (direktørordre 68)

Dato: 2026-11-09 (UTC). Gren `claude/66b-engine-audit`, kun lokalt: ikke pushet, ikke deployet. Alle nye tilstande er
**slået fra** som standard (`BOOK_AGE_MODE "off"`, `DAILY_RETURNS_MODE "legacy"`, `FUNDING_MISSING_MODE "legacy"`).
Testen `test_default_is_legacy` holder fast i standardværdierne.
`lab/straks.py` (`7a110f1f…`), `lab/pairs.py` (`5c9b60a4…`) og `research/tools/net_report.py` (`e8cac57c…`) er byte for
byte uændrede. Ingen pin, ingen protokol og ingen ledger er ændret.

Tests: `tests/test_lab_engine_gates_68.py` (11 tests); `tests/test_lab_engine_remediation_67.py` (20) har fået
justeret sine funding-fixtures, så de leverer en rigtig 8-timers serie. Forslag og note:
`PROPOSAL_STRICT_DAILY_RETURNS.md` og `PARBOG_DATA_QUALITY_NOTE.md`. Grundlaget er
`PAPER_ENGINE_QUALITY_REPORT.md` (66B) og `PAPER_ENGINE_REMEDIATION_67.md`.

## P0: paritet for MEASURE

**Resultat: bestået.** `test_measure_changes_nothing_but_the_three_sim_exec_fields` kører samme scenarie to gange,
med `off` og med `measure`, i to midlertidige databaser. Scenariet har 28 pas over 26 timer og 7 konti:
1 lane (spot/perp), 3 carry90, 2 STRAKS og PAR-BOG. Det giver 196 kontokørsler og én fælles bogcache pr. pas, som i
`paper_runner.run`. Det indeholder:

- et udfald af klines og funding (pause `data_fetch`, PROBE og auto-resume),
- et spot-udfald (mærkefejl og genopretning),
- et udfald af perp-bogen (ordrer ikke sendt),
- en ny kørsel i samme time,
- STRAKS-udgange efter 24 t og en PAR-indgang og -udgang.

Skrevet i alt: 20 ordrer og fyld (carry90 6, STRAKS 8, PAR 4, lane 2), 172 mærker, 30 funding-rækker, 12 risk-rækker
(4 PAUSE, 4 PROBE, 4 CLEAR) og 92 hændelser.

Identisk mellem `off` og `measure`:

- Hver række i `sim_orders`, `sim_fills`, `sim_cancels`, `sim_equity`, `sim_funding` og `risk_events`, inklusive
  hash-kæderne.
- Hver hændelse (kind, actor, exp_id, payload; ts er vægur og er udeladt).
- Hver returværdi fra kørslerne.
- `sim_exec` på alle felter undtagen de tre nye (`book_observed_wall`, `exec_wall`, `book_age_exec_s`). Kun disse
  felters egen hash-kæde afviger.

STRAKS og PAR-BOG kan dækkes uden at røre de frosne filer. De køres, som de er, og testen tjekker, at alle fire veje
faktisk handlede.

## P0: GUARD forbliver slået fra. Foreslået pause- og genforsøgspolitik (kun forslag)

1. Er bogen mere end `data_max_age_s` (60 s) gammel ved udførelsen, hentes én frisk bog med det samme. Er den gyldig,
   udføres ordren på den.
2. Er den friske bog også forældet eller ugyldig, afvises ordren (BLOCK `data_stale`). Den gemmes ikke og prøves med
   samme ordre-id i næste pas samme time. Der kommer ingen pause.
3. Tre afvisninger i træk for samme konto giver PAUSE `data_stale`. Pausen ophæves automatisk efter 50 min med friske
   bøger, efter samme mønster som amendment 18 for `data_fetch`.
4. Lukkeordrer (reduce-only) blokeres aldrig. De udføres på den friske bog fra punkt 1. Er den heller ikke frisk, prøves
   de igen i næste pas.
5. Mærker blokeres ikke. Under `measure` registreres mærkebogens alder.
6. Rækkefølge: `measure` i mindst 7 dage → beslutning om tærskel og politik ud fra de målte aldre → et dateret
   amendment → `guard`.

## P1: STRICT for daglige afkast

`legacy` er stadig aktiv. Det daterede forslag står i `PROPOSAL_STRICT_DAILY_RETURNS.md`:

- hvorfor sammenlægning er forkert (skala, n, ikke-tilfældigt frafald),
- en tabel for de seks lane-konti,
- at `COVERAGE_MIN` skal fastsættes ved en forudgående designregel eller en simulering under nulhypotesen, aldrig ud
  fra de nuværende kontis tal,
- at 0,8 kun er en pladsholder,
- at intet gælder med tilbagevirkende kraft.

Ingen regel skifter udfald i dag. Med 0,8 ville 5 af de 6 lane-konti være INCONCLUSIVE.

## P2: FAIL_CLOSED, fejlmatrix

Der er tre tilstande:

- `legacy` (aktiv).
- `report`: samme hændelser og statusfelter som `fail_closed`, men **bogføringen er byte-identisk med legacy**. Det er
  ren registrering; testen sammenligner hash-kæderne.
- `fail_closed`: tjekker desuden satsserien og **holder senere afregninger tilbage**. Det er *ikke* ren registrering.

Intervallet aflæses som det hyppigste mellemrum blandt de sidste 10 i serien. Det skal ses mindst to gange.

| # | Tilfælde (position åben) | LEGACY | FAIL_CLOSED | Forskel i bogføring | Ændrer senere simuleret adfærd |
|---|---|---|---|---|---|
| 1 | Bar mangler ved afregningen, senere barer findes | venter i stilhed; intet bogføres efter den for instrumentet, før baren dukker op eller falder ud af vinduet (1000 t / 48 t); derefter `funding_gap` og spring over | samme bogføring; `paper.funding_missing` MISSING_BAR (én gang) og `funding_status` ERROR | ingen | nej |
| 2 | Den nyeste bar er ikke ude endnu | venter | venter; status WAITING, ingen fejl | ingen | nej |
| 3 | Baren er ældre end det hentede vindue | `paper.funding_gap`, springes over | samme | ingen | nej |
| 4 | **Sats mangler midt i serien** | bogføres aldrig, i stilhed; senere afregninger bogføres | MISSING_RATE; hverken hullet eller noget efter det bogføres, før satsen dukker op; dukker den aldrig op, står instrumentet stille, indtil et menneske griber ind | **ja**: senere funding mangler (forsinket eller blokeret) | **ja**, se nedenfor |
| 5 | Sats mangler, mens positionen er flad | intet | intet, ingen fejl | ingen | nej |
| 6 | **Ukendt interval** (færre end 3 kendte afregninger, fx en ny notering) | bogfører det kendte | UNKNOWN_INTERVAL; intet bogføres, før intervallet er kendt; derefter bogføres alt i rækkefølge | **ja**: forsinkelse | **ja**; bl.a. scanner-udgang efter 12c (test) |
| 7 | Tom serie for en åben perp (hentningen gav intet) | intet, i stilhed | UNKNOWN_INTERVAL ERROR, intet bogføres | ingen | nej |
| 8 | **Interval øges** (4 t → 8 t) | bogfører alt | falsk MISSING_RATE, indtil de fleste af de sidste 10 mellemrum er 8 t (ca. 5–6 nye afregninger, omkring 2 døgn); derefter bogføres alt i rækkefølge | **ja**: forsinkelse | **ja** |
| 9 | Interval mindskes (8 t → 4 t) | bogfører alt | bogfører alt (kortere mellemrum er ikke hul) | ingen | nej |
| 10 | Funding kan ikke hentes (pause- og lukkevejen) | intet i dette pas; indhentes senere | samme; `paper.funding_unavailable` højst én gang i timen, ERROR | ingen | nej |
| 11 | Genopretning efter hul | – | det tilbageholdte bogføres i rækkefølge med bogføringspassets ts | **ja**: ts bliver senere end i legacy | ja: rapporter, der skærer på ts (dagsrapport, `at_mark`), henfører funding til en senere dag eller et senere mærke |
| 12 | Samme pas igen eller to skrivere | UNIQUE: én gang | samme; én hændelse | ingen | nej |
| 13 | Spotben og flade instrumenter | intet | intet, ingen fejl | ingen | nej |

**Når bogføringen ændres (4, 6, 8 og 11), ændres også den senere simulerede adfærd.** Kontanter og equity afviger, og
det slår igennem i:

- drawdown-breakeren (`max_drawdown`-pause),
- tabsstop (lane 3 %, scanner/HL 5 %, carry90 5 %, STRAKS/PAR 20 %),
- kildereglen (funding − gebyrer ≤ 0 efter 14 dage, scanner/HL efter 3 dage),
- størrelsen af nye lane-positioner (seneste equity),
- daglige afkast og z,
- scanner-udgang efter 12c. Den kræver en *bogført* afregning efter indgangen; testen
  `test_held_back_funding_changes_the_scanner_exit_rule` viser, at den forsinkes.

Derfor må `fail_closed` ikke slås til i en måleperiode uden et dateret amendment.

## P3: patches og basis

- `research/desk/patches/66_straks_pairs_mark_guard.diff` er uændret siden ordre 67 og ikke anvendt. Testen
  anvender den strengt på midlertidige kopier:
  - STRAKS: én `mark_failed` og én `mark_recovered`, og bøgerne er byte-identiske med den frosne version.
  - PAR: én `mark_failed`, hvor den frosne version intet skriver.
  - Der er ingen ny pin og ingen deploy.
- `research/tools/basis_ref.py` er stadig en separat reference. `net_report.py` er pinnet og uændret.

## Nye fund, der berører milepælenes troværdighed

1. **Skjult genbrug af bøger.** STRAKS og PAR kan genbruge bøger, som FWD- og SHADOW-passene (`fetch_market`) eller
   carry90-mærkerne læste tidligere i samme pas. Det efterlader intet spor i `sim_exec`. Den øvre grænse for alderen
   (ordrehændelse minus passets start) er:
   - STRAKS: 74 ordrer, højst 52 s, p50 17–28 s. Alle ligger under 60 s, selv i værste fald.
   - PAR: 6 ordrer højst 49 s; **2 ordrer 61 s** (én ETH/BTC-entré).

   STRAKS 12/11 berøres ikke. PAR-BOG 19/11 får en note (`PARBOG_DATA_QUALITY_NOTE.md`); tallene ændres ikke.
2. **Rettelse til ordre 67-rapporten:** "61–168 s" for de 2 PAR-ordrer var den globale grænse. For PAR-ordrerne er den
   61 s.
3. HFC-1 (14 d) og S1 (20/11) læser ingen sim_*-tabeller og berøres ikke.

Alle fire milepæle kan vurderes under de oprindelige protokoller: intet er aktiveret, og ingen cutoff er ændret.

## Anbefaling for senere aktivering (i denne rækkefølge)

1. Efter 20/11 og efter review: deploy de rene registreringsrettelser: 59-D, `close_ledger`, `reportcheck` og
   `on_trade`.
2. Samme vindue: anvend STRAKS/PAR-patchen med nye pins af `STRAKS_CODE`/`PAIRS_CODE`, efter at rapporterne for STRAKS
   12/11 og PAR 19/11 er lavet.
3. `BOOK_AGE_MODE "measure"` og `FUNDING_MISSING_MODE "report"`. Begge er ren registrering, og pariteten er bevist;
   de kan aktiveres sammen med punkt 1, når det er godkendt.
4. Efter mindst 7 dage med målinger: beslut GUARD-politikken (ovenfor) og `fail_closed`-semantikken. Hver af dem
   kræver et dateret amendment, fordi tilfælde 4, 6, 8 og 11 ændrer bogføringen.
5. STRICT for daglige afkast: et dateret amendment med en `COVERAGE_MIN`, der er fastsat på forhånd.
6. `net_report` og basis ved fortegnsskift: en ny pin, kun hvis FWD-konti skal med i rapporten.

## Tests, der stadig er forventede fejl (standardværdierne er legacy/off)

- `test_confirmed_stop_book_and_fill_times_are_the_pass_clock_not_the_read_time`
- `test_confirmed_stop_a_missing_utc_day_is_merged_into_one_daily_return`
- `test_confirmed_stop_a_missing_middle_bar_stalls_funding_silently`
- `test_confirmed_stop_straks_mark_failure_is_silent`
- `test_confirmed_stop_net_report_keeps_the_old_basis_through_a_flip`
