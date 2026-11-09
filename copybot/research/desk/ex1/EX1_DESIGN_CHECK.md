# EX1_DESIGN_CHECK: syntetisk designkontrol (direktørordre 70 P2). UDKAST, IKKE LÅST

**Skrevet:** 2026-11-09 kl. 21:55 lokal (20:55 UTC, læst med `date`).

**Status:** kun syntetisk. Direktøren har afvist adgang til K3-data; ingen K3-række er åbnet, og modulet læser ingen
filer. EX1 er en beskrivende hypotese med lav forhåndssandsynlighed og ikke en dokumenteret handelsfordel. Tal fra
`ex1_design_check.py` (`report()`, 2.000 gentagelser, faste seeds). Sd 0,35 %, 52 fredage og 11 bp omkostning er
antagelser fra `ORIGINAL_DESIGNS_ORDER69.md` afsnit 3.

## Hvad kontrollen viste

**1. Den reelle styrke er ca. 75 %, ikke 80 %.** Ved en brutto-rekyl på 26 bp (15 bp netto) kun på fredage:

| Dom | Andel |
|---|---|
| PASS | 74,7 % |
| INCONCLUSIVE | 25,2 % |
| FALSIFIED | 0,2 % |

Notatets 80 % (0,78 med t(51)) gælder kun nettotesten. Placeboen kræver tosidet p > 0,05 og afviser derfor ca. 5 % af
sande effekter af ren tilfældighed. Det skal stå i en eventuel låsetekst.

**2. Falske PASS under nul:**

| Verden | PASS | FALSIFIED | INCONCLUSIVE |
|---|---|---|---|
| brutto 0 | 0 % | 99,1 % | 0,9 % |
| brutto 11 bp (netto 0) | 0,8 % | 49,9 % | 49,3 % |

**3. DiD-porten virker.** Med en daglig 08:00-effekt på 26 bp og intet udløb: PASS 4,2 %, PASS_NOT_EXPIRY 74,0 %,
INCONCLUSIVE 21,6 %, FALSIFIED 0,2 %. Porten tager næsten alle daglige effekter, men 4,2 % slipper igennem, som
ventet ved 5 %.

**4. Futilitetsstop ved 26 fredage.** Sandsynligheden for at stoppe ved en sand brutto-effekt:

| Brutto | Stop |
|---|---|
| 26 bp | 0,01 % |
| 11 bp | 5,6 % |
| 5 bp | 23,7 % |
| 0 bp | 50,1 % |

Stoppet koster næsten intet ved en reel effekt. Det hæver ikke fejlraten: andelen af bestået nettotest med stop
undervejs er 1,55 % (brutto 11 bp, inden for simuleringsstøj om 1,25 %).

**5. Datavej uden K3.** K3-vejen (første fredag 2026-11-20, dom 2027-11-12) er væk efter direktørens afslag. Tilbage er
kun `ex1/1`, som kræver dateret ejer-ja til datalinjen og deploy tidligst 2026-11-30:

| | Dato |
|---|---|
| Første tællende fredag | 2026-12-04 |
| Futilitet (26. fredag) | 2027-05-28 |
| Dom (52. fredag) | 2027-11-26 |

Der er 57 fredage frem til 2027-12-31, så der er plads til 5 ugyldige fredage før 52, og mindst 40 kræves.

## Huller i designteksten

Kontrollen fandt fire steder, hvor afsnit 3 ikke er entydig. Koden tager et valg; ingen af dem er godkendt.

1. **Net og DiD består, men placeboen fejler:** teksten siger kun, at PASS kræver placebo ok. Koden giver INCONCLUSIVE
   (`PLACEBO_FAILED`). Mangler placeboen, giver den INCONCLUSIVE (`PLACEBO_UNAVAILABLE`).
2. **Antal kontroldage:** teksten siger "middel af man-tor". Koden kræver mindst én gyldig kontroldag. Direktøren bør
   sætte et minimum.
3. **Omkostningens tidspunkt:** `book_rt` måles ca. 08:02, altså efter indgangen ved +1 min. Det påvirker kun
   omkostningen, ikke signalet, men er ikke strengt point-in-time.
4. **Tælling ved stop:** koden bruger de første 26 og 52 *gyldige* fredage. Teksten siger bare "fredage".

## Testet

`tests/test_ex1_design.py`: definitioner af r_pre, r_post, y og c_t; domstræet; designkontrollerne ovenfor; kalenderen;
at modulet ikke åbner filer og kun importerer stdlib plus t-testen fra LQ1-evaluatoren.

## Ikke gjort

Deribits regler og datoer er stadig UNVERIFIED (kun søgeresumé). Ingen K3-række, scanner-række eller markedsdata er set.
Ingen datalinje `ex1/1` er skrevet.
