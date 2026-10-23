# Audit af hypotesepipelinen (ændring 17) — 2026-10-22

Kun læsning af produktionens register (ca. 20:30–21:00 UTC). Ingen gate, tærskel eller hypotese er ændret.
Udforskning er aldrig bevis.

## Tal

116 nøgler er screenet på explore0 (2020-03..2021-12): 87 UNTESTABLE, 26 SCREEN_FAIL, 3 SCREEN_PASS.

### De 87 UNTESTABLE

Én formel årsag for alle 87: "færre end 15 hændelser med data". Udelukkelserne bag (summeret over nøgler):

| Underårsag | Udelukkelser | Hvad det betyder |
|---|---|---|
| for få timer | 775 | ingen perp-kurs i målevinduet |
| manglende pris | 771 | ingen perp-pris ved t (fx før perpen fandtes) |
| ingen pris inden for 72 t | 595 | ingen perp indtil 72 t efter t (17a) |
| for få funding-afregninger | 290 | ingen perp → ingen funding |
| vindue uden for fasen | 18 | slutter efter 2021-12 |

Typer med 0 hændelser i explore0: `futures_delisting`, `margin` (m17; 17c læser margin-titler), `funding_interval`,
`margin_tiers`. Typer med hændelser, men under 15 med data: `launchpool` (23), `staking` (32), `airdrop` (37),
`innovation_zone` (57), `spot_listing` (156), `delisting` (3), `futures_listing` (98, kun `ar_*`/`vol*`, der kræver en
pris ved t).

**Kontrol af kodefejl (stikprøve, 24 hændelser fra spot_listing, airdrop og innovation_zone):** de udelukkede mønter
havde ingen USD-M-perp i data.binance.vision i hændelsens måned eller måneden før (fx KSM, ALCX, GHST, QNT, FARM,
BADGER); hvor en perp fandtes (OMG, TRX), blev hændelsen brugt. Udelukkelserne er reelle: der mangler data, ikke kode.

**Fundet fejl uden virkning:** udfaldene læser `<MØNT>USDT`; perps med 1000-præfiks (1000SHIBUSDT, 1000XECUSDT) findes
ikke under det navn. I explore0 rammer det 5 hændelser (SHIB 2021-05-10 som spot_listing og innovation_zone; XEC
network_swap ×3, hvoraf kun 2021-11-04 er efter 1000XECUSDT's start 2021-09-16). Højst `spot_listing|far_1d` ville gå
fra n=13 til 14 (< 15); ingen afgørelse ændres. Ikke rettet: en ny metode kræver en ændring og giver ingen ny testbar
nøgle.

**Delisting:** af 22 afnoteringstitler i explore0 ville 16e's faste møntregel give ca. 45 mønter, men af 10 tjekkede
havde kun SRMUSDT en perp med data. Ingen ny metode.

### De 26 SCREEN_FAIL

Fejlede tjek (en nøgle kan fejle flere): p ≤ 0,005: 21; samme fortegn 2020 og 2021: 9; placebo p > 0,05: 8. Alle
afvisninger følger kriterierne.

**Blind vinkel (ikke ændret — kræver brugerens beslutning):** 7 af de 8 placebo-afvisninger har *ingen* placebo-værdi
(`p = None`), fordi placeboen flytter t 30 døgn *tilbage*, og en nynoteret mønt har ingen kurs dengang. Nøglerne:
`spot_listing|sar_1d`, `spot_listing|sar_7d`, `innovation_zone|sar_1d`, `innovation_zone|sar_7d`,
`futures_listing|far_1d`, `futures_listing|far_7d`, `staking|sar_7d`. For dem kan placebo-tjekket aldrig bestå.
Stærkest: `spot_listing|sar_7d` (n=113, middel −19,4 %, p=0,0001, negativ i både 2020 og 2021) og
`spot_listing|sar_1d` (n=117, −8,6 %, p=0,0001). Et andet placebo (fx en flytning *frem*) ville være en ændring af et
evalueringskriterium; den må kun ske efter brugerens beslutning og med dateret tekst før data.

### De 3 SCREEN_PASS og uafhængige data

| Nøgle | Screening (explore0) | Måling | Resultat |
|---|---|---|---|
| `futures_listing\|sar_7d\|m17` | n=91, −15,1 %, p=0,0001 | train3 | REJECTED, p=0,378 |
| `margin\|far_7d\|m17c` | n=93, −7,4 %, p=0,0044 | validation3 | REJECTED, p=0,907 |
| `margin\|sar_1d\|m17c` | n=287, −2,0 %, p=0,0012 | validation3 | REJECTED, p=0,443 |

De to margin-nøgler bruger de samme margin-meddelelser (samme fortegn, overlappende mønter) og er i praksis ét fund.
Screeningens træfrate på uafhængige data er indtil videre 0 af 3 (for lidt til at sige mere).

## Konklusion

- Ingen kodefejl, der ændrer en afgørelse. Den manglende testbarhed er manglende historiske data for nynoterede mønter.
- Blind vinkel: placeboen for "første tilgængelige pris" på nynoterede mønter — en beslutning for brugeren.
- Nye hypoteser kræver data, explore0 ikke har. Fremadrettede målinger (H5F, H5X) og `news-watch` samler evidensen.

## Tillæg 2026-10-23: den blinde vinkel er lukket (ændring 17e/17f)

Brugeren besluttede "fiks 4". Ændring 17e (tekst 64a9848 før kode 83a5392) giver de 7 nøgler ovenfor en placebo med
t + 30 d, når t − 30 d har under 15 hændelser (metode m17e); måling, alfa og låse er uændrede. Resultat i explore0:
`spot_listing|sar_1d|m17e` og `innovation_zone|sar_1d|m17e` SCREEN_PASS; de øvrige 5 SCREEN_FAIL, bl.a.
`spot_listing|sar_7d` (fremad-placebo −5,2 %, p 0,014) og `futures_listing|far_7d` (−11 %, p 0,0001) — dér fortsætter
faldet en måned senere, så det er ikke en hændelseseffekt.

Ændring 17f låste `spot_listing|sar_1d|m17e` (k 4, alfa 0,003125); `innovation_zone|sar_1d|m17e` blev ikke låst (14
hændelser i train3, 1 i validation3). Målingen: train3 n 28, −9,1 %, p 0,0069 (bestået); validation3 n 11, −2,9 %,
p 0,3525 ≥ 0,003125 → **REJECTED**. Screeningens træfrate på uafhængige data er nu 0 af 4. `lab hypo-audit` viser
stadig de 7 m17-nøgler under "uden placebo-værdi"; det er m17-resultaterne, og deres m17e-afgørelser står under deres
egne nøgler.

## Tillæg 2026-10-23 (eftermiddag): de 87 UNTESTABLE klassificeret efter afhjælpning

Kun læsning af registret (alle 123 screenede nøgler, seneste resultat pr. nøgle). Ingen gate, tærskel eller
hypotese er ændret. Brugeren bad om andelen, der kan løses med (1) teknisk rettelse, (2) bedre brug af eksisterende
data, (3) ny tilladt dataindsamling, (4) ingen forsvarlig løsning.

| Klasse | Nøgler | Hvilke | Hvorfor |
|---|---:|---|---|
| 1. Teknisk rettelse | 0 | — | Stikprøven ovenfor fandt ingen kodefejl; 1000-præfiks-fejlen rammer 5 hændelser og ændrer ingen afgørelse. |
| 2. Eksisterende data | 0 (højst 2) | `airdrop` med spot-baseret `vol_3d`/`volume_1d` | Spotkurser findes før t for højst 23 airdrop-hændelser; `staking` (14) og `launchpool` (8) når ikke 15. Volatilitet og volumen er ikke et handelbart afkast alene, så det er ikke forfulgt. Afkastudfaldene er allerede målt på spot (`sar_*`). |
| 3. Ny dataindsamling | 36 | `funding_interval`, `futures_delisting`, `margin_tiers` (hver 9) og `margin` under m17 (9; 17c læser titlerne) | 0 hændelser i explore0 (2020-03..2021-12): meddelelsestyperne fandtes ikke, eller titlerne nævnte ikke mønter. De kan kun samles fremad (`news-watch` kører, se nedenfor); explore0 er fast og 2022-2023 er train/validation. |
| 4. Ingen forsvarlig løsning | 51 | perp-baserede udfald (`ar_*`, `far_*`, `fund_7d`, `vol_3d`, `volume_1d`) for `spot_listing` 7, `innovation_zone` 7, `airdrop` 7, `staking` 8, `launchpool` 9, `delisting` 9, `futures_listing` 4 | Mønten havde ingen USD-M-perp ved t (nynoteret eller kun spot). For `futures_listing` kræver `ar_*`/`vol*` en perp-pris før noteringen — umuligt per definition. `delisting` har kun 3 hændelser i explore0. |

87 = 0 + 0 + 36 + 51. Konklusion: andelen af meningsfulde, testbare eksperimenter kan ikke øges med kode eller ved
at sænke krav; den kan kun øges med nye data.

### Nyhedskilden fremad (tjekket 2026-10-23 ca. 13:50 UTC)

Alle 60 aktuelle meddelelser i Binances tre kataloger (48 listing, 161 delisting, 49 news) var gemt; der mangler
intet. Siden 2026-10-22 har Binance næsten kun noteret TradFi-produkter (bStocks, TradFi-perps), så H5F/H5X
(ændring 16d/16f, 20 noteringer efter 2026-10-22) venter på markedet, ikke på en fejl.

### Uklassificerede meddelelser i explore0

938 af 1.833 Binance-meddelelser i explore0 passer ikke på nogen af de 13 typer; 136 af dem nævner mønter. Største
grupper: "Binance Liquid Swap Adds" 39, "Notice of Removal of (Trading Pairs)" 34, "Binance Futures Will Launch"
(uden "Perpetual", fx kvartalskontrakter) 27, "Binance Loans Adds Borrowable/Collateral/Loanable" 28, "Binance
Futures Will List" 8 og "Binance Futures: New Listings" 5. En ny type kræver en ny ændring (17 punkt 1). Ingen er
tilføjet: screeningen har indtil nu 0 af 4 træffere på uafhængige data, og hver ny lås halverer alfa. En ny type
bør kun låses ind med en mekanisme, der er skrevet før data — ikke fordi den findes i titlerne.
