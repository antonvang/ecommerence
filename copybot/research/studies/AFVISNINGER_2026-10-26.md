# Afvisninger af nye papirbaner, likviditetsgatens første afgørelse og forslag til 500-niveaus-måling (2026-10-26)

Kun læsning af produktionens `lab.db` (2026-10-26 ca. 15:45 UTC). Alle tider UTC. Ingen regel, tærskel eller
kontostørrelse er ændret; intet er implementeret.

## 1. Likviditetsgatens første naturlige afgørelse (ændring 25) — og en rettelse

**Rettelse:** rapporterne fra 2026-10-26 13:43 UTC og frem (Mission 16, 17 og 18) sagde "0 afgørelser fra gaten" og
"VELODROME nåede ikke gaten". Det var forkert. Optællingen 13:20 UTC var korrekt (0), men afgørelsen kom 13:39:13 UTC;
den stod i outputtet 13:43 UTC med en afkortet payload og blev læst som en regel 19-afvisning. Senere rapporter
genbrugte det gamle tal. Først ca. 15:40 UTC blev den talt og læst korrekt.

| Felt | Værdi (fra hændelsen `lane.skipped` id 25352) |
|---|---|
| Instrument | VELODROMEUSDT (perp) + VELODROMEUSDT.SPOT, funktion `scanner_funding`, familie fcarry |
| Tid | 2026-10-26 13:39:13 UTC (scanningerne 13:38:50 og 13:37:49) |
| Bogalder | bøgerne hentet 13:39:13,66 (spot) og 13:39:13,95 (perp): under 1 s; indbyrdes skew 0,30 s (12h-grænse 5 s) |
| Størrelse | 5 000 USD pr. ben (qty 168 265) |
| Rundtur (bog, uden gebyrer) | perp 0,6218 % + spot 0,7383 % = 1,3601 % (levende 20-niveaus-vandring) |
| Kapacitetskurve | `absent` for begge ben (instrumentet er ikke i kurvens univers), så kun den levende vandring blev brugt |
| Grænse | 0,46 % |
| Afgørelse | AFVIST — "afvist af omkostninger" (data var tilstrækkelige: begge bøger kunne fylde 5 000 USD i 20 niveauer) |
| Tidligere regler | 19 bestået (spotpar findes); funding vedvarende (sidste 3: 0,005 %, 0,005 %, 0,0588 %); 12h bestået; 12g "kan fylde" bestået; 12g "funding dækker": forventet 3-dages funding 1,977 % ≥ omkostning 1,839 % (bog 1,360 % + gebyrer 0,40 % + tillæg 0,08 %) — **bestået** |

**Betydning (målt, ikke en profitpåstand):** uden ændring 25 ville banen være startet, fordi 12g's regnestykke gav
1,977 % > 1,839 %. Gaten stoppede den på bogomkostningen alene (1,36 % > 0,46 %), samme type tynd bog som
EPIC/MITO/HOT. Hvad banen ville have tjent eller tabt, er ukendt. Samme mønt 14:40:11 UTC: spot-buddene i 20 niveauer
var 4 240 USD, så 12g ("bogen for tynd") stoppede den før gaten.

## 2. Alle afvisninger af nye baner

| Regel / grund | Alt (fra 2026-10-19) | Siden gaten (2026-10-25 20:52 UTC) | Unikke mønter (alt) | Input |
|---|---|---|---|---|
| 19 intet spotpar på Binance | 996 | 190 | 78 | målt (børsens instrumentliste) |
| HTTP 400 ved spotbog (10-19 21:30 → 10-22 19:26) | 306 | 0 | 33 + 22 | manglende data: samme årsag som 19, før regel 19 kom 10-22 19:36 |
| 11b "would hold nothing now" (carry_hysteresis/floor, 10-22 → 10-23) | 505 | 0 | 1 | målt (variantens funktion på levende data) |
| Funding ikke vedvarende (sidste 3 / timegennemsnit) | 145 | 4 | 55 | målt (afregnet funding) |
| 16e afnotering annonceret | 26 | 0 | 2 | målt (Binance-meddelelser) |
| 12g bogen for tynd til størrelsen | 9 | 2 | 1 | målt bog (20 niveauer), censureret, aldrig 0 |
| 12g funding dækker ikke omkostningen | 2 | 1 | 1 | blandet: målt bog + antagne gebyrer/tillæg + målt forventet funding |
| 25 likviditetsgate | 1 | 1 | 1 | målt levende bog (20 niveauer); kurve fraværende |
| Øvrige (netværk, krydset bog, < 5 mønter med bog, Unicode-symbol) | 10 | 0 | – | manglende data |

Banestarter i alt: 14 (seneste 2026-10-22). **Flaskehals:** 96 % af afvisningerne siden gaten (190 af 198) er
mønter uden spotpar. Kun 3 kandidater i alt har nået 12g eller gaten, og alle var samme mønt.

## 3. Forslag (ikke bygget): ekstra måling med 500 niveauer ved afvisning for tynd bog

**Formål:** skelne "tynd i papirmotorens 20 niveauer" fra "tynd i hele bogen". Afgørelsen ændres aldrig af målingen.

- **Udløser:** en `lane.skipped` med 12g "bogen for tynd" eller gaten "bogen er for tynd til … USD".
- **Hentning:** de berørte bøger én gang med 500 niveauer (spot `/api/v3/depth?limit=500`, perp
  `/fapi/v1/depth?limit=500`), efter afvisningen er skrevet, i samme proces. Højst én måling pr. (instrument, time).
- **Data:** én `observations`-række pr. instrument, detektor `depth500/1`, metric `thin_probe`, med: hændelsens nøgle og
  id, `fetched_at` (vægur) og forskel til 20-niveaus-bogens `fetched_at`, Binance `lastUpdateId`, antal niveauer pr.
  side, mid, spread, dybde i USD inden for 20 og 500 niveauer, VWAP-afstand fra mid for størrelsen pr. side inden for
  20 og 500 niveauer, og `censored` pr. side (true, når 500 niveauer ikke kan fylde).
- **Censur:** kan 500 niveauer ikke fylde størrelsen, gemmes `null` og `censored: true`; aldrig 0, aldrig et estimat.
- **Omkostning:** to ekstra offentlige kald pr. afvisning (vægt ca. 25 spot + 10 perp af 6 000 / 2 400 pr. minut);
  ved højst få afvisninger pr. døgn er det ubetydeligt. Fejler kaldet, gemmes en fejlrække én gang pr. time, og
  afgørelsen står uændret.
- **Mærkning:** "måling, ikke en afgørelse; papirmotoren fylder kun inden for 20 niveauer".
- **Kræver:** en dateret ændring i PROTOCOL_V3 før kode, tests (afvisningen uændret; censur; ingen række ved andre
  afvisninger) og brugerens ja til deploy. Kontostørrelse og alle tærskler uændrede.

## 4. Hvad vi ved, hvad vi ikke ved, næste måling

- **Ved:** gaten har afgjort én sag naturligt og afvist den på målt bogomkostning (1,36 % mod 0,46 %) med under 1 s
  gamle bøger; uden gaten ville banen være startet efter 12g. Afvisningerne domineres af manglende spotpar.
- **Ved ikke:** hvordan gaten afgør kandidater med kapacitetskurve (`curve_status` var `absent`); om tynde bøger i 20
  niveauer også er tynde i hele bogen (kun ét øjebliksbillede, en time senere).
- **Næste måling:** flere naturlige gate-sager; den foreslåede 500-niveaus-måling, hvis brugeren godkender den.

## 5. Mission 20 (2026-10-26 ca. 16:00 UTC): reproduktion, rapporteringsveje, optælling

**VELODROMEUSDT's fulde række i dag (`lane.skipped`, `scanner_funding`, ca. hver time):** 09:30, 10:36, 11:37 funding
ikke vedvarende (sidste 3 afregnede −0,0748 %, 0,01 %, 0,01 %); 12:38 12g "3 dages forventet funding 1,8737 % dækker ikke
rundturen 2,0335 %"; **13:39 ændring 25 "bogens rundtur 1,3601 % > grænsen 0,46 %"**; 14:40 og 15:41 12g "bogen for
tynd". Reproduceret fra den gemte hændelse (id 25352): benene 0,6218 % + 0,7383 % = 1,3601 % = `round_trip`; grænse
0,0046; 1,3601 > 0,46 → afvist. Perp-benet er lig 12g's vandring; spot-benet afviger 0,0006 %-point, fordi gaten
regner mængden fra spot-mid og 12g fra perp-mid. 12g's omkostning 1,8395 % = vandringer 1,3595 % + gebyrer 0,40 % +
tillæg 0,08 %.

**Rapporteringsveje:** `/api/lanes` viser afgørelsen med hele årsagen og klassen "afvist af omkostninger" (`classify`
genkender "likviditetsgate (25): bogens rundtur"). Banekoden afkorter `reason` til 200 tegn (`f"{e!r}"[:200]`), men
gate-præfikset står først, og hele gate-detaljen ligger uafkortet i `trigger.liquidity`; der er ingen produktfejl.
Fejlen var Claudes egne ad hoc-forespørgsler (`substr` på payload). Forebyggelse: `research/tools/gate_decisions.py`
(read-only) lister alle gate-afgørelser med fuld årsag og tæller alle afvisningsregler; køres før enhver
"IKKE OBSERVERET".

**Optælling siden gaten (2026-10-25 20:52:25 UTC, `system.running`; tidligere fejlagtigt skrevet "21:53 UTC"), kl.
16:00 UTC:** 201 forsøg, 0 starter: 193 intet spotpar (41 forskellige mønter), 4 funding ikke vedvarende, 2 12g tynd
bog, 1 12g funding dækker ikke, 1 gate. Bekræftet med både værktøjet og ren SQL (`LIKE '%intet spotpar%'` = 193).

**Andre egnede kandidater i eksisterende data?** Nej, uden at ændre univers eller screening. Siden gaten er
VELODROMEUSDT den eneste kandidat fra scannerens funding-liste med spotpar; de 41 andre mangler spotpar og kan ikke
handles som spot–perp. Ingen kandidat er genåbnet.
