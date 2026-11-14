# Historisk lab 2026-11-14: opsummering (skrevet kl. 15:16 lokal)

Alt på explore0 (BTC/ETH USDT-M perps, 2020-03..2021-12). UDVIKLING 2020-03..2021-06; KONTROL 2021-07..2021-12.
Udforskning, aldrig bevis. Kun papir.

| Familie | Ændring | Udvikling | KONTROL | Dom |
|---|---|---|---|---|
| Event farm (ICT/SMC-kæder) | 47 | 9 kørsler, 195 tests; 5m–15m negative efter omkostning; 1h ob/market-plateau +0,13..+0,19 R | 1 åbning (fastfrysning 01, 1h ob/rr3/market): netto −0,215 R, alle 4 kriterier dumpet | Ingen fordel; familien lukket for 1h/2h-naboer |
| Funding-ekstremer efter afregning | 48, 48a | 2 kørsler, 72 tests; bedst +6..+7 bps netto ved 9 bps (t ≤ 0,7); fortegn skifter med holdetid | ikke åbnet (intet at fryse) | Ingen fordel |
| Nedlukning før afregning | 48b | 1 kørsel, 18 tests; contra 1–2 t +7 bps brutto, netto ≤ −2 bps ved 9 bps | ikke åbnet | Ingen fordel; funding-familien lukket på explore0 |

**Tværgående fund:** de rå signaler ligger på 0–30 bps brutto pr. handel; omkostningen bestemmer resultatet. Lab'ets
papirmodel (28 bps rundtur) er spot-niveau; for USDT-M perps er taker begge veje ca. 14 bps og maker ind/taker ud ca.
9 bps (Binance VIP 0: 0,02 % / 0,05 %). Selv ved 9 bps bestod intet. Papirbøgernes omkostningsmodel er ikke ændret.

**N:** 285 udviklingstests og 1 KONTROL-åbning i dag (logget i `research/data/event_farm_hist/`).
