# UDKAST — Ændring 12: scannerkonti — scannerens fund handles automatisk på papir (ikke godkendt, ingen kode)

Skrevet 2026-10-19 af Claude efter brugerens ønske ("når noget mærkeligt ... ændrer sig og kan være profitabelt,
handler vi på det"). Udkastet bliver først gældende, når brugeren godkender det. Derefter flyttes teksten ind i
`research/PROTOCOL_V3.md`, og først da skrives koden. Tal mærket [BEKRÆFT] er Claudes forslag.

**Uændret:** Ændring 10 punkt 1 og ændring 11 gælder: kun simuleret handel, aldrig bevis, ingen formelle rækker, ingen
saldo, ingen alfa. Kun F1's godkendte mekanisme (`lab/families/fcarry.py`) og instrumentmodel (`spot_perp_ratio`);
en ny mekanisme kræver fortsat en familie efter ændring 8.

## Baggrund (målt read-only i produktionens register 2026-10-19)

Scanneren (`perp_premium`, |mark/index − 1| ≥ 0,5 %) har siden 2026-10-17 markeret vedvarende præmier på mindre
mønter, fx ERAUSDT i 42 målinger (gennemsnit 1,6 %, maks. 3,8 %), GTCUSDT 32 (0,9 %) og SANDUSDT 16 (1,0 %). En
vedvarende positiv præmie trækker funding op, og funding er netop den pengestrøm, F1 høster (lang spot, kort perp).
Ingen afkastserie er beregnet; om det betaler sig efter omkostninger, er ukendt.

## Regler

1. **Udløser (hver time, ikke først i døgnets opgørelse).** En mønt er kandidat, når dens `perp_premium` i de seneste
   24 timer er markeret i mindst 6 forskellige klokketimer, medianen af den markerede præmie er positiv (lange
   betaler funding) og mindst 4 × omkostningsreferencen (samme regel som `scan_digest` i ændring 9). Negative præmier
   handles ikke: det ville kræve kort spot.

2. **Konto.** `SCAN_<10 hex>` med 10.000 USD (simuleret), én mønt. Regel: F1's `carry_filter` med `lookback_days` 1
   og `enter_apr` 0,219 [BEKRÆFT] — beslutning kl. 01:00 UTC som altid i F1, så en konto tidligst handler ved næste
   beslutning. Mængde = halvdelen af kontoens værdi pr. ben. Handel, omkostninger, funding, risikoregler og afstemning
   som banekontiene (ændring 11 punkt 4).

3. **Start.** Højst 3 aktive scannerkonti [BEKRÆFT], højst én pr. mønt, højst én ny pr. time. Begge ordrebøger skal
   kunne hentes; ellers `scan_account.skipped`. En mønt kan få en ny konto tidligst 7 dage efter, at dens forrige
   blev stoppet.

4. **Automatisk stop** (reducerende lukning som ændring 11):
   - tab ≥ 3 % af startkapitalen;
   - 24 timer på pause af en risikoregel;
   - kilden betaler ikke: funding − gebyrer ≤ 0 efter 7 dage [BEKRÆFT];
   - episoden er ovre: ingen position i 3 sammenhængende døgn efter en position [BEKRÆFT];
   - udløb efter 30 dage [BEKRÆFT];
   - brugerens `lane-off` stopper også scannerkonti.
   Der er ingen forventning fra historiske data (mønterne er ikke i `explore0`), så z-reglen gælder ikke.

5. **Ærlige forbehold.**
   - Små mønter: tynde ordrebøger og store spreads. Ordren går gennem bogens 20 niveauer, så slippage bogføres ærligt;
     spread-reglen pauser kontoen, og pausen stopper den efter 24 timer.
   - En høj præmie kan betyde forestående afnotering eller en presset short. Prisændringen på spot/perp-forholdet
     rammer kontoen, og tabsreglen stopper den.
   - Scannerens 0,5 %-tærskel og reglen i punkt 1 er ikke valgt efter afkast. Ingen af kontiene er bevis.

6. **Netværk.** Ingen nye værter: USD-M som i dag og spot-bogen fra `data-api.binance.vision` (ændring 11 punkt 8).
   Højst 3 ekstra mønter.

7. **Visning.** "SCANNERKONTO (scannerfund, simuleret, aldrig bevis)", adskilt fra formel saldo, fremadtest og
   banekonti, med udløser (præmie, timer, median) og stopgrund.

8. **Rækkefølge.** Brugerens godkendelse → tekst i protokollen → kode og tests i dev → brugeren deployer (regel B:
   ikke 2026-10-31..11-13).
