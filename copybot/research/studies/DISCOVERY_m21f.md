# Screening m21f: tre nye hypotesefamilier (krypto-perps, explore0)

**Regel:** `research/PROTOCOL_V3.md` ændring 21f, committet 2026-10-24 kl. 17:40 (1dae8fb) før kode og beregning.
**Kode:** `lab/m21fscreen.py` (e736fa6). **Kørt:** 2026-10-24 ca. kl. 17:41, kun cache og registret (skrivebeskyttet),
intet netværk, 29 s CPU-tid.
**Data:** 971 månedsfiler, 132 symboler, samme fillistes sha256 som m21c
(`3f384de3…07aca`). Katalysatorer: Binance-meddelelser i registret (1 354 navngivne mønter i alle år).
**Mærkat:** UDFORSKNING, aldrig bevis. Rådata: `DISCOVERY_m21f.json`.

| Familie | Nøgle | Hændelser | Klynger | Gns. (± SE) | p | 2020 / 2021 | Placebo p | Krav | Dom |
|---|---|---|---|---|---|---|---|---|---|
| A tværgående | `btc_lead\|alt_excess_24h\|m21f` | 150 | 150 | +0,05 % (± 0,36 %) | 0,90 | −0,20 % / +0,25 % | 0,57 | 1,11 % | **SCREEN_FAIL** |
| B volatilitetsregime | `squeeze_break\|cont_24h\|m21f` | 143 | 89 | +1,20 % (± 2,03 %) | 0,87 | −0,28 % / +2,46 % | 0,95 | 0,65 % | **SCREEN_FAIL** |
| C katalysator | `catalyst_move\|cont_24h\|m21f` | 9 | 9 | – | – | – | – | 0,65 % | **UNTESTABLE** (< 15 klynger) |

Hændelsernes sha256: A `66915375…4429`, B `d568f25c…af23`, C `8d394468…3170` (fuldt i json-filen).

## Hvad det betyder

- **A:** efter en 3σ-BTC-time (150 hændelser, gennemsnitligt 43 alt-mønter) er alt-kurvens merafkast over BTC de næste
  24 t lig nul (+0,05 % ± 0,36 %). Der er ingen langsom spredning fra BTC til alts på dette tidsniveau, og et eventuelt
  udslag skulle overstige en rundtur på 1,11 % for to ben. Beskrivende: i selve hændelsestimen bevægede alts sig
  0,10 % mindre end BTC (s-fortegnet).
- **B:** udbrud efter en stille periode (σ_72/σ ≤ 0,5, |z| ≥ 2,5) fortsætter ikke målbart. Gennemsnittet +1,2 % har et
  standardfejl på 2,0 % (89 klynger) og skifter fortegn mellem årene. Placeboen er også nul.
- **C:** kun 9 af 2 197 4σ-bevægelser havde en Binance-meddelelse om mønten i [h − 24 t, h + 1 t]. Meddelelserne
  handler mest om nye mønter, som endnu ikke har 600 timers perp-historik. Familien kan ikke testes med Binance-kilden
  i explore0. En katalysatortest kræver en anden historisk nyhedskilde med udgivelsestid (ikke tilgængelig på de
  tilladte værter i explore0) eller fremadrettede data fra news-watch.

Alle tre nøgler screenes aldrig igen under m21f. Ingen lås og intet alfa er brugt.
