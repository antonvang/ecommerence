# RESEARCH_PORTFOLIO_RANKING (direktørordre 52 P3, 2026-11-06)

Dette er en anbefaling, ikke en allokering. Der er ingen ny alfa-allokering, ingen godkendelse og ingen data testet.
W0 har stadig 0,0375 tilbage (0,05 minus fcarry-reservationen på 0,0125), og det rækker til 3 familier á α_F 0,0125.
Ingen hypotese er omklassificeret til en måling. Kilder: `desk/PROTOCOL_SHORTLIST.md`,
`studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`, `desk/NOV14_READINESS.md`, `desk/SMALL_PLAYER_FALSIFICATION.md` og
evidensregistrene E/X/S (168 kilder).

## 1. Kandidater og vurdering

Skala 1–5 (5 er bedst). "Tid" betyder tid til første gyldige bekræftende resultat, hvis alle gates og godkendelser falder
på plads til tiden.

| Kandidat | Type | Evidens | Uafhængighed | Effekt / styrke | Tid | Data | Omkostning/kapacitet | Informationsværdi pr. time | Status |
|---|---|---|---|---|---|---|---|---|---|
| **F2** HAR-RV mod EWMA, QLIKE | prognose (ikke profit) | 4: HAR er stærkt i litteraturen (E-kategori 10 + X, replikeret), men økonomisk værdi er ikke målt | 4: ny familie, ingen afvist slægt | 3: styrke 0,92 ved e 0,10 på train3 ∪ validation3 (ρ_c 0,5). Sandsynligvis overvurderet (AMB-03/04: højst ~335 target-dage uden overført historik). Effekten i krypto er UNKNOWN. | 4: historiske 1h-klines ligger i cachen, gate 14/11. Kalibreringsspec og evalueringsvindue mangler. | 4: alle 20 mønter i train3/validation3, explore0 delvist (5 mønter med 15–18 af 22 måneder) | 5: ingen handel | **5**: bruges af alle senere strategier (risiko og størrelse) og af C1 | CONDITIONAL; NOT_READY til 14/11 (AMB-02..11) |
| **LIQPROXY1** kline-spreadproxy mod målt spread | hypotese (β > 0), ikke måling | 3: Abdi-Ranaldo (E17, JBF), ingen effekt i krypto rapporteret | 4: omkostningsslægt (H-SPR), ingen afvist test af proxyen | 3: 0,864 ved antaget r 0,15, men skrøbelig: 0,56 ved ρ_c 0,2 og 0,55 ved 26 uger | 1: tidligst 2026-12-07 + 52 uger, kræver 2 foreslåede streams | 2: fwd_tob_universe og fwd_spec_journal er kun foreslået | 5: ingen handel | **4**: afgør om historiske omkostningsbevidste test efter 14/11 overhovedet kan bruge en kline-proxy | PROPOSED-udkast |
| **FUNDFRAG1** ekstrem funding mod fremtidig volatilitet | risikoprognose | 3: E04/E05/E16/E41 (carry går forud for crashes), X014 (ADL-halerisiko) | 3: tæt på HFC-1-kohorten (deler event-tællinger) | 3: 0,863 ved antaget e 0,15 over 270 dage (0,685 ved 180) | 2: ~270 dage forward | 2: foreslåede streams, census som fallback | 5: ingen handel | **3**: halerisiko for alle carry-baner | PROPOSED-udkast |
| **F3** COIN-M kvartalsbasis | netto-handel (carry) | 2: carry er presset (E08: Sharpe negativ i 2025; X001) | 2: overlapper carry-slægten (carry_v1 FAIL, fcarry, M2) | 3: 0,97 ved s 1,0 med K 1 over 8 udløb, men kun 0,53 ved s 0,5 | 2: COIN-M tidligst 28/11; observationsenheden er udefineret (AMB-27) | 2: COIN-M-gate og dapi-host mangler godkendelse | 3: kapitalbinding og margin | **2** | DEFERRED |
| LIQREC1 spread- og dybde-genopretning | prognose | 2: én ekstrem kaskade (E16) | 3 | 1: 0,22 | 1 | 2 | 5 | 1 | PARKED |
| SP-S1 tålmodig likviditet | risikopræmie | 2 | 2: pm_lp_v1 dækker allerede prediction markets | 1: 0,24 | – | – | 1: gebyrtrappen æder spreadet | 1 | PARKED |
| SP-S2 token-unlocks | prognose | 2: vendor-tal, IPO-lockup-analog | 2: supply_dilution er REJECTED, og alder siden notering forstyrrer | 1–2: 0,26–0,71 | – | 1: ingen PIT-kalender inden for gates | 3 | 1 | PARKED |

**Afviste beslægtede familier** (de bruges ikke igen under et nyt navn):
- carry_v1 (FAIL), fcarry-OBSERVATION, M2
- m21h-screen (funding retning)
- tsmom og Donchian (momentum)
- L20/taker_pressure/R4 (ordreflow)
- E_supply_dilution_p3
- vrp_timing og stablecoin_flow (v3-kataloget)

## 2. Rangering og anbefalet brug af W0 (ejerens beslutning D6)

1. **F2.** Den hurtigste vej til et gyldigt resultat og den største infrastrukturværdi. Kræver at AMB-02..11 lukkes og en
   signeret godkendelse af evalueringsvinduet (D3/D4/D5).
2. **LIQPROXY1.** Højest informationsværdi for omkostningsmodellen, men langsom og afhængig af streams. Uden B1/D1-streams
   kan den ikke starte.
3. **FUNDFRAG1.** Relevant halerisiko for carry. Den kan rykke foran LIQPROXY1, hvis streams godkendes til FUNDFRAG1
   alene.
4. **F3.** Venter til efter 28/11. Den har den svageste nye evidens (carry-kompression) og overlapper en afvist slægt.

Anbefaling til ejeren: tildel W0 til F2, LIQPROXY1 og FUNDFRAG1, i den rækkefølge godkendelserne faktisk foreligger, og
hold F3 uden for, indtil observationsenheden er defineret. Tildel ingen alfa, før familie, estimand, test og signeret
ejergodkendelse er på plads.

## 3. Hvad porteføljen samlet siger

- Ingen kandidat er en dokumenteret nettohandelsfordel. De to stærkeste er prognose- og risikomålinger. Det stemmer med
  litteraturen: ingen peer-reviewed nettofordel efter 2022 i et likvidt univers, og kode-audits sænker publicerede
  faktorer (X066).
- Små aktører skal især undgå at være den utålmodige, longshot- eller opmærksomhedsdrevne modpart. De kapacitetsbegrænsede
  effekter, vi fandt, forsvinder efter gebyrer på basis-niveau (SP-S1).
- Den største flaskehals er ejerens nøgle og godkendelser (D1–D7), ikke ideer eller kode.
