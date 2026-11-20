# Datakilder og observationsjournal (P1), 2026-11-17

Status: adapters og journal er implementeret og testet. Den 2026-11-20 blev
`live-check` kørt to gange fra en cloud-session med et særskilt miljø
("ecommerence"), der kun tillader kildernes værter. Fem af seks kilder svarede,
og deres rå svar ligger uændret i `tests/fixtures/live_20261120/` med SHA-256 i
`meta.json`. Én afvigelse fra antagelserne blev fundet og rettet: RSS-tidszonen
`-0000`. Grænser og vilkår nedenfor stammer stadig fra søgeresultater, som
markeret. Brugsvilkårene er ikke læst.

Dokumentet er skrevet sammen med koden, ikke før den. Det er committet som
særskilt commit forud for koden.

## Valgte kilder (implementeret)

| Id | Hvad | Endpoint (fast allowlist) | Nøgle | Grænse i adapteren | Dokumenteret grænse | Verifikation |
|---|---|---|---|---|---|---|
| `binance_spot_klines` | 1m/5m/15m/1h-candles for Binance Spot `SOLUSDC` | `GET https://api.binance.com/api/v3/klines?symbol&interval&limit` | Nej | ≥ 2 s mellem kald pr. journal; `limit` ≤ 1000; 429 → `Retry-After`, ellers 60 s; 418 → 900 s | Samme API som market-data-only-hosten `data-api.binance.vision`, men den blokeres af den lokale DNS (192.168.1.3 svarer `0.0.0.0`), så collectoren bruger `api.binance.com` (2026-11-20). Allowlisten tillader kun GET `/api/v3/klines` uden nøgle. Klines vejer 2 ud af 6.000 weight/min pr. IP. 429 ved overskridelse. (søgeresultater fra Binance-docs) | **Live 2026-11-20:** format som antaget (12 felter, `closeTime = open + 60.000 − 1`, decimaler som tekst). Sidste række er den åbne bar og blev droppet. `Date`-header findes. `x-mbx-used-weight-1m` var 266 efter ét kald, så cloud-IP'ens budget deles med andre. 418-reglen er tidligere kendskab |
| `jupiter_quote` | Eksekverbart tilbud for én fast størrelse (prøve, aldrig et fill) | `GET https://api.jup.ag/swap/v2/order?inputMint&outputMint&amount` | Nej | ≥ 2,1 s pr. journal | Nøglefri: 0,5 RPS, 30 kald/60 s pr. konto/IP; `/order` deler den generelle pulje (søgeresultat fra Jupiters portal-side) | **Live 2026-11-20 (3 svar):** `metis` begge veje og `jupiterz` (RFQ). `outAmount` er netto efter `feeBps` (se nedenfor). Intet udløbsfelt. Netværksgebyrfelter er 0 uden `taker` |
| `solana_status` | Hændelser på Solanas statusside | `GET https://status.solana.com/api/v2/incidents.json` | Nej | ≥ 60 s; 429 → 300 s | Ukendt | **Live 2026-11-20:** Statuspage v2-format bekræftet. 30 hændelser, alle parset. Seneste hændelse er fra 2024-02-06. `Date` lå 13 s efter vores ur (CDN-cache) |
| `jupiter_status` | Jupiters statusside som RSS | `GET https://status.jup.ag/feed.rss` | Nej | ≥ 60 s | Ukendt | **Live 2026-11-20:** RSS 2.0 bekræftet. Ét element pr. *opdatering* (samme link, forskellig `guid`). `pubDate` bruger `-0000`, som først blev afvist (rettet) |
| `agave_releases` | Releases af Agave, Solanas primære validatorklient | `GET https://github.com/anza-xyz/agave/releases.atom` | Nej | ≥ 60 s | GitHubs grænser for anonyme web-feeds er ukendte | **Ikke testet:** cloud-sessionens GitHub-proxy tillader kun de konfigurerede repos og svarede 403 (gemt som fixture). Kan virke fra en anden maskine; ubekræftet |

Jupiter-gebyrer i de rå svar (2026-11-20, `tests/test_live_fixtures.py`):
- `metis`, USDC→SOL (`feeMint` = output): `outAmount` = rutens output −
  ⌊output · 2/10.000⌋ (362.829.593 − 72.565 = 362.757.028).
- `metis`, SOL→USDC (`feeMint` = **input**): hele input går til ruten, og
  de 2 bps trækkes alligevel fra output (6.922.000 − 1.384 = 6.920.616).
- `jupiterz` (RFQ, `gasless: true`, `guaranteedPrice: true`): rutens output =
  `outAmount`. Gebyret er ikke specificeret, men ligger i makerens pris.
- Papirbogen bruger `outAmount` direkte. Swapgebyret trækkes altså ikke to
  gange, og det er nu målt for `metis`. De 25 bps og 0,01 USDC er fortsat
  egne antagelser, da netværksgebyrfelterne er 0 uden `taker`.

Hvorfor disse:
- **Binance SOLUSDC** er en primær børs med egne, dokumenterede og gratis
  klines og et eksplicit lukketidspunkt pr. bar. Det er en CEX-pris, ikke en
  onchain-pris. Forskellen til Jupiter skal måles, ikke antages.
- **Jupiter-tilbud** er udførelsesstedets egen pris for en konkret størrelse,
  inklusive rute og gebyr. Det er den mest relevante omkostningsdata til P2.
  Tilbuddene giver ingen OHLCV.
- **Status og releases** er primære, officielle hændelseskilder (nedbrud,
  opgraderinger). Der bruges ingen nyhedsaggregatorer.

## Fravalgt nu (med grund)

| Kilde | Grund |
|---|---|
| Pyth Benchmarks / History API | TradingView-shim nedlagt 26-08-2026, og API-nøgle kræves siden da (søgeresultater fra Pyth). Strider mod "ingen nøgler". Kan genovervejes med mandat |
| Birdeye | Kræver API-nøgle og betalte planer for historik |
| GeckoTerminal / CoinGecko | Aggregatorer, ikke primære. Mulig senere kilde til DEX-pool-OHLCV, markeret sekundær |
| Kraken / Coinbase | Alternative CEX'er, typisk SOL/USD. Mulig krydskontrol senere |
| Jupiter Price API | Kun aktuel pris, ingen bars |
| SEC/CFTC-RSS | SEC's fair-access-regel kræver en User-Agent med kontaktoplysninger. Det kræver Antons beslutning (privatliv) |
| X/Discord/Telegram | Ingen tilladt, nøglefri officiel adgang |
| "Fundamentaldata" for memecoins | Ingen. Der opfindes ingen regnskaber |

## Journal (`marketdata/journal.py`)

En SQLite-fil med eget `application_id` (`JBO1`). En papirbog eller en fremmed
database afvises og skrives aldrig i. Tabellerne for observationer og hentninger
er append-only (triggers afviser `UPDATE`/`DELETE`).

| Krav fra handoff | Felt |
|---|---|
| kilde, instrument, interval | `fetches.source`, `instrument`; `candles.interval_s` |
| udgivelsestid | nyheder: `published_at` og `updated_at`. Mangler `published`, bruges `updated`, og `published_is_updated=1`. Candles: Binance angiver ingen udgivelsestid. Barens `end` er det tidligste mulige tidspunkt |
| første set | `candles.first_seen_at` og `news.first_seen_at` = modtagelsestid for første svar med værdien |
| modtagelsestid | `fetches.requested_at` (før kald) og `received_at` (efter læsning) |
| råsvar og hash | `fetches.body` (præcise bytes, også fejlsvar) og `body_sha256`; udvalgte headers i `headers_json` |
| første værdi bevares | `candles`/`news` ændres aldrig. En afvigende senere værdi giver en række i `candle_revisions`/`news_revisions` |

Regler:
- **Åbne bars** gemmes ikke. En bar er lukket, når `end + 5 s ≤ min(vores ur,
  serverens Date-header)`, så et for hurtigt lokalt ur ikke lukker den for tidligt.
- **Manglende bars** udfyldes aldrig. `journal-status` viser huller. Et snapshot
  bruger kun den seneste sammenhængende række og oplyser, hvor der er skåret.
- **Stale:** er seneste lukkede bar ældre end 2 intervaller + 5 s, får hentningen
  `STALE`. Et snapshot afvises af `analyse`, hvis data er for gamle.
- **Dubletter:** identiske gentagelser i ét svar slås sammen og tælles.
  Modstridende gentagelser afviser hele svaret (`PARSE_ERROR`). Råsvaret gemmes stadig.
- **Fejl** (`TRANSPORT_ERROR`, `HTTP_ERROR`, `PARSE_ERROR`, `RATE_LIMITED`,
  `COOLDOWN`) giver kun en `fetches`-række, aldrig en observation eller en
  "sidst kendt" værdi.
- **Rate limits** gælder pr. kilde på tværs af processer, der bruger samme
  journal. De holdes i tabellen `limiter` og overlever genstart. Et kald i en
  cooldown journalføres som `COOLDOWN` uden netværk.
- **Snapshot (point-in-time):** kun bars og historier set senest ved `as_of`,
  hver i den version, der var kendt da. `observed_at` er tidspunktet for den version.

## Nyheder som data

Kun titel, HTTPS-link og tider gemmes, plus en hash af det rå element til
revisionsdetektion. Brødtekst gemmes ikke. Kontrol- og formattegn (fx
bidi-override, ANSI, NUL) fjernes, og længden begrænses. Feeds med DOCTYPE eller
ENTITY afvises. Historier deduplikeres på tværs af kilder via normaliseret URL
(uden `utm_*` m.m.) eller normaliseret titel. `core.analyse` bruger aldrig nyheder
til retning (`news_used_for_signal: false`). Intet i koden lader en tekst ændre
grænser, wallet eller ordrer. Det er testet med en fjendtlig titel.

## Løbende indsamling (besluttet 2026-11-20)

Anton valgte at køre den på sin Linux-pc. Plan, kadence og installation står i
[deploy/linux/README.md](deploy/linux/README.md): candles og to Jupiter-tilbud
hvert minut, status/releases hver time, systemd-brugertimer, journal uden for
repoet. Punkterne nedenfor gælder stadig.

## Før løbende indsamling (oprindelig tjekliste)

1. Hostene skal tillades i miljøets netværk, eller indsamlingen skal køre på
   Antons maskine. Det er Antons beslutning.
2. Brugsvilkår for Binance API, Jupiter, GitHub og statussiderne skal læses.
   Det var ikke muligt i denne session.
3. Kør `python -m jupiter_bot live-check` (én hentning pr. kilde, ingen løkke)
   og send `summary.json` til review. Kontrollér det rå svar mod parserens antagelser:
   kline-felter, Statuspage-felter, RSS/Atom-struktur og Jupiters gebyr- og
   udløbsfelter. Først derefter planlægges en kadence. Eksempel: candles hvert
   minut med `limit=5` ≈ 1.440 kald og 2.880 weight pr. døgn, langt under
   6.000 weight/min.
4. Der installeres ingen scheduler eller service som del af reviewet.
