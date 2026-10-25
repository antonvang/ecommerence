# De registrerede explore0-screeninger — oversigt (2026-10-25 kl. 21:29)

Læst fra de committede resultatfiler med `python3 research/tools/screen_overview.py` (reproducerbart). Intet er
genberegnet, ingen tærskel ændret, ingen variant genkørt. Explore0 = 2020-03..2021-12, 1 t USD-M-klines (spot og funding
hvor angivet). Test pr. nøgle: tosidet fortegnsskift-test på UTC-døgnklynger, p ≤ 0,005, samme fortegn 2020/2021,
placebo p > 0,05, |gennemsnit| ≥ omkostningskrav (21i).

| # | Nøgle | Klynger (hændelser) | Gns. bp (se) | t | p | 2020 / 2021 bp | Placebo p | Krav bp | Dom | Fejlede krav | Klassifikation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `abnormal_move|cont_4h|m21c` | 450 (2196) | -3.4 (–) | – | 0.822 | -11.2 / 1.6 | 0.713 | 46 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021; |mean| >= 0.0046 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt); effekt under omkostningskravet |
| 2 | `abnormal_move|cont_24h|m21c` | 450 (2194) | 43.6 (–) | – | 0.215 | 4.4 / 68.9 | 0.768 | 46 | SCREEN_FAIL | p <= 0.005; |mean| >= 0.0046 | ingen påviselig effekt (p > 0,05); effekt under omkostningskravet |
| 3 | `btc_lead|alt_excess_24h|m21f` | 150 (150) | 4.7 (36.2) | 0.13 | 0.899 | -19.6 / 25.0 | 0.574 | 111 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021; |mean| >= 0.0111 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt); effekt under omkostningskravet |
| 4 | `squeeze_break|cont_24h|m21f` | 89 (143) | 119.7 (202.5) | 0.59 | 0.869 | -28.4 / 246.3 | 0.949 | 65 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt) |
| 5 | `catalyst_move|cont_24h|m21f` | 9 (9) | – (–) | – | – | – / – | – | 65 | UNTESTABLE |  | lille stikprøve (< 60 klynger) |
| 6 | `funding_crowd|squeeze_24h|m21h` | 312 (1162) | 2.2 (49.1) | 0.04 | 0.956 | 12.2 / -3.8 | 0.808 | 46 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021; |mean| >= 0.0046 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt); effekt under omkostningskravet |
| 7 | `spot_lead|perp_1h|m21i` | 499 (4151) | 10.8 (5.3) | 2.04 | 0.039 | -0.6 / 18.6 | 0.575 | 47 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021; |mean| >= 0.004650917905583458 | svagt signal (0,005 < p ≤ 0,05); fortegnsskift 2020/2021 (ustabilt); effekt under omkostningskravet |
| 8 | `perp_led|move_24h|m21i` | 436 (2004) | 8.8 (34.6) | 0.26 | 0.789 | 19.2 / 2.1 | 0.309 | 47 | SCREEN_FAIL | p <= 0.005; |mean| >= 0.004657281344969441 | ingen påviselig effekt (p > 0,05); effekt under omkostningskravet |
| 9 | `macro_release|post_drift_24h|m21j` | 57 (58) | 18.0 (49.5) | 0.36 | 0.728 | 50.5 / -7.4 | 0.714 | 46 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021; |mean| >= 0.0046 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt); effekt under omkostningskravet; lille stikprøve (< 60 klynger) |
| 10 | `attention_shock|cont_7d|m21j` | 22 (32) | -383.7 (670.8) | -0.57 | 0.587 | -1899.1 / 62.0 | 0.850 | 46 | SCREEN_FAIL | p <= 0.005; same sign in 2020 and 2021 | ingen påviselig effekt (p > 0,05); fortegnsskift 2020/2021 (ustabilt); lille stikprøve (< 60 klynger) |

## Afvisningsårsager (fra resultatfilerne)
- **9 SCREEN_FAIL, 1 UNTESTABLE** (`catalyst_move`: 9 klynger < 15).
- **Ingen påviselig effekt (p > 0,05):** 8 af 9 FAIL.
  - Den eneste med p < 0,05 er `spot_lead|perp_1h|m21i` (p 0,039, 10,8 bp, t 2,04).
  - Med 10 nøgler forventes ca. 0,5 sådanne alene ved tilfældighed; Holm-justeret p ≈ 0,35.
  - Dens 2020-halvdel er −0,6 bp, så effekten ligger i 2021 alene. Det er ikke et robust signal.
- **Ustabilt signal (fortegnsskift mellem 2020 og 2021):** 7 af 9 FAIL.
- **Under omkostningskravet:** 7 af 9 FAIL. Ingen nøgle fejlede **kun** på omkostninger. Mulighed C (lavere krav for
  likvide markeder) ville ikke ændre en eneste dom.
- **For lille stikprøve:**
  - J1 (57 klynger) har lav styrke; dens effekt (18 bp, se 49,5 bp) kan ikke skelnes fra 0;
  - J2 (22 klynger) og catalyst (9) er for små til at sige noget.
- **Datakvalitet:** ingen nøgle er afvist på grund af datafejl. Udelukkelserne er dækningsregler, ikke fejl:
  - m21h: neutral funding 860, ingen fundingfil 76, ingen nylig funding 97;
  - m21i S2: ingen spotbar 110, manglende funding 80;
  - øvrige: højst 7 hændelser pr. nøgle.

## Er de ni uafhængige? Nej
- **Samme hændelser:** `abnormal_move|cont_4h` og `|cont_24h` (m21c) bruger de samme 4σ-hændelser med to horisonter.
  `perp_led|move_24h` (m21i S2) bruger m21c's hændelser igen, opdelt efter spot/perp. Det er tre nøgler på én
  hændelsesmængde.
- **Samme data og samme regime:** alle bruger explore0's 1 t-klines og døgnklynger i 2020–21. Flere nøgler har negativ
  eller nul effekt i 2020 og positiv i 2021 (cont_24h 4/69 bp, squeeze_break −28/246 bp, spot_lead −1/19 bp). Det peger
  på ét fælles træk, 2021's trendmarked, ikke på uafhængige mekanismer.
- **Effektivt antal uafhængige spørgsmål:** ca. 6 mekanismegrupper:
  - bevægelser (m21c + m21i S2);
  - BTC-føring;
  - kompression;
  - funding;
  - spot–perp samme aktiv;
  - makro/opmærksomhed.
  Ingen af dem viser et signal, der overlever p ≤ 0,005.

## Konklusion
Explore0 indeholder ingen robust timefrekvens-effekt i de afprøvede mekanismer. Det er ikke omkostningerne, der
blokerer, men fraværet af et stabilt signal. Det støtter ændring 21l punkt 3 (discovery i explore0 er lukket). Ny
evidens kan kun komme fra nye data: K1/K2 og K3 (fremadrettet) og R3 (minutdata, 14/11).

## Uløste spørgsmål med mest informationsværdi
1. **K3:** findes et pres omkring fundingafregningen, som timebarer ikke kan se? Svar ca. 14/11 (60 runder, 20 døgn).
2. **R3:** reagerer BTC/ETH på makroudgivelser inden for 60 min, når timeopløsningen ikke maskerer det? Svar 14/11.
3. **K1/K2:** har TradFi-perps en weekendstruktur uden underliggende prisopdagelse? Svar tidligst 2027-01-18.
4. **Er 2021-effekterne regime, ikke mekanisme?** Det kan kun besvares med data uden for explore0, altså en LÅS på
   train3/validation3 (kræver brugerens beslutning). Ingen af nøglerne har bestået screeningen, så der er intet at låse.
