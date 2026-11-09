# PAR-BOG: datakvalitetsnote om bogalder (følger rapporten 19/11)

Dato: 2026-11-09 (UTC). Direktørordre 68 P4. Noten er et **bilag** til PAR-BOG-rapporten for den 19/11 og ændrer
intet: skæringstidspunkt, beregning, værktøj, pin og ledger er uændrede. Kilden er skrivebeskyttede forespørgsler på
produktionens `lab.db` (`mode=ro`, `query_only`, `unshare -rn`).

## De to ordrer

Begge er ben af samme parentré (ETHUSDT–BTCUSDT, z = −2,127) i kontoen `LANE_68b8b6feb9` (PAR-BOG):

| Ordre-id | Instrument | Side | Bogført tid (UTC) | Ordrehændelse, vægur (UTC) | Forskel | Fyldt | Notional |
|---|---|---|---|---|---|---|---|
| `LANE_68b8b6feb9\|in\|ETHUSDT-BTCUSDT\|1794178800\|ETHUSDT` | ETHUSDT | køb | 2026-11-08 23:00:59 | 23:02:00 | 61 s | 0,468 | 998,19 USD |
| `LANE_68b8b6feb9\|in\|ETHUSDT-BTCUSDT\|1794178800\|BTCUSDT` | BTCUSDT | salg | 2026-11-08 23:00:59 | 23:02:00 | 61 s | 0,013 | 970,44 USD |

Bogen havde 20 niveauer på hver side for begge ordrer (spread 0,0005 % og 0,0001 %). Gebyrerne var 0,998 og
0,970 USD.

## Hvad der er dokumenteret, og hvad der ikke er

**Dokumenteret:**

- PAR-BOG henter en bog via passets fælles cache (`books`), hvis et andet regnskab allerede har læst den i samme pas.
  Ellers henter den bogen selv (`lab/pairs.py`).
- Cachen nulstilles ved hvert pas. Bogen kan derfor ikke være ældre end passets start.
- Den bogførte tid (23:00:59) er passets start, og ordrehændelsen er skrevet 61 s senere.
- Bogens alder ved udførelsen ligger derfor mellem **0 og 61 s**.
- I samme pas har ingen anden ordre en `sim_exec`-række for ETHUSDT eller BTCUSDT. Genbrug kan altså ikke påvises ud
  fra ordrer.

**Sandsynligt, men ikke dokumenteret:**

- BTCUSDT og ETHUSDT er med i de univers-sæt, som FWD- og SHADOW-regnskaberne læser bøger for ved passets start, før
  bane-kontiene køres. Carry90-kontiene for BTC og ETH mærker også deres perp-ben før PAR-BOG, fordi kontiene køres
  sorteret efter ledger-id.
- Det taler for, at bøgerne blev genbrugt, og at alderen da ligger nær den øvre grænse (op til ca. 61 s). Den slags
  genbrug efterlader intet spor i databasen.

**Hvorfor effekten ikke kan måles:**

- Bogen ved udførelsen blev ikke gemt.
- `sim_exec.book_age_s` er regnet med passets eget ur. Den ligger i (−1, 0) og siger intet om alderen.
- Der findes ingen senere, frisk læsning af de samme instrumenter i passet at sammenligne med.
- En vurdering ville kræve et skøn over prisbevægelsen i op til 61 s. Det er et estimat, ikke en måling, og hører
  ikke til i rapportens tal.

## Betydning for rapporten

- Grænsen ligger 1 s over motorens egen friskhedsgrænse på 60 s (`data_max_age_s`). Grænsen håndhæves i dag med
  passets ur, så den har aldrig kunnet slå til her.
- De øvrige 6 PAR-ordrer har en øvre grænse på højst 49 s.
- Til sammenligning har alle 74 STRAKS-ordrer en øvre grænse på højst 52 s.
- Indtil friskhedsmålingen er aktiveret (`BOOK_AGE_MODE "measure"`, ordre 67/68), bør rapporten nævne de to ordrer
  som et forbehold om datakvaliteten, sådan: *"2 af 8 ordrer (én entré, begge ben) blev udført på en bog af
  ukendt alder, 0–61 s; effekten kan ikke måles."* Rapportens tal ændres ikke.
