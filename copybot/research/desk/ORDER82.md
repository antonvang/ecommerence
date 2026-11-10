# ORDER82: post-terminal funding, STRAKS/PAR-BOG-auto-resume og regressionstests (direktørordre 82)

Skrevet 2026-11-10 kl. 02:46 lokal (01:46 UTC). Dev-only. Ingen patch er anvendt. `lab/`, `lab/straks.py` og `lab/pairs.py` er
uændrede. Ingen deploy, intet netværk. lab.db er kun læst for aggregater (`risk_events` pr. konto). **[F]** = fakta, **[V]** = vurdering.

## Testresultat

`test_post_terminal_funding_82,test_regression_82,test_research_gates,test_note_times` i den beskyttede loader: 32 tests OK
(20 nye: 7 + 13), 0 blokerede forsøg.
En mutation af 82-patchen (cutoff = 0) gav 2 fejl og er rullet tilbage.

## 1. Post-terminal funding

Ny patch: `research/desk/patches/82_close_post_terminal_funding.diff` (81 close v2 plus dette; 81 v2 er uændret). Test:
`tests/test_post_terminal_funding_82.py`.

- Når en lukning bliver `CLOSE_INCOMPLETE_TERMINAL` (eller `PARTIAL_CLOSE_TERMINAL`), gemmer tilstandshændelsen `terminal_ts` og `funding_id_at_terminal` (højeste `sim_funding.id` i det øjeblik).
- Funding på det åbne perp-ben bogføres fortsat som før. Nye rækker registreres én gang i en append-only `paper.post_terminal_funding` med række-id'er, afregningstider og `in_strategy_performance: false`.
- `funding_split(db, ledger)` deler funding i `strategy` (til og med cutoff) og `post_terminal`. Summen er altid alle bogførte rækker; intet slettes.
- Gentagelse og genstart: ingen ny række, ingen ny hændelse.

**Fund [F]:** `research/tools/net_report.py` summerer funding til cutoff og ville stadig tælle post-terminal rækker med. Den skal bruge splittet, før en eventuel aktivering. Ikke ændret her.

## 2. Auto-resume for STRAKS og PAR-BOG (kun undersøgt; pinnede filer urørt)

| | STRAKS (`lab/straks.py`) | PAR-BOG (`lab/pairs.py`) |
|---|---|---|
| Nødvendige markeder [F] | 12 perps fra `moves.WATCH`: BTC, ETH, XAU, XAG, XPT, COPPER, CL, BZ, NATGAS, SPY, QQQ, USDBRL | 8 perps: BZ, CL, ETH, BTC, QQQ, SPY, XAG, XAU |
| Nødvendige data [F] | Signaler fra `abnormal_move/1` (1h-klines), bog ved ind- og udgang, funding og bog til mærkning af holdte | 720 t 1h-klines pr. ben, bog for begge ben, funding, mærkning |
| Proben [F] | Én `fetch_book("BTCUSDT")`: hverken klines, funding, andre markeder eller krydsede bøger | Samme |
| Hvornår proben bruges [F] | Kun ved en `data_fetch`-pause, som ingen af de to moduler selv sætter (de sætter `spread_anomaly`, `max_drawdown`). Proben kaldes ikke ved andre pauser | Samme |
| Faktisk brug [F] | 0 `risk_events` for STRAKS-FØLG og STRAKS-MOD i lab.db | 0 for PAR-BOG |

**Risiko [V]:** i dag er proben en sovende fejl. Hvis en `data_fetch`-pause opstår (fremtidig kode eller manuel hændelse), kan én BTC-bog genoptage en bog, hvis andre markeder mangler data. `test_one_working_book_resumes_a_book_whose_other_markets_fail` viser mekanismen.

Samtidig betyder fraværet af `data_fetch`-pauser, at manglende data i de to bøger kun ses i passets svar ("no bars", "entry not sent"), ikke som en pause.

**Designforslag (kan godkendes senere; ingen kode mod de pinnede filer):**

1. Proben skal være en liste af navngivne kilder, én pr. nødvendigt marked (fresh 1h-bar ≤ 2 t, ikke-krydset bog), plus `abnormal_move/1`'s friskhed for STRAKS. Brug 81's flerkilde-`auto_resume`. `test_the_81_multi_source_rule_would_not` viser, at én fejlende kilde holder pausen.
2. TradFi-perps med handelspauser: kun med en dateret liste over pauser; ellers tæller de som fejl [V, ikke verificeret].
3. Om manglende data skal give en `data_fetch`-pause i STRAKS/PAR-BOG overhovedet, er en regelændring. Det er ejerens valg.

## 3. Regressionstests

`tests/test_regression_82.py` (13 tests) binder patchene sammen:

- Alle patches anvender strengt på de nuværende filer; 81 observability ligger oven på 72.
- 80, 81 v2 og 82 er alternativer: 82 kan ikke lægges oven på 81 v2.
- Pinnede filer har deres pin-hash.
- **Manglende spot**, samme konto:
  - Rigtig kode: lukker perp alene og svarer kun `closing`; klassificeres `PARTIAL_CLOSE` (78).
  - 80: `PARTIAL_CLOSE_TERMINAL`.
  - 81 v2 og 82: `CLOSE_INCOMPLETE_TERMINAL`, parret beholdes.
  - Ingen version melder `CLOSE_SUCCESS` med et åbent ben.
- **Falsk recovery** med rigtige filer under en midlertidig mappe: kun trade-polls virker. 72 alene giver `external.recovered`, 72 + 81 gør ikke.
- **Én-bog-probe:** dokumenteret som ovenfor.

## Kræver ejerens godkendelse

1. Om post-terminal funding skal bogføres (som nu) eller fryses. Patchen bogfører og adskiller.
2. Anvendelse af 72, 81 og 82, rækkefølge og deploy-vindue (tidligst efter 20/11, G12 for `ops`/`risk`).
3. Ændring af `lab/straks.py`/`lab/pairs.py`-proben og eventuel `data_fetch`-pause (pinnede filer, ordre 59-E).
4. `net_report` skal bruge `funding_split`.
5. Valg mellem 80, 81 v2 og 82: kun én kan anvendes.
