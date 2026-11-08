# POWER_AND_FEASIBILITY: fomo 30 s-kopi (direktørordre 56, 2026-11-08)

Alt her er syntetisk. Der bruges ingen markedsdata. Tallene kan genskabes med `python3 research/desk/fomo/power.py`
(stdlib, seed 56, 2.000 gentagelser pr. celle, cirka 1,5 min).

## 1. Hvorfor TP 10× gør det til et spørgsmål om ramningsrate

Med TP 10×, intet stop-loss og et tidsstop har hver handel to slags udfald:
- TP fyldes: netto cirka **+850 %**. Det er 10× minus 2 % gebyr pr. side og netværksgebyr på 0,25 SOL. Gevinsten er
  loftet her.
- Alt andet (tidsstop, rug, død pulje): et gennemsnit L mellem −100 % og 0. Lab'ets graduation-data gav en median på
  −95 % efter 60 min.

Gennemsnittet er p·8,5 + (1−p)·L, hvor p er følgerens TP-ramningsrate. Det giver break-even-raten p\* = −L/(8,5−L):

| L (ikke-TP-gennemsnit) | Break-even TP-rate p\* |
|---|---|
| −40 % | 4,5 % |
| −60 % | 6,6 % |
| −80 % | 8,6 % |

Påstanden holder altså kun, hvis mindst cirka 1 ud af 15 kopier når 10× **efter** 30 s og fills. I videoen er det én
udvalgt handel.

## 2. Styrke (sandsynlighed for hver klasse ved n signaler)

Spredningen pr. handel er stor (sd 1,0–3,0, dvs. 100–300 %). Spredningen for ikke-TP-udfald er sat til 40 %. Tabellen
viser L = −60 %, og MC er Monte Carlo med normalinterval:

| TP-rate p | Middel | n = 70: P(FALSIFIED) / P(POSITIVE) | n = 140 | n = 300 |
|---|---|---|---|---|
| 1 % | −51 % | 0,85 / 0,00 | 0,99 / 0,00 | 1,00 / 0,00 |
| 3 % | −33 % | 0,39 / 0,00 | 0,59 / 0,00 | 0,84 / 0,00 |
| 5 % | −15 % | 0,15 / 0,00 | 0,16 / 0,00 | 0,24 / 0,00 |
| 8 % | +13 % | 0,03 / 0,04 | 0,01 / 0,06 | 0,00 / 0,16 |
| 12 % | +49 % | 0,00 / 0,25 | 0,00 / 0,54 | 0,00 / 0,91 |

Ved L = −40 % og L = −80 % er billedet det samme, blot forskudt:
- Ved n = 140 og p = 3 % er P(FALSIFIED) 0,25 (L −40 %) og 0,84 (L −80 %).
- Ved n = 140 og p = 12 % er P(POSITIVE) 0,86 (L −40 %) og 0,27 (L −80 %).

Hele tabellen genereres af scriptet.

**Det betyder:**
- Er kopien klart tabsgivende (p ≤ 3 %, L ≤ −60 %), falsificerer 7 dage med cirka 140 signaler den med sandsynlighed
  0,6–1,0.
- Tæt på break-even (p 5–8 %) ender 7 dage næsten altid som INCONCLUSIVE. Det er en ægte grænse, ikke en designfejl.
- Et positivt fund kræver en meget høj TP-rate (≥ 12 %) og n ≥ 140. Selv da er det kun PRELIMINARY_POSITIVE.
- Normaltilnærmelsen og MC er uenige ved små p, fordi fordelingen er skæv. Den endelige analyse bruger
  klyngebootstrap (protokollen afsnit 6).

## 3. Forventet antal observationer på 7 dage

| Kilde til rate | Rate | 20 ledere × 7 d |
|---|---|---|
| L01 (8 kolscan-KOL'er, 14 d, filter ≥ $20k likviditet): 114 kopier | ≈ 1,0 pr. leder pr. dag | ≈ 140 |
| Uden likviditetsfilter (protokollen har intet) | højere, UKENDT | 140–300 (skøn) |
| L02's selvfundne tradere: 100–850 coins pr. uge | 14–120 pr. leder pr. dag | ikke brugbart: botagtige, udelukket af filteret |
| Videoens 4 ledere ("1 copy tonight") | ≈ 1 pr. dag i alt? | **≈ 7–28 → INSUFFICIENT_DATA** |

- Et centralt skøn er **n ≈ 140 (interval 70–300)** med 20 ledere.
- Klynger på mint, når flere ledere køber samme coin, sænker det effektive n. Det gør falsifikation lidt sværere.

## 4. Gennemførlighed

| Krav | Status |
|---|---|
| Lederhandler, puljereserver og priser on-chain, fremadrettet | Teknisk muligt med offentlig Solana-RPC eller PublicNode uden nøgle (DATA_SOURCE_APPROVAL_MATRIX.md) |
| Værter på tilladt liste | **Nej.** Ingen Solana-vært står i `ALLOWED_HOSTS`. Det kræver ejer-ja og en dateret PROTOCOL_V3-ændring |
| HTTP-metode | **Konflikt:** Solana JSON-RPC er POST med body, mens lab'ets sikkerhedstest kun tillader GET. Indtil ejeren beslutter, gælder den strengeste regel: ingen Solana-data |
| Ny collector/stream | Kræver godkendelse (ordre 54/55: ingen nye streams uden godkendelse) |
| Kapacitet | L01-erfaringen: 1 kald/s på den offentlige RPC, cirka 1.000 spam-tx pr. dag pr. wallet. 20 ledere i realtid kræver filtrering pr. signatur. Det er muligt ved 1–2 kald/s, men ikke verificeret |
| DNS | Det lokale filter blokerer i øjeblikket flere værter. Tilgængeligheden af Solana-værter er ukendt og testes ikke |
| Lederkilde | kolscan-billede gemt af ejeren og committet med hash, eller on-chain-kriterier |
| Simulator | Syntetisk testet (SYNTHETIC_EXECUTION_TESTS.md) |

**Konklusion:**
- Forsøget har god styrke til at falsificere en klart tabsgivende kopi.
- Det har dårlig styrke nær break-even, og det kan aldrig validere.
- Med lab'ets tidligere resultater (−15 %/handel ved 10 s, −18,8 % ved 10 s for selvfundne tradere) er det mest
  sandsynlige udfald FALSIFIED_UNDER_TESTED_CONDITIONS.
