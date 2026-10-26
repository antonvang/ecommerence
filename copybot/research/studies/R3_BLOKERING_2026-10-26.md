# Mission 21: hvorfor R3 først står til 14/11, og hvad der kan starte nu

Skrevet 2026-10-26 kl. 21:40 lokal (20:40 UTC) af Claude på brugerens anmodning (Mission 21). Kun læsning af protokol,
kode og cache. Intet hentet, ingen regel ændret. Forslaget i afsnit 4 er **ikke vedtaget**.

## 1. Hvad blokerer R3 — én ting ad gangen

| Slags | Findes? | Hvor | Indhold |
|---|---|---|---|
| Teknisk | **nej** | `lab/r3.py`, `tests/test_lab_r3.py` (6 OK, kørt 2026-10-26 aften) | Koden er færdig: `fetch` (44 filer, 2 delte slots, sha256, `fetch_log.jsonl`) og `run` (én screening fra cachen). Kalenderen er cachet (58 planlagte begivenheder, 57 UTC-døgn). Det eneste stop er konstanten `FETCH_FROM = 2026-11-14 00:00 UTC` (`lab/r3.py:39`, `:70`). |
| Protokol | **ja** | `research/PROTOCOL_V3.md` ændring 24 punkt 2 | "Data (først fra 2026-11-14 00:00 UTC, brugerens regel; koden afviser tidligere)". Metoden (punkt 3-10) er låst før data og afhænger ikke af datoen. |
| Brugerens tilladelse | **ja — den egentlige blokering** | brugerens beskeder 2026-10-24 kl. 18:19 UTC ("Ingen nye historiske forespørgsler før 2026-11-14. Ingen omgåelse af denne begrænsning.") og gentaget i hver mission siden, senest Mission 21 punkt 5 | Ændring 24 punkt 2 henviser hertil. Kun brugeren kan ophæve den. |
| Beskyttet holdout | **nej** | ændring 10c (explore0 = 2020-03..2021-12); 2024 er holdout; 2025+ læses aldrig | R3 læser kun BTCUSDT/ETHUSDT 1m i 2020-03..2021-12 = explore0. Ingen holdout berøres, uanset dato. |
| pm_lp | **nej før 10-31** | ændring 10b punkt 1; hukommelse/pm_lp-regel B | Den oprindelige grund til 14/11 var pm_lp's D1-holdout **2026-10-31..11-13** (indsamlerens net under holdout). Før 2026-10-31 00:00 UTC er pm_lp i udviklingsperioden, hvor dækning ikke er en gate. Ingen pm_lp-regel forbyder en hentning 10-27..10-30. |
| Manglende data | ja, men det er netop hentningen | `data/lab/market/klines_1m/` findes ikke i produktionen | 0/44 filer, som krævet. |
| Utilstrækkelige tests | **nej** | `tests/test_lab_r3.py` | Afvist hentning, 404, fejl, log, regel og placebo er testet. |

### Sådan opstod datoen (sporbart)
1. **Ændring 10b (2026-10-19):** banens netvindue lukket 2026-10-24..11-14 af hensyn til pm_lp's D1 (10-31..11-13).
2. **Ændring 10d (2026-10-20):** vinduet blev **ophævet** for banens explore0-filer (`lab/explore.py:217`: "10d: any time").
3. **Fejl i Claudes eget udkast:** `research/drafts/DATAAUDIT_PLAN_2026-10-24.md` afsnit 5 skrev "Regel i dag: ændring 10b
   punkt 2" og anbefalede at vente til 14/11. Det overså 10d. (1m-filerne til R3 er ikke banens filer, så 10d dækkede dem
   ikke automatisk; men begrundelsen "pm_lp's holdout" gælder kun fra 10-31.)
4. **Brugeren 2026-10-24 kl. 17:19-18:19 UTC:** "Hvis hentning … er blokeret til 14. november, skal du respektere
   blokeringen", derefter som fast regel: "Ingen nye historiske forespørgsler før 2026-11-14."
5. **Ændring 24 (2026-10-25):** R3 låst før data med 14/11 som dato ("brugerens regel").

Datoen er altså en brugerregel, der oprindeligt hvilede på pm_lp's D1 — og den begrundelse dækker ikke 10-27..10-30.

## 2. Hvad R3 kan vise (styrke, beregnet uden at se begivenhedstimerne)
Ubetinget spredning af 1-times-afkastet (gennemsnit af BTC og ETH) i explore0 fra den cachede 1 t-serie: **0,96 %**
(16 103 timer, alle timer, ikke begivenhedstimer). Med 57 klynger og p ≤ 0,005 (z ≈ 2,81) er den mindste påviselige
gennemsnitseffekt ≈ **0,36 %** (makrotimer er mere urolige; realistisk ca. 0,5 %). Omkostningsgulvet er 0,46 %.
R3 har altså styrke omkring gulvet: et PASS kræver en stor, ensartet effekt; et FAIL lukker sporet med rimelig sikkerhed.
Forventet udfald skrevet før data (ændring 24 punkt 8): SCREEN_FAIL.

## 3. Hvad kan starte i dag (prioriteret efter informationsværdi pr. time)

| # | Arbejde | Tilladt nu? | Værdi | Status |
|---|---|---|---|---|
| 1 | **R3 tidligere** via ændring 24a (afsnit 4): 44 filer 10-27..10-30, én kørsel | kræver brugerens ja | høj: lukker/åbner makrosporet 19 døgn før | forslag klar; kode er en ændring af én konstant + test |
| 2 | FOMC 2026-10-28 (ændring 21d) | ja, låst | middel: første test af kæden bevægelse + nyhed + kalender | kører automatisk; rapport efter 10-29 19:00 UTC |
| 3 | depth500 (ændring 27) | ja, kører | middel: skelner tynd 20-niveaus-bog fra reelt dyr bog | 2 hændelser, begge reelt dyre (174-210 bp) |
| 4 | R1 foreløbig rapport | ja | høj for alle senere screeninger | tidligst 2026-10-31 |
| 5 | K3 indsamling | ja, kører | høj, men først ved 60 runder | 7/60 real, 8/60 placebo; datakvalitet auditeres hver runde; **intet afkast kigges på før testen** |
| 6 | R3F: fremadrettet minutreaktion efter nye udgivelser | ville kræve en ny dateret ændring og en fremadrettet kalender | lav: ca. 5 begivenheder/md → 15 klynger tidligst ca. februar 2027, mindste påviselige effekt ≈ 0,7 % | ikke bygget; anbefales ikke før R3's udfald kendes |
| 7 | Beskrivende bevægelsesanalyse (`opportunity.move/outcome`) | ja | lav nu: 23 bevægelser, 7 udfald siden 10-24 | for få til noget; venter |

Ingen screening er gjort på nye data, og ingen strategi er kaldt profitabel.

## 4. FORSLAG (ikke vedtaget): ændring 24a — R3's hentning før pm_lp's holdout

Tekst, der committes **først efter brugerens udtrykkelige ja**:

> **Ændring 24a (dato, før data):** Ændring 24 punkt 2's dato erstattes af to vinduer: hentningen må køre
> **2026-10-27 14:35 UTC … 2026-10-30 23:59 UTC** (efter S7-testgenstarten og før pm_lp's D1) eller fra 2026-11-14
> 00:00 UTC. Kun i K3's frie vinduer (XX:35-(XX+1):25 UTC, XX lige). Alt andet i ændring 24 og præciseringen er uændret:
> samme 44 filer, samme vært, højst 2 samtidige downloads, sha256 og `fetch_log.jsonl`, én kørsel, resultatet committes
> som `research/studies/R3_m24.json/.md` uanset udfald, nøglen screenes aldrig igen, ingen LÅS, ingen ordrer.

- **Kode:** `FETCH_FROM` bliver to vinduer; testene udvides (afvist 10-27 14:34, tilladt 14:35, afvist 10-31 00:00,
  tilladt 11-14). Fuld suite grøn. Kun CLI-modul → pull, ingen genstart af lab'en.
- **Konsekvenser:** ingen holdout, ingen pm_lp-regel og ingen metode ændres. pm_lp's D1 berøres ikke (hentningen slutter
  før 10-31). Belastning: 44 statiske filer, ca. 1-3 MB hver. Risiko: hvis hentningen ikke bliver færdig før 10-31,
  stopper koden og resten venter til 11-14 (intet hentes i D1).
- **Kræver:** brugerens ja til at ophæve sin egen regel "ingen historiske forespørgsler før 2026-11-14" **kun** for disse
  44 filer i dette vindue. Reglen gælder uændret for alt andet.

## 5. Beslutninger der reelt kræver brugeren
1. **Ændring 24a: ja/nej.** (Det eneste, der kan fremskynde R3.)
2. Intet andet blokerer: punkt 2-5 i afsnit 3 kører allerede under eksisterende tilladelser.
