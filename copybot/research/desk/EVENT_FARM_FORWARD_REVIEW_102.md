# Event farm fremadrettet: endelig designgennemgang (direktørordre 102)

Claude skrev gennemgangen 2026-11-12 kl. 14:26 lokal tid (13:26 UTC).

Status: **kun design.** Ingen underskrift, ingen ny stream, ingen aktivering, ingen deploy og ingen historisk
dataadgang.

**Nye filer:**
- `research/tools/event_farm_forward_v2.py`;
- `tests/test_event_farm_forward_v2.py` (15 tests);
- `research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.md` og `.sha256`.

Committede filer er ikke ændret.

## 1. Integration af de 96 tests

`ForwardBookV2` arver den uændrede `ForwardBook`. For hver behandlet bar bogfører den:
- baseline-setups som `base/<variant>`, uændret;
- hvert setup, der består en kombination, som `<kombination>/<variant>`.

Hver test har egen konto, og indgang, stop, mål, fills, omkostninger og statusser er de samme. Databasens identitet er
et nyt skema, så en v1-fil afvises af v2, og omvendt.

## 2. known_ts i den levende vej

Filterværdien ved bar k kommer kun fra de behandlede barer til og med k:
- **F1:** en trinvis 1t-tracker, `Trend1H`, en tvilling af `trend_1h`;
- **F2 og F3:** `prior_day_retest` og `vwap_series` på barerne fra dag D−1 eller sessionsstart til k.

Testene bruger syntetiske serier med manglende 5m-barer (ufuldstændige timer og huller) og barer med volumen 0. De
viser:
- den levende kontekst er lig den offline kontekst for alle k og begge symboler;
- trackerens serie er lig `trend_1h`;
- VWAP er INCOMPLETE fra en nulvolumen-bar til døgnets slutning og OK igen næste døgn;
- ingen F3-handel er bogført i en blokeret periode;
- en time med manglende 5m-barer bruges ikke.

## 3. Genstart, deduplikering og replay

**Replay:** bogføring bar for bar er lig offline for alle 96 tests, også med huller og nulvolumen. Det gælder alle
indgange, stop, mål, statusser og udgange. Batching giver samme bog.

**Genstart og crash:**
- genåbning midt i forløbet genopbygger 1t-trackeren og giver samme bog;
- et crash inde i et trin ruller tilbage til tilstanden før trinnet;
- et nyt trin giver derefter samme bog som en uafbrudt kørsel.

**Deduplikering:** genlevering af identiske barer ændrer intet, og et trin uden nye data ændrer intet.

## 4. Register V2 mod koden

`v2_final_records()` giver 19 FUTURE-poster: 12 baseline og 7 kombinationer á 12. Testen viser:
- de dækker præcis 96 tests;
- alle har universstørrelse 96 og `members_sha256` = sha256 af `event_farm_filters.all_forward_tests()`, som er
  præcis bogens test-id'er;
- reference-N er 19.849 = 19.753 + 96.

**Fundet uoverensstemmelse:** `event_farm_forward.v2_plan_records` (udkast 100) har univers 12 og N 19.765. Den
afløses af revisioner af de samme 12 id'er med en afvigelse, der nævner de ændrede felter. `chain_verify` består for
hver revision. Den committede fil er ikke rettet.

## 5. Endelig ændringstekst

`research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.md` er én samlet tekst. Den indeholder:
- datakilden: `GET /fapi/v1/klines`, 5m, felterne [0]–[6] med volumen i felt [5], kald og vægt;
- omkostningerne, hvor 28 bps står som ANTAGELSE;
- stop- og evalueringskriterierne;
- sha256 for alle fem kodefiler.

Tekstens sha256 står i `EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.sha256` (sha256sum-format). En test kontrollerer, at
sha256-filen passer til teksten, og at teksten nævner kodefilernes aktuelle sha256. Ændres en kodefil eller teksten,
fejler testen, og der kræves en ny underskrift.

**Kildeadapteren er ikke skrevet.** Teksten kræver derfor et separat, dateret og underskrevet tillæg med adapterens
sha256 før aktivering.

## 6. G15 og G31, vurderet hver for sig

**G15_OWNER_SIGNATURE** (`GATE_MATRIX.json`, as_of 2026-11-06T14:38:27Z: CLOSED).
- **Krav:**
  - `owner_key_registered`;
  - en underskrevet erklæring pr. skabelon. Historiske godkendelser er UNVERIFIED_ORIGIN.
- **Nøglen:** D5 er ANCHORED (`research/owner/D5_REGISTRATION.md`, beslutning 97), så nøglebetingelsen er opfyldt i
  substansen. GATE_MATRIX er dog ikke opdateret siden 11-06, og EVENT_FARM står ikke i G15's studieliste, fordi
  udkastets `list_additions` ikke er anvendt.
- **Underskrift:** der findes ingen underskrevet erklæring for event farm fremadrettet. Den endelige tekst er ikke
  godkendt af direktøren og ikke underskrevet.
- **Status for denne handling: CLOSED.** Den kan åbne, når direktøren har godkendt teksten, og ejeren har underskrevet
  dens sha256 med D5-nøglen, og underskriften er verificeret med `owner_approval.py`. Claude underskriver ikke (G28).

**G31_EVENT_FARM_FORWARD** (`EVENT_FARM_FORWARD_GATE_ENTRY_DRAFT_100.json`, DRAFT_NOT_APPLIED).
- Gaten og handlingen `event_farm_forward_paper` findes ikke i `GATE_MATRIX.json`. Efter matricens fail-closed-regel er
  handlingen derfor **BLOCKED**.
- **Status: CLOSED.**

| flag | status |
|---|---|
| `director_approves_event_farm_forward_amendment` | nej |
| `event_farm_forward_amendment_committed` | nej |
| `owner_key_registered` | ja (D5 ANCHORED) |
| `owner_signed_event_farm_forward_amendment_sha256` | nej |
| `fwd_5m_kline_stream_approved` | nej |
| `event_farm_forward_code_committed` | delvis: v1, filtre og driver er committet; `event_farm_forward_v2.py` er ikke committet endnu |
| `event_farm_forward_source_adapter_committed` | nej (ikke skrevet) |
| `loader_tests_green` | ja, kun syntetisk |
| `host_reachable_without_bypass` | ukendt, intet kald foretaget |

**Gate-udkastets tekst** siger stadig "PENDING_INDEPENDENT_ANCHOR" om D5. Den er rettet i tillæg 101 og her, men ikke
i den committede JSON. Gate-posten skal derfor gennemgås, før den anvendes.

## 7. Tests

Den beskyttede loader kører `test_event_farm_forward_v2`, `test_event_farm`, `test_event_farm_driver`,
`test_event_farm_forward`, `test_event_farm_filters`, `test_research_gates` og `test_note_times`. Resultatet står i
rapporten til koordinatoren.
