# fomo / "Grok Bot": syntetisk eksekveringssimulator (direktørordre 56)

Kun design. Intet netværk. Ingen markedsdata. Ingen live handel. Alt er syntetisk.

Påstanden i TikTok-videoen: en bot kopierer en Solana-memecoin-leders køb 30 s senere,
sælger ved 10× og har et tidsstop, og tjener penge. Simulatoren skal kunne falsificere det.
Den kan ikke bevise det modsatte.

Kode: `research/desk/fomo/sim.py`. Test: `tests/test_research_desk_fomo_sim.py` (34 tests).
Kør: `cd copybot && python3 -m unittest tests.test_research_desk_fomo_sim -v`.

## Model

Leder og følger er to separate positioner i samme pool.

1. En sti er en liste af hændelser: `swap` (andres køb/salg), `leader_buy`, `leader_sell`,
   `rug` (likviditet fjernes), `pool_dead`, `migrate` (succes eller fejl), `missing`
   (ingen prisobservation i `[t, until)`) og `tick` (en observation uden handel).
2. Hændelserne afspilles i tidsorden gennem poolens tilstand.
3. Lederen køber ved `t_L`. Følgeren køber ved `t_L + delay_s` (standard 30 s).
   Følgeren køber EFTER alle hændelser med `t ≤ t_L + delay_s`. Lederens eget køb er med.
4. Følgerens eget køb flytter poolen. Følgerens eget salg flytter den igen.
5. Udgang fyldes altid til et eksekverbart salgskvote for hele positionen efter gebyrer.
   Aldrig til en mid-pris.
6. Hver input-sti giver præcis én række i output. Ingen rækker forsvinder.

### Formler

Konstant-produkt AMM (PumpSwap/Raydium-lignende), gebyr `f` på input:

- Køb af `s` SOL: `tokens = T · s(1−f) / (S + s(1−f))`.
- Salg af `n` tokens: `sol = S · n(1−f) / (T + n(1−f))`.
- `lp_fee_share` af gebyret bliver i poolen. Så vokser `k = S·T`. Resten forlader poolen.
- Mid-pris `S/T` bruges kun som trigger og diagnose.

Bonding curve (pump.fun-lignende), virtuelle reserver `vS·vT = k`, gebyr på SOL-siden:

- Køb: `tokens = vT · s(1−f) / (vS + s(1−f))`, højst de resterende rigtige tokens.
- Salg: `sol_rå = vS · n / (vT + n)`, højst den rigtige SOL. Følger får `sol_rå · (1−f)`.
- Når de rigtige tokens er solgt, er kurven KOMPLET og lukket. Ingen handel.
- `migrate` med succes åbner en AMM med kurvens rigtige SOL og `migration_tokens`.
- `migrate` med fejl dræber poolen.

Regnskab for følgeren (alt i SOL):

- `swap_in = size · (1 − bot − mev)`. `E = swap_in − dex_gebyr_ind` er den SOL, der reelt køber tokens.
- `X = sol_ud + dex_gebyr_ud` er salgsværdien uden exit-gebyr.
- `brutto = X − E`. Prisimpact ligger i brutto. Den er fysik, ikke et gebyr.
- `cost_basis = size + priority + network`.
- `netto = modtaget − cost_basis = brutto − sum(alle omkostninger)`. Testen kræver `|fejl| ≤ 1e-12`.
- Omkostninger: bot, mev, dex, priority og network, både ved ind og ud.
- `net_pct = netto / cost_basis · 100`.

Lederen betaler kun dex-gebyr samt priority + network pr. transaktion. Lederen har ingen bot-fee.
Lederens resterende tokens værdisættes eksekverbart på følgerens exit-tilstand (før følgerens salg).

### Udgangsregler (rækkefølge ved hver observation efter entry)

1. `RUG`: poolen er rugget. Sælg ind i resten (ofte ~0).
2. `POOL_DEAD`: poolen er død eller migrationen fejlede. Værdi 0. Ingen transaktion.
3. `TP_10X`, to varianter (`tp_trigger`):
   - `"price"` (primær, videoens regel): fyrer når spot-prisen (= market cap) er ≥ 10× følgerens
     spot-pris lige før dens eget køb. Fyldet er stadig det eksekverbare salg for hele positionen.
   - `"executable"` (konservativ): fyrer kun når det eksekverbare netto-provenu er ≥ 10× `cost_basis`.
4. `LEADER_SELL`: kun hvis `follow_sells=True`. Ved første observation ≥ lederens salg + `delay_s`.
5. `TIME_STOP`: ved første observation ≥ `t_entry + time_stop_s`. Tidsstoppet er en timer, så
   tidspunktet selv er en observation (tilstanden fra seneste hændelse, ikke interpoleret).

Ingen eksekverbar observation før stiens slutning giver `MISSING_PRICE`. Så bruges den laveste af
(sidste observerede eksekverbare kvote, kvoten på slut-tilstanden). Den loftes ved `size_sol`.
En `MISSING_PRICE`-handel kan derfor aldrig blive en gevinst. Uden nogen kvote er det fuldt tab.

`NOT_EXECUTABLE` ved entry: realiseret pris > kvote ved signal · (1 + `slippage_tolerance`),
eller poolen er død/rugget/komplet, eller kurven har ikke plads. Den fejlede transaktion koster
priority + network. Rækken beholdes.

## Antagelser og ukendte

| Punkt | Status | I modellen |
|---|---|---|
| fomos bot-fee | UNKNOWN | `bot_fee_frac` er påkrævet. Testen sweeper 0 / 0,01 / 0,02. |
| Tidsstop | ASSUMPTION | Risikokortet viser "TP 10× · 7:00". Vi læser det som 7 t (`time_stop_s = 25200`). Den viste handel blev holdt 12:19→3:39 (3 t 20 min). En læsning som klokken 07:00 er UNKNOWN og ikke modelleret. `time_stop_s` er påkrævet. |
| Slippage-indstilling | UNKNOWN | `slippage_tolerance` er påkrævet. |
| Følger fomo salg? | ASSUMPTION | Primært `follow_sells=False`. Videoen siger "aiwass still holding · rule kept" efter bottens TP. `follow_sells` er påkrævet. |
| TP-trigger | ASSUMPTION | Primært `"price"` (market cap 10×). `"executable"` er den konservative variant. |
| Referencepris for TP | ASSUMPTION | Følgerens spot-pris lige før dens eget køb. |
| Dex-gebyr | ASSUMPTION | 0,25 % standard. 0,5 % i `LEGACY_COPYBOT_FEES`. |
| pump.fun-gebyr og kurvekonstanter | ASSUMPTION | 1 %; 30 SOL / 1,073 mia. virtuelle, 793,1 mio. rigtige, 206,9 mio. til migration. Ikke verificeret on-chain. |
| Gebyr til LP | ASSUMPTION | `lp_fee_share = 1,0`. |
| Priority fee | ASSUMPTION | 0,0001 SOL pr. transaktion. Network 0,000005 SOL. |
| Fejlet transaktion | ASSUMPTION | Betaler priority + network. Ingen bot-fee. |
| Exit-latens | ASSUMPTION (optimistisk) | Salget sker på samme tilstand, som botten observerer. Det favoriserer påstanden. |
| Manglende data ved entry | ASSUMPTION | `missing` påvirker kun exit-overvågning, ikke entry. |
| `LEGACY_COPYBOT_FEES` | ét scenarie | dex 0,5 %, bot 1,0 %, mev 0,5 %, network 0,0015 SOL (fra git 586fcbb). Ikke sandhed. |

Legacy-reglen fra den gamle CopyBot: "kopien kan aldrig købe billigere eller sælge dyrere end den
wallet, den kopierer". Den findes som `legacy_floor=True` og som tjekket `copy_never_better_than_leader`.
Ren fysik kan godt give følgeren en bedre pris, hvis andre sælger i vinduet. Legacy-reglen er strengere.

## Tests: navn → hvad den beviser

| Test | Beviser |
|---|---|
| `test_k_never_decreases_after_fee_swap` | `k` falder aldrig efter et swap med gebyr. Med LP-andel > 0 stiger `k`. |
| `test_round_trip_loses_at_least_both_fees` | Køb og straks salg taber mindst købsgebyr + salgsgebyr, målt i SOL som opkrævet. Fund: den bogstavelige grænse `tab ≥ 2·f·s` er FORKERT for gebyr-på-input (tab → `s(2f − f²)`). Den er derfor ikke testet. |
| `test_bigger_size_worse_average_price` | Større ordre giver dårligere gennemsnitspris, både ved køb og salg. |
| `test_price_rises_with_cumulative_buys` | Kurvens pris stiger med samlede køb. |
| `test_completion_closes_curve_and_migration` | Kurven lukker ved ~85 SOL. Migration åbner en AMM med kurvens SOL. |
| `test_entry_after_failed_migration_not_executable` | Entry efter fejlet migration er `NOT_EXECUTABLE`. |
| `test_holding_through_failed_migration_is_pool_dead` | Position gennem fejlet migration ender `POOL_DEAD` med fuldt tab. |
| `test_successful_migration_trades_on` | Ingen exit mens kurven er komplet. Handel fortsætter efter migration. |
| `test_follower_entry_not_better_than_leader` | Med kun køb i vinduet er følgerens entry-pris ≥ lederens. |
| `test_delay_zero_still_pays_own_impact` | Også med 0 s forsinkelse betaler følgeren sin egen impact, ved køb og salg. |
| `test_follower_net_not_above_leader_net` | Samme størrelse og tx-gebyrer, kun køb i vinduet, lederen værdisat på følgerens exit-tilstand: følgerens netto ≤ lederens, for 25 tilfældige stier efter entry. |
| `test_mid_hit_but_not_executable_no_tp` | `"executable"`: mid når 10×, men eksekverbart salg gør ikke. Ingen TP. |
| `test_executable_hit_is_tp` | `"executable"`: eksekverbart 10× giver `TP_10X`. |
| `test_price_trigger_fires_but_net_far_below_900` | `"price"`: TP fyrer på 10× market cap, men netto er langt under +900 %. |
| `test_price_trigger_not_fired_below_10x` | Under 10× fyrer TP ikke. |
| `test_time_stop_exact_with_executable_quote` | Tidsstop sælger ved første tilstand ≥ `time_stop_s` til den eksekverbare kvote (genberegnet uafhængigt). |
| `test_missing_prices_exit_at_next_state_no_interpolation` | Hul i data: exit ved næste tilgængelige tilstand. Ingen interpolation. |
| `test_missing_to_the_end_is_kept_as_missing_price` | Ingen data til slut: `MISSING_PRICE`, tab, rækken beholdes. |
| `test_time_stop_beyond_path_end_is_missing_price` | Tidsstop efter stiens slutning er `MISSING_PRICE`, ikke en gevinst. |
| `test_tiny_pool_not_executable_reported` | Lille pool: `NOT_EXECUTABLE` (slippage) bliver rapporteret, ikke droppet. |
| `test_x20_spike_shorter_than_delay_not_captured` | En ×20-spike kortere end forsinkelsen fanges ikke. Lederen vinder, følgeren taber. |
| `test_rug_value_near_zero` | Rug giver ~0 i værdi og tab over 99 %. |
| `test_pool_dead_full_loss` | Død pool giver −100 %, og tabet tælles med. |
| `test_net_equals_gross_minus_costs` | Netto = brutto − alle omkostninger til 1e-12 for alle rækker i en blandet batch. |
| `test_legacy_fee_scenario_reconciles` | Det samme med `LEGACY_COPYBOT_FEES`. |
| `test_bot_fee_sweep_net_decreases` | Bot-fee 0 / 0,01 / 0,02 giver faldende netto. |
| `test_unknowns_have_no_default` | `time_stop_s` og `bot_fee_frac` skal angives. Ukendt `tp_trigger` afvises. |
| `test_no_silent_drops` | `len(results) == len(inputs)`. Ugyldige stier bliver `INVALID_INPUT`-rækker. Tællingerne stemmer. |
| `test_determinism` | Samme input og seed giver identisk JSON. |
| `test_legacy_formulas_equal_feefree_xyk` | Den gamle CopyBots formler er præcis gebyrfri x·y=k. |
| `test_legacy_floor_never_cheaper_than_leader` | Fysik tillader et billigere køb, når andre sælger. Legacy-gulvet forhindrer det. |
| `test_legacy_fee_numbers` | Legacy-gebyrerne er 0,5 % / 1,0 % / 0,5 % / 0,0015 SOL. |
| `test_worked_example` | Tallene nedenfor er deterministiske og har de rigtige fortegn. |
| `test_only_stdlib_allowlist` | `sim.py` importerer kun math, random, statistics, dataclasses, json. Intet netværk, ingen database, ingen `lab`. |

## Regneeksempler (syntetiske, fra `sim.worked_example()`)

### A: 30 SOL-pool, leder og andre køber i vinduet

Pool 30 SOL / 1 mia. tokens, dex 0,25 %. Lederen køber 1 SOL ved t=0. Andre køber 2 SOL ved
t=10 og 3 SOL ved t=20. Følgeren køber 1 SOL. Bot-fee 1 %. `time_stop_s = 25200`,
`follow_sells=False`. "Nødvendig mid-multipel" er den spot-pris, målt mod prisen før lederens køb,
hvor et eksekverbart salg af hele positionen giver 10× `cost_basis` netto.

| Forsinkelse | Følger-entry vs leder-entry | Følger skal bruge | Leder skal bruge |
|---|---|---|---|
| 0 s | +6,6 % | 12,49× | 11,52× |
| 30 s | +43,1 % | 16,53× | 11,52× |

Med 30 s forsinkelse skal kursen stige 16,5×, før følgeren har 10× netto. Lederen skal kun bruge 11,5×.

### B: videoens tal med x·y=k og `LEGACY_COPYBOT_FEES`

Fra videoen: lederen gik ind ved $47,6K MC. Botten gik ind 30 s senere ved $49,8K MC (+4,6 % dårligere).
Salget blev vist som $72,00 → $720,00. Det er nøjagtigt 10×, altså nul gebyr og nul slippage i appens SIM-visning.

Antagelser (ASSUMPTION):

- SOL = $150. Udbud 1 mia. tokens. MC = mid-pris · 1 mia. · SOL-pris.
- Tokenet er migreret fra pump.fun. PumpSwap-poolen startede med 85 SOL / 206,9 mio. tokens. `k` er fast.
  Ved $47,6K MC giver det `S = √(MC·k/udbud)` = 74,70 SOL og 235,4 mio. tokens i poolen.
- Lederen køber 1,0 SOL. Andre køber 0,711 SOL i vinduet. Det giver præcis $49,8K MC ved bottens entry.
- Botten køber for $72 = 0,48 SOL. Senere køber andre, til spot-prisen er præcis 10× bottens entry-pris.
- `tp_trigger="price"`, `time_stop_s = 25200`, `follow_sells=False`.

| Scenarie | Udgang | Netto % | Netto $ |
|---|---|---|---|
| Appens visning | TP | +900,0 % | +$648,00 |
| x·y=k, nul gebyrer (kun impact) | TP_10X | +874,5 % | +$629,66 |
| x·y=k + `LEGACY_COPYBOT_FEES` | TP_10X | +833,4 % | +$601,95 |
| Lederen, samme tilstand | (værdisat) | +879,1 % | |

Brutto er +854,9 %. Omkostningerne er $15,53. Selv med fysik og gebyrer er en lille ordre i en
pool af denne størrelse tæt på +900 %, HVIS 10× market cap faktisk kommer. Det er forudsætningen,
der skal testes. Simulatoren kan ikke afgøre, hvor tit det sker.

Samme 10× MC-bevægelse, større ordre (legacy-gebyrer):

| Ordre (SOL) | Netto % | Eksekverbar multipel ved TP |
|---|---|---|
| 0,48 | +833,4 % | 9,33× |
| 2 | +767,6 % | 8,68× |
| 5 | +658,7 % | 7,59× |
| 10 | +527,3 % | 6,27× |
| 20 | +365,8 % | 4,66× |

Med `"price"`-trigger kan den realiserede netto derfor ligge langt under +900 %. TP fyrer på
market cap, men fyldet er det eksekverbare salg efter impact og gebyrer.

## Hvad simulatoren IKKE kan bevise

- Den siger intet om reel lønsomhed. Syntetiske stier er ikke evidens.
- Den kender ikke fordelingen af rigtige memecoin-stier: hvor tit 10× sker, hvor tit rug sker,
  hvor hurtigt andre køber efter en kendt leder.
- `random_path` er ikke kalibreret til noget. Dens gennemsnit betyder ingenting.
- Den kender ikke fomos rigtige gebyr, slippage, tidsstop eller salgsregel.
- Den modellerer ikke MEV-sandwich mekanisk, kun som en procent (`mev_frac`).
- Den modellerer ikke blokrækkefølge, fejlede transaktioner under trængsel eller exit-latens.
  Exit sker på den observerede tilstand. Det er optimistisk for påstanden.
- Den modellerer ikke andre kopibotter, der køber samme signal. Det ville gøre følgerens entry værre.
- En falsifikation kræver rigtige, forward-indsamlede data under lab-reglerne. Det er ikke en del af ordre 56.
