# Event farm fremadrettet: tre kontekstfiltre (tillæg til udkast 100, UDKAST, IKKE LÅST)

Claude skrev tillægget 2026-11-12 kl. 13:55 lokal tid (12:55 UTC) efter direktørbeslutning 101 ("3 filtre GO til
design før protokollåsen, ingen aktivering").
- Kode: `research/tools/event_farm_filters.py`.
- Tests: `tests/test_event_farm_filters.py` (20 tests, kun syntetiske data).
- Tillægget hører til `EVENT_FARM_FORWARD_AMENDMENT_DRAFT_100.md`. Det ændrer ingen committet fil.

**Status:**
- G31_EVENT_FARM_FORWARD er stadig **CLOSED**.
- Ingen 5m-stream, ingen adapter, ingen aktivering, ingen lås, ingen alfa.
- Ingen påstand om en fordel.

**Rettelse af en dokumentationsfejl i udkast 100** (afsnit 9 punkt 3 og gate-udkastets `opens_by` / `source`): D5 er
**ANCHORED** (direktørbeslutning 97), ikke PENDING_INDEPENDENT_ANCHOR. G15_OWNER_SIGNATURE vurderes stadig særskilt.
Kravet om ejerens D5-underskrift på sha256 af den præcise ændringstekst består. De committede filer er ikke rettet.
Rettelsen står kun her.

## 1. Princip

De 12 baseline-varianter bevares uændret. Et filter kan kun **beholde eller fjerne** et baseline-setup og bruger motorens
egen indgang, stop, mål og udfald. Hvert filter er en ren funktion af den samme 5m-series `bars[:known_i + 1]`.
`context(bars)` beregner tre kausale serier i ét gennemløb, så værdien ved bar i kun afhænger af barer 0..i.

Testene viser:
- trunkering og ombyttet fremtid ændrer intet før snittet;
- `check_lookahead` giver PASS;
- for hvert setup og hver kombination giver filteret samme svar på `bars[:known_i + 1]` som på hele serien.

## 2. Definitioner, inputdata og kildeafhængigheder

**F1 TREND_1H (1t-trendstruktur).**
- **1t-barer:**
  - en fuld UTC-time består af 12 på hinanden følgende 5m-barer: o = første, h = max, l = min, c = sidste;
  - mangler en 5m-bar, er timen ugyldig og bruges aldrig. Der er ingen ufuldstændige HTF-barer;
  - en 1t-bar findes først fra lukningen af dens 12. 5m-bar.
- **1t-swings:** fraktal med k1 = 2 med samme regel som motoren: h[j] > de k1 høje før og ≥ de k1 høje efter, lave
  spejlet. En swing kendes, når 1t-bar j + k1 er lukket.
- **Trend:**
  - +1, når de to seneste bekræftede swing-toppe OG de to seneste swing-bunde hver er strengt højere;
  - −1, når begge er lavere;
  - ellers 0.
- **Regel:** long passerer kun ved +1, short kun ved −1.
- **Input:** 5m OHLC fra samme kilde. Ingen anden kilde.
- **Opvarmning:** der skal være mindst to swings af hver slags, typisk mange timer. Før det er trenden 0, og intet
  passerer.

**F2 PDL_RETEST (gårsdagens high/low, breakout med retest).**
- **Niveauer:**
  - dag D = UTC-datoen for setuppets kendte bar;
  - PDH og PDL = max high og min low af dag D−1's 5m-barer;
  - de bruges kun, hvis D−1 har ≥ 95 % af sine 288 barer. Ellers findes intet niveau, og intet passerer.
- **Long:** tilstandsmaskine over dag D's barer op til known_i (k = position i døgnet):
  - **breakout:** et luk > PDH (bar b);
  - **retest:** en senere bar r med b < r ≤ b + 12, hvor low ≤ PDH, uden noget luk < PDH siden b. Breakout-baren
    tæller ikke som retest;
  - **annullering:** et luk < PDH annullerer breakout og retest;
  - **spent:** ingen berøring inden b + 12 gør breakouten "spent", indtil et luk < PDH nulstiller den.
- **Setup:** long passerer, når en retestet breakout er i kraft ved known_i (intet luk < PDH siden b) og indgangen er
  ≥ PDH.
- **Short:** spejlet med PDL.
- **Input:** 5m OHLC for dag D−1 og D.
- **Opvarmning:** første brugbare dag er dag 2 efter start, og kun hvis dag 1 har ≥ 95 % dækning.

**F3 VWAP_STRETCH (sessionsankret VWAP og afstand i ATR).**
- **VWAP:** ankeret er 00:00 UTC (parameter `vwap_anchor`, fastsat nu; én session pr. døgn). VWAP_i = Σ(tp·v) / Σv over
  sessionens barer til og med i, med tp = (h + l + c) / 3.
- **Stretch:** dir · (VWAP − close_i) / ATR, hvor ATR = motorens ATR ved known_i (setuppets `atr`).
- **Regel:** setuppet passerer ved stretch ≥ 1,0. En long skal ligge mindst 1 ATR under VWAP ("discount"), en short
  mindst 1 ATR over ("premium").
- **Volumen er påkrævet:**
  - mangler en 5m-bar i sessionen, begynder sessionen ikke ved ankeret, eller har en bar manglende, NaN- eller
    nulvolumen, er VWAP **INCOMPLETE** fra den bar til sessionens slutning;
  - F3 er **BLOCKED** i den periode (intet passerer). Der bruges aldrig en upræcis erstatning;
  - næste session begynder forfra. Det er testet.
- **Input:** 5m OHLC og volumen. fapi-klines har volumenkolonnen. Kildeadapteren skal levere den uændret pr. bar.
  Leverer kilden ikke volumen pr. 5m-bar, er F3 blokeret.

**Kombinationer:** alle ikke-tomme delmængder af {F1, F2, F3}, dvs. 7 kombinationer (F1, F2, F3, F1+F2, F1+F3, F2+F3,
F1+F2+F3). Et setup skal bestå alle filtre i kombinationen.

## 3. Tærskler, valgt nu uden data

| parameter | værdi | begrundelse |
|---|---|---|
| k1 (1t-fraktal) | 2 | den klassiske 5-bars fraktal, samme regel som motorens swings; bekræftelse efter 2 timer |
| trenddefinition | to højere toppe og to højere bunde | Dow-definitionen af en optrend; strengt, så lige niveauer ikke tæller |
| PD-dækning | 95 % | samme dækningsgrænse som den fremadrettede bogs pause (udkast 100 afsnit 3 punkt 5) |
| retest-vindue | 12 barer (1 t) | lig motorens `fill_window` (12), så retest og indgang har samme tidsskala |
| VWAP-anker | 00:00 UTC | samme døgngrænse som PDH/PDL og bogens dagsopgørelse; én session, så der ikke opstår flere varianter |
| stretch | 1,0 ATR | én typisk 5m-range; samme enhed som motorens `rej_min_atr` (1,0); rundt tal |

**Ingen tærskel ændres efter resultater.** Giver et filter nul setups eller negativt netto, rapporteres det sådan. Det
er et gyldigt negativt udfald, ikke en grund til at ændre reglen.

## 4. Varianttal og N

| | tests |
|---|---:|
| baseline (12 varianter) | 12 |
| 7 filterkombinationer × 12 varianter | 84 |
| **fremadrettet familie i alt** | **96** |

Reference-N = 19.753 (registret 19.438 + 315 event farm-tests) + 96 = **19.849**. Den afløser de 19.765 i udkast 100,
som kun talte de 12 baseline-tests.

`event_farm_filters.v2_filter_records(start, slut)` giver 7 FUTURE-poster i kode, én pr. kombination med 12 varianter
hver. Universet er 96, og `reference_n` er 19.849. Posterne er validerede og ikke persisteret. De 12 baseline-poster
fra udkast 100 gælder fortsat, men skal læses med N = 19.849.

## 5. Null med filtre (seed 83, uændret null)

`python3 research/tools/event_farm_filters.py` bruger nullens egne barer (`event_farm.random_walk_bars`, seed 83, 3 ×
60 dage, 5m), samme motor og samme 12 varianter. Baseline giver præcis nullens tal: 5.429 handler og −0,0195 R
brutto.

Puljet over de 12 varianter pr. kombination:

| | setups pr. instr.-dag (snit af varianter) | handler | R brutto | netto @1 bps | netto @8 bps | netto @28 bps |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 3,62 | 5.429 | −0,020 | −0,049 | −0,260 | −0,86 |
| F1 | 1,11 | 1.674 | −0,052 | −0,083 | −0,296 | −0,91 |
| F2 | 0,22 | 358 | −0,055 | −0,085 | −0,295 | −0,89 |
| F3 | 0,93 | 1.442 | −0,047 | −0,082 | −0,328 | −1,03 |
| F1+F2 | 0,15 | 242 | −0,087 | −0,117 | −0,328 | −0,93 |
| F1+F3 | 0,15 | 244 | −0,178 | −0,219 | −0,509 | −1,34 |
| F2+F3 | 0,01 | 6 | +1,61 | +1,59 | +1,47 | +1,10 |
| F1+F2+F3 | 0,00 | 0 | – | – | – | – |

**Læsning:**
- I støj tjener ingen kombination noget. Filtrene fjerner setups, men gør ikke resultatet bedre.
- F2+F3's plus er én enkelt handel, der går igen i 6 varianter. Det er netop de 6 tests ud af 78 med handler, der er
  positive ved 28 bps.
- Den største |t| blandt de 96 tests er −3,17 (F3/ob/rr2/mid, 19 handler). Med 96 tests opstår |t| > 3 i ren støj.
  Det er grunden til N = 19.849.
- **F2 og F3 udelukker næsten hinanden.** F2 kræver en long over gårsdagens high efter et breakout. F3 kræver en long
  mindst 1 ATR under dagens VWAP. Derfor er der næsten ingen setups i F2+F3 og ingen i F1+F2+F3. Kombinationerne er
  alligevel registreret og ændres ikke. Det er en egenskab ved de forudvalgte regler, og at rette den efter dette tal
  ville være tilpasning.

## 6. Omkostninger: 28 bps er en ANTAGELSE

**28 bps pr. rundtur er en antagelse, ikke verificerede fremtidige omkostninger.** Tallet er lab'ets papirbogsmodel
(`lab/lane.py`):
- taker 0,001, slippage 0,0002 og halv spread 0,0002 pr. fyld;
- alle fyld regnes som taker, også limit.

Virkelige gebyrer, spread og slippage for BTCUSDT/ETHUSDT 5m-handler er ikke målt i dette arbejde. Antagelsen og nullen
bevares uændret. Nettotallene ved 0/1/5/8 bps står ved siden af, så forskellen kan ses.

## 7. Hvad ikke ændres og ikke påstås

- `event_farm.py` (f686c9a), `event_farm_driver.py`, `event_farm_forward.py`, nullen og de 12 baseline-varianter er
  uændrede.
- Der er ingen påstand om en fordel. Fremadrettede rapporter efter 14, 28 og 90 dage er beskrivende, og to ugers
  observation er ingen dokumentation. En påstand kræver en ny, låst, bekræftende protokol med styrkeberegning ved
  N ≥ 19.849.
- Filtrene kan give negativt resultat (nul setups, negativt netto) uden regelændring, og det rapporteres.
- G31 er CLOSED. Der er ingen 5m-stream, ingen adapteraktivering, ingen lås og ingen aktivering.
- **Åbne punkter:**
  - `ForwardBook` anvender ikke filtrene i dag. Det kræver en ny bogversion eller en rapportlæser, der kalder
    `event_farm_filters.apply` på bogens barer, og den skal godkendes sammen med ændringen;
  - adapteren skal levere volumen pr. 5m-bar for F3.
