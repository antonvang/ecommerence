# Tredje reference: lukkede former for R2

Her udledes forventninger fra matematik og håndskrevne positioner, uafhængigt
af evaluatorens loops. `test_r2.py` kontrollerer disse orakler mod ref_eval.
Der bruges ikke anden implementerings kode eller output.

## 1. R2_09_T30: alternerende serie

Én aktiv position, ingen omkostning/funding, x_i = (-1)^i + 1/8,
i=0,...,29. Dermed T=30, middel=1/8, L=3 og d_i=(-1)^i.

γ_k = (-1)^k (30-k)/30. Med Bartlett-vægte 3/4, 1/2, 1/4:

S = 1 + 2[-(3/4)(29/30) + (1/2)(28/30) - (1/4)(27/30)] = 1/30.

se = sqrt((1/30)/30) = 1/30; t = (1/8)/(1/30) = 15/4 = 3.75.
p_one = erfc(3.75/sqrt(2))/2 = 0.00008841728520080039.
Med m=1 afviser både Holm og BH. T=29 er utilstrækkelig uanset middel.
R2_15_tiny og R2_16_large multiplicerer serien med henholdsvis 1e-140 og
1e140: middel og se skalerer tilsvarende, t og p er uændrede op til afrunding.
Produkterne ligger inden for binær floats repræsenterbare interval.

## 2. R2_02_flip_cost: vendinger og HAC

q=10/10000=1/1000. Positionerne er +1,-1,+1,... over 30 bars;
ret=0 og funding=0. Første indgang koster q, de 29 vendinger hver 2q.
total_cost=59q=0.059, middel-net=-59q/30.

d_0=29q/30 og d_i=-q/30 for i=1,...,29.
γ_0=29q²/900; for k=1,2,3 er γ_k=-kq²/27000.
S=173q²/5400 og se=q sqrt(173/162000).
t=-(59/30)sqrt(162000/173), omtrent -60.1818054812471.
Der er ingen ekstra afsluttende likvidation.

## 3. R2_03_clip_turnover: delvise positionsændringer

Positionerne er 0,1/4,3/4,-1/2,-1,0. Absolutte ændringer er
0,1/4,1/2,5/4,1/2,1: sum=7/2.
total_cost=(7/2)/1000=0.0035; middel-net=-0.0035/6.
T=6 giver INSUFFICIENT med null lag og testfelter.

## 4. R2_17–20: Holm og BH

Generatorens `multiple(z)` giver x_i=(1/4)[(-1)^i+z/30]. Udledning 1 giver
middel=z/120 og se=1/120, så t=z, uanset den perfekte korrelation mellem
hypoteserne. Forskellige families gør fingeraftrykkene forskellige.

- R2_17: z=2.4 for alle tre; p≈0.00819754 < 0.05/3. Alle afvises.
- R2_18: z=1.875, m=1; p≈0.0303964 < 0.05. Den ene afvises.
- R2_19: z=(3.5,1.8,1.7). Første p≈0.000232629 < 0.05/3.
  Anden p≈0.0359303 > 0.05/2: Holm stopper. Tredje p≈0.0445655
  er under 0.05, men må stadig ikke afvises af Holm. BH afviser alle tre.
- R2_20: z=(2.05,1.88,1.76). Mindste p≈0.0201822 > 0.05/3,
  så Holm afviser ingen. Største p≈0.0392039 < 0.05, så BH afviser alle.

## 5. R2_14_fsum_assets og positionsnulstilling

Hver bar har gross=(1e16,1,-1e16,3). Eksakt sum er 4 og middel er 1.
fsum skal bevare 1-leddet; en simpel venstre-sum i assetrækkefølge giver 3
og forkert middel 0.75. Den korrekte serie er konstant: S=0, lag=3,
status INSUFFICIENT og null testfelter.

R2_04 har fem betalinger af q: første indgang, genindgang efter gap,
genindgang efter MISSING, lukning ved manglende signal, ny indgang.
total_cost=0.005; gap=1, empty=1, missing_ret=1, signal_missing=1.
R2_05 tæller fire embargo-rækker, ingen dubletter og én off-grid-række;
første aktive indgang og efterfølgende vending koster samlet 3q=0.003.

## Konklusion

De analytiske orakler består: T30 giver t=3.75 og se=1/30; flip-serien
giver total_cost=0.059 og den udledte HAC; clip-serien giver 0.0035.
Holm-mønstrene er henholdsvis (true,true,true), (true),
(true,false,false), (false,false,false), mens BH afviser alle i disse fire
cases. Fsum-casen giver middel 1 og S=0. Alle kontroller bruger højst
1e-13 relativ tolerance eller 12–15 decimalers absolut kontrol, altså
strengere kontrol end specifikationens uændrede 1e-9-regel.
