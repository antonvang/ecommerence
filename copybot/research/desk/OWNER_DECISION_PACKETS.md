# OWNER_DECISION_PACKETS (direktørordre 53 P2, 2026-11-06)

**Denne fil er ikke en godkendelse.** En tekstpakke er ikke en ejer-signatur. Assistenten genererer, bruger og opbevarer
aldrig en nøgle på ejerens vegne, og den udfører hverken approve-template, lås, aktivering eller alfa-allokering på
baggrund af denne fil. Hver pakke beskriver præcist, hvad ejeren kan sige ja til. Siges der ikke ja, sker der intet.

**Fælles krav til et gyldigt ja**, efter direktørordre 53 og OWNER_APPROVAL_P0:
- Ejeren skriver det selv.
- Det er dateret.
- Det nævner pakke-id, protokolversion, commit og sha256 ordret.
- Det er ikke en generel instruks. "I må godkende alt" tæller ikke.
- Så snart ejernøglen findes (D5), skal godkendelsen være signeret med `owner_approval.verify` (namespace
  copybot-approval). Indtil da kan et chat-ja højst give status UNVERIFIED_ORIGIN og kan ikke åbne en factory-gate.

Identiteter (git HEAD-commit pr. fil, sha256-præfiks):

| Fil | Commit | sha256 |
|---|---|---|
| research/PROTOCOL_V3.md | ec91280 | 0a09b3e954d92c82 |
| research/studies/MISSION27_3_2026-11-02.md (låsetekster 6b/6c/7d/10) | 586a34d | 103fd0afe3e2fd47 |
| research/studies/READINESS_2026-11-14.md | dba9bda | 33de9d7bcd485ea3 |
| research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md (F2 låst) | b54cb3c | 6dd1ca82934419c0 |
| research/desk/F2_AMBIGUITY_RESOLUTION_PROPOSAL.md | 75d42e5 | a7dcd259f189f2c9 |
| research/desk/F2_CALIBRATION_SPEC_DRAFT.md | 75d42e5 | 5f29f1b33bb08ddb |
| research/desk/B_N4_RESOLUTION_OPTIONS.md | 67fd4f6 | 48ca63ed358bbe32 |
| research/desk/C1_FORECAST_DESIGN.md | 80fb255 | 530a86d5bb56ec62 |
| research/desk/DATA_CONTRACT_F2_C1.md | c8f95c2 | 7db2ac5c8e1ac881 |

## PKT-A: lås A (n6, X1/X2; ændring 44)

- **Hvad ejeren godkender:** at låsetekst A fra MISSION27_3 punkt 6b, som rettet i punkt 7d (fil `586a34d`/`103fd0af…`),
  indsættes ordret som næste ledige ændring i PROTOCOL_V3 (nu `ec91280`/`0a09b3e9…`). Det sker tidligst 2026-11-14
  00:00 UTC. Derefter skrives indlæseren efter låsen, suiten skal være grøn, og der laves én kørsel pr. test.
- **Hvad ejeren ikke godkender:** ændringer af teksten, X3 (COIN-M, tidligst 28/11), historiske data før låse-commit,
  nye tests eller alfa ud over det, låseteksten selv angiver.
- **Risici:**
  - AMB-15: låseteksten ligger i to afsnit, 6b og 7d. Indsættelsen skal derfor gengive den rettede tekst, ikke
    sammenfatte den.
  - AMB-28: ændringsnummeret kan forskydes.
  - AMB-29: det er uklart, om en PROTOCOL_V3-lås kræver signatur.
- **Alternativer:**
  - Udsæt låsen.
  - Lås først, når ejernøglen findes (D5), så godkendelsen bliver verificeret.
- **Tidligste lovlige dato:** 2026-11-14 00:00 UTC.
- **Eksempeltekst ejeren kan skrive:** "2026-11-DD: Ja til PKT-A: indsæt låsetekst A (MISSION27_3 6b rettet i 7d, fil
  586a34d sha256 103fd0afe3e2fd47…) ordret i PROTOCOL_V3 (ec91280, 0a09b3e954d92c82…) tidligst 14/11 00:00 UTC."

## PKT-B: B n4 (ændring 45): ikke klar, B forbliver BLOCKED

- B n4 kan ikke låses forsvarligt. Låsetekst 6c punkt 1 bygger universet af den karantænerede liste med 232 par.
  Ethvert lovligt univers ændrer forsøgets identitet (`factory.fingerprint`).
  - Detaljer: `B_N4_QUARANTINE_AUDIT.md` og `B_N4_RESOLUTION_OPTIONS.md` (`67fd4f6`/`48ca63ed…`).
- **Ejerens valg** (ingen af dem låser B n4):
  - **B-1 (anbefalet):**
    - Luk B n4 som WITHDRAWN_BEFORE_LOCK. Der er ingen dataadgang og ingen alfa brugt.
    - Bed om en ny, separat protokol, N4b, med en point-in-time-medlemsregel fra tilladte kilder efter 14/11 og egen
      alfa.
    - N4b bliver en selvstændig fremtidig pakke med egen version og hash. Den skrives og committes, før der hentes data.
  - **B-2 (frarådes):** 38 B-vejen med et nyt `market/all`-kald efter låsen. Den giver ny identitet, kendt
    survivorship og kræver en undtagelse fra factory's survivorship-gate, dvs. en svækkelse af en sikkerhedsregel.
- **Uden et svar:** B n4 forbliver BLOCKED, og Upbit-gaten forbliver lukket.

## PKT-F2: F2-præciseringer og kalibrering (D3/D4)

- **Præciseringer** (ingen identitetsændring, kan godkendes som fortolkning af den låste tekst):
  - UTC-dag og kline-fakta;
  - cutoff og lås i forhold til target;
  - Corsi-lags;
  - 365 regressionsrækker = 395 hele dage;
  - ingen overførsel mellem vinduer;
  - 100 % dækning;
  - EWMA-start og burn-in;
  - lige vægte;
  - sidste target 2023-12-31, aldrig 2024.
- **Materielle ændringer** (kræver F2 v2 som ny version og hash før data, og et separat ja):
  - dagkonventionen B23: 23 afkast og en embargo-time, cutoff 23:00, lås inden 23:30, target 00:00–00:00;
  - gulvregel for HAR ≤ 0;
  - ingen forward-styrkeregel, før en dateret ændring definerer en.
- **Vigtigt for beslutningen:** den låste styrketabel er overvurderet.
  - Med 334 target-dage er styrken 0,66 ved e 0,10 (ρ_c 0,5), og MDE er 0,121.
  - F2's eget GO-kriterium (≥ 0,8 ved e 0,08) er ikke opfyldt selv i den låste tabel.
  - validation3 alene har 0 targets.
  - Et ja til F2 er altså et ja til et forsøg, der meget vel kan ende INCONCLUSIVE.
- **Kalibrering (explore0):**
  - Udkastet (`75d42e5`/`5f29f1b3…`) estimerer kun sd(d), HAC-faktoren og ρ_c. e rapporteres, men bruges ikke til GO.
  - Det er aldrig evidens.
  - Data hentes først efter G01 (14/11) og efter ejerens daterede ja med specversion og sha256.
- **Uden et svar:** F2 er fortsat CONDITIONAL og BLOCKED, og der sker ingen datahentning.

## PKT-C1: forward-1h-kline-kilde til C1 (D7)

- **Hvad ejeren godkender:**
  - en forward-only kilde til 1h-klines (en ny stream eller en udvidelse af en eksisterende fetch);
  - C1 config v2 på F2's klines;
  - ekstern forankring af journalens head-hash, fx dagligt i et commit;
  - en dateret ændring;
  - deploy kun uden for K1–K3, og ingen genstart før 27/11.
- **Hvad ejeren ikke godkender:** backfill som "forward", ændring af F2, eller aktivering før F2-pakken.
- **Risici:**
  - AMB-12/13: fapi-1h-stream blev tidligere afvist som dublet, og daglige arkiver kommer for sent.
  - Første ægte prognose ligger langt ude: EWMA cirka 2027-01, HAR cirka 2027-12, hvis den kun bygger på forward-data.
- **Uden et svar:** C1 forbliver READY_NOT_ACTIVE.

## PKT-W0: resterende alfa-budget (D6)

- W0 har 0,0375 tilbage (3 × α_F 0,0125).
- Direktøren har **ikke** accepteret Claudes rangering (F2, LIQPROXY1, FUNDFRAG1).
  - F2 er blokeret, og de to andre kræver nye streams.
  - En rangering er ikke en godkendelse af budget.
- Ejeren kan:
  - (a) vente, hvilket anbefales, indtil mindst én kandidat har låst estimand, test, data og en signeret godkendelse;
  - (b) reservere alfa til en navngiven kandidat med version og hash.
- Ingen hypotese omklassificeres til en måling for at slippe for korrektion.

## Afhængighed: ejernøgle (D5)

Uden ejernøglen (skabt uden for maskinen, fingeraftryk publiceret, rodindgang signeret) bliver alle ja ovenfor
UNVERIFIED_ORIGIN. De kan ikke åbne nogen factory-gate (S2/S3 forbliver NO-GO).

Maskinlæsbar liste over fortsat blokerede handlinger: `research/desk/blocked_actions.json`.
