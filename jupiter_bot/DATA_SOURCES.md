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

## Kilder og vilkår, læst 2026-11-20

Dette afsnit erstatter "Brugsvilkårene er ikke læst" i statusafsnittet øverst
og markeringen "søgeresultat" for Jupiters grænser i tabellen. Alt er læst
2026-11-20 fra primærkilder, medmindre det står som **UBEKRÆFTET**. Detaljer,
citater og P3-konsekvenser står i
[research/JUPITER_API_FACTS.md](research/JUPITER_API_FACTS.md).

### Jupiter: nøgle og grænser (bekræftet i docs)

- Uden nøgle er grænsen 0,5 RPS eller 30 kald pr. 60 s i et glidende vindue.
  Grænsen gælder pr. IP. En anmodning uden `x-api-key` behandles som nøglefri
  og afvises ikke. En ugyldig nøgle giver 401.
  [rate-limits](https://developers.jup.ag/docs/portal/rate-limits.md),
  [responses](https://developers.jup.ag/docs/portal/responses.md)
- Med nøgle (gratis 1 RPS, Developer 10, Launch 50, Pro 150) gælder grænsen pr.
  organisation, ikke pr. nøgle. Nøglen sendes i headeren `x-api-key`.
  `/swap/v2/execute` har sin egen pulje: 20 RPS uden nøgle, 50 med gratis nøgle,
  100 med betalt plan.
  [api-keys](https://developers.jup.ag/docs/portal/api-keys.md),
  [plans](https://developers.jup.ag/docs/portal/plans.md)
- Ved 429 er der ingen ekstra karantæne. Vent til `x-ratelimit-reset`
  (Unix-sekunder). Headerne kommer kun med 200- og 429-svar.
- Vores adapter (≥ 2,1 s, to tilbud pr. minut) holder sig inden for den
  nøglefri grænse. `swap/v2/order` og `execute` er Jupiters aktuelle API. Ultra
  er flyttet til `api.jup.ag/swap/v2` uden ændringer i felterne, og
  `lite-api.jup.ag` udfases.
  [migration](https://developers.jup.ag/docs/swap/migration/ultra-to-order.md)

### Jupiter: vilkår

Gældende dokumenter er "SDK & API License Agreement" fra 16-10-2025 og "Terms
of Use" fra 21-01-2025 (filnavne i `jup-ag/docs`).
[API-aftale](https://developers.jup.ag/docs/legal/sdk-api-license-agreement.md),
[Terms of Use](https://developers.jup.ag/docs/legal/terms-of-use.md)

- **Danmark:** Danmark og EU er ikke på listen over forbudte lande. Listen
  omfatter bl.a. USA, Kina, Singapore, Cuba, Iran, Nordkorea og Syrien samt
  lande under sanktioner fra USA, Storbritannien eller EU. VPN og skjult IP er
  forbudt.
- **Bots:** Hverken aftalen eller vilkårene nævner automatiseret handel som
  forbudt. Docs nævner selv "trading bots and AI agents" som målgruppe.
  Overdreven brug kan blive stoppet efter Jupiters skøn (§3.2(e)).
- **Røde flag i API-aftalen:**
  - §3.2(d): indhold fra API'et må ikke deles med tredjepart. Rå
    Jupiter-svar, fx fixtures, må derfor ikke offentliggøres.
  - §3.2(f): ingen "competitive analysis" og ingen offentliggørelse af
    benchmarks for API'et.
  - §3.2(g): API-indhold må ikke kombineres med data, der er hentet uden for
    API'et. Læst bogstaveligt rammer det sammenligningen af Jupiter-tilbud med
    Binance-candles. **Bør afklares skriftligt med Jupiter (info@jup.ag, §2.4),
    før P2-resultater bruges eller deles.**
  - §5.1 siger, at API'et kun må bruges med udstedte nøgler, mens docs
    tillader nøglefri adgang. §6 og §13.1 taler om gebyrer og 30 dages
    forudbetaling. Begge dele er uklart.
  - Mærkning med "Jupiter Ultra"/"Metis" og "Powered by Jupiter" (§2.3, §8.4)
    gælder slutbrugere af et produkt. Det er ikke relevant for en privat bot,
    så længe intet offentliggøres.
  - Dansk ret gælder ikke: aftalen følger panamansk ret og kræver voldgift
    (§14).
- **Lovlighed i Danmark/EU (MiCA):** Om en privatperson må køre en
  selvforvaltet bot, er **UBEKRÆFTET** og ikke undersøgt. Dette er ikke
  juridisk rådgivning.

### Binance (offentlige klines)

- **Bekræftet** i Binances officielle API-docs
  ([rest-api.md](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md),
  [market data only](https://developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only)):
  klines vejer 2, og `limit` er højst 1000. Rene markedsdata bør hentes fra
  `data-api.binance.vision`, som ikke kræver nøgle. 429 betyder, at grænsen er
  overskredet. 418 er en automatisk IP-ban på 2 minutter til 3 dage, og 403 er
  en WAF-blokering. 6.000 weight/min er docs' eksempel. Den gældende værdi står
  i `exchangeInfo`.
- **UBEKRÆFTET:** Binances Terms of Use og listen over forbudte lande kunne
  ikke læses. Siderne kræver JavaScript og en bot-kontrol. Ifølge et
  søgeresultat er listen fra 27-02-2024, og her er Danmark ikke med.
  Bestemmelser om automatiseret adgang, videredistribution og kommerciel brug
  er ikke læst.
- **UBEKRÆFTET:** Binance Vision-vilkårene for historiske datasæt kræver
  ifølge et søgeresultat en skriftlig licens til kommerciel brug og forbyder
  brug til live-handel. Det er uvist, om de også gælder API-svar. PDF'en kunne
  ikke hentes, fordi den lokale DNS blokerer `*.binance.vision`.
- **Rødt flag (sekundære kilder):** Binance har efter sigende ingen
  MiCA-tilladelse efter 1. juli 2026 og stod ikke i Finanstilsynets register
  pr. 24-09-2026. Det betyder mest, hvis der oprettes en konto. Vi bruger kun
  offentlige data uden konto.

### GitHub (privat repo)

[GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service),
gældende fra 27-04-2026, og
[Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies):

- Indhold i private repos er fortroligt. GitHub tilgår det kun af hensyn til
  sikkerhed, automatisk scanning, support, tjenestens integritet eller
  lovkrav.
- Indhold, der gives til AI-funktioner, kan bruges til træning. Det kan fravælges
  efter §J.3.
- Overdreven automatiseret brug og misbrug af API'et kan føre til suspension.
  Timevis hentning af et Atom-feed er let belastning. GitHubs grænser for
  anonyme feeds er stadig ukendte.
- Nøgler og walletdata må aldrig ligge i repoet. Repoet skal forblive privat,
  fordi det indeholder rå Jupiter-svar (jf. §3.2(d) ovenfor).

### Solana offentlig RPC (til P3-bekræftelse)

Officiel adresse er nu `https://api.mainnet.solana.com`. Den gamle
`api.mainnet-beta.solana.com` svarede også 2026-11-20. Den dokumenterede grænse
er 100 kald pr. 10 s pr. IP og 40 pr. 10 s pr. metode. Ifølge docs er den
offentlige RPC ikke beregnet til produktion og kan blokere uden varsel
([clusters](https://solana.com/docs/references/clusters)). Til en eventuel
livebot skal Anton derfor vælge en privat RPC-udbyder.
