# NasDipEA – anbefalet bot (NAS100, dagscandles)

Efter test af 150+ strategiopsætninger på EURUSD (ingen holdt uden for udvælgelsesperioden)
og veldokumenterede dagsstrategier på 7 markeder er dette den eneste, der holdt:

**"Køb dykket" på NAS100 (IBS mean reversion)**
| Regel | |
|---|---|
| Køb | Dagen lukker over SMA200 (optrend) **og** tæt på dagens bund (IBS < 0,2) |
| Sælg | En dag lukker over den foregående dags high |
| Nødstop | 3 × ATR(14) under købskursen |
| Størrelse | Kursværdi = kontoen (1x). Med 200 USD købes for ca. 200 USD NAS100. |
| Kun køb | Ingen short. Maks. én position. |

Parametrene er den offentliggjorte standard (IBS < 0,2, SMA200) og er **ikke tunet** på data.

## Resultat (Dukascopy-data 2012–2026, med spread og finansiering)
| | NasDipEA | Køb og behold NAS100 |
|---|---|---|
| Afkast pr. år | ca. **8 %** | ca. 18 % |
| Største fald | **15 %** | 36 % |
| Handler pr. år | ca. 25 (76 % vindere) | – |
| Tabsår | 3 af 15 | – |
| Tid i markedet | 29 % | 100 % |
| 2026 til og med august | +8,9 % | |

200 USD fra 2013 ville være blevet til ca. 600 USD. Det er historik og ingen garanti.

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
