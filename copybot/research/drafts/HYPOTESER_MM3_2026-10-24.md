# Nye hypoteseudkast — master mission 3 (2026-10-24 kl. 23:2x)

**Status 2026-10-24 kl. 23:39:**
- K1 og K2 er nu protokolleret i PROTOCOL_V3 ændring 21y med to præciseringer: sessioner, afregnet funding, regler for
  brugbare timer, PASS/SCREEN_FAIL/UNTESTABLE og eksakt Wilcoxon.
- Status er `NO_DECISION`: 0 af 12 komplette weekender. Tidligste test er 2027-01-18.
- Ingen LÅS og intet alfa (mission 4).

Udkastets oprindelige tekst står nedenfor. Ingen af kandidaterne kan screenes nu:
- TradFi-perps fandtes ikke i explore0 (2020-03..2021-12);
- historiske hentninger er spærret til 2026-11-14;
- 2025+ læses aldrig.

Begge er derfor **fremadrettede**.

**Kontrol mod eksisterende arbejde (genopliver intet):**
- Weekend-TradFi-afkast, volumen, bog og gab: allerede planlagt i 21h punkt 4 (kun fremad, ≥ 12 weekender, egen lås).
  Ikke gentaget her.
- Spot–perp lead/lag for **samme** aktiv: m21i SCREEN_FAIL. Ikke gentaget.
- Bevægelse + nyhed: m21j SCREEN_FAIL. Ikke gentaget.
- 4σ-fald: DROPPED. Ikke gentaget.
- Hyperliquid–Binance-funding: ændring 13 (baner). Ikke gentaget.
- Notering og afnotering (SETTLING, Monitoring Tag): H5F/H5X/U1F/M1F er låst fremad. Ikke gentaget.

---

## K1 — BTC fører TradFi-perps uden for åbningstid (tværs af aktiver, kun lukket marked)

1. **Mekanisme:** når aktiemarkedet er lukket, prissætter Binance SPY- og QQQ-perpens indeks fra perpens egen bog
   (21g). Den eneste likvide risikoaktiv, der handles døgnet rundt, er krypto. Hvis perp-handlerne bruger BTC som
   risikoproxy, følger SPY/QQQ-perpen BTC med forsinkelse, når den ikke har sin egen prisopdagelse.
2. **Observerbar forudsigelse:** i lukkede timer er korrelationen mellem BTC's afkast i time t og SPY/QQQ-perpens
   afkast i time t+1 positiv og større end i åbne timer. Placebo (t−1) er ≈ 0.
3. **Falsifikation:** korrelationen ved t+1 i lukkede timer er ≤ den i åbne timer, eller ≤ placebo-korrelationen
   (t−1 eller tilfældigt forskudt), eller ikke signifikant efter klynger pr. weekend.
4. **Data:** scannerens timeobservationer (`abnormal_move/1`: `ret_1h`, `open_s`, sessionsmærke fra 21g) for BTCUSDT,
   SPYUSDT og QQQUSDT. Indsamles allerede hver time.
5. **Point-in-time:** kun lukkede timebarer, som de forelå ved scanningen (scan-ts > barens lukketid). Ingen genhentning
   bagud.
6. **Benchmark/placebo:**
   - samme korrelation i åbne timer;
   - forskydning t−1;
   - en tilfældig cirkulær forskydning (1 000 permutationer inden for hver weekend).
7. **Omkostninger:** en handel på signalet koster SPY/QQQ-perpens rundtur. Den er < 1 bp ved 5k i den første
   kapacitetskurve, plus 2 × 0,04 % TradFi-taker (21g). Kravet er reglen B (21i) uændret.
8. **Stikprøve:** ≥ 12 weekender (som 21h punkt 4), dvs. ca. 2026-01-16. Hver weekend er én klynge.
9. **Informationsværdi:** middel til høj. En ny mekanisme (prisopdagelse uden underliggende marked) i en ny
   instrumentklasse, og billig at måle, da data allerede indsamles.
10. **Tilladt næste skridt:** ingen måling før en dateret ændring fastlægger signal, vindue og test. Den skrives, når
    12 weekender er indsamlet. En LÅS (brugerens ja 22:43 / alpha k5) må først bruges, hvis screeningen består.

## K2 — Funding og præmie på TradFi-perps er større uden for åbningstid

1. **Mekanisme:** uden underliggende handel kan arbitrage ikke afdække perpen mod det underliggende. Præmien
   ((mark − indeks)/indeks) og dermed funding bliver en ren betaling for at bære risiko i lukkede timer.
2. **Observerbar forudsigelse:** median |præmie| og median |forudsagt funding| er højere i lukkede end i åbne timer.
   Præmiens fortegn ved weekendens slutning forudsiger ikke mandagens gab (ellers ville præmien være information,
   ikke risikobetaling).
3. **Falsifikation:** ingen forskel lukket/åben (klynget pr. weekend). Eller præmien ved weekendens slutning forudsiger
   gabet med korrekt fortegn; så er den information, og K2's mekanisme er forkert.
4. **Data:** `mark`, `index` (findes i scannerens payload) og `funding_rate` / `next_funding_ts` (fra 21x, indsamles fra
   2026-10-24).
5. **Point-in-time:** forudsagt funding som den stod ved scanningen. Afregnet funding læses aldrig bagud.
6. **Benchmark/placebo:** krypto-perps (BTC, ETH) i de samme timer. De har intet lukket underliggende, så forskellen
   bør være ≈ 0.
7. **Omkostninger:** beskrivende indtil videre. En carry-strategi på K2 skal klare reglen B over holdeperioden.
8. **Stikprøve:** ≥ 12 weekender (deler klynger med 21h punkt 4 og K1). Ingen test før.
9. **Informationsværdi:** middel. Den forklarer, om TradFi-perpenes præmie er risikobetaling (mulig carry) eller
   information (mulig retningsindikator).
10. **Tilladt næste skridt:** kun beskrivende indsamling, som kører. Test kræver en dateret ændring, og en LÅS kun ved
    bestået screening.

---

## Måling, ikke hypotese: omkostningsmodellen er konservativ på likvide mønter

Monitoren (21w, M2) viser realiseret slippage på 0,61–0,91 × den modellerede på de fremadrettede og skyggekonti
(likvide perps, 40–269 fills pr. konto). Det er **ikke** en fordel og ændrer ingen omkostningsregel. Enhver ændring af
kravet kræver en dateret ændring og brugerens ja. Det er dokumentation for, at papirresultaterne ikke er pyntet af en
for lav omkostningsmodel.

---

## K3 — prispres op til fundingafregning på mønter med ekstrem funding (UNTESTABLE i dag)

1. **Mekanisme:** ved meget høj positiv forudsagt funding lukker lange positioner lige før afregningen for at undgå
   betalingen. Prisen falder ind i afregningen og retter sig bagefter.
2. **Forudsigelse:** log-afkastet fra afregning − 30 min til afregning er negativt for de 10 mønter med højeste
   forudsagte funding og omvendt for laveste. Afkastet de næste 30 minutter efter afregning har modsat fortegn.
3. **Nul og baseline:** samme 30-minutters afkast i tilfældige halve timer for de samme mønter (matchet på klokkeslæt
   modulo 8 t), og i mønter med funding nær medianen.
4. **Forstyrrelser:** generel markedsbevægelse (træk BTC-afkastet fra) og listninger/afnoteringer (udeluk mønter med
   H5F/H5X/M1F-hændelse ±3 døgn).
5. **Data:** forudsagt funding findes for top-mønterne (`pricing_constraint/2`, minutvis). **Mangler:** priser med
   minutopløsning omkring afregningen. Scanneren har kun timebarer, og historiske minutdata er spærret til 2026-11-14
   (og 2025+ læses aldrig).
6. **Omkostninger:** to taker-ben pr. halv time på tynde mønter. Den første kapacitetskurve viser 5–245 bp rundtur ved
   5 000 USD, så effekten skal være stor.
7. **Stikprøve og test:** ≥ 60 afregninger fordelt på ≥ 20 døgn (klynger pr. døgn), Holm over 2 retninger, grænse
   0,005.
8. **Status:** `UNTESTABLE` indtil en fremadrettet minutindsamling omkring afregningerne er protokolleret og har kørt
   ≥ 20 døgn. Ingen indsamling er bygget endnu. Den kræver en dateret ændring, og den lægger ca. 3 × 10 GET-kald pr.
   afregning oven i den eksisterende belastning.
9. **Informationsværdi:** middel. Den er sandsynligvis spist af omkostningerne på tynde mønter. Prioriteret efter K1/K2.
