# F3 `fregime` (D2): præcis definition, sammenligning, bias og testplan — udkast, BLOKERET

Skrevet 2026-10-24 kl. 13:13 af Claude. Familiefilen er `research/families/drafts/fregime.json` (status BLOKERET:
ændring 8 punkt 3, én åben familie pr. mekanisme-tag; fcarry er åben til sit fremadvindue slutter). Ingen
registrering, lås, godkendelse eller alfa. **Ændring 8 punkt 4 forbyder udkastet at beregne afkast eller signaler
på data fra noget vindue**, så denne plan indeholder ingen backtest og ingen optælling af, hvor tit porten var åben.

## 1. Præcis definition

- **Marked:** Binance spot + USD-M-perp i samme mønt, `UNIVERSE_30_V3` med fcarrys udelukkelser (holdout uden
  BTC/ETH/SOL), samme datakilder (`data.binance.vision`, månedsarkiver).
- **Fundingmål:** for hver mønt summen af afregnet funding i de 7 døgn før beslutningen, divideret med 7 (pr. døgn;
  uafhængigt af afregningsintervallet 8/4/2 t).
- **Markedsport:** medianen af fundingmålet over de mønter, hvis første time ligger mindst 7 døgn før beslutningen.
  Åben iff median ≥ `gate_day`. Gitter fastlagt før data: `gate_day` ∈ {0,0004; 0,0005} pr. døgn (gulvet er 0,0003
  = 0,01 %/8 t × 3). Ingen andre værdier.
- **Tidsjustering:** beslutning mandag 01:00 UTC med funding afregnet før beslutningen; positionen holdes fra timen
  der åbner 01:00 (fcarrys konvention, så indgangen aldrig får 00:00-afregningen).
- **Signal/entry:** +1 (lang spot, kort perp, 1x) i mønt i for ugen iff porten er åben OG møntens floor-andel (andel af
  de seneste 14 hele UTC-døgn med summeret funding ≥ 0,0003) ≥ 0,8.
- **Exit:** 0 ved næste mandag, hvis en af betingelserne ikke længere holder. Ingen stop-loss (prisdelta ≈ 0).
- **Risiko:** 1x, aldrig negativ position, ingen gearing; familiens omkostningsmodel (taker 0,15 % pr. parrundtur
  + spread/slippage 0,08 %, stress 2×); attributionsgaten (funding − omkostninger > 0 og prisforholdets P&L ≤ funding).

## 2. Sammenligning — er signalet nyt?

| Eksisterende | Forskel | Overlap |
|---|---|---|
| `E_fcarry__floor_a8` (OBSERVATION) | samme mønt-regel; F3 tilføjer markedsporten | **høj**: F3's positioner er en delmængde af floor's (samme mønter, samme uger, når porten er åben) |
| `E_fcarry__hyst_a8` (OBSERVATION) | dagligt pr. mønt, APR_7 med hysterese | samme pengestrøm |
| `E_fcarry__filt_a8`, `filt_w_a8` (REJECTED) | egen APR_7 pr. mønt; tabte til omkostninger | lærdom: omsætning × omkostninger |
| `E_funding_contrarian_p1` (REJECTED) | retningsbet på ekstrem funding | ingen prisretning i F3 |
| F2 `dbasis` (udkast) | låst basis i COIN-M-kvartalskontrakter | samme gearingspræmie, positivt korreleret (F2_PLAN.md) |
| L13 `carry_v1` (Hyperliquid, kirkegård) | ugentlig top-5-rotation; aftagende kant | idéen "carry kun når den betaler" |

**Konklusion:** F3 er ikke et nyt signal i snæver forstand; det er fcarry's floor-regel med et markedsbredt filter.
Det, der er nyt, er påstanden, at omkostningerne i lav-funding-regimer er hele forskellen. En F3-PASS ved siden af en
fcarry-PASS ville **ikke** være to uafhængige fund.

## 3. Bias og risici

- **Selektionsbias (alvorligst):** idéen kom fra at se floor/hyst's train3 (flad) og validation3 (positiv) — de
  faser, F3 selv ville blive screenet på. Screeningen er derfor ikke uvildig; kun et fremadvindue kan afgøre.
- **Datalækage:** ingen i reglen (kun funding afregnet før beslutningen); men porten bruger tværsnittet af hele
  universet, så en mønt, der mangler data, ændrer medianen; derfor kræves 7 døgns historik pr. mønt.
- **Survivorship:** `UNIVERSE_30_V3` er valgt med kendskab til, hvilke mønter der overlevede til 2022+ (fcarry har
  samme forbehold).
- **Tærskelfølsomhed:** to tærskler fastlagt før data; ingen gentagne forsøg. Ligger det sande regimeskifte mellem
  0,0004 og 0,0005, er resultatet følsomt, og det skal rapporteres som sådan.
- **Få uafhængige regimer:** 2022–2023 indeholder groft to fundingregimer (lavt 2022–23-H1, højt 2023-H2). En
  regimeregel har derfor reelt få uafhængige observationer, selv med mange dage.

## 4. Testplan, når reglen tillader det (tidligst når fcarry lukker)

1. Ejeren godkender (`approve-family`/`confirm-family`); α_F = 0,0125 reserveres, hvis W0 har plads.
2. Screening i familiepipelinen på train3/validation3 med alle uændrede gates (train-gate, placebo p < 0,10, DSR,
   2× omkostninger, attribution). Kendt bias: se punkt 3.
3. Negative kontroller (forudbestemt): (a) samme regel med porten forskudt 26 uger (et regime fra et andet halvår);
   (b) porten tilfældigt permuteret over uger med samme andel åbne uger (seed 7, 2 000 træk). F3's netto skal slå
   begge; ellers er det ikke porten, der virker.
4. Fremadvindue 12 måneder, futilitetskig efter 6, α_i = α_F/M; påkrævet Sharpe ca. 2,25 (M = 1).
5. **Afvisning:** enhver gate fejler; eller netto ≤ netto af fcarry-floor i de samme fremadmåneder (porten tilføjer
   intet); eller færre end 8 åbne uger i fremadvinduet (UNTESTABLE: for få regimeobservationer).

## 5. Det billigste informative skridt, der er tilladt nu

Ændring 20 (samme dag) forudregistrerer en **regime-diagnostik af fcarrys eget fremadvindue**: når fcarrys
fremadtest kører, opdeles medlemmernes daglige nettoafkast efter, om D2's port var åben eller lukket den uge.
Det tester D2's mekanisme på data, der ikke findes endnu, uden ny familie og uden alfa, og den afgør intet for fcarry.
Resultatet skal oplyses i F3's `drafting_data_access`, før F3 nogensinde godkendes.
