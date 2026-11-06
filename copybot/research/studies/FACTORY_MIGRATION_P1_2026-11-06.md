# FACTORY_MIGRATION P1 — overgangsplan v1 (direktørordre 48 P1, frist 11/11)

Kode `research/tools/factory_migration.py`, tests `tests/test_research_factory_migration.py` (2), maskinlæsbar plan
`research/data/factory/migration_v1.json` (én række pr. eksperiment med klasser, låsebevis, universtype og
beslutninger). **Plan, ikke udført:** intet i laboratoriet ændres, ingen deploy, ingen markedsdata. Ingen historik
omskrives, ingen gate svækkes, og ingen papirbog stoppes.

## Fakta fra laboratoriet (read-only, 06/11)

- 65 eksperimenter, 179 transitioner. Klasser fra shadow-genafspilningen (ordre 47 P3): legacy 25, delegeret
  godkendelse 9 og instruks-citeret godkendelse 19 (28 registreringer fra 29 bekræftede skabelonhændelser),
  familiegodkendelse 4 (fcarry), hash-at-access 32, universe-asof-unrecorded 32. 0 uforklarede.
- **Låsebevis:** for alle 32 screeninger blev specen (regler, vinduer, univers, grid, omkostninger, afvisning)
  committet til git **før** screeningen startede (git-tid for `spec_commit` ≤ SCREENING-tidspunktet). Låsen før data
  findes altså som git-commit; det, der mangler, er en hash af data før adgang.
- **Univers:** alle 32 bruger faste symbollister (8, 16 eller 30 symboler), valgt i 2026 blandt nutidens store coins
  for vinduer i 2022-2023. Coins, der var store i 2022 og senere faldt bort (fx LUNA og FTT), er ikke med. Det er en
  reel survivorship-risiko for tværsnitsresultaterne (P3 målte +6 til +12 bp/dag i syntetiske verdener).

## Beslutning pr. legacy-klasse

| Klasse | Antal | Beslutning |
|---|---|---|
| legacy (import) | 25 | LEGACY_RECORD: beholdes som registreret, 1 forsøg i ledgeren (nedre grænse), testes aldrig igen |
| delegeret / instruks-citeret godkendelse | 9 + 19 | godkendelsen får UNVERIFIED_ORIGIN; resultater bevares som udforskende evidens; ingen ny instans af skabelonen uden en ny verificeret ejergodkendelse (P0) |
| familiegodkendelse (fcarry) | 4 | UNVERIFIED_ORIGIN (teksten kan ikke bevise ophav); familiens låste fremadtest fortsætter efter sine egne regler og blokeres ikke |
| hash-at-access | 32 | HASH_AT_ACCESS: hashes identificerer, hvad der blev læst; låsen før data er spec-committen; en hash beregnet i dag af gamle data mærkes POST_HOC_IDENTITY og fremstilles aldrig som en lås |
| universe-asof-unrecorded | 32 | SURVIVORSHIP_UNKNOWN: flaget følger tværsnitsresultaterne; ingen gentest (en gentest er et nyt eksperiment med nyt budget) |
| human-verdict | 1 | uændret |

Ingen resultater ændres. Ingen afvisning bliver til en godkendelse, og ingen godkendelse bliver "verificeret".

## Krav til nye screeninger (efter en fremtidig cutover)

1. **Hash ved låsen uden at læse data.** Låsen binder datasættets identitet, ikke indholdet: filnavne og de
   checksummer, data-værten selv offentliggør pr. fil (data.binance.vision har en `.CHECKSUM` pr. zip), hentes og
   registreres ved låsen. Ved adgangen skal den downloadede fils sha256 matche den låste checksum; ellers BLOCK.
   Hentningen af checksummer er en forespørgsel mod en historisk vært og følger datagrænserne (tidligst 14/11, aldrig
   2024-holdout, COIN-M først fra 28/11).
2. **Univers som regel, point-in-time.** Universet defineres som en regel (fx "alle USD-M-perps noteret før
   vinduets start med mindst N dages historik, inkl. senere afnoterede") med `universe_asof` = vinduets start.
   Medlemslisten afledes af arkivets filindeks (som også viser afnoterede symboler) og låses med checksummerne.
3. **Godkendelse:** ny skabelon kun med en verificeret ejersignatur (P0), bundet til skabelonens blob.
4. **Regnskab:** én idempotent ledger-post pr. forsøg (P3), Holm som primær regel, K = 1 primær variant (ordre 47 P2).

## Udrulning i shadow mode (forslag; hvert trin kræver sin egen beslutning)

| Trin | Hvad | Stopper drift? | Rollback |
|---|---|---|---|
| S0 (nu) | offline snapshot og genafspilning (research-værktøjer) | nej | ikke relevant |
| S1 | efterfølgende shadow: et read-only job kører fabrikkens gate på nye transitioner og skriver ALLOW/BLOCK til en separat fil, aldrig til lab.db | nej | slet jobbet |
| S2 | rådgivende kald før en transition i laboratoriet; logger kun, blokerer aldrig (kræver lab-kode og deploy under de stående betingelser) | nej | politikflag fra; git revert |
| S3 | håndhævelse kun for eksperimenter oprettet efter cutover-datoen; legacy undtaget med deres mærker; fail-closed for nye; papirbøger, baner og låste fremadtests er uden for gaten | nej (kun nye forskningsovergange) | politikflag fra → tilbage til S2 |

**Kriterier for at gå videre:** 14 dage i S1/S2 uden uforklarede BLOCK, uden fejl i gaten og uden forskel mellem
fabrikkens og pipelinens beslutninger, som ikke falder i en dokumenteret klasse. **Tilbagerulning** ved første
uforklarede BLOCK af en eksisterende proces, enhver fejl i gaten eller enhver påvirkning af papirhandlen.

**Forudsætninger før S2/S3 (fra P0-svaret):** ejerens nøgle bundet til ejeren uden for allowed_signers; signering
uden adgang for assistenten (ingen ssh-agent eller oplåst nøgle på maskinen); et rollback-sikkert kontrolpunkt for
auditloggen uden for maskinen.

## Direktørens afgørelser (ChatGPT 06/11 kl. 09:47 lokal)

S0 godkendt; S1 godkendt til forberedelse; S2 afventer særskilt beslutning; S3 ikke godkendt. Git-committen før
screeningen dokumenterer en tidlig specifikation, men ikke at universet blev valgt uden kendskab til senere
markedsudvikling; SURVIVORSHIP_UNKNOWN nedgraderes ikke. Krav før integration:

1. **Checksummer med verificerbar kilde:** registrér checksum, kilde, hentetidspunkt og låsetidspunkt. En checksum fra
   samme vært som data beviser filintegritet, men ikke at filen var uændret på låsetidspunktet; uden betroet
   historisk bevis skal begrænsningen stå i resultatet.
2. **Reproducerbart point-in-time-univers:** reglen for kvalificerede mønter ved vinduets start fastlægges før data;
   en efterfølgende rekonstrueret liste må aldrig fremstilles som et oprindeligt låst univers.
3. **Ingen bagdør i legacy-undtagelsen:** kun de allerede identificerede eksperimenter i `migration_v1.json`, bundet
   til uforanderlig identitet (exp_id + spec_commit + oprindelig protokolversion). Nye forsøg kan ikke vælge et
   gammelt ID eller en legacy-status.
