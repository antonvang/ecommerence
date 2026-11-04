# H-SPR-2: spotspread bestemt af tick-størrelsen (skrevet kl. 14:26 lokal 11-04, før data)

Forslået af ChatGPT (direktør) 11-04, besluttet af Claude. Separat fra H-SPR-1, som fortsætter uændret; H-SPR-1's
observationer bruges ikke som bekræftelse. Ændrer ingen model, alarm eller omkostning; et senere forslag om at bruge
resultatet i alarmreferencen kræver ejerens ja, fordi det rører en eksisterende alarm.

## Eksponering

Set før denne tekst: ETCUSDT.SPOT's spread var præcis én tick (0,01) i alle 11 capacity/1-målinger (kurs 7,0-7,7);
XTZUSDT.SPOT 1-4 ticks (0,0001) ved kurs 0,25-0,30 (MISSION27_4B R-B). Ingen andre instrumenters spreads er set
i forhold til tick. **Alle rækker med ts før dette commit udelukkes.**

## Hypotese

For et Binance-spotinstrument med tick/mid ≥ 8 bp (2 × den faste reference på 4 bp, "tick-bundet") er bogens relative
spread typisk præcis én tick: s = tick/mid. Forudsigelse uden tilpasning: s_pred = tick / mid.

## Data (kun fremadrettet, efter commit)

- **Primær:** `capacity/1`, metric `rt_500`, instrumenter *.SPOT, felterne `spread` og `mid` (samme definition
  som `Book.spread()`).
- **Sekundær (rapporteres særskilt):** `sim_exec` for LANE_* på *.SPOT; mid = fill-pris for samme order_id i
  `sim_fills`.
- **Tick:** `PRICE_FILTER.tickSize` fra én GET af `https://data-api.binance.vision/api/v3/exchangeInfo` (samme
  market-data-host som `lab/paper_runner.py` SPOT_REST og `lab/lane.py` spot_pairs), lavet efter commit; svaret gemmes
  med sha256 i `research/data/hspr2_ticks_2026-11-04.json`. Ændres en tick senere, bruges den nye fra en ny GET.
- **Observation:** én række; k = s / (tick/mid) (antal ticks). Datakvalitet: mid > 0, spread > 0.

## Kriterier (fastsat nu)

Pr. tick-bundet instrument med n ≥ 20 observationer på ≥ 5 UTC-dage (pr. kilde):
1. **Holder**, hvis ≥ 80 % af observationerne har k ∈ [0,95; 1,05] (én tick, afrundingstolerance) **og** medianen af k
   ligger i [0,95; 1,5].
2. **Falsificeret**, hvis < 50 % har k ∈ [0,95; 1,05].
3. Ellers **delvis** (bredere end én tick en del af tiden); andelen pr. antal ticks rapporteres.
- Ikke-tick-bundne instrumenter (tick/mid < 8 bp) rapporteres beskrivende; der forudsiges intet for dem.
- Evalueres første gang, når mindst ét tick-bundet instrument har n ≥ 20 i den primære kilde (forventet ~3 uger ved
  capacity/1's daglige takt); ingen p-værdier; kriterierne ændres ikke efter at tallene er set.
