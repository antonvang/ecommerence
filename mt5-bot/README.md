# Test på Vantage NAS100 5-minutters data (sep. 2023 – sep. 2026)

| Strategi | Handler | Win % | PF | Afkast/år (1x) | Kommentar |
|---|---|---|---|---|---|
| ICT London-sweep | 623 | 26 | 1,12 | +2,2 % | Plus 2023–25, nul i 2026. PF 1,06–1,10 ved højere spread. Ikke statistisk sikker. |
| ICT sweep + FVG | 245 | 46 | 0,93 | −1,0 % | Taber |
| ICT silver bullet | 712 | 36 | 0,98 | −1,2 % | Taber |
| Kontrol: breakout | 733 | 42 | 1,00 | −0,7 % | Nul |
| NasDayEA (intradag-momentum) | 744 | 51 | 1,00 | −0,1 % | Nul på Vantage-data |

Konklusion: ingen daytrading-regel har en klar fordel efter omkostninger. NasDipEA (flere dage) er stadig anbefalingen.

---

# NasDayEA – daytrading (NAS100, H1)

Én handel hver handelsdag, ingen positioner natten over.
| Regel | |
|---|---|
| Kl. 15:00 New York (22:00 server) | Er NAS100 steget siden gårsdagens luk, købes der. Er det faldet, sælges der short. |
| Kl. 15:55 New York (22:55 server) | Alt lukkes |
| Nødstop | 1 % fra indgang |
| Størrelse | `InpExposure` × kontoen (1.0 = ingen gearing, maks. 10) |

Bygger på "Market intraday momentum" (Gao, Han, Li & Zhou, Journal of Financial Economics 2018).

**Test (Dukascopy H1, med spread):** NAS100 2019–2021 og US500 2019–2023 gav profit factor ca. 1,08,
ca. 50 % vindere og ca. 2,5 % om året ved 1x. Største fald var ca. 18 %, og der var tabsår (2019, 2021 på US500).
Det er et svagt og usikkert plus, og det er dårligere dokumenteret end NasDipEA. Start på demo.
Gearing forstærker både gevinst og tab: ved 10x ville det største fald i testen have tømt kontoen.

Installation: dobbeltklik `START_DAYTRADE.bat` (eller kør `install-and-backtest.ps1 -Expert NasDayEA -Symbol NAS100 -Period H1 -Years 5`).

---

# NasDipEA – anbefalet bot (NAS100, dagscandles)

Efter test af 150+ strategiopsætninger på EURUSD (ingen holdt uden for udvælgelsesperioden)
og veldokumenterede dagsstrategier på 7 markeder er "køb dykket i en optrend" på aktieindeks det eneste,
der holdt stabilt.

**Standard: Connors RSI(2)**, som tjente penge på alle 4 testede indeks (NAS100, US500, Dow, DAX)
| Regel | |
|---|---|
| Køb | Dagen lukker over SMA200 (optrend) **og** RSI(2) < 10 (kort, skarpt dyk) |
| Sælg | Dagen lukker over SMA5 |
| Nødstop | 3 × ATR(14) under købskursen |
| Størrelse | Kursværdi = kontoen (1x). Med 200 USD købes for ca. 200 USD NAS100. |
| Kun køb | Ingen short. Maks. én position. |

Parametrene er Connors & Alvarez' offentliggjorte standard fra 2008 og er **ikke tunet** på data.
IBS-varianten kan vælges med `InpMode`, men den virkede kun på NAS100 og ikke på US500, Dow eller DAX.

## Resultat (Dukascopy-data 2012–aug. 2026, med spread og finansiering)
| | RSI(2) på NAS100 | Køb og behold NAS100 |
|---|---|---|
| Profit factor | **1,85** (US500: 1,85) | – |
| Afkast pr. år (1x) | ca. **4,7 %** | ca. 18 % |
| Største fald | ca. 19 % | 36 % |
| Handler pr. år | ca. 10 (72 % vindere, holdes ca. 4 dage) | – |
| Tabsår | 3 af 15 (2016, 2018, knap 2012) | – |
| Tid i markedet | 11 % | 100 % |
| 2026 til og med august | +7,3 % | |
| Med dobbelt spread og 9 % rente | PF 1,73 | |

200 USD fra 2013 ville være blevet til ca. 375 USD. Det er historik og ingen garanti.

## Installation, compile og backtest i ét script
Luk MT5, og kør i mappen `mt5-bot`:
```powershell
powershell -ExecutionPolicy Bypass -File .\install-and-backtest.ps1 -Expert NasDipEA -Symbol NAS100 -Period D1 -Years 10
```
Hvis Vantage kalder symbolet noget andet (fx `NAS100.r` eller `USTEC`), så brug det navn i `-Symbol`.

## Kør den
1. Åbn en **NAS100 D1**-graf, og træk `NasDipEA` ind på den.
2. Slå **Algo Trading** til. Botten handler én gang om dagen, når en ny dagscandle starter.
3. Kør den på en **demokonto** i 2–4 uger først, og sammenlign med backtesten.

---

# Ældre: TrendPullbackEA (anbefales ikke)

Testen viste, at denne strategi taber penge (PF ca. 0,6–0,9). Den er kun beholdt til sammenligning.


Botten handler helt automatisk, når den er lagt på en graf i MT5. Du skal kun installere den én gang.

## Sådan virker den

| Del | Regel |
|---|---|
| Trend | Pris og EMA 50 over EMA 200 = kun køb. Under = kun salg. |
| Indgang | RSI dykker under 40 i optrend og krydser op igen (salg: over 60 og ned igen) |
| Stop-loss | 1,5 × ATR |
| Take-profit | 3 × ATR (gevinst er 2 × risiko) |
| Risiko | 1 % af kontoen pr. handel (2 USD på 200 USD). Lotstørrelsen udregnes automatisk. |
| Breakeven | Når handlen er +1R, flyttes stop-loss til indgangsprisen |
| Nødbremse | −5 % på en dag, så lukkes alt, og botten holder pause til næste dag |
| Filtre | Maks. én handel ad gangen, ingen handel ved høj spread, i weekenden eller fredag aften |

**Anbefalet marked: EURUSD på H1.** Guld (XAUUSD) svinger så meget, at selv 0,01 lot risikerer mere end 1 % af 200 USD. Botten springer derfor selv de handler over.

## Hurtigste vej: ét script

Luk MT5, læg `TrendPullbackEA.mq5` og `install-and-backtest.ps1` i samme mappe, og kør i PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-and-backtest.ps1
```

Scriptet finder din Vantage MT5, installerer og compiler botten, kører en 3-års backtest på EURUSD H1 med 200 USD og åbner rapporten. Hvis dit symbol hedder noget andet, fx `EURUSD+`, så tilføj `-Symbol "EURUSD+"`.

## 1. Installation manuelt (5 minutter)

1. Hent `TrendPullbackEA.mq5`.
2. I MT5: **Filer → Åbn datamappe** → gå til `MQL5\Experts` → læg filen der.
3. Tryk **F4** (MetaEditor), åbn filen og tryk **F7** (Compile). Der skal stå `0 errors`.
4. Tilbage i MT5: højreklik på **Expert Advisors** i Navigator → **Opdater**.

## 2. Backtest – år af data på få minutter (dag 1)

1. Tryk **Ctrl+R** (Strategy Tester).
2. Expert: `TrendPullbackEA`, Symbol: `EURUSD`, Periode: `H1`.
3. Dato: de sidste **3 år**. Model: **Every tick based on real ticks**.
4. Indskud: `200` USD. Gearing: den samme som på din konto.
5. Tryk **Start**, og se fanerne **Backtest** og **Graph**.

**Kør kun videre, hvis:**
- Profit factor er over **1,2**
- Max drawdown er under **20 %**
- Der er mindst **50 handler** (færre er for lidt at bedømme ud fra)

Hvis tallene er dårlige, så send mig rapporten, så justerer vi. Pres ikke parametrene, til backtesten ser perfekt ud. Det virker ikke på fremtiden.

## 3. Demo i en uge (dag 2–7)

1. **Filer → Åbn konto** → opret en Vantage-**demo** med 200 USD.
2. Åbn en EURUSD H1-graf og træk `TrendPullbackEA` ind på den.
3. Sæt flueben i **Allow Algo Trading**, og slå knappen **Algo Trading** til i værktøjslinjen, så den bliver grøn.
4. Øverst til venstre på grafen viser botten sin status.

Botten handler kun, mens din PC og MT5 kører. Hvis den skal køre døgnet rundt, så brug en VPS: MT5 har en indbygget, eller spørg Vantage.

## 4. Live

Først når demoen ligner backtesten, skifter du til din rigtige konto og gør det samme. Behold **1 % risiko**.

## Ærlig forventning

Botten er bygget til at **overleve**, ikke til at fordoble kontoen på en uge. Med 1 % risiko og ca. 2–6 handler om ugen er et godt resultat et par procent om måneden. Det kan også blive minus. Hvis du skruer risikoen op for at få hurtigere penge, går kontoen hurtigere i nul. Handl kun for penge, du kan tåle at miste.
