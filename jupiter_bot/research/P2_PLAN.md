# P2-forskningsplan: findes der en målbar fordel på SOL/USDC?

Status: **GODKENDT af Anton 2026-11-20** (i chatten: "godkend planen og lås den").
Låst med `python3 -m jupiter_bot.research.lock --approved-by Anton`, som gemmer
hashes af denne fil, `strategies.py` og `replay.py` sammen med git-commit i
`~/.local/share/jupiter-bot/research/plan_lock.json`.

Skrevet 2026-11-20, **før** nogen afkast- eller strategiresultater på de
indsamlede data er set. Kun antal rækker og fejl i journalen er set.

## 1. Spørgsmål

Kan en simpel, forhåndsfastlagt regel, der skifter mellem at holde SOL og
USDC via Jupiter, slå (a) kontanter og (b) tilfældige handler med samme antal
skift, **efter** målte Jupiter-priser og ekstra omkostninger, på data den
aldrig er tilpasset?

Forventningen er nøgtern: de fleste simple regler på ét marked i få uger
finder intet. Et "nej" er et gyldigt og nyttigt resultat.

## 2. Univers, data og frekvens

- Kun SOL/USDC. Ingen andre tokens, ingen valg af "dagens vindere".
- Signaler: Binance Spot SOLUSDC 1m-candles fra journalen, point-in-time
  (kun bars, der var set på beslutningstidspunktet, i den version der var
  kendt da).
- Priser for handler: **kun journalførte Jupiter-tilbud** (`/swap/v2/order`
  uden taker): 25 USDC → SOL til køb, 0,35 SOL → USDC til salg, ét pr.
  minut. Fill = første tilbud i rigtig retning observeret ≥ beslutning +
  forsinkelse. Intet tilbud inden for forsinkelse + 120 s → handlen
  registreres som `MISSING_QUOTE` og udføres ikke.
- Nyheder/statusfeeds bruges ikke som signal i P2.

## 3. Hypoteser og forsøgsbudget (i alt 4 konfigurationer)

### H1 — tidsseriemomentum (`tsmom`)
Mekanisme: information spreder sig langsomt, og trendfølgende flows giver
fortsættelse i krypto på timers til dages horisont (Moskowitz, Ooi og
Pedersen 2012; Liu og Tsyvinski 2021).
Regel: ved hver 4-timers UTC-grænse (00, 04, …, 20) er positionen LONG,
hvis log-afkastet over de seneste `lookback` minutter er > 0, ellers FLAT.
Positionen holdes til næste grænse.
Parametre: `lookback` ∈ {240, 1440} min, `rebalance` = 240 min. **2 forsøg.**

### H2 — kortsigtet reversal efter kraftigt fald (`reversal`)
Mekanisme: tvangssalg (likvidationer, stop-ordrer) skyder over målet, og den,
der leverer likviditet, får betaling for det (Nagel 2012).
Regel: LONG, hvis 30-minutters log-afkast < −k · σ · √30, hvor σ er
std af 1-minuts log-afkast over de 360 minutter før faldet. Positionen holdes
60 minutter efter, at betingelsen sidst var sand, derefter FLAT.
Parametre: `k` ∈ {2, 3}. **2 forsøg.**

Fravalgt på forhånd: CEX/DEX lead-lag (Binance foran Jupiter). Med ét tilbud
i minuttet og ≥ 60 s forsinkelse lukker arbitrageurer gabet på sekunder, før
vi kan nå det. Tidspunkt-på-døgnet-effekter: for få dage til at teste.

Koden er `jupiter_bot/research/strategies.py`. Registret `STRATEGIES` og
`TRIAL_BUDGET = 4` **er** budgettet. Flere forsøg kræver en ny plan og en
ny, fremtidig kontrolperiode.

## 4. Benchmark og negative kontroller

- **Kontanter** (0 %) og **hold SOL** (købt med første købstilbud i perioden,
  værdisat med salgstilbuddet ved periodens slutning). Begge rapporteres.
- **Tilfældige indgange:** 400 kørsler med tilfældig LONG/FLAT-rækkefølge og
  samme antal positionsskift som strategien, prissat præcis ens.
- **Blandede signaler:** strategiens egne beslutninger i tilfældig rækkefølge,
  400 kørsler.
- Faste seeds står i hver resultatfil.

## 5. Omkostninger og forsinkelse

- `outAmount` fra Jupiter er allerede netto efter `feeBps` (målt 2026-11-20)
  og trækkes ikke fra igen.
- Ekstra ugunstig pris pr. fill: 0, 10, **25** (primær) og 50 bps.
- Netværksgebyr: 0,01 USDC pr. fill (antagelse fra paper-bogen).
- Forsinkelse fra beslutning til tilbud: 60, **120** (primær) og 300 s.
- Positionsstørrelse: én enhed = 25 USDC. Salg prissættes ved lineær
  skalering af 0,35 SOL-tilbuddet. Ved disse beløb er prispåvirkningen lille,
  men det er en antagelse og står i resultatfilen.

## 6. Tidsopdeling

| Periode | Fra (UTC) | Til (UTC) | Brug |
|---|---|---|---|
| Udvikling | 2026-11-21 00:00 | 2026-12-19 00:00 | 4 uger. Alle 4 forsøg køres her. |
| Kontrol (uset) | 2026-12-19 00:00 | 2027-01-02 00:00 | 2 uger. Kun den valgte konfiguration, én gang. |

Kontrolperioden ligger i fremtiden, når planen låses, så ingen kan have set
den. Replay-værktøjet nægter at køre `holdout`, medmindre perioden præcis
svarer til den låste.

Dashboardet kan vise papirhandel løbende. Det er tilladt at se på den, men
**enhver ændring af regler, parametre eller kode efter 2026-12-19 gør
kontrolperioden ugyldig**, og så kræves en ny plan med en ny fremtidig periode.

## 7. Krav til datakvalitet før evaluering

- Candles: ≥ 95 % af minutterne i perioden.
- Jupiter-tilbud: ≥ 95 % af minutterne i begge retninger.
- Er kravet ikke opfyldt, er resultatet `INCONCLUSIVE_DATA`, ikke et ja eller nej.

## 8. Beslutningsregel

**Udvikling, pr. konfiguration** (primær: 120 s, 25 bps). `PASS_DEV` kræver alle fire:
1. Afkast efter omkostninger > 0 (slår kontanter).
2. Højst 1,25 % af de tilfældige kørsler og højst 1,25 % af de blandede
   kørsler slår strategien (5 % delt på 4 forsøg, Bonferroni).
3. Afkastet er stadig > 0 ved 300 s forsinkelse og ved 50 bps.
4. Mindst 10 afsluttede ture (køb og salg), og højst 5 % `MISSING_QUOTE`.

Færre end 10 ture giver `INCONCLUSIVE`. Ellers er resultatet `FAIL`.
Hold SOL rapporteres altid, men er ikke et krav, fordi en LONG/FLAT-regel kan
være værdifuld ved at undgå fald uden at slå et stigende marked.

**Valg:** består flere, vælges den med lavest andel slåede kontroller
(uafgjort: færrest handler). Kun den går videre til kontrolperioden.

**Kontrol, én kørsel efter 2027-01-02:** `PASS` kræver afkast > 0 ved 120 s
og 25 bps, at højst 5 % af de tilfældige kørsler slår den, og mindst 5 ture.
Færre ture giver `INCONCLUSIVE`, ellers `FAIL`.

**Ingen fordel fundet** (ingen `PASS_DEV` eller ingen `PASS`): P2 slutter med
"intet brugbart signal". Den eneste vej frem er en ny plan med en ny
fremtidig kontrolperiode. Gamle perioder genbruges aldrig som kontrol.

## 9. Hvad et PASS betyder, og hvad det ikke betyder

Et PASS betyder, at én forhåndsvalgt regel slog tilfældighed efter
omkostninger i 2 usete uger. Det beviser ikke fremtidig profit. 2 uger er
kort, og statistisk styrke er lav. Et PASS åbner kun for P3-gaten
`p2_holdout_pass`. Rigtig handel kræver stadig Antons mandat, review og en
lille, afgrænset start.

## 10. Registrering

Hver replay-kørsel skriver én fil i
`~/.local/share/jupiter-bot/research/evaluations/` med plan-hash, kode-hash,
journal-hash, alle handler, mangler og antagelser, også de dårlige kørsler.
Ingen fil overskrives. Fejlrettelser i `replay.py` efter låsning noteres
som tillæg nederst i denne fil med dato og begrundelse, før kontrolkørslen,
og aldrig efter.

## Tillæg

(ingen)
