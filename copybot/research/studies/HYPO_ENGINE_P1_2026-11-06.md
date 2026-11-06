# HYPO_ENGINE P1 — hypotesemotor med falsifikationskontrol (direktørordre 47 P1, frist 12/11)

Kode `research/tools/hypo_engine.py`, tests `tests/test_research_hypo_engine.py` (9), data
`research/data/hypo_engine/report.json` + `report.md` (sha256 i report.md). **Kun syntetiske data**; ingen
markedsdata åbnet. Motoren foreslår og evaluerer; den godkender, fryser og promoverer intet (forslag går ind i
factory-registret som PROPOSED; godkendelse kræver en `human:`-aktør, testet).

## Opsætning

- Syntetiske verdener: 24 aktiver × 500 dage; fælles markedsfaktor (ρ 0,4, i stress 0,7), Student-t-stød (df 5;
  stress df 3; kontrol normalfordelt), to-tilstands volatilitetsregime (×2), manglende afkast (1 %, stress 5 %),
  og i signalverdener et observeret, vedvarende kendetegn z (AR(1), φ 0,9), der flytter næste dags afkast med
  ic · σ_t · z (ic 0,03; omkostningsscenariet ic 0,015).
- 51 kandidater pr. verden: momentum (24 lookbacks), kortsigtet reversal (8), lav volatilitet (12), kendetegnet z
  med lag 1-6 (6) og én bevidst lækkende kandidat (bruger dagens eget afkast). Tertil long-short, positioner
  besluttes før dagen; omkostning pr. enhed omsætning 5 bp (omkostningsscenariet 40 bp).
- Beslutningsregel: valgt kun hvis (1) den eksakte trunkeringstest ikke finder look-ahead, (2) netto-middel efter
  omkostninger > 0, (3) ensidet HAC-p (Newey-West, 5 lags) overlever korrektion over alle kandidater i verdenen.
  Holm (FWER 5 %) er hovedreglen; BH (FDR q 10 %) og Bonferroni ved N_eff rapporteres ved siden af.
- Hvert forslag har mekanisme, falsifikator, hvorfor ikke arbitreret væk, omkostninger/kapacitet, antal afviste i
  samme slægt og en prioritet = forventet styrke ud fra antal observationer / (1 + afviste i slægten). Prioriteten
  bruger aldrig afkast.

## Resultat (200 verdener pr. scenarie, 1.000 i alt)

| Scenarie | Type I pr. test (netto) | FWER uden korrektion | FWER Holm [95 % CI] | FWER BH | Andel falske fund Holm / BH | Ægte effekt fundet (Holm) | Lækage fanget | Brutto-signifikant dræbt af omkostninger | Profit-PASS med netto ≤ 0 | N_eff af 50 |
|---|---|---|---|---|---|---|---|---|---|---|
| null_base | 0,027 | 0,355 | 0,010 [0,003; 0,036] | 0,075 | 1 / 1 (kun nul) | — | 200/200 | 0 | 0 | 44,2 |
| null_gauss_calm | 0,021 | 0,280 | 0,015 [0,005; 0,043] | 0,040 | 1 / 1 (kun nul) | — | 200/200 | 8 | 0 | 44,3 |
| null_fat_regime | 0,014 | 0,230 | 0,005 [0,001; 0,028] | 0,015 | 1 / 1 (kun nul) | — | 200/200 | 3 | 0 | 44,1 |
| signal | 0,036 | 0,375 | 0,010 [0,003; 0,036] | 0,095 | 0,026 / 0,248 | 74 af 200 | 200/200 | 1 | 0 | 44,1 |
| signal_cost_killed | 0,000 | 0,000 | 0,000 [0,000; 0,019] | 0,000 | — | 0 | 200/200 | 724 | 0 | 44,0 |

FWER = andel verdener med mindst ét falsk valg. "Type I pr. test" er puljet over korrelerede tests; dets interval i
report.json er for smalt og bruges ikke til beslutninger.

## Hvad det viser

1. **Bredde uden korrektion giver falske fund.** Med 50 kandidater og intet andet end 5 %-niveauet finder vi
   mindst ét "signifikant" resultat i 23-36 % af verdener helt uden fordel. Det er videoens "tusindvis af grafer"
   uden kontrol.
2. **Holm holder FWER under 5 %** i alle nul-scenarier, også med fede haler, regimeskift, høj korrelation og
   manglende data (højeste øvre CI-grænse 0,043). Testen er konservativ: netto-afkast efter omkostninger trækker
   type I under det nominelle niveau.
3. **Prisen er styrke.** En plantet effekt på ic 0,03 findes kun i 74 af 200 verdener (37 %) efter Holm. Bredde
   koster opdagelsesevne; det er argumentet for få, forhåndsregistrerede familier frem for mange varianter.
4. **FWER og FDR er forskellige ting.** BH holder q 10 % på rene nul-verdener (dér er FDR = FWER), men i
   signalverdener er andelen falske blandt de valgte 0,248 efter den strenge mærkning. En gentagen kørsel (40
   signalverdener) viser, at **alle** BH's "falske" valg er momentum-varianter (lookback 15-95). De opfanger den
   plantede, vedvarende effekt indirekte gennem afkastene og kommer i klumper (mange korrelerede varianter i samme
   verden). Det er den virkelige fælde: én effekt fundet mange gange under forskellige navne. Derfor tæller
   slægt og N_eff i P0-registret, og BH alene må ikke bruges til at udvælge.
5. **Lækage fanges altid** (1.000/1.000) uden falske alarmer på de 50 ærlige kandidater (0 af 50.000).
6. **Omkostninger:** 724 brutto-signifikante kandidater blev afvist, fordi netto ≤ 0; ingen kandidat fik PASS med
   netto ≤ 0 i nogen regel.
7. N_eff ≈ 44 af 50: variantfamilierne er korrelerede, men slet ikke så meget, at de kan behandles som én test.

## Begrænsninger (UNKNOWN)

- Syntetiske verdener er enklere end markeder (ingen strukturbrud ud over regimet, ingen survivorship i universet,
  ingen ændring af omkostninger over tid). Survivorship og ændrede data efter lås testes i P3.
- Momentum-proxyerne viser, at "falsk" afhænger af mærkningen; en rigtig undersøgelse skal på forhånd definere,
  hvad der tæller som samme mekanisme.
- Shadow mode mod pipelinens faktiske beslutninger (ALLOW/BLOCK) hører til P3, jf. ChatGPT's svar på P0.
