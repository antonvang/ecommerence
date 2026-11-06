# Carry-realisme med Kraken-gebyrer og kapitalscenarier (direktørordre 46 P0 + P1; kl. 02:07 lokal 11-06)

- **Værktøj og tests:** `research/tools/carry_realism.py` (read-only lab.db) med 7 tests i
  `tests/test_research_carry_realism.py`.
- **Resultat:** `research/data/carry_realism/carry_realism.{json,md}`, sha256 `e36dbdaf69c5…`.
- **Gebyrkilder:** DK_RETAIL_P0. Kraken laveste niveau: spot 0,40 / 0,80 % (maker/taker), perps 0,02 / 0,05 %.
- **Status:** scenarier, ikke verificeret handelsadgang eller forventet profit. Ingen hedget position kaldes risikofri
  eller kapitalneutral.

## P0: hvad en carry-handel koster hos Kraken

Round trip er regnet som andel af perp-notionalen (spot ind + ud, perp ind + ud). Maker-fyld er kun et scenarie og
antages ikke.

| Scenarie | Round trip | Break-even 3 d | 14 d | 90 d | 180 d |
|---|---|---|---|---|---|
| Bøgernes Binance-model | 0,48 % | 58 % | 12,5 % | 1,95 % | 0,97 % |
| Kraken maker/taker (slip 0,02 %) | 1,35 % | 164 % | 35,2 % | 5,47 % | 2,74 % |
| Kraken taker/taker (slip 0,02 %) | 1,78 % | 217 % | 46,4 % | 7,22 % | 3,61 % |
| Kraken taker/taker (slip 0,10 %) | 2,10 % | 256 % | 54,8 % | 8,52 % | 4,26 % |

**Hovedfund:**
- Hos Kraken er en carry-handel cirka 3,7 gange så dyr som i bøgerne. Det skyldes næsten kun spotbenet: 0,80 % taker
  mod 0,10 %. Perp-benet er billigere end i bøgerne.
- Kortvarig carry (3-14 d) kræver 35-217 % p.a. funding og er dermed uinteressant.
- Ved 90 dage kræver den 5,5-8,5 % p.a. Ved 180 dage 2,7-4,3 %.

**Netto på allokeret kapital (1x):**
- Ved 10 % p.a. funding og taker/taker: −0,70 % efter 14 d, +0,34 % efter 90 d og +1,58 % efter 180 d på 10.000.
- Bøgernes model giver ved samme funding +0,99 % efter 90 d og +2,23 % efter 180 d.

**Kontiene genprissat** (egne fyld × Kraken-satser):
- 9 aktive carry-konti har bogført 62,16 i gebyrer. Kraken taker ville have kostet 264,25; Kraken maker 130,57.
- CARRY90-BTC: 10,00 bogført mod 42,53 med Kraken taker.

**Observeret funding:**
- Det er Binance' 8 t-afregning over 0,2-7,8 dage. Den varierer fra −23 % til +14 % p.a.
- Den er ikke Kraken's funding. Kraken's timeinterval er dokumenteret, men niveauet er UNKNOWN. Der er ikke omregnet
  noget fra timeafregning til forventet indtjening.

## P1: kapital og margin

**Ét carry-par** (5.000 pr. ben): spot er betalt fuldt på én enhed, og den korte perp har eget collateral på en anden
enhed. Close-out sker ved 50 % af initialmarginen (Finanstilsynet 2019).

| Gearing perp | Samlet allokeret | Stigning til close-out | P(BTC rører) 14 / 90 / 180 d | P(ETH rører) 14 / 90 / 180 d |
|---|---|---|---|---|
| 1x | 10.000 | 50 % | 0 / 10 / 25 % | 0 / 21 / 37 % |
| 2x (DK krypto-CFD) | 7.500 | 25 % | 2 / 37 / 53 % | 8 / 49 / 62 % |
| 5x | 6.000 | 10 % | 33 / 70 / 79 % | 45 / 77 / 83 % |
| 10x | 5.500 | 5 % | 62 / 84 / 89 % | 70 / 88 / 91 % |

Sandsynlighederne er beregnet under scenarieantagelser: BTC 50 % og ETH 65 % vol, driftløs GBM, refleksionsprincippet.

- **Spotgevinsten dækker ikke perp-marginen.** Den ligger på en anden enhed og dækker kun marginen efter en overførsel.
  En close-out efterlader en ubeskyttet lang spotposition, så "afdækket" holder kun, så længe der tilføres
  variationsmargin.
- **Kapitalbinding ved 90 d:**
  - 2x frigør kapital: 7.500 i stedet for 10.000, og afkastet på allokeret kapital stiger med 1/3. Men BTC har 37 %
    sandsynlighed for at nå close-out uden ny margin.
  - 1x er det eneste scenarie, hvor risikoen er lav over 90 d (10-21 %). Ved 1x er nævneren 10.000.

**Parbogen** (1.000 pr. ben, højst 72 t, hvert ben med egen margin; netting på tværs er UNKNOWN):
- Ved ≤ 2x er close-out-risikoen inden 72 t ≈ 0 for alle par.
- Ved 10x: 3 % (QQQ/SPY) til 41-69 % (ETH/BTC).
- Ved 20x: 28-100 %.
- Beta-ubalancen fra P3 (250-670 USDT) skal dækkes af margin.

## Svar på direktørens spørgsmål

Kan en fundingpræmie være økonomisk interessant med alle omkostninger, kapitalbinding og risici medregnet?

- **For Binance-bøgerne:** kun ved lang horisont (≥ 90 d) og en funding over 5,5-8,5 % p.a. *hos den venue, der handles
  på*.
- **For en dansk detailmodel:** det niveau er ikke verificeret. Kraken's fundingniveau, spreads og den gearing, en dansk
  detailkunde får, er UNKNOWN. Med 1x-kapital giver 10 % funding cirka +0,3 % på 90 d og +1,6 % på 180 d før skat.
- **Konklusion:** carry ser kun attraktiv ud under Binance' spotgebyr. Det er et negativt resultat for den danske model,
  ikke en anledning til at lede efter omveje.

## UNKNOWN

- Kraken's spreads og dybde.
- Kraken's fundingniveau (kun intervallet er dokumenteret).
- Om en dansk detailkunde får 2x eller 10x.
- Margin-netting på tværs af enheder og produkter.
- Sandsynligheden for maker-fyld.

CARRY90-GULD er kun med som regnskab: PAXG-spot kan ikke overføres (ESMA's ART-register er tomt). For parbogens lange
ben er faldet regnet symmetrisk, ln(1 + bevægelse); det undervurderer risikoen en smule.

## Præciseringer (ChatGPT kl. 02:20 lokal 11-06, indført uden ændring af tallene)

1. **Sandsynlighederne for at nå close-out er scenarier.** Tallene 10-77 % kommer fra antaget vol, en GBM-prisproces og
   den antagne margin. De er ikke sandsynligheder for faktisk likvidation og ikke observerede risici.
2. **To nævnere vises side om side.** Break-even-funding er regnet mod perp-notionalen. Investorens afkast afhænger af
   den samlede allokerede kapital (10.000 ved 1x, 7.500 ved 2x). Tabellen "netto på allokeret kapital" er den
   relevante for afkastet.
