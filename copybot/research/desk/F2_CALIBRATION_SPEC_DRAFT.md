# F2 — kalibreringsspecifikation for explore0 (UDKAST, direktørordre 53 P0)

**Version `F2_CALIB_SPEC/0-draft`, skrevet 2026-11-06 ca. 15:30 UTC (16:30 lokal). Status: UDKAST. Ikke godkendt og ikke kørbar.**

- Der findes ingen kalibreringskode, og den skrives først, når specifikationen er godkendt.
- Dataadgang kræver G01 (≥ 2026-11-14 00:00 UTC) og ejerens udtrykkelige, daterede ja til netop denne version og dens
  sha256 (AMB-09).
- Specifikationen ændrer ikke den låste F2 (`FACTORY_P2_PROTOCOLS_2026-11-06.md` L78-123, L194-205).
- Punkter, der kræver en MATERIEL ÆNDRING, er markeret **[MATERIEL]**. De gælder kun, hvis ejeren har godkendt F2 v2
  før adgang. Ellers gælder v1-faldbakken i samme punkt.

## 1. Formål og status

- **Låst:** "kalibrering i explore0 (2020-03..2021-12, udforskning, ingen alfa, aldrig bevis) estimerer kun sd(d) og
  autokorrelationen … Kalibreringen må ikke ændre model, univers eller benchmark" (L107-109).
- **Direktøren:** "explore0-kalibreringen må kun estimere effektstørrelse og varians. Bruges den til GO/NO-GO, er den
  udviklingsinformation og aldrig uafhængig validering" (L198-199).
- Kalibreringen er **udviklingsinformation**. Den er aldrig bevis, giver ingen alfa, ingen PASS og ingen afgørelse om
  HAR mod EWMA. Hvert output bærer `"window": "explore0", "evidence": "development_only"` (DATA_CONTRACT afsnit 7).

## 2. Hvad der estimeres

| Størrelse | Definition | Hjemmel |
|---|---|---|
| sd(d) | pooled standardafvigelse af d_{i,t} = QLIKE(EWMA) − QLIKE(HAR) over scorede mønt-døgn | L107 "sd(d)" |
| autokorrelation | ACF af dbar_t, lag 1..5; HAC-faktor h = 1 + 2·Σ_{k=1..5} (1 − k/6)·ρ_k (Bartlett, som DM-testen) | L107-108 "autokorrelationen" |
| ρ_c | middel af parvise korrelationer af d_{i,t} mellem mønter over fælles døgn | L120-121 "den målte tværsnitskorrelation" |
| e | middel(d)/sd(d) pr. mønt-døgn, kun som rapporteret effektstørrelse | direktøren: "effektstørrelse og varians" |
| projiceret styrke | `p2_power.dm_power(e*, N, T_conf, ρ_c målt, α 0,05, h målt)` for e* ∈ {0,02; 0,05; 0,08; 0,10} | L119-121 |

- **Bekræftelsens måldøgn** er T_conf = 334 under B23 og 335 under A24/A23, aldrig 730 (AMB-04, punkt 9 i forslaget).
  N = antal mønter, der vil bestå 100 %-reglen i bekræftelsesvinduet. N kendes først ved bekræftelsens
  dækningstjek. Kalibreringen projicerer derfor ved N = 20 og N = 10.
- **GO-reglen (låst):** "e ≥ 0,08 giver styrke ≥ 0,8 ved den målte tværsnitskorrelation".
  - Den bruger den hypotetiske e* = 0,08 og den målte ρ_c (og h). Den målte e indgår ikke.
  - At bruge den målte e til GO/NO-GO ville være en afvigelse fra den låste GO-regel → **[MATERIEL]**. Den målte e
    rapporteres kun.
- **Forhåndsudsagn (fra forslagets punkt 9):** ved T_conf = 334, N = 20 og h = 1,5 kræver GO ρ_c ≤ 0,19. Er den målte
  ρ_c højere, er udfaldet INSUFFICIENT POWER efter den låste regel. Et redesign er da et nyt, versionsstyret udkast,
  aldrig en justering af denne kørsel.

## 3. Hvad der ikke estimeres eller ændres

- Model, lags (1, 7, 30), HAR-vinduet på 365 rækker, benchmark (EWMA 0,94), univers, QLIKE, DM-testen, 5 HAC-lags,
  K = 1 og α ændres ikke.
- Konventionerne fra `F2_AMBIGUITY_RESOLUTION_PROPOSAL.md` vælges før adgang og ændres ikke bagefter. Kørslen sker
  under præcis én konvention, aldrig under flere med et valg bagefter.
- Ingen tuning: ingen alternative λ, vinduer, gulve, vægte, mønter eller tærskler.
- Der fittes ingen tværsnitsvægte i explore0 (AMB-08: lige vægt).
- Ingen DM-p-værdi eller t rapporteres som resultat. Hvis t beregnes som mellemregning, gemmes den kun i
  `development_only`-filen uden fortolkning.

## 4. Konventioner (fastlåses ved godkendelsen af denne spec)

| Emne | v2 (hvis godkendt) | v1-faldbak |
|---|---|---|
| RV-døgn | B23: closes af barer D−1 23:00..D 22:00, 23 afkast **[MATERIEL]** | A24: closes af barer D−1 23:00..D 23:00, 24 afkast; aldrig baren åbnet D+1 00:00 |
| sidste input / cutoff | bar D 22:00, endelig D 23:00 | bar D 23:00, endelig D+1 00:00 (= målstart) |
| HAR | 365 rækker, 395 sammenhængende komplette døgn, OLS uden udfyldning | samme |
| HAR ≤ 0 | gulv = mindste positive mål-RV i egne rækker, tælles; > 1 % → markeret **[MATERIEL]** | tælles; ingen regel i v1. I kalibreringen udelades intet: forekomster tælles og rapporteres som specifikationshul |
| EWMA | s₀ = første RV i løbet, indkøring 50, løbet afkortet til 395, genstart ved hul | samme |
| dækning | 100 % af timebarerne i explore0 pr. mønt, mekanisk før noget tab | samme |
| flade døgn | RV = 0 → ufuldstændigt døgn, tælles | samme |
| vægte | lige vægt over scorede mønter pr. døgn | samme |
| vindue | 2020-03-01..2021-12-31; første RV-døgn 2020-03-02 (B23/A24); første mål 2021-04-01; 275 mål | samme |

## 5. Dataidentitet ved adgang (DATA_CONTRACT afsnit 6)

1. **Kun disse filer:** `data/futures/um/monthly/klines/<SYM>/1h/<SYM>-1h-YYYY-MM.zip` for de 20 mønter og
   månederne 2020-03..2021-12 fra cachen.
   - Ingen 2020-02-fil: den behøves ikke, fordi første RV-døgn er 2020-03-02.
   - Ingen 2022+-fil.
   - Manglende filer hentes kun ad lab'ets hentevej (højst 2 samtidige, `absent_404.json`) og kun efter G01.
2. **Før nogen fil fortolkes** committes et manifest. Pr. fil: sti, størrelse, sha256 og cachens filtid. Dertil
   manifestets egen sha256.
   - Lokale hashes mærkes **POST_HOC_IDENTITY**. Filerne blev hentet før låsen (10-17 og 10-19).
   - Værtens `.CHECKSUM` kan hentes efter G01 og mærkes **CHECKSUM_SAME_SOURCE**.
   - Begrænsningen ("ingen betroet lås før data") står i outputtet.
3. **Ved læsning** genberegnes sha256. Afvigelse fra manifestet → BLOCK, og intet læses.
4. **Rækkefilter:**
   - en række med `open_time` < 2020-03-01 00:00 eller ≥ 2022-01-01 00:00 kasseres og tælles (deterministisk
     overskriftsregel som i DATA_CONTRACT afsnit 3);
   - en række ≥ 2024-01-01 → BLOCK af hele kørslen.
5. **Rækkefølge:** dækningstjekket (100 %) kører og committes, før noget RV eller tab beregnes. Udelukkede mønter
   står med årsag.

## 6. Output (`research/data/f2_calib/`, adskilt fra enhver journal)

- `calib.json`, kanonisk og med deterministisk sha256. Indhold:
  - spec-version og sha256, manifest-sha256, konvention (v1/v2), konfigurations-hash;
  - mønter med/uden og årsag, antal scorede mønt-døgn, void-tællinger efter årsag, antal gulvede HAR-prognoser og
    antal flade døgn;
  - sd(d), ACF lag 1..5, h, ρ_c og e (markeret `reported_only`);
  - den projicerede styrketabel og GO-reglens udfald: `GO_ELIGIBLE` (styrke ≥ 0,8 ved e* 0,08) eller
    `INSUFFICIENT_POWER`;
  - `"window": "explore0"`, `"evidence": "development_only"`.
- `calib.md`: en beskrivende tekst uden konklusionsord om HAR mod EWMA.
- Ingen prognoser skrives i en C1-journal (DATA_CONTRACT afsnit 7). Ingen tal sendes til PROTOCOL_V3 som evidens.
- En anden kørsel med samme input skal give samme sha256. Et eksisterende `calib.json` med anden hash overskrives
  aldrig (som milepælsværktøjerne i ordre 52).

## 7. Godkendelse og rækkefølge

1. Ejeren beslutter v1 eller v2. v2 betyder en ny F2-version med B23, HAR-gulv og W0-oversættelse.
2. Denne spec fryses som version `F2_CALIB_SPEC/1` med sha256.
3. Ejerens udtrykkelige, daterede ja nævner version og sha256. Direktørens CONDITIONAL er ikke nok, og "gør alt"
   tæller ikke.
4. Kode og syntetiske tests skrives (genbrug af `f2_timeline.py`-konventionerne), og fuld suite skal være grøn.
5. Efter 2026-11-14 00:00 UTC: manifest-commit → dækningstjek-commit → én kørsel → resultat-commit.
6. GO-udfaldet er udviklingsinformation. Det gør F2 "klar til godkendelse" (L119), men godkender hverken
   bekræftelsesvinduet (direktøren: særskilt godkendt vindue, G16) eller noget andet.

## 8. Hvad der kræver MATERIEL ÆNDRING, hvis det ønskes

- B23 i stedet for A24 (punkt 4).
- Et HAR-gulv eller en anden regel for HAR ≤ 0 (punkt 4).
- Målt e i GO-reglen i stedet for e* = 0,08 (punkt 2).
- Overført opvarmning fra explore0 til bekræftelsen (730 mål i stedet for 334).
- En dækningsregel under 100 % (99 %).
- Ikke-lige tværsnitsvægte.
- Enhver ændring af vindue, univers, model, benchmark eller test.

## 9. Kendte begrænsninger

- explore0 er 2020-2021, et usædvanligt marked (DeFi-sommer, tyrmarked 2021). sd(d) og ρ_c kan være andre i
  2022-2023. Styrkeprojektionen er en projektion, ikke en garanti.
- Med 100 %-reglen får explore0 sandsynligvis 15 mønter (SOL, AVAX, DOT, DOGE og FIL er sandsynligvis noteret efter
  2020-03, ifølge filnavne), mens bekræftelsen kan få 20. ρ_c kan afhænge af sammensætningen.
- 275 mål × 15 mønter giver et upræcist estimat af ρ_c og h. Usikkerheden (bootstrap på døgnblokke, deterministisk
  seed) rapporteres. Ved grænsetilfælde vælges den konservative ende: øvre 80 %-grænse for ρ_c og h ved GO-reglen.
  **Dette er en skærpelse, som ejeren skal bekræfte.**
- explore0-1h-klines er brugt af udforskningsbanen (ændring 10-11). HAR-mod-EWMA er ikke set.
