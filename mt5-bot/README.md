# TrendPullbackEA – automatisk bot til MetaTrader 5 (Vantage)

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

## 1. Installation (5 minutter)

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
