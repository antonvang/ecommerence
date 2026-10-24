# 4σ-fald: leave-one-day-out (beskrivende) og DROPPED efter brugerens beslutning

**Regel:** `research/PROTOCOL_V3.md` ændring 21m punkt 1, committet 2026-10-24 kl. 19:40 (c2ff910) før kode og
beregning. **Kode:** `lab/drop4s.py` (fb32981). **Kørt:** 2026-10-24 ca. kl. 19:41, explore0, kun cache. Fillistens
sha256 `3f384de3…` (samme som m21c), hændelsernes `384b6e26…`. Rådata: `DROP4S_LOO_m21c.json`.
**Mærkat:** BESKRIVENDE og efterfølgende valgt, aldrig bevis. **Status: DROPPED** (brugerens beslutning, mulighed 3 efter
1a). Ingen test, intet alfa, ingen LÅS, ingen train3/validation3.

| Klynger | Antal | Gennemsnit | Udelad én (min / median / maks) | Uden de 10 travleste | Andel positive |
|---|---|---|---|---|---|
| UTC-døgn | 167 (1 020 fald) | +1,57 % | +1,29 % / +1,57 % / +2,05 % | +1,28 % | 65 % |
| ISO-uge | 74 | +1,17 % | +0,97 % / +1,15 % / +2,24 % | +0,55 % | 72 % |

Sammenligning: ubetinget 24 t-afkast i explore0 +0,26 % pr. døgn (670 døgn, hver 6. time).

## Hvad det viser

- Klyngegennemsnittet +1,57 % fra eftermiddagens ad hoc-beregning er nu reproduceret og gemt.
- **Mønstret hænger ikke på ét eller få krakdøgn.** Udelades et vilkårligt døgn eller de 10 travleste, ligger det stadig
  over +1,2 %. Det svækker et af mine argumenter i beslutningsoplægget (koncentration). På ugeniveau halveres det uden
  de travleste uger (0,55 %), så nogle få urolige uger betyder noget.
- De tilbageværende risici er uændrede: mønstret er valgt efter at have set explore0 (efter en screening, der fejlede),
  2020–21 var et tyrmarked (driften forklarer ca. 0,26 af 1,57 %), og omkostninger på krakdage er højere end gennemsnittet.
- Hypotesen er **DROPPED** efter brugerens beslutning. Ønsker brugeren at genoverveje det på grundlag af dette, er
  mulighederne fortsat en LÅS (k = 5, α 0,0015625, måling i train3 og validation3) eller en fremadrettet test med eget
  budget. Begge kræver en ny dateret ændring og brugerens ja.
