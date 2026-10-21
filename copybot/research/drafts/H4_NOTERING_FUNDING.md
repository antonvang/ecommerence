# H4 `notering`: funding på nye USD-M-perps er højere de første dage efter listningen (målehypotese)

**Status:** præregistrering, skrevet 2026-10-21 af Claude før nogen funding for nye listninger er hentet eller set.
Låses af `research/PROTOCOL_V3.md` ændring 16a. Intet handles. Kun måling; en handelsregel kræver en senere ændring
og ændring 8's vej (brugerens `approve-family`).

## 1. Påstand og mekanisme

- **Påstand:** for en USD-M-perp, som Binance lister for første gang, er den gennemsnitlige afregnede funding (pr. 8 t)
  i de første 7 døgn efter første afregning højere end i døgn 31–60 for samme perp.
- **Mekanisme:** ved en ny listning er der få market makers og stor spekulativ efterspørgsel efter gearet lang
  eksponering, før spot-arbitrage er etableret; funding betaler for den ubalance og falder, efterhånden som
  arbitragekapital kommer til (samme pengestrøm som F1, her betinget af listningstidspunktet).
- **Modbevises af:** gennemsnittet af Y = F_tidlig − F_sen er ikke signifikant > 0 i validering (punkt 6).

## 2. Data

- Binance' egne meddelelser om nye futures (ændring 16, kategori 48, udgiverens tidsstempel; titlen skal matche
  "Binance Futures Will Launch" og "Perpetual"). Mønterne findes efter ændring 16's faste regler.
- Afregnet funding pr. symbol fra `data.binance.vision` (månedlige `fundingRate`-filer, allerede tilladt vært).
- **Stikprøve:** symboler hvis første afregning i arkivet ligger i `train3` (2022-01..2023-06) eller `validation3`
  (2023-07..2023-12), og som ikke har funding før meddelelsen (en genlistning tæller ikke). Symbolet skal have
  afregninger i mindst 60 døgn efter første; ellers udelades det (rapporteres med antal).
- **Vinduer:** et symbol hører til det vindue, dets første afregning ligger i. Døgn 31–60 for et symbol i `train3`
  kan ligge i `validation3`'s måneder; det er tilladt, fordi symbolets egen måling hører til `train3`. Intet fra 2024
  (holdout) eller senere hentes eller bruges; et symbol hvis døgn 60 ligger efter 2023-12-31, udelades.

## 3. Måling (fastlåst; én konfiguration)

- Funding pr. 8 t = rå rate × 8 / timer siden forrige afregning (som ændring 12i).
- Første afregning t0 udelades (den kendes først, når den er sket).
- **F_tidlig** = gennemsnit af afregninger i (t0, t0 + 7 døgn]. **F_sen** = gennemsnit i (t0 + 30 døgn, t0 + 60 døgn].
- **Y** = F_tidlig − F_sen pr. symbol. Primær statistik: gennemsnit af Y over symbolerne i vinduet.
- **Sekundært** (afgør intet): median af Y; andel symboler hvor summen af funding i (t0, t0 + 7 døgn] dækker en
  rundtur på 0,46 % (F1's omkostningsmodel); Y med døgn 1–3 i stedet for 1–7.

## 4. Placebo og baseline

- **Placebo:** samme måling med en falsk start t0 + 90 døgn (tidlig = døgn 91–97, sen = døgn 121–150) for de
  symboler, der har data så længe (og ikke ud over 2023-12-31). Rapporteres; afgør intet.
- **Baseline:** 0 (ingen forskel mellem tidlig og sen funding).

## 5. Point-in-time og lækage

- Meddelelsen og første afregning kendes på deres tidspunkt; målingen bruger kun afregninger efter t0.
- Intet resultat for nogen ny listning er set før denne tekst (scannerens fremadrettede data fra 2026 indgår ikke).
- Kendt: generel funding i 2022–2023 lå ofte på gulvet (ændring 8 punkt 20); det er set i aggregat for 30 store
  mønter, ikke for nye listninger.

## 6. Statistik (fastlåst)

- **Enhed:** ét symbol. **Minimum:** 20 symboler i `train3` og 8 i `validation3`; ellers UNTESTABLE.
- **Train-gate:** gennemsnit Y > 0. Ellers REJECTED, og validering læses ikke.
- **Validering:** ensidet fortegnsskift-test af gennemsnit Y > 0 (eksakt ved n ≤ 20, ellers 100.000 træk, seed 7,
  p = (k + 1) / (B + 1)); α = 0,05 (én test, egen målefejlrate efter ændring 16a).
- **Stop:** testen køres én gang. Andre vinduer, døgn eller symbolfiltre efter resultatet er en ny hypotese.

## 7. Styrke og risici (ærligt)

- Antal nye USD-M-listninger i 2022–2023 er ikke talt endnu (kræver meddelelserne); forventet flere dusin pr. år [A].
- Overlevelse: symboler, der delistes inden døgn 60, udelades; de kan have haft den mest ekstreme funding. Antallet
  rapporteres.
- Selv et PASS siger intet om netto carry-afkast; scannerstudiet viste, at omkostningerne på små mønter æder
  funding (`research/studies/CARRY_BASIS_PLAN.md`).
