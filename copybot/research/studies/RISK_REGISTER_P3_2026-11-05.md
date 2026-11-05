# P3: risikoregister for short- og proxy-positioner (direktørordre 44; kl. 21:45 lokal 11-05)

Beskrivende; ingen ny handel, ingen regelændring. Data: bevægelses-scannerens gemte timeafkast (`abnormal_move/1`,
`z_1h`-rækkernes `ret_1h`, 2026-10-24 11:00 → nu, 273-277 timer pr. marked; fremadrettet indsamlet, ingen historisk
forespørgsel). β = cov(A, B) / var(B) af timeafkast; timerne er afhængige, så tallene er beskrivende, ikke estimater
med kendt usikkerhed. **UNKNOWN betyder ukendt, ikke nul.**

## 1. Parbogen (ændring 43: 1.000 USDT pr. ben, β = 1 fast)

| Par | n timer | β | korrelation | vol-forhold | Netto markedseksponering ved 1:1 (≈ (β − 1) × 1.000) | Vurdering |
|---|---|---|---|---|---|---|
| BZ/CL (Brent/WTI) | 275 | 1,01 | 0,96 | 1,06 | ≈ 10 USDT | tæt på neutral i perioden |
| ETH/BTC | 273 | 1,25 | 0,92 | 1,35 | ≈ 250 USDT krypto-beta | **ikke neutral** |
| QQQ/SPY | 275 | 1,54 | 0,94 | 1,64 | ≈ 540 USDT aktie-beta | **ikke neutral** (den åbne position: lang QQQ / kort SPY = netto lang aktier) |
| XAG/XAU | 274 | 1,67 | 0,88 | 1,90 | ≈ 670 USDT metal-beta | **ikke neutral** |

- Ved β ≠ 1 driver markedet selve log-spreadet; z-signalet i tre af fire par er delvis et retningsvæddemål på markedet,
  ikke kun en tilbagevenden. En z-score beviser hverken kointegration eller mean reversion (ChatGPT, P3).
- Øvrige risici pr. par: **korrelationsbrud** (Brent/WTI ved lager- og fragtchok; sølv ved industriefterspørgsel);
  **funding-forskel** mellem benene (begge bogføres; størrelse UNKNOWN indtil afregninger foreligger); **weekend og lukket
  underliggende** for TradFi-perps (perpen handles 24/7, de underliggende futures/ETF'er ikke: huller ved åbning);
  **likviditetsasymmetri** (TradFi-bøger er tyndere end BTC/ETH; 43a stopper indgang uden fuldt fyld, men en **udgang**
  kan stadig fyldes delvist: resteksponering UNKNOWN); **lot-afrunding** giver op til ca. 1 % forskel i notional mellem
  benene (QQQ 1,53 × 652,6 = 998,5 mod SPY 1,35 × 736,3 = 994,0 i den åbne position).

## 2. Korte positioner i straks-bogen

- Perp-shorts på olie, metaller m.m. (FØLG ved fald, MOD ved stigning): **gap-risiko** (TradFi-perps hen over
  weekender/helligdage), **funding** betales eller modtages (bogført; FØLG −0,25 / MOD +0,25 indtil nu), ingen stop ud
  over 24 t-holdet og kontoens 20 %-grænse. **Likvidation/margin modelleres ikke** (papirmotoren har ingen marginmodel):
  UNKNOWN.
- FØLG og MOD er ikke spejlbilleder: begge betaler gebyrer og bog; funding og fyldpriser er asymmetriske.

## 3. Korte perp-ben i carry-bøgerne (carry-baner, carry90 BTC/ETH/GULD)

- **Basisrisiko:** spot − perp ved indgang/udgang (BTC/ETH ca. 8 bp imod; GULD ca. 25 bp med, PAXG ca. 0,3 % under
  XAU-perpen). **PAXG-specifikt:** tokeniseret krav (Paxos), præmie/rabat og depeg: UNKNOWN fordeling.
- **Negativ funding:** census viser enkeltmønter langt under nul (XTZ −34 % p.a. over 72 t, i to nye carry-baner).
- **Margin:** i virkeligheden kan spotbeholdningen ikke uden videre stille margin for perpen; et kraftigt rally kan kræve
  ekstra margin på perp-benet. Ikke modelleret: UNKNOWN.
- **Modpartsrisiko** (én børs for begge ben): uden for papirmodellen.

## 4. Forslag til særskilte fremtidige hypoteser (kræver hver sin daterede ændring før data; intet ændres nu)

1. β-vægtede par (hedge-forhold fastsat fra en forhåndsdefineret, forudgående periode) mod den nuværende 1:1-bog.
2. Delvis udgang: modellér og registrér resteksponering, eller send udgang kun ved fuldt fyld på begge ben.
3. Marginmodel for korte perp-ben (likvidationspris pr. position) i papirmotoren, så margin-risiko kan måles.
