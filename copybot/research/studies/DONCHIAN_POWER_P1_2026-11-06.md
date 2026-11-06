# Donchian-ensemble: styrkeberegning før låsning (direktørordre 45 P1; kl. 01:48 lokal 11-06)

**Dom: INSUFFICIENT POWER.** En 24 måneders fremadrettet papirtest kan ikke skelne en realistisk netto-fordel fra nul.

## Om beregningen

- Værktøj: `research/tools/donchian_power.py`, testet i `tests/test_research_donchian_power.py`.
- Resultat: `research/data/donchian_power/`, sha256 `89c087cdd576…`.
- Den bruger ingen markedsdata, ingen strategikode og ingen netværksadgang.
- Alle input er antagelser, og de står i værktøjets `SCENARIO` og `GRID`.

## Hvad der testes

Hypotesen er fra ONLINE_EDGES afsnit 2: ensemblet giver en højere Sharpe end lige-vægtet købe-og-hold. Testen bruger de
to porteføljers daglige afkastserier, én observation pr. dag.

- 20 korrelerede mønter tælles ikke som uafhængige. Med en parvis korrelation på 0,65 svarer de til 1,5 uafhængige.
- Overlappende signaler indgår kun gennem porteføljeafkastet.
- To estimander:
  - ΔSR: Memmel 2003, ganget med Los AR(1)-faktor og med et kurtosisled.
  - Alfa: OLS-intercept mod købe-og-hold, residual-vol = vol-target × √(1 − ρ²).
- Monte Carlo-kontrollen bruger 2.000 syntetiske, fedhalede AR(1)-forløb med seed 45:
  - størrelsen ved α 0,05 er 0,048;
  - simuleret styrke er 0,111 / 0,183 / 0,444 mod analytisk 0,116 / 0,185 / 0,439 ved ΔSR 0,3 / 0,5 / 1,0.

## Basisscenariet

| Antagelse | Værdi |
|---|---|
| Fremadrettet periode | 2 år |
| Købe-og-hold Sharpe | 0,6 |
| Korrelation trend/købe-og-hold (ρ) | 0,6 |
| Vol-target | 25 % |
| AR(1) | 0,05 |
| Kurtosis | 8 |
| Styrke | 80 %, ensidet |

## Resultat

| α | MDE ΔSharpe | MDE alfa p.a. | År nødvendige for ΔSR 0,3 / 0,5 / 1,0 | År for alfa 5 % / 10,8 % / 18 % |
|---|---|---|---|---|
| 0,005 (lab'ets) | 2,33 | 50,8 % | 115 / 42 / 10,5 | 207 / 44 / 16 |
| 0,05 | 1,68 | 37,0 % | 61 / 22 / 5,6 | 109 / 23 / 8,4 |

Til sammenligning: litteraturens alfa mod BTC er 10,8 % p.a. (Zarattini m.fl. 2025, ved 0,10 % pr. handel).

## Følsomhed

Ingen plausibel antagelse redder 24 måneder.
- ρ 0,4-0,8: MDE ΔSR 1,2-2,9.
- Kurtosis 3-15: MDE ΔSR 2,29-2,39.
- AR(1) 0-0,15: MDE ΔSR 2,21-2,59.
- 10 år ved α 0,05: MDE ΔSR 0,74 og alfa 16,5 %. Det er stadig over en beskeden effekt.

## Omkostninger

Omkostningerne trækker fra den effekt, der skal påvises:
- 0,5-7,5 % p.a. ved 5-15 × omsætning og 0,10-0,50 % pr. side.
- Ved realistiske danske detailomkostninger er effekten mindre end litteraturens.
- Spørgsmålet om de danske omkostninger ligger i P0.

## Hvad det betyder og ikke betyder

- Det betyder **ikke**, at trend ikke virker. Det betyder, at lab'et ikke kan *påvise* det fremadrettet inden for en
  brugbar horisont. Et positivt papirresultat efter 24 måneder ville ikke være evidens.
- En historisk test i stedet er heller ikke en løsning:
  - explore0 (2020-03..2021-12) er under 2 år og overlapper litteraturens periode, så den er ikke uafhængig;
  - 2024+ er holdout og må ikke bruges;
  - perioden 2017-2023 giver cirka 6-7 år, og MDE ΔSR ved α 0,05 er da 0,89-0,96. Den er stadig for stor.

## REDESIGN-muligheder

Ingen af dem er valgt. Hver kræver sin egen protokol før data og tidligst efter 11-14.

1. **Risiko-estimand.** Test om trend reducerer vol eller drawdown mod købe-og-hold. Den har styrke, fordi vol måles
   præcist, men den er ikke evidens for netto-profit.
2. **Bredere uafhængighed.** Trend på tværs af aktivklasser (krypto, råvarer, aktieindeks, valuta) har lavere
   korrelation mellem markederne og dermed flere effektive observationer. Det kræver historik for de klasser og en
   eksekverbar venue (P0).
3. **Parkér.** Det anbefales: Donchian forudregistreres ikke som en profitbog. Den nævnes igen kun, hvis 1 eller 2
   vælges.
