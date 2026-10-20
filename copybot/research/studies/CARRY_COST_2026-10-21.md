# Carry-studiet efter rettelse, med observerede omkostninger (2026-10-21)

**Status:** studie af offentlige 2026-data; ikke en test, ikke bevis, ingen alfa. Skrevet af Claude under brugerens
mandat. Fuldt output: `CARRY_COST_2026-10-21_output.txt`; kode: `research/tools/recent_study.py` (rettet),
`research/tools/fetch_recent_funding.py` (henter nu også spot-listen).

## Fejlen i det tidligere studie

`recent_study.py` normaliserede hver afregning til 8 timer (rate × 8 / timer siden forrige) for at kunne sammenligne
tærskler på tværs af mønter, men summerede **den normaliserede værdi** som indtægt. Mønter med 4-timers funding (de
fleste på Binance i 2026: 201.674 af 254.077 intervaller) fik dobbelt indtægt; Hyperliquid (hver time) otte gange.
Rettet: reglerne bruger den normaliserede rate, indtægten er den betalte rate (`tests/test_research_recent_study.py`).
`spread_study.py` summerede de betalte rater i 8-timers spande og var ikke ramt.

## Data (hentet igen 2026-10-21, efter at genstarten tømte /tmp)

- Binance USD-M `fundingRate`: 522 perps (5 fejlede), højst 500 afregninger pr. perp (API'ets grænse), 2026-05-07 til
  2026-10-20; 4-timers mønter dækker derfor kun cirka 83 dage. Ingen dubletter. 354 med Binance spot (511 spot-par
  med USDT, status TRADING, hentet samme dag).
- Hyperliquid `fundingHistory`: 172 mønter (20 fejlede), 60 dage, timeafregning, ingen dubletter; 126 med Binance spot.
- **Begrænsninger:** kun perps, der handles i dag (overlevelsesbias: afnoterede mønter mangler); ingen pris- eller
  basisbevægelse; handler, der stadig er åbne ved slut, værdisættes til funding indtil da; en symbolmapping ud over
  `MØNT` + `USDT` forsøges ikke (fx 1000-præfiks), så nogle mønter med spot udelades.

## Omkostninger: observeret og antaget

Omkostning = én tur ind og ud, begge ben (spot køb/sælg og perp sælg/køb), i procent af **ét bens** værdi.

| Scenarie | Grundlag |
|---|---|
| 0,3 % | antaget: VIP0-gebyrer alene (spot 0,10 % × 2 + perp 0,05 % × 2), intet spread eller slippage |
| 0,6 % | det tidligere studies antagelse |
| 1,0 % | mellemscenarie |
| 1,5 % | **observeret**: de tre scanner-konti (EPIC, HOT, MITO; 5.000 USD pr. ben) betalte ind 0,72–0,73 % og ud 0,62–0,88 %, i alt 1,35–1,60 % (gebyrer + afstand mellem fyldpris og midte, fra `sim_fills`) |

## Resultat (mønter med Binance spot)

| Regel | Handler | Brutto funding | Netto 0,3 % | 0,6 % | 1,0 % | 1,5 % |
|---|---|---|---|---|---|---|
| Binance ≥ 0,05 % (scanner-regel, 12e/12f) | 64 (16 åbne) | +0,79 % | +0,49 % (5 %-grænse +0,21 %) | +0,19 % (−0,09 %) | −0,21 % | −0,71 % (17 % vundet) |
| Hyperliquid ≥ 0,10 % × 8 (HL-regel, 13a) | 36 (10 åbne) | +1,11 % | +0,81 % | +0,51 % (+0,30 %) | +0,11 % (−0,10 %) | −0,39 % |

## Konklusion (beregnet, ikke bevist)

1. Med de omkostninger, papirkontiene faktisk har betalt i tynde mønter, taber begge regler.
2. En fordel findes kun, hvis en tur koster tæt på gebyrerne alene; det kræver likvide bøger, mens de højeste
   funding-rater typisk findes i tynde mønter.
3. 12g-gaten (3 døgns funding skal dække de live bøgers omkostning ved størrelsen) er netop værnet mod dette og bliver
   stående.
