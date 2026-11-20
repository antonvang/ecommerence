# Claude-review P0 — Jupiter-prototype, 2026-11-17

Reviewet: `b9001e4` (PR #1, `codex/jupiter-bot-2026-11-17`), oven på
`4f8b647` (SPEC) og `745e755`. Rettelser ligger på
`claude/stoic-clarke-o5weig`. Ingen Copybot-filer, protokolpins, holdouts,
indsamlinger eller services er ændret.

## Metode

1. Læst `SPEC.md`, `README.md`, `VALIDATION.md`, `CLAUDE_HANDOFF.md` og al kode.
2. Kørt de oprindelige 26 tests og `demo` (begge grønne).
3. Skrevet et separat reproduktionsscript for hver mistanke og kørt det mod
   den oprindelige kode, før noget blev rettet. Fire fejl blev reproduceret
   (F1–F4); en femte (F5) blev reproduceret med en låst database.
4. Rettet, tilføjet regressionstests, og kørt en mutationskontrol: hver rettelse
   blev fjernet igen i en midlertidig kopi, og den tilhørende test fejlede.

## Fund og rettelser

| # | Alvor | Fund (reproduceret på `b9001e4`) | Rettelse |
|---|---|---|---|
| F1 | Høj (isolation) | `status --db <fil>` og `paper-step` oprettede tabellerne `accounts/fills/decisions` og en konto i **enhver** eksisterende SQLite-fil. Copybot bruger selv filnavnet `data/paper.db`, så en forkert sti ville skrive i labbens database. | Ny papir-DB får `PRAGMA application_id` (`JBP1`) og `user_version`, sat i samme `BEGIN IMMEDIATE` som skemaet. En ikke-tom fil uden mærket afvises før enhver skrivning. `status` åbner read-only (`mode=ro`) og opretter intet. CLI afviser stier i `copybot/` for `--db` og `--out`. |
| F2 | Høj (tid) | Beslutningens alder var ubegrænset. Et snapshot fra for en uge siden plus et frisk tilbud gav `PAPER_FILLED` til dagens pris. `analyse` tjekker kun data mod `as_of`, ikke `as_of` mod udførelsestid. | `runner.step` kræver `0 ≤ udførelsestid − as_of ≤ 60 s` både før prisforespørgslen og ved fill. CLI parser `as_of` med `timestamp()`. |
| F3 | Mellem (samtidighed) | To processer, der traf beslutning på samme tomme konto, kunne begge købe. Med standardgrænserne blev det andet køb kun stoppet af tilfældigheden 25,01 + 25,01 > 50; med `network_fee_usdc=0` opstod to positioner (reproduceret: `sol=2001`, 2 fills). | `PaperBook.fill(..., expect=state)`: bogføringen sammenligner `usdc/sol/cost/fills` med beslutningens tilstand inde i skrivetransaktionen og afviser ved ændring. Runneren sender altid `expect`. |
| F4 | Lav (beløb) | `atoms()` ganger i Decimal-standardkonteksten (28 cifre), så fx `1000000000.0000000009999999999` SOL blev stiltiende til `1000000000000000001` atomer, trods testnavnet "never silently round". | Eksakt `scaleb` i en lokal kontekst med `Inexact`/`Rounded` som fejl; størrelse tjekkes før `int()`. |
| F5 | Lav (fejlrapport) | Hvis `BEGIN IMMEDIATE` fejler (fx "database is locked"), kaldte `except` blindt `ROLLBACK` og erstattede den rigtige fejl med "cannot rollback - no transaction is active". | `ROLLBACK` kun når `in_transaction`. |
| F6 | Lav (journal) | Kun `Rejected` blev journalført som `BLOCKED`. En `RuntimeError`, sqlite-fejl eller et ikke-`Quote`-svar fra udbyderen efterlod ingen BLOCKED-række. | Alle undtagelser journalføres som `BLOCKED` med type og tekst og kastes videre. En `Quote`-typekontrol er tilføjet. |
| F7 | Lav (transport) | Fejl under `response.read()` (`IncompleteRead`, `ConnectionResetError`) blev ikke til `Rejected`. Dublerede JSON-nøgler blev stille "sidste vinder". | Bredere, men eksplicit fejlhåndtering. `strict_json` (i `core.py`) afviser dublerede nøgler og NaN/Infinity og bruges også til snapshot- og tilbudsfiler. |
| F8 | Lav (kontrakt) | Svar med `swapMode` ≠ `ExactIn` eller `feeMint` uden for de to aktiver ville blive accepteret, selvom bogføringen forudsætter exact-in-output efter gebyr. | Begge afvises, når felterne findes. Et manglende felt er stadig tilladt. |
| F9 | Lav (input) | Ugyldige nyhedsfelter (titel som tal, `url=None`, ikke-objekt) gav `AttributeError`/`TypeError` i stedet for en kontrolleret afvisning. | Typekontrol og `Rejected`. |
| F10 | Lav (afrunding) | Ved delsalg blev fjernet kostpris rundet ned, så realiseret P&L kunne blive op til 1 atom bedre. | Rundes op: afrunding kan kun gøre resultatet dårligere. |
| F11 | Lav (rækkefølge) | `quote --out <beskyttet/eksisterende sti>` brugte først et rate-begrænset netværkskald og fejlede bagefter. Fundet af den nye netværksvagt i testene. | Destinationen kontrolleres før kaldet. |

Testvagter: `tests/guard.py` patcher `socket.connect`, `create_connection` og
`getaddrinfo` i alle testmoduler. En AST-test kontrollerer, at intet modul i
`jupiter_bot/` importerer `copybot`.

## Gennemgået uden fejl

- Heltalsbalancer, `CHECK(>= 0)`, `UNIQUE(account, quote_id)` og `BEGIN IMMEDIATE`
  forhindrer negativ saldo og dobbelt-fill af samme tilbud, også efter genstart.
- Swapgebyr fratrækkes ikke to gange: bogføringen bruger `outAmount` og lægger
  kun de to navngivne antagelser til (25 bps, 0,01 USDC). Demoens udbyder
  regner selv 50 bps ind i `outAmount`, i overensstemmelse hermed.
- Tilbud, papirfill og onchain-handel blandes ikke sammen: der er ingen
  signering, `taker`, POST eller `/execute`. `state()` og fill-audit siger nu
  også eksplicit `onchain_confirmed: false` og `kind: PAPER_SIMULATED`.
- Frosne grænser pr. konto og adskilte konti for `SYNTHETIC` og `JUPITER_QUOTE`.

## Ikke verificeret / tilbageværende risici

- **Opdatering 2026-11-20 (live-svar):** Tre rigtige `/order`-svar ligger
  nu som fixtures. For `metis` er `outAmount` målbart netto efter `feeBps` i
  begge retninger, også når `feeMint` er input-mint. For `jupiterz` (RFQ) er
  gebyret ikke specificeret, men rutens output er lig `outAmount`. Ingen
  dobbelt fradrag er dermed bekræftet for `metis` og sandsynligt for RFQ.
  Jupiters dokumentation er stadig ikke læst direkte.
- Udløb: ingen af de tre svar har et udløbsfelt (`expireAt` e.l.). RFQ-svaret
  har `quoteId`, `maker` og `guaranteedPrice: true`, men ingen tid. De faste
  15 s bevares. RFQ-tilbud kan i praksis udløbe hurtigere; det kan først
  måles med `/execute`, som er uden for denne opgave.
- Netværksomkostning: uden `taker` er `signature/prioritization/rentFeeLamports`
  0, og `gasless` varierer. Papirbogens 0,01 USDC er derfor stadig en antagelse.
- Rate-grænsen (2,1 s) gælder pr. proces. Søgeresultater angiver nøglefri
  adgang til 0,5 RPS (30 kald/60 s) pr. konto/IP. Flere samtidige CLI-processer
  kan overskride den. Der er ingen fælles limiter på tværs af processer.
- `quote_id` er hash af svar + lokale tider. Det samme upstream-svar gemt med
  andre tider får et nyt id. Friskhedsgrænsen på 15 s begrænser konsekvensen;
  upstream `requestId` som ekstra nøgle kan overvejes.
- EMA-referencen startes på den første lukning i det leverede vindue, så
  resultatet afhænger af snapshot-længden. Den er kun til rørføring (se P2).
- Den gamle papir-DB-version uden `application_id` afvises nu. En sådan fil
  skal erstattes af en ny. Det er bevidst.

## Kommandoer

```bash
python -m unittest discover -s jupiter_bot/tests -v   # 46 tests OK (26 oprindelige + 20 nye)
python -m jupiter_bot demo                           # 2 syntetiske fills, uændret resultat
python -m compileall -q jupiter_bot && git diff --check
```
