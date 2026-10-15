# CopyBot: kopiér memecoin-wallets på Solana (paper trading)

Botten gør det samme som "Grok Bot"-videoen: følger topwallets, kopierer deres køb og salg og fyrer en wallet efter N tab i træk. Forskellen er, at den **regner ærligt**. Hver handel prissættes, som vi reelt ville få den: *efter* walletten, med slippage, DEX-gebyr, bot-gebyr og netværksgebyr. Formålet er at finde ud af, **om** det kan tjene penge, før der sættes rigtige penge i.

- Kun paper trading. Botten sender aldrig transaktioner og skal ikke bruge en privat nøgle.
- Kun Python 3.9+ standardbibliotek. Ingen `pip install`.
- Gratis datakilder: Solana RPC, DexScreener og GeckoTerminal.

Kom i gang: læs `LAES MIG.txt`, skriv dine wallets i `wallets.txt`, og dobbeltklik på `START_COPYBOT.bat`.

## Sådan virker det

| Del | Hvad den gør |
|---|---|
| `swaps.py` | Finder køb og salg i en wallets transaktion ud fra dens saldoændringer. Virker for pump.fun, PumpSwap, Raydium, Meteora og Jupiter. Finder også poolens SOL-reserve til beregning af slippage. |
| `engine.py` | Kopi-motoren. **Shadow**: kopierer *alle* wallets med $10 pr. handel og måler, hvad hver af dem reelt giver. **Konto**: følger én wallet ad gangen og fyrer den efter N tab i træk. |
| `backtest.py` | Henter de sidste 14 dages handler og minut-priser og afspiller dem. Sammenligner også videoens regel med andre regler og andre forsinkelser på de samme data. |
| `paper.py` | Live med falske penge. Forsinkelsen er den rigtige, fordi prisen hentes, når botten opdager handlen. |
| `dashboard.html` | Dashboard i stil med videoen på http://localhost:8765 |

Prisregler, der holder tallene ærlige:
- Vi kan ikke købe billigere eller sælge dyrere end den wallet, vi kopierer.
- Slippage beregnes med x·y=k: gennemsnitsprisen stiger med ordrestørrelse divideret med poolens størrelse.
- Når walletten sælger en del af sin beholdning, sælger vi samme andel.

## Indstillinger (`config.json`)

| Nøgle | Standard | Betydning |
|---|---|---|
| `rpc_url` | offentlig | Solana RPC. En gratis Helius-nøgle er langt hurtigere: backtesten bruger så `getTransactionsForAddress` og tager minutter i stedet for timer. |
| `rpc_requests_per_second` | 1.5 | Den offentlige RPC giver 429-fejl over ca. 1,5 kald/sek. Med Helius: 8. |
| `paper.rpc_url` | tom | RPC til paper trading. Tom + offentlig `rpc_url` = PublicNode (gratis, hurtig, men kun ca. 1 dags historik, hvilket er nok live). |
| `start_balance_usd` | 50 | Startbeløb (falske penge) |
| `position_pct` | 20 | Procent af kontoen pr. handel |
| `max_open_positions` | 4 | Højst så mange åbne handler ad gangen |
| `shadow_trade_usd` | 10 | Fast beløb pr. shadow-handel (til at sammenligne wallets) |
| `fire_after_losses` | 3 | Fyr efter så mange tab i træk (0 = aldrig). Videoen bruger 2. |
| `next_trader` | `best_shadow` | `list` = næste på listen (som videoen). `best_shadow` = den wallet, der har tjent mest som kopi de sidste `rank_window_days` dage. |
| `warmup_hours` | 48 | Ved `best_shadow`: kun observation de første timer |
| `min_shadow_trades` | 5 | Mindst så mange målte handler, før en wallet kan vælges |
| `min_median_hold_minutes` | 5 | Vælg ikke wallets, der typisk sælger hurtigere end dette, fordi deres handler ikke kan kopieres |
| `require_positive_shadow` | true | Kopiér kun wallets, der har tjent penge som kopi. Ellers pause. |
| `min_leader_buy_usd` | 50 | Ignorér små testkøb |
| `min_liquidity_usd` | 20000 | Spring coins med mindre likviditet over |
| `max_price_impact_pct` | 3 | Spring over, hvis vores ordre flytter prisen mere end dette |
| `stop_loss_pct` | 40 | Sælg ved et fald på 40 % fra vores købspris |
| `max_hold_hours` | 24 | Sælg senest efter så mange timer |
| `fees.dex_pct` | 0.5 | DEX-gebyr pr. handel |
| `fees.bot_pct` | 1.0 | Bot-gebyr pr. handel (Trojan, BonkBot og copy-platforme tager typisk ~1 %) |
| `fees.mev_slippage_pct` | 0.5 | Ekstra tab til sandwich-bots og slippage-tolerance |
| `fees.network_fee_sol` | 0.0015 | Priority fee og Jito-tip pr. transaktion |
| `backtest.copy_delay_seconds` | 10 | Antaget forsinkelse i backtest |
| `backtest.max_tx_per_wallet` | 15000 | Højst så mange transaktioner pr. wallet. Mange KOL-wallets får ~1.000 spam-transaktioner om dagen (andres handler i coins, de selv har lavet), så 14 dage kan være 10.000+. På den offentlige RPC tager det 1 sek pr. transaktion; første kørsel kan derfor tage en hel nat. |

## Kommandoer

```
python copybot.py backtest [--days 14] [--no-sweep]
python copybot.py paper
python copybot.py dashboard [--db data/backtest.db]
python copybot.py report [--db data/paper.db]
python -m unittest discover -s tests
```

## Begrænsninger

- Wallets med mange tusinde transaktioner om dagen (fx coin-skabere) kan ikke følges på en gratis RPC. Botten siger til i backtesten, hvis loftet nås.

- **Backtesten er for optimistisk**, når wallets kommer fra en leaderboard, fordi de er valgt efter at have vundet i perioden. Paper trading på nye dage er den rigtige test.
- Minut-candles skjuler udsving inden for minuttet. Stop-loss i backtesten rammer derfor lidt for pænt.
- DexScreener-priser kan halte et par sekunder. Reglen om "ikke billigere end walletten" dækker det meste.
- Token-til-token-handler kopieres ikke.
