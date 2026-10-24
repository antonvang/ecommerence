# Screening m21c: bevægelse → fortsættelse eller tilbagevenden (krypto-perps, explore0)

**Regel:** `research/PROTOCOL_V3.md` ændring 21c, committet 2026-10-24 kl. 15:58 (788b1ac) før kode og før beregning.
**Kode:** `lab/movescreen.py` (2bbfca7). **Kørt:** 2026-10-24 kl. 16:00, kun cache, ingen netværk, 22 s.
**Data:** 971 månedsfiler, 132 symboler (alle cachede USD-M `<mønt>USDT` i explore0 undtagen BTCDOMUSDT), fillistens
sha256 `3f384de3fddfdd9a146c42216abeb002dfa5d0bee9be5a75644cde42c1007aca`. Rådata: `MOVESCREEN_m21c.json`.
**Mærkat:** UDFORSKNING, aldrig bevis.

## Resultat (begge kandidater registreret, også de negative)

| Nøgle | Hændelser | Døgnklynger | Klyngegennemsnit | p (tosidet) | 2020 / 2021 | Placebo (−30 d) p | Dom |
|---|---|---|---|---|---|---|---|
| `abnormal_move\|cont_4h\|m21c` | 2 196 | 450 | −0,03 % | 0,82 | −0,11 % / +0,02 % | 0,71 | **SCREEN_FAIL** (p, fortegn, størrelse) |
| `abnormal_move\|cont_24h\|m21c` | 2 194 | 450 | +0,44 % | 0,22 | +0,04 % / +0,69 % | 0,77 | **SCREEN_FAIL** (p, størrelse) |

Hændelsernes sha256: cont_4h `07bff8fa…adcaa`, cont_24h `403cd211…c04f` (fuldt i json-filen).

**Konklusion:** et 4σ-timeflag på en krypto-perp har, målt én time efter flaget, ingen retning ud over tilfældighed på
døgnniveau: hverken fortsættelse eller tilbagevenden efter 4 eller 24 timer. Det passer med de tidligere afviste
spor (`daily_reversal`, MISSION3 M2, tsmom_v1). Ændring 21's flag er derfor **beskrivende** og ikke et handelssignal.
Nøglerne screenes aldrig igen under m21c.

## Beskrivende, ikke testet (punkt 6) — og et efterfølgende mønster

- Hændelsesgennemsnittet (−1,14 % ved 24 t) og klyngegennemsnittet (+0,44 %) har modsat fortegn. Store markedsdage
  har mange hændelser, så hændelsesniveauet overvægter få dage. Klyngetesten er den registrerede.
- Op-bevægelser: +1,23 % (n 1 174). Ned-bevægelser: −3,86 % (n 1 020), dvs. kursen steg i gennemsnit 3,9 % i
  døgnet efter et 4σ-fald.
- Ned-bevægelserne fordeler sig på 167 døgn. De 5 største døgn har 20 % af hændelserne (2021-05-19 +20,6 %,
  2021-02-23 +15,9 %, 2021-04-18 +10,8 %). Uden de 5 døgn er hændelsesgennemsnittet en stigning på 2,1 % (n 817).
  Over alle 167 døgn er klyngegennemsnittet en stigning på 1,6 %. Til sammenligning: det ubetingede 24 t-afkast i explore0 er +0,26 % pr. døgn (klyngegennemsnit over 670 døgn,
  hver 6. time).
- **Vurdering:** "køb efter et 4σ-fald, hold 24 t" er et mønster, der er fundet **efter** at have set explore0. Det
  er ikke screenet og kan ikke screenes ærligt på explore0 igen. 2020–21 var et tyrmarked, så mønstret kan være
  regimet. En test kræver en ny dateret ændring, der nævner dette forbehold (som 17e), og den kan kun gøres i train3
  (2022–23H1, et bjørnemarked) efter en LÅS med α ≈ 0,0016. Ingen sådan beslutning er taget.

## Gyldighed

Kun krypto-perps. TradFi-perps (guld, olie, SPY osv.) har al historik fra 2025 (reserveret) og er UNTESTABLE
historisk. Indgang ved næste bars lukkekurs; gebyrer, spread og funding er ikke trukket fra (screeningens krav er
|gennemsnit| ≥ 0,46 %, F1's rundtur).
