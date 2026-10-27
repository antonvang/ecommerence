# Gebyrer, perps for danske detailkunder og API-enhed (2026-10-27, læst 17:40–17:55 UTC)

Brugerens ja: "JA kør punkt 1 og 2 og 3" (ca. 18:39 lokal). Kun offentlige sider; ingen konto, intet login, ingen
omgåelse af bot-spærringer. "uafklaret" = ingen officiel kilde læst. Grundlag for ændring 29b.

## 1. Spot-gebyrer, laveste niveau (taker bruges i V1)

| Børs | Maker | Taker | Kilde (eget domæne?) | Status |
|---|---|---|---|---|
| Binance (reference) | 0,100 % | 0,100 % | binance.com/en/fee/schedule: "Regular User 0.100% / 0.100%" (ja) | bekræftet |
| Kraken Pro | 0,40 % | 0,80 % | kraken.com/features/fee-schedule: "Tier 1 $0+ < $5M N/A 0.40 % 0.80 %" (ja; sha256 a0fb928d…3d69c) | bekræftet |
| OKX EEA, konto kun med spot | 0,100 % | 0,200 % | okx.com/en-us/help/important-notice-upcoming-adjustment-to-vip-trading-volume-tiers-europe, "Published on Sep 25, 2026", gælder fra 2026-10-09 10:00 UTC+2: "\| Regular \| 0 \| 0 \| 0.100% \| 0.200% \|" (ja) | bekræftet; konti med derivater 0,080/0,100 % |
| Bitvavo, EUR-par (A) / USDC-par (B) | 0,15 / 0,05 % | 0,25 / 0,05 % | bitvavo.com/en/fees i brugerens Chrome 2026-10-27 kl. 20:15 lokal: "€0 + \| 0.15% \| 0.25%" (A), "€0 + \| 0.05% \| 0.05%" (B) (ja) | bekræftet (ændring 29c) |
| Bitstamp | 0,30 % | 0,40 % | bitstamp.net/fee-schedule i brugerens Chrome, "Valid from 21 October 2026": "< $10,000 \| 0.30% \| 0.40%" (ja); nyt skema varslet fra 2026-11-24 | bekræftet (ændring 29c) |
| Coinbase Advanced (EU) | 0,25 % | 0,50 % | Coinbase' blog 2026-09-16 i brugerens Chrome: "EU and UK: 0.25% maker & 0.50% taker" (spot entry level) (ja); gebyrsiden kræver login (ikke brugt) | bekræftet (ændring 29c) |

Kraken-appen ("instant buy") tager 1 % plus spread; Kraken Pro er tallet ovenfor.

## 2. Perps for en dansk detailkunde

Svar: **lovligt gennem et MiFID-investeringsselskab med pas til Danmark, sandsynligvis højst 2x gearing.**

- MiCA art. 2, stk. 4, litra a: forordningen gælder ikke kryptoaktiver, der er finansielle instrumenter. Krypto-perps
  er derivater under MiFID II.
- ESMA35-243228190-8024 (24. februar 2026, PDF sha256 bafecae8…e4cab): "derivatives, often marketed as perpetual
  futures or perpetual contracts, that provide leveraged exposure …"; "the commercial name provided by firms (e.g.
  "perpetual futures") is irrelevant". De er sandsynligvis omfattet af CFD-indgrebet.
- Finanstilsynets afgørelse af 1. august 2019 (PDF sha256 49e85602…2a922): "50 % af CFD'ens nominelle værdi, når det
  underliggende instrument er en kryptovaluta"; den gælder også ydelser "i henhold til reglerne om fri udveksling af
  tjenesteydelser". CFD-definitionen undtager "option, future, swap". Om de "5-års futures", som Coinbase og OKX
  sælger med op til 10x, falder uden for, er uafklaret (ingen afgørelse fundet).
- Selskaber med pas til Danmark i hjemlandets register:
  - Payward Europe Digital Solutions (CY) Ltd (Kraken), CySEC 342/17: Danmark med instrument C9. Bekræftet.
  - Coinbase Financial Services Europe Ltd, CySEC 374/19: Danmark med instrument 1, 3, 4, 5 og 10, ikke C9. Bekræftet.
  - OKX Europe Markets Ltd (MFSA): Danmark står kun i OKX' egne kampagnevilkår. Uafklaret.
  - Bybit, Bitvavo og Deribit: ikke i ESMA's MiFID-register.
- Skat: SKM2022.92.SR: perps og kvartalsfutures falder under kursgevinstloven § 29 og beskattes efter lagerprincippet
  (§ 33).

## 3. Er den offentlige bog den bog, en EU-kunde handler på?

| Børs | EU-kundens modpart | Bog | Status |
|---|---|---|---|
| Coinbase | Coinbase Luxembourg S.A. (mægler) | Ordreudførelsespolitikken siger: "interact, through CB Lux, with the … order book(s) on the Coinbase Exchange", drevet af Coinbase, Inc. Det er den bog, `api.exchange.coinbase.com` viser. | bekræftet |
| Kraken | Payward Europe Solutions Ltd (mægler) | Politikken siger: "PESL routes all client orders to the PGSL Central Limit Order Book (CLOB)" (tekst-sha256 2867248a…c615). Om `api.kraken.com` er PGSL's bog, står ingen steder. PGSL har kun pas til CY og IE. | uafklaret |
| OKX | OKX Europe Ltd | Politikken taler om "its own central limit order book". Dokumentationen siger, at EU-brugere skal bruge `eea.okx.com`. www- og eea-hosten gav samme handels-ID'er kl. 17:41 og 17:50 UTC. | samme bog observeret, ikke officielt bekræftet |
| Bitvavo | Bitvavo B.V. | Én enhed. Den offentlige bog er dens egen MiCA-platform (docs.bitvavo.com). | bekræftet |
| Bitstamp | Bitstamp Europe S.A. | Handelsregler og gennemsigtighedsside er bag bot-spærring. | uafklaret |

## Konsekvens (beskrivende, ingen dom)

Med bekræftede gebyrer koster en rundtur i taker-gebyr 160 bp hos Kraken, 100 bp hos Coinbase, 80 bp hos Bitstamp,
50 bp hos Bitvavo (EUR) eller 10 bp (USDC) og 40 bp hos OKX, mod 20 bp hos Binance. Kun Bitvavos USDC-par er billigere. Forskellen alene er større end V1's grænse på 10 bp. V1-dommen afgives dog først efter mindst 48 timers
data (ændring 29b punkt 2).
