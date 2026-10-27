# Børsregister for hypotese V1 (ændring 29a punkt 4), skrevet 2026-10-27 kl. 15:17 lokal

Kilde: ESMA's officielle interim-MiCA-register, `CASPS.csv` fra
https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv (hentet 2026-10-27 14:16 UTC; serverens
`last-modified` 2026-10-22 15:14:35 GMT; 189 687 bytes; sha256 b0d68e59b71a9f6135eae96ac7c0c3cff1a2f0f1dc071f3512f476a704bb75fb;
387 rækker). Tjenestekoder efter MiCA art. 3(1)(16): a forvaring, **b drift af handelsplatform**, c veksling mod
fiat, d veksling mod krypto, **e udførelse af ordrer for kunder**, f placering, g modtagelse/formidling af ordrer,
i porteføljeforvaltning, j overførsel. "DK" = Danmark står i enhedens liste over lande, hvor tjenesterne må ydes.

## Resultat

- **Binance står ikke i registret** (ingen række med "binance" i juridisk eller kommercielt navn). Det bekræfter
  `PILOT_VILKAAR_2026-10-27.md` punkt 1 fra den officielle kilde.
- Udvalgte store børser (ingen er "godkendt" af os; dette er kun registrets oplysninger):

| Juridisk enhed (LEI) | Hjemland, myndighed | Tilladt | Tjenester | DK |
|---|---|---|---|---|
| Bitpanda GmbH (5493007WZ7IFULIL8G21) | AT, Austrian Financial Market Authority (FMA) | 09/04/2025 | acdefgj | ja |
| Bybit EU GmbH (5299005V5GBSN2A4C303) | AT, Austrian Financial Market Authority (FMA) | 28/05/2025 | acdfj | ja |
| KuCoin EU Exchange GmbH (529900B4G0EGK7Z9KT45) | AT, Austrian Financial Market Authority (FMA) | 27/11/2025 | acdfj | ja |
| Payward Global Solutions Limited (9845003D98SCC2851458) | IE, Central Bank of Ireland (CBI) | 25/06/2025 | b | nej |
| Payward Europe Solutions Limited (254900641D8KNHUZYX24) | IE, Central Bank of Ireland (CBI) | 25/06/2025 | acdefgij | ja |
| Bitstamp Europe S.A. (549300XIBGTJ0PLIEO72) | LU, Commission de Surveillance du Secteur Financi | 15/05/2025 | abcdegj | ja |
| Coinbase Luxembourg S.A. (984500F14CA4571AAC11) | LU, Commission de Surveillance du Secteur Financi | 20/06/2025 | acdefgj | ja |
| OKX Europe Limited (54930069NLWEIGLHXU42) | MT, Malta Financial Services Authority (MFSA) | 27/01/2025 | abcdefgij | ja |
| Foris DAX MT Limited (2549005CVR5HH70FDO07) | MT, Malta Financial Services Authority (MFSA) | 27/01/2025 | acdegj | ja |
| Gemini Intergalactic EU Ltd (2138002QAMX8PPKSO715) | MT, Malta Financial Services Authority (MFSA) | 21/08/2025 | acdefgj | ja |
| Gate Technology Limited (984500D6A0F945BB5A15) | MT, Malta Financial Services Authority (MFSA) | 29/09/2025 | abcdej | ja |
| Bitvavo B.V. (724500MX2WBKDJP9HE56) | NL , Netherlands Authority for the Financial Marke | 26/06/2025 | abj | ja |

## Uafklaret (skal verificeres, før en børs kan kaldes kandidat)

1. Hvilken platform og hvilket API den registrerede enhed faktisk driver for danske kunder (fx om Kraken-kunder i
   Danmark betjenes af Payward Europe Solutions Limited, og Bitstamp af Bitstamp Europe S.A.).
2. Hvilke af de 7 mønter (ændring 29 punkt 3) der handles mod USDT eller EUR på den enhed.
3. Offentliggjort gebyr på laveste niveau og ordretyper (market, post-only) for den enhed.
4. Offentlig adgang til ordrebog og historik uden konto (endpoint, grænser, vilkår for brug).
5. Registret er "interim"; det skal genhentes og sha256 sammenlignes før enhver beslutning.

Næste skridt (kun offentlige data, ingen konto): punkt 2–4 for Bitstamp Europe, Kraken (Payward Europe), OKX Europe,
Bitvavo og Coinbase Luxembourg, derefter V1-målingen efter ændring 29a punkt 3.

## Tilføjet kl. 15:22 lokal: de 7 mønter på offentlige marked-lister (ingen konto)

Hentet 2026-10-27 14:22 UTC fra hver børs' offentlige liste: Kraken `api.kraken.com/0/public/AssetPairs`, Bitstamp
`www.bitstamp.net/api/v2/trading-pairs-info/`, OKX `www.okx.com/api/v5/public/instruments?instType=SPOT`, Bitvavo
`api.bitvavo.com/v2/markets`, Coinbase `api.exchange.coinbase.com/products`. Noteret: hvilke citatvalutaer findes.

| Mønt | Kraken | Bitstamp | OKX | Bitvavo | Coinbase |
|---|---|---|---|---|---|
| BTC | USDT, USDC, EUR, USD | USDT, USDC, EUR, USD | USDT, USDC, EUR | USDC, EUR | USDT, USDC, EUR, USD |
| ETH | USDT, USDC, EUR, USD | USDT, USDC, EUR, USD | USDT, USDC, EUR | USDC, EUR | USDT, USDC, EUR, USD |
| EPIC | – | – | – | EUR | – |
| XTZ | USDT, USDC, EUR, USD | EUR, USD | USDT, USDC, EUR | EUR | EUR, USD |
| VET | USDT, USDC, EUR, USD | – | – | EUR | USD |
| MITO | – | – | – | – | – |
| HOT | – | – | – | EUR | – |

- **Fund:** BTC og ETH findes overalt. Af banernes fem småmønter findes MITO intet sted, EPIC og HOT kun på Bitvavo
  (EUR). Banernes univers er altså stort set Binance-specifikt; en lovlig fremtidig platform begrænser universet.
- **Uafklaret:** om de globale API'er (fx `www.okx.com`, `api.exchange.coinbase.com`) viser samme markeder som de
  registrerede EU-enheder (OKX Europe, Coinbase Luxembourg). Listerne siger intet om likviditet eller gebyrer.
- V1 kan derfor kun måles på de fælles mønter (BTC, ETH, XTZ, evt. VET), ikke på banernes småmønter.
