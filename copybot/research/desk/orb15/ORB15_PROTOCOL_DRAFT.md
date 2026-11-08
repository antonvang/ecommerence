# ORB15_PROTOCOL_DRAFT: lab-hypotese ORB15-QQQ (direktørordre 57 P1/P3, udkast 2026-11-09)

**Status:**
- DRAFT. Ikke låst, ikke godkendt.
- DATA COLLECTION BLOCKED. LIVE TRADING NO-GO.

**Dette er IKKE en reproduktion af videoen.** Videoens præcise strategi er NOT_REPLICABLE_FROM_VIDEO
(ORB15_VIDEO_RULE_AUDIT.md). Herunder er en selvstændig, fuldt specificeret ORB-15-hypotese. Den bygger på litteraturens
breakout-form (Zarattini, Barbon & Aziz 2024, 15-min-varianten) og ikke på videoens udfyldte huller.

## 1. Hypotese

H1: På Binance USD-M **QQQUSDT** giver en 15-minutters opening-range-breakout fra NYSE-åbningen et positivt
gennemsnitligt **nettoafkast pr. handelsdag** efter gebyrer, slippage og funding.

H0: gennemsnittet er ≤ 0.

## 2. Regler (alle fastsat før data)

| Punkt | Regel |
|---|---|
| Marked | QQQUSDT (TRADIFI_PERPETUAL, onboardet 2026-04-06 13:30 UTC, kilde: lokalt exchangeInfo-snapshot 2026-11-01). Ikke NQ, ikke QQQ: ingen tilladt vært for dem |
| Data | 1m-klines (sidste pris) fra `fapi.binance.com`, kun GET. Kun fremadrettet: al historik fra 2026 er reserveret. Indekspris-klines kun som sekundær, hvis de findes for TradFi (UNVERIFIED) |
| Kalender | NYSE-handelsdage efter `lab/sessions.py` (helligdage fra 2026-11-26; listen er en antagelse og verificeres før lås). Halve dage: lukketid 13:00 ET. Weekender og helligdage: ingen session |
| Tidszone | America/New_York med US-sommertid. 09:30 ET = 14:30 UTC om vinteren og 13:30 UTC om sommeren |
| Range | high H og low L af de 15 1m-lys 09:30:00–09:44:59 ET. Mangler et af de 15 lys, er dagen NO_RANGE (tæller som 0 og rapporteres) |
| Signal | Første 1m-lys efter 09:45 ET, hvis high ≥ H (long), eller hvis low ≤ L (short). Rammer samme lys begge, er dagen AMBIGUOUS og tæller som et fuldt stop-tab (konservativt) |
| Indgang | Stop-ordre: long ved max(H, lysets åbning), short ved min(L, lysets åbning). Et gab gennem niveauet fyldes til åbningen |
| Stop | Modsat side af range'et (L for long, H for short). Rammes stoppet i samme lys som indgangen, tæller det som et stop |
| Target | Intet. Exit ved lukning (15:59-lyset; på halve dage 12:59) |
| Maks signaler | 1 pr. session. Ingen genindgang |
| Størrelse | 1 enhed notional uden gearing. Afkast i bp af notional |
| Ikke-eksekverbart | Bryder et fill PERCENT_PRICE ±3 % eller min. notional, er dagen NOT_EXECUTABLE og tæller 0 minus intet gebyr. Andelen rapporteres |
| Omkostninger (primær) | Taker 4 bp pr. side (TradFi-kampagnen, PROTOCOL_V3 21g) + slippage 1 bp pr. side + faktisk funding, hvis positionen krydser 16:00 UTC (hentes fra den eksisterende fundingRate-linje) |

**Følsomhed (DIAGNOSTIC_ONLY, ændrer aldrig afgørelsen):**
- taker 5 bp (uden kampagne);
- slippage 0/3 bp;
- brutto på indekspris, dvs. den del, der kan overføres til NQ.

## 3. Endepunkter og afgørelse

- **Primært endepunkt:** gennemsnitligt nettoafkast pr. **handelsdag**. Dage uden signal tæller 0 og bevares.
  Observationsenheden er dagen; minutlys er ikke uafhængige observationer.
- **Interval:**
  - 95 % HAC Newey-West på dagsserien med L = floor(4·(T/100)^(2/9)) (lab'ets standard);
  - én-sidet p rapporteres;
  - multiplicitet: én primær test.
- **Sammenligning (sekundær):**
  - QQQUSDT købe-og-holde i samme tidsrum 09:45–16:00, net af samme gebyrer;
  - bruttoresultat i R-enheder for at kunne sammenligne med Krueger 0,131R brutto / 0,002R netto på NQ.

| Klasse | Betingelse |
|---|---|
| INSUFFICIENT_DATA | færre end 120 sessioner med range, eller over 10 % NO_RANGE |
| FALSIFIED_UNDER_TESTED_CONDITIONS | øvre 95 %-grænse ≤ 0 |
| PRELIMINARY_POSITIVE | nedre 95 %-grænse > 0 **og** positiv i begge halvdele **og** positiv uden de 3 bedste dage. Aldrig VALIDATED_ALPHA |
| INCONCLUSIVE | alt andet |

**Faste regler:**
- Ingen optimering af range-længde, stop, target eller sessionstid.
- Ingen tidlig stop.
- Sekundære varianter (5 min, 08:00 ET som i videoen, BTC/ETH) er **separate hypoteser** og kræver hver deres lås.

## 4. Tidsplan (kun efter godkendelse)

- **Tidligste lås:** 2026-11-14. Kræver ejer-godkendelse af den nye datalinje (1m QQQUSDT på en tilladt vært) og en
  ophævelse af ordre 57's indsamlingsblok.
- **Første observation:** første NYSE-session efter lås og deploy, tidligst mandag 2026-11-16.
- **Opgørelse:**
  - beskrivende pr. 20 sessioner;
  - afgørelse tidligst efter 120 sessioner, cirka 2027-05;
  - styrken er lav (ORB15_POWER_AND_COSTS.md).
