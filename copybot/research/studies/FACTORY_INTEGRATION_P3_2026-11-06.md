# FACTORY_INTEGRATION P3 — beslutningsgrundlag for integration (direktørordre 48 P3, frist 14/11)

**Kun beslutningsgrundlag. Integrationen gennemføres ikke**, intet deployes, intet i laboratoriet ændres. Kilder:
ordre 47 P0-P3 og ordre 48 P0-P2 (commits nedenfor), INBOX 06/11.

| Leverance | Commit |
|---|---|
| Register + testbudget-ledger (47 P0) | df9c32d, 1b592ba, b032318 |
| Hypotesemotor (47 P1) | f7654ed |
| Protokoludkast F1-F3 (47 P2) | 8626fd7 |
| Shadow run (47 P3) | 70856c5 |
| Verificerbar ejergodkendelse (48 P0) | 808a056 |
| Migrationsplan v1 (48 P1) | ce67d14 |
| Bred screening mod én primær (48 P2) | 33147a8 (+ klynge-intervaller i denne commit) |

## 1. Sikkerhedsstatus

| Kontrol | Status | Hvad mangler før S2/S3 |
|---|---|---|
| Ejergodkendelse | Design + 9 syntetiske tests består (signatur bundet til blob, replay, udløb, delegering, generisk scope, fail-closed) | ejerens nøgle bundet til ejeren uden for allowed_signers; signering uden adgang for assistenten (ingen ssh-agent/oplåst nøgle på maskinen); ejerens egen opsætning |
| Revisionslog | Hashkæde opdager ændringer i kæden; manipulation på disk opdages | rollback-sikkert kontrolpunkt for seneste logtilstand uden for maskinen |
| Legacy-undtagelser | 65 eksperimenter klassificeret i `migration_v1.json`; resultater uændret; 30 godkendelsesrækker + familiegodkendelse = UNVERIFIED_ORIGIN | undtagelsen bindes til uforanderlig identitet (exp_id + spec_commit + protokolversion); nye forsøg kan ikke vælge et gammelt ID eller en legacy-status |
| Dataidentitet | Fabrikken kræver hashes ved låsen; laboratoriet hasher ved adgang | låsning af værtens checksummer med kilde, hentetid og låsetid; begrænsningen skrives i resultatet, når der ikke er betroet historisk bevis |
| Univers | Fabrikken afviser survivor-univers og manglende univers-dato | regel for kvalificerede mønter fastlagt før data; en rekonstrueret liste fremstilles aldrig som låst |
| Testbudget | Kun-tilføj, hashkæde, idempotent pr. forsøg, ingen tilbagebetaling | ingen (kører read-only i dag) |

## 2. Shadow-migration: de 60 historiske blokeringer

Fabrikken ville have blokeret 60 af laboratoriets 179 transitioner. Alle 60 er forklaret, og de overlapper på
eksperimentniveau:

| Eksperimenter | Årsager (alle på samme eksperiment) | Blokerede transitioner |
|---|---|---|
| 19 | instruks-citeret godkendelse + hash ved adgang + univers-dato mangler | registrering + screening |
| 9 | delegeret godkendelse ("Approved by Claude") + hash ved adgang + univers-dato mangler | registrering + screening |
| 4 | (fcarry; familiegodkendelse består) hash ved adgang + univers-dato mangler | screening |
| 25 | legacy-import | ingen (kun registrering, 1 forsøg) |
| 8 | aldrig screenet (PROPOSED) | ingen |

28 registreringer + 32 screeninger = 60. Alle 32 screeninger havde specen committet til git før screeningen, så
regler og vinduer var låst; det, der mangler, er dataidentitet før adgang og et point-in-time-univers. Risikoen for
survivorship nedgraderes ikke (P1-afgørelse).

## 3. Statistisk standard for nye bekræftende hypoteser

1. **Én primær variant pr. mekanismefamilie (K = 1)**, økonomisk begrundet, valgt og låst før evaluering (48 P2:
   højest styrke i alle testede effektstørrelser, ~40 gange mindre beregning). Mekanismegrænsen og slægten låses med
   (47 P2).
2. **Multipel test:** Holm over familier i samme vindue ved α 0,05 (ændring 2). En fremadtest trækker α_F = 0,0125 fra
   ændring 8's programformue (0,0375 tilbage = 3 familier). BH kun diagnostisk; N_eff bruges aldrig til at tælle færre
   forsøg.
3. **Styrkekrav før aktivering:** styrke ≥ 0,8 ved en forhåndsangivet, plausibel effekt, beregnet med
   `research/tools/p2_power.py`; ellers INSUFFICIENT_POWER/REDESIGN. Ændring 8 punkt 14 (≥ 0,5 ved SR 3,0, α_F/3)
   gælder fortsat som gulv for fremadtests.
4. **Bred screening** kun til idéudvikling: i explore0 eller på data, der aldrig genbruges til bekræftelse, altid
   registreret i ledgeren, aldrig evidens.
5. **Usikkerhed:** intervaller med verden (eller i rigtige data: tidsperiode/udløb) som klyngeenhed, når
   observationer deler et marked. Se afsnit 6.

## 4. GO/NO-GO-kriterier

| Trin | Beslutning nu | Kriterier for GO |
|---|---|---|
| S0 offline | **GO** (godkendt) | — |
| S1 read-only shadow (job skriver ALLOW/BLOCK til en separat fil, aldrig lab.db) | **GO til forberedelse** | jobbet er read-only (mode=ro), kører uden for laboratoriets processer, påvirker ikke papirbøger/pm_lp; første rapport efter 14 dage |
| S2 rådgivende kald i laboratoriet | **NO-GO** | 14 dage S1 uden uforklarede BLOCK og uden gatefejl; nøglebinding og rollback-sikker log verificeret; særskilt ejerbeslutning; deploy kun under de stående betingelser (uden for K1-K3, grøn suite) |
| S3 håndhævelse for nye eksperimenter | **NO-GO** | 14 dage S2 uden forskelle uden dokumenteret klasse; legacy-undtagelse bundet til uforanderlig identitet; checksum-låsning og point-in-time-univers implementeret og testet; særskilt ejerbeslutning med verificeret ejersignatur |

## 5. Tilbagerulning

- S1: stop og slet jobbet; ingen tilstand i laboratoriet.
- S2/S3: politikflag fra (tilbage til forrige trin) og git revert af integrationskoden; gaten gælder kun forsknings-
  overgange for eksperimenter oprettet efter cutover. **Papirbøger, baner, låste fremadtests (fcarry OBSERVATION,
  HFC-1, straks, carry90, parbog) og pm_lp er uden for gaten** og kan ikke blokeres af den. Tilbagerulning ved første
  uforklarede BLOCK af en eksisterende proces, enhver gatefejl eller enhver påvirkning af papirhandlen.

## 6. Klynge-intervaller (48 P2 genberegnet med verden som enhed)

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

## Anbefaling

**S1 GO til forberedelse; S2 og S3 NO-GO.** Det svarer til direktørens foreløbige beslutning. Integrationen er ikke
moden, før ejerens nøgle er bundet uden for repoet, auditloggen har et kontrolpunkt uden for maskinen, og
checksum-låsning og point-in-time-univers er bygget. Indtil da forbliver registret et read-only lag.
