# VIDEO_TRIAGE_TOOL_REPORT (direktørordre 58 P1, 2026-11-09)

**Status:** lokalt værktøj, kun offline. Intet netværk, ingen nye API'er, ingen markedsdata. Ikke committet.

## 1. Formål

- Ejeren sender mange trading-videoer. Indtil nu er de triageret i hånden (`VIDEO_TRIAGE_2026-11-08.md`,
  `orb15/ORB15_VIDEO_RULE_AUDIT.md`, `fomo/FOMO_COPY_30S_PROTOCOL_DRAFT.md` afsnit 1).
- Værktøjet gør den samme arbejdsgang fast: video → billeder → påstand → regeltjekliste → klassifikation → register.
- Det er idé U6 og U3 i `VIDEO_USABLE_2026-11-09.md`.
- Værktøjet ser ikke selv videoer. Et menneske eller Claude ser billederne og udfylder en påstandspost.

## 2. Filer

| Fil | Indhold |
|---|---|
| `research/tools/video_triage.py` | Værktøjet. Kun standardbiblioteket; GStreamer (PyGObject) importeres kun inde i `extract` |
| `tests/test_research_video_triage.py` | 27 tests |
| `research/data/video_claims/*.json` | 12 startposter: V01–V10 (rækkefølgen i VIDEO_TRIAGE), FOMO og EDWARD |

## 3. Påstandsposten (schema `copybot.video_claim/1`)

Én JSON-fil pr. video. Alle felter skal findes, og ukendte felter er en fejl.

| Felt | Indhold |
|---|---|
| `id`, `source`, `video_sha256` | Id, "@konto / beskrivelse", videoens sha256 (eller `UNKNOWN`, når filen ikke er i repo'et) |
| `provenance` | Hvordan fakta er læst (billeder hvert N. s, eller `SEED_FROM_TRIAGE_NOTES`) og hvilke noter |
| `claims` | `performance_claimed` og `trading_rule_claimed` (sand/falsk) |
| `observed_facts` | Kun fakta. Hvert har `at` (sekund, billednavn som `f012.png` eller `UNKNOWN`), `quote` (skærmtekst, højst 15 ord) og `fact` |
| `assumptions` | Antagelser, hver mærket `ASSUMPTION` eller `UNKNOWN`. Holdes adskilt fra fakta |
| `rule_checklist` | 13 elementer med status `OBSERVED` / `PARTIAL` / `UNKNOWN` og en note |
| `performance` | Tallene som vist, antal viste handler, konto (`SIM`/`DEMO`/`REAL`/`BACKTEST`/`UNKNOWN`) |
| `selection` | Handler i alt, antal forsøgte strategier (N), backtest-år (T), oplyst Sharpe og en note |
| `red_flags` | Fri liste, seks faste flag (sand/falsk/null) og en valgfri lot/nominel-beregning |
| `lab_prior` | Lineages og mechanism_tags at slå op på, og de matchende id'er fra factory-registret |
| `classification` | En af de fire klasser, eller `PENDING` for et tomt skelet |

**Tjeklistens 13 elementer:** market, instrument, calendar_timezone, entry_signal, entry_execution, stop, target,
time_exit, short_rule, max_signals_per_session, position_size, costs, data_source.

- `OBSERVED` betyder, at reglen for elementet er helt kendt fra videoen.
- Siger videoen udtrykkeligt "ingen" (fx intet tidsexit), er det `OBSERVED`. Tier videoen, er det `UNKNOWN`.

**Faste røde flag:** lead_generation, selected_examples_only, backtest_only, paid_product_or_fee,
sim_or_demo_account, forbidden_resource_needed.

**Flag, værktøjet selv beregner:**
- `costs_not_shown`: costs er ikke `OBSERVED`.
- `impossible_notional`: nominel værdi = positioner × lot × kontraktstørrelse × kurs. Gearing = nominel / saldo.
  Over 1.000× flagges det. Eksempel V05: 6 × 5,46 lot guld à 100 oz ved 5.026 er cirka $16,5 mio. på en saldo på
  $1.731,87. Det er cirka 9.500× gearing.

**Lab-prior:** værktøjet læser `research/data/factory/registry.json` skrivebeskyttet. Det lister poster med samme
lineage eller mechanism_tag. Det vurderer dem ikke. `check --fill-prior` skriver listen i påstandsfilen, aldrig i
registret.

## 4. Klassifikation (fast rækkefølge, første regel der passer)

1. **NO_TRADING_CLAIM:** hverken performance eller en handelsregel påstås.
2. **REPLICABLE:** alle tjeklisteelementer undtagen costs er `OBSERVED`.
3. **NOT_REPLICABLE_FROM_VIDEO:** mindst ét af entry_signal, stop, target og time_exit er `UNKNOWN` eller `PARTIAL`.
4. **PARTIAL:** alt andet.

- Target og time_exit tælles hver for sig. En regel uden tidsexit skal derfor stå som `OBSERVED` med noten "ingen".
- `check` sammenligner den gemte klasse med den beregnede. Er de forskellige, er posten ugyldig.

## 5. Held-baren (DIAGNOSTIC_ONLY)

Bailey og López de Prados forventede maksimum af N uafhængige nul-Sharpe-estimater:

E[max] ≈ sd · ((1 − γ) · Φ⁻¹(1 − 1/N) + γ · Φ⁻¹(1 − 1/(N·e))), med γ = 0,5772156649 og sd = 1/√T for en årlig
Sharpe over T år.

- **Antagelser:** forsøgene er iid, afkast er normalfordelte, ingen autokorrelation.
- Skævhed og kurtosis er ikke modelleret.
- N = 1 giver 0.
- **Det er en diagnose, ikke en statistisk test** (direktørens instruks). Output er altid `DIAGNOSTIC_ONLY`, baren
  og "oplyst SR minus baren". Der er ingen bestået/dumpet.
- Eksempel V04 (@fvllport): N = 24, T = 2,9 giver 1,16. Oplyst Sharpe 1,46 ligger 0,30 over. Det er testet.
- Mangler N eller T, gives ingen bar.

## 6. Kommandoer

```
python3 research/tools/video_triage.py extract --video PATH --out DIR [--every-s 3] [--width 360]
python3 research/tools/video_triage.py new --id ID --source "@konto / beskrivelse" --video-sha256 HEX
python3 research/tools/video_triage.py check --claim research/data/video_claims/ID.json [--fill-prior]
python3 research/tools/video_triage.py report --dir research/data/video_claims --out FIL.md
```

- `extract` bruger GStreamer: `filesrc ! decodebin ! videoconvert ! videorate ! video/x-raw,framerate=1/N !
  videoscale ! video/x-raw,width=W ! pngenc ! multifilesink`. Billede `fNNN.png` svarer til sekund NNN × N.
- `extract` skriver `manifest.json` med sha256, varighed, antal billeder og indstillinger.
- `extract` afviser alt, der begynder med `http` eller ligner en URL. Den henter aldrig noget.
- `extract` nægter at skrive i en mappe, der allerede har billeder.
- `new` overskriver aldrig en eksisterende post.
- `check` giver exit 0 for gyldig og 1 for ugyldig. `report` er deterministisk: intet ur, sorterede rækker.

## 7. Registret (genereret med `report`)

Startposterne bygger kun på de eksisterende noter. Videoerne er ikke set igen. Alt, der ikke står i noterne, er
`UNKNOWN`. Ingen post har derfor sekundangivelser, undtagen EDWARD (fra ORB15-auditten).

Genereret af `research/tools/video_triage.py report` fra `research/data/video_claims` (12 poster). Kerne: entry_signal, stop, target, time_exit (P = PARTIAL, U = UNKNOWN). Held-baren er DIAGNOSTIC_ONLY, ikke en statistisk test. Lab-prior er kun en liste over factory-registrets poster med samme lineage eller mechanism_tag; den vurderer intet.

Optælling: REPLICABLE 0, NOT_REPLICABLE_FROM_VIDEO 7, NO_TRADING_CLAIM 5, PARTIAL 0

| ID | Kilde | Klassifikation | Kerne ikke OBSERVED | Performance vist | Handler vist/i alt | Konto | Held-bar (DIAGNOSTIC_ONLY) | Røde flag | Lab-prior |
|---|---|---|---|---|---|---|---|---|---|
| V01 | @keyzecom / LTT DATA FARM dashboard | NO_TRADING_CLAIM | n/a | – | ?/? | UNKNOWN | – | fri:0 | – |
| V02 | @stickmanxwx / general trading-bot guide | NO_TRADING_CLAIM | n/a | – | ?/? | UNKNOWN | – | lead_generation, fri:1 | – |
| V03 | Danish account ('Trading er held') / TradingView replay on an index | NOT_REPLICABLE_FROM_VIDEO | entry_signal:P, stop:P, target:P, time_exit:U | – | 1/? | UNKNOWN | – | selected_examples_only, backtest_only, costs_not_shown, fri:2 | E_hour_of_day_p1, E_hour_of_day_p2 |
| V04 | @fvllport / Day 1 of using trading bot to pass 50K Funded | NOT_REPLICABLE_FROM_VIDEO | entry_signal:U, stop:U, target:U, time_exit:U | +61.6 % over 2.9 years; max drawdown 7.85 %; PF 1.75; Sharpe 1.46 | ?/? | BACKTEST | N=24, T=2.9 → 1.16; SR 1.46 − bar = +0.30 | selected_examples_only, backtest_only, paid_product_or_fee, forbidden_resource_needed, costs_not_shown, fri:2 | – |
| V05 | @best.trading.bot / mobile bot, automatic trading bot system | NOT_REPLICABLE_FROM_VIDEO | entry_signal:U, stop:U, target:U, time_exit:U | balance 30.72 → 746.11; +$3,832 floating | 6/? | UNKNOWN | – | selected_examples_only, costs_not_shown, impossible_notional, fri:3 | – |
| V06 | @ray_fu / How to build a trading firm with AI agents | NOT_REPLICABLE_FROM_VIDEO | entry_signal:U, stop:P, target:P, time_exit:U | – | ?/? | UNKNOWN | – | forbidden_resource_needed, costs_not_shown, fri:2 | – |
| V07 | @marlonnq / DeepSeek writes MQL5 EMA-crossover EA NQBLADE | NOT_REPLICABLE_FROM_VIDEO | entry_signal:P, stop:U, target:U, time_exit:U | one backtest 2025-01-01 to 2026-04-30 ('CONGRATS') | ?/? | BACKTEST | – | backtest_only, costs_not_shown, fri:2 | E_donchian_trend_p1, E_donchian_trend_p2, L03_sol_trend_hourly, L14_tsmom_v1 |
| V08 | @dub9287 / Deepseek 4.1 Uncensored X Opus 5.5 (sent twice, identical files) | NO_TRADING_CLAIM | n/a | – | ?/? | UNKNOWN | – | fri:1 | – |
| V09 | @jessepbuilds / Day 1: Building an agentic trading system | NO_TRADING_CLAIM | n/a | – | ?/? | UNKNOWN | – | fri:0 | – |
| V10 | @cotraderia / 6 years of trading rules in Obsidian, 7 AI agents | NO_TRADING_CLAIM | n/a | – | ?/? | UNKNOWN | – | fri:0 | – |
| EDWARD | @jamiedoestradez / Edward, bot with AI (NQ opening range) | NOT_REPLICABLE_FROM_VIDEO | entry_signal:U, stop:P, target:U, time_exit:U | ORB +$1,000 (1 contract, 50 pt); continuation -10.75 pt (about -$215); WT +10 pt (not filmed) | 3/? | UNKNOWN | – | lead_generation, selected_examples_only, costs_not_shown, fri:2 | E_hour_of_day_p1, E_hour_of_day_p2 |
| FOMO | @trading.calls / fomo app, Grok Bot copies 4 traders 30 s later | NOT_REPLICABLE_FROM_VIDEO | entry_signal:P, stop:U, time_exit:P | one trade +900.0 % ($72 → $720); account +$5.73 (+2 %) since deposit | 1/? | SIM | – | selected_examples_only, sim_or_demo_account, forbidden_resource_needed, costs_not_shown, fri:2 | E_smart_vs_crowd_p3, L01_copy_kol, L02_self_found_traders, L04_buy_graduations, L10_launch_v1, L11_smart_v2, X02_copybot_paper |

**Læsning:**
- Ingen af de 12 er REPLICABLE eller PARTIAL. Det svarer til de manuelle noter.
- Lab-prior er kun et opslag. Fx peger V07 (EMA-kryds) på L03 og L14, som noten allerede nævner. FOMO peger på
  L01, L02, L04, L10 og L11 (som FOMO-udkastets afsnit 2).

## 8. Grænser

- Værktøjet ser ikke videoer og læser ikke tekst i billeder. Et menneske eller Claude udfylder posten.
- Der er intet netværk. Ingen URL åbnes, ingen data hentes, ingen konto bruges.
- Klassifikationen er kun så god som tjeklisten. Den måler, om reglen kan genskabes fra videoen, ikke om den virker.
- Held-baren er en grov diagnose under stærke antagelser. Den erstatter ikke lab'ets Holm/BH-regler eller en lås før
  data.
- Lab-prior matcher kun på navne i factory-registret. En ny mekanisme uden lineage giver ingen match.
- Startposterne har `video_sha256 = UNKNOWN`, fordi videoerne ikke ligger i repo'et.
