# Claude → ChatGPT, 2026-11-17

Gren: `claude/stoic-clarke-o5weig` (fast-forward fra PR #1-hovedet `b9001e4`).
Ingen PR er oprettet. Intet i `copybot/` er ændret.

## Udført

| Commit | Indhold |
|---|---|
| `5b54d30` | P0-rettelser F1–F11, `tests/guard.py` (ingen sockets/DNS i tests), 20 regressionstests, `reviews/CLAUDE_REVIEW.md` |
| `e3f2af3` | `DATA_SOURCES.md`: valgte/fravalgte kilder, grænser, journalkontrakt (committet før koden) |
| `790a876` | `marketdata/` (transport, Binance-klines, Jupiter-prøver, Statuspage/RSS/Atom, journal, snapshot), `storage.py`, CLI `observe`/`snapshot`/`journal-status`, 29 tests |
| `79c7f88` | Ét ugyldigt nyhedslink vælter ikke længere hele feedet (+1 test) |

De vigtigste P0-fund (alle reproduceret på `b9001e4` før rettelse):
- **F1** `status`/`paper-step` skrev tabeller ind i enhver SQLite-fil, også en
  med Copybots filnavn `paper.db`. Nu kræves et eget `application_id`,
  `status` er read-only, og `copybot/`-stier afvises.
- **F2** Beslutningsalder var ubegrænset: en uge gammel beslutning blev fyldt
  til dagens pris. Nu ≤ 60 s.
- **F3** To samtidige runnere kunne åbne to positioner (med fee 0). Nu en
  compare-and-swap på kontotilstanden.
- **F4** `atoms()` afrundede stille i Decimal-konteksten med 28 cifre.

## Verificeret

- `python -m unittest discover -s jupiter_bot/tests -v` → 76 OK på 3.11, 3.12
  og 3.13. 3.9-syntaksen er tjekket med `ast.parse(feature_version=(3, 9))`.
- Mutationskontrol: 9 P0-rettelser og 15 markedsdataregler blev fjernet én ad
  gangen i en kopi. Den relevante test fejlede hver gang.
- `python -m jupiter_bot demo` giver samme resultat som før (2 fills, −572.407 atomer).
- Ét rigtigt `observe candles`: proxyen afviste værten → `TRANSPORT_ERROR`
  journalført, 0 candles; straks efter gav kaldet `COOLDOWN` uden netværk.
- Kildereferencer: se `DATA_SOURCES.md` (søgeresultater fra Binance-, Jupiter-
  og Pyth-dokumentation; tydeligt markeret, hvor intet er bekræftet).

## Fund (åbne)

- **Ingen live-data eller primær dokumentation i denne session.** Netværket
  afviste `api.jup.ag`, `developers.jup.ag`, `dev.jup.ag`,
  `data-api.binance.vision`, `status.solana.com` m.fl. (403). Parserne er kun
  testet mod syntetiske fixtures, der efterligner de forventede formater.
- Det er stadig en antagelse, at `outAmount` er netto efter **alle** Jupiter-
  gebyrer. Søgeresultater støtter, at platformgebyret er inkluderet. `feeBps`
  kan indeholde et gasless-tillæg, og et eventuelt udløbsfelt er ikke bekræftet.
- Binance-candles er CEX-priser. Afvigelsen fra Jupiter er ikke målt.
- `status.solana.com` som Statuspage og `status.jup.ag/feed.rss` er slutninger.
- Rate-grænsen i `quote` uden journal gælder pr. proces. `observe quote` deler
  grænse via journalen.
- EMA-referencen afhænger af vindueslængden, men bruges kun til rørføring.

## Næste

**P1-afslutning: live-formatkontrol.** Hent ét svar pr. kilde
(`observe candles`, `observe quote` begge veje, `observe news` for hver feed).
Gem de rå svar som fixtures, og ret parserne, hvor virkeligheden afviger. Notér
Jupiters `feeMint`/`platformFee`/udløbsfelter og indfør udløb som strengere
grænse. Først derefter P2-forskningsplanen (mekanisme, univers, budget for forsøg
og afvisningskrav før data).

Behov for adgang (særskilt): enten tillader Anton værterne
`data-api.binance.vision`, `api.jup.ag`, `status.solana.com`, `status.jup.ag` og
`github.com` (feeds) samt `developers.jup.ag` til dokumentation i
cloud-miljøets netværksindstillinger, eller også køres hentningen på Antons
egen maskine. Ingen nøgler eller betalte kald er nødvendige. Brugsvilkårene
skal læses før løbende indsamling.

---

## Opdatering 2026-11-20 — live-formatkontrol udført

**Udført:**
- `e41f5df`: `live-check` (ét kald pr. kilde, `summary.json`).
- Anton godkendte et personligt cloud-miljø "ecommerence". Det tillader kun
  kildernes værter, `developers.jup.ag` og den eksisterende Dukascopy-vært.
  Ingen nøgler, ingen setup-script.
- `live-check` blev kørt to gange. Fund og rettelse: Jupiters RSS bruger
  `-0000` (RFC 5322 = UTC), og alle 4 elementer blev afvist. Nu parses de.
  Snapshot repræsenterer en historie ved dens første publikation på tværs af
  opdateringselementer.
- 7 uændrede live-svar er gemt som fixtures (`tests/fixtures/live_20261120/`,
  SHA-256 i `meta.json`, `-text` i `.gitattributes`) med 12 tests.

**Verificeret:**
- 90 tests OK på 3.11, 3.12 og 3.13.
- Mutationskontrol af de to nye regler.
- Anden live-kørsel: 5/6 kilder OK, og GitHub gav 403 fra cloud-proxyen.

**Fund:**
- `outAmount` er målbart netto efter `feeBps` for `metis` i begge retninger,
  også med `feeMint` = input. Ved RFQ er gebyret ikke specificeret, men rutens
  output er lig `outAmount`. Det tidligere åbne punkt om dobbelt fradrag er
  dermed lukket for `metis`.
- Svarene har intet udløbsfelt, så de faste 15 s bevares.
- Netværksgebyrfelterne er 0 uden `taker`, så 0,01 USDC er fortsat en antagelse.
- Binance-weight var allerede 266 efter vores ene kald: cloud-IP'en deles med
  andre. En løbende indsamler bør køre fra en fast egen maskine eller med lav kadence.
- GitHub-feeds kan ikke hentes fra en cloud-session, fordi proxyen kun tillader
  repoets egne stier.
- Jupiters dokumentation er stadig ikke læst direkte, og brugsvilkårene er ikke læst.

**Næste:** P2-forskningsplanen skrives *før* nye resultatdata: mekanisme,
univers, frekvens, budget for forsøg, benchmark, omkostninger (nu med målte
Jupiter-gebyrer) og afvisningskrav. Samtidig skal Anton beslutte, om og hvor
en løbende indsamling må køre (kadence, maskine). Den er ikke installeret.
