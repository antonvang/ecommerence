# BREADTH_VS_PRIMARY P2 — bred screening mod én primær hypotese pr. familie (direktørordre 48 P2, frist 12/11)

Kode `research/tools/breadth_vs_primary.py`, tests `tests/test_research_breadth_vs_primary.py` (4), data
`research/data/breadth_vs_primary/report.json` + `report.md` (sha256 i report.md; genkørt med klynge-intervaller, samme punktestimater). **Kun syntetiske data**; ingen
alfa, ingen markedsdata, ingen deploy.

## Opsætning

- 8 mekanismefamilier pr. verden, hver med sit eget observerede, vedvarende kendetegn z_f (AR(1), φ 0,9). I hver
  signalverden er 3 tilfældige familier ægte: z_f med en **tilfældig sand forsinkelse 1-6 dage** flytter næste afkast
  med ic · σ_t · z_f. De øvrige 5 er støj. 24 aktiver × 500 dage, markedsfaktor, Student-t, volatilitetsregime,
  5 bp pr. omsætning, ensidet HAC-t på netto, netto > 0 krævet.
- 42 stærkt korrelerede varianter pr. familie (forsinkelse k 1-6 × udglatning m 1-21 dage), 336 i alt.
- **A bred:** alle 336, Holm over 336. En familie er fundet, hvis én af dens varianter vælges.
- **B primær:** én variant pr. familie, fastlagt før data af en regel, der **ikke kender** den sande forsinkelse
  (k 1, m 3: nyeste information, let udglattet; samme for alle familier), Holm over 8.
- **C udforsk → bekræft:** første halvdel vælger hver families bedste variant (udforskning, ingen korrektion, aldrig
  evidens); anden halvdel tester kun de 8 valg, Holm over 8.
- 100 verdener pr. scenarie (nul, ic 0,015, 0,02, 0,03); mål på mekanismeniveau med Wilson 95 %-intervaller.

## Resultat

| Scenarie | Tilgang | FWER (mekanismer) [95 % CI] | Styrke pr. ægte mekanisme [95 % CI] | Ægte fundet / verden | Beregninger / verden | CPU s / verden |
|---|---|---|---|---|---|---|
| nul | A | 0,000 [0,000; 0,037] | — | 0 | 336 | 3,9 |
| nul | B | 0,010 [0,002; 0,054] | — | 0 | 8 | 0,09 |
| nul | C | 0,020 [0,006; 0,070] | — | 0 | 344 | 2,0 |
| ic 0,015 | A | 0,010 | 0,043 [0,025; 0,073] | 0,13 | 336 | 3,9 |
| ic 0,015 | B | 0,020 | **0,103** [0,074; 0,143] | 0,31 | 8 | 0,09 |
| ic 0,015 | C | 0,050 | 0,057 [0,036; 0,089] | 0,17 | 344 | 2,0 |
| ic 0,02 | A | 0,000 | 0,120 [0,088; 0,162] | 0,36 | 336 | 3,9 |
| ic 0,02 | B | 0,020 | **0,190** [0,150; 0,238] | 0,57 | 8 | 0,09 |
| ic 0,02 | C | 0,020 | 0,077 [0,052; 0,112] | 0,23 | 344 | 2,0 |
| ic 0,03 | A | 0,010 | 0,510 [0,454; 0,566] | 1,53 | 336 | 3,9 |
| ic 0,03 | B | 0,020 | **0,563** [0,507; 0,618] | 1,69 | 8 | 0,09 |
| ic 0,03 | C | 0,010 | 0,263 [0,217; 0,316] | 0,79 | 344 | 2,0 |

C valgte den rigtige forsinkelse i 23-27 % af de ægte familier (tilfældigt gæt: 17 %).

## Svar på direktørens spørgsmål

1. **Ja, i disse verdener finder én blind primær hypotese pr. familie flest ægte mekanismer** ved alle tre
   effektstørrelser. Ved små effekter er forskellen klar (0,10 mod 0,04 og 0,19 mod 0,12; intervallerne overlapper
   ikke ved ic 0,015). Ved ic 0,03 overlapper intervallerne (0,56 mod 0,51). B koster 8 beregninger mod 336 (cirka
   40 gange mindre CPU).
2. **Alle tre holder familiefejlen** på mekanismeniveau (punktestimater 0-5 %, øvre CI-grænse højst 0,112 med 100
   verdener). Bred testning med Holm er altså ikke farlig; den er bare ineffektiv: korrektionen over 336 varianter
   æder styrken, når effekterne er små.
3. **Udforsk-og-bekræft på samme vindue er den dårligste tilgang her.** At halvere data koster mere, end det er værd
   at vælge varianten ud fra data, og valget rammer kun lidt bedre end tilfældigt. Bred screening er nyttig til
   idéudvikling (at opdage, at en familie overhovedet rører sig), ikke som bekræftende test på samme data.
4. **Ingen tilgang når 80 % styrke** ved ic 0,03 med 500 dage. Det er samme budskab som P1 og ordre 47 P2: med de
   tilladte historiske vinduer kan kun store effekter bekræftes.

## Forbehold (UNKNOWN)

- B's fordel afhænger af, at den forhåndsvalgte variant ligger i nærheden af den sande. Her gør persistensen φ 0,9
  naboforsinkelser stærkt korrelerede. Med lav persistens eller en sand mekanisme langt fra den forhåndsvalgte (fx
  lang forsinkelse) mister B, mens A er robust. Det er argumentet for, at den primære variant skal begrundes
  økonomisk på forhånd, og for at en dårligt begrundet familie hellere skal udforskes på separate data end testes
  bredt.
- Ét verdenssæt, én omkostning, ét univers; strukturbrud og afnoteringer er ikke modelleret.

## Konsekvens for fabrikken

Bekræftende tests: én økonomisk begrundet primær variant pr. familie (K = 1), Holm over familier. Bred screening kun i
udforskningsvinduet (explore0) eller på data, der aldrig genbruges til bekræftelse, og altid registreret i ledgeren.

## Klynge-intervaller (tilføjet efter direktørens P2-svar)

Percentil-bootstrap over verdener (2.000 træk, fast seed); verden er enheden, fordi mekanismer i samme verden deler
afkast. Punktestimaterne er de samme som i P2 (deterministiske seeds).

| Scenarie | A bred | B primær | C split | B − A (parret pr. verden) |
|---|---|---|---|---|
| ic 0,015 | [0,023; 0,067] | [0,070; 0,140] | [0,030; 0,083] | +0,060 [0,027; 0,093] |
| ic 0,02 | [0,087; 0,157] | [0,153; 0,233] | [0,050; 0,107] | +0,070 [0,027; 0,113] |
| ic 0,03 | [0,450; 0,570] | [0,503; 0,623] | [0,213; 0,313] | +0,053 [0,000; 0,107] |

Klynge-intervallerne ligner Wilson-intervallerne her. Den parrede forskel B − A er positiv med et interval over nul ved
ic 0,015 og 0,02 og på grænsen ved ic 0,03 (nedre grænse 0,000). Konklusionen fra P2 holder: B er mindst lige så god
som A og bedre ved små effekter, i disse verdener.
