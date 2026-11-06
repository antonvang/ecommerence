# OWNER_APPROVAL P0 — verificerbar ejergodkendelse (direktørordre 48 P0, frist 09/11)

Kode `research/tools/owner_approval.py`, tests `tests/test_research_owner_approval.py` (9; kun engangsnøgler i en
midlertidig mappe), legacy-liste `research/data/factory/legacy_approvals.json`. **Design og syntetiske tests; intet
er koblet ind i laboratoriet, ingen deploy, ingen markedsdata.**

## Problem

Ordre 47 P3 fandt, at laboratoriets 30 skabelongodkendelser (29 bekræftede) står som `human:anton`, men blev udført
af assistenten. 6 siger "Approved by Claude (AI assistant) on behalf of the user", og 24 (23 bekræftede) citerer en
generel instruks ("User instruction 2026-10-17 … 'Du godkender og gør alt du har tilladelse'"). En etiket eller en
generel instruks kan ikke bevise, at ejeren har godkendt en bestemt skabelon.

## Mekanisme

1. **Erklæring.** Én kanonisk JSON pr. skabelonversion med `scope: template`, skabelonens id, den præcise git-blob af
   skabelonen/kataloget, protokolversion, en ny nonce, udstedelses- og udløbstid (højst 7 dage), namespace
   `copybot-approval` og ejerens egne ord.
2. **Signatur.** Ejeren signerer med `ssh-keygen -Y sign -n copybot-approval`. Den offentlige nøgle står for principal
   `owner` i en allowed_signers-fil i repoet (kun offentlige nøgler).
3. **Nøglens placering (ejerens handling, ikke assistentens).** Privatnøglen skal ligge, hvor processer på denne maskine
   ikke kan bruge den: på en anden enhed eller som en passphrase-beskyttet nøgle, hvis passphrase assistenten aldrig
   får (assistenten indtaster aldrig adgangskoder). Ejerens eksisterende `~/.ssh/id_ed25519` på maskinen må **ikke**
   bruges: alt, der kører som samme bruger, kan læse den. Assistenten har ikke åbnet den.
4. **Verifikation (`verify`, fail-closed).** Signaturen skal være gyldig for `owner` og namespace. Blob og protokol
   skal matche den version, der godkendes. Erklæringen må ikke være udløbet, og noncen må ikke være brugt før
   (replay). Ejerens ord må ikke indeholde delegering (Claude, ChatGPT, Codex, "on behalf", "User instruction",
   "gør alt"), og scope skal være specifikt (ikke "all", "*", "alt").
5. **Auditlog.** Hver afgørelse, accepteret eller afvist, skrives i en kun-tilføj-log med hashkæde. En ødelagt log
   afviser alt.
6. **Legacy.** Alle eksisterende godkendelser (29 skabelonhændelser, fcarry-familiehændelsen og approvals-rækken for
   familien) har status **UNVERIFIED_ORIGIN**. De beholder deres testresultater, men bruges aldrig som bevis for
   ejerens personlige godkendelse og opgraderes aldrig. Kræver en fremtidig handling verificeret godkendelse, indhentes
   den på ny gennem `verify`.

## Testet (syntetisk)

| Forsøg | Afgørelse |
|---|---|
| Gyldig ejersignatur på korrekt version | ACCEPTED (logget) |
| Samme erklæring igen (replay) | REFUSED |
| Signeret med en anden nøgle (fx assistentens) | REFUSED |
| Ændret erklæring efter signering | REFUSED |
| Anden blob, anden protokol, udløbet, gyldighed > 7 dage | REFUSED |
| Signeret, men generisk scope ("all", "*") | REFUSED |
| Signeret, men ejerens ord er delegering ("gør alt", "Approved by Claude", "User instruction") | REFUSED |
| Ingen signatur; ødelagt auditlog | REFUSED |
| Manipuleret auditlog på disk | opdages ved indlæsning |
| Legacy-godkendelser | UNVERIFIED_ORIGIN, aldrig opgraderet |

## Grænser (UNKNOWN / ejerens del)

- Mekanismen beviser kun, at den, der har ejerens privatnøgle (og passphrase), signerede netop denne erklæring. Den
  kan ikke stoppe nogen, der har begge dele. Tilbagekaldelse sker ved at fjerne den offentlige nøgle fra
  allowed_signers.
- Opsætningen kræver ejerens egen handling: at lave nøglen et sted, assistenten ikke kan nå, og lægge den offentlige
  nøgle i repoet. Det gør assistenten ikke.
- Ejerens alder: ifølge ChatGPT er ejeren under 18 (ikke verificeret). Mekanismen giver ikke adgang til rigtige penge
  eller produkter; den gælder kun forskningsskabeloner i papirlaboratoriet.

## Direktørens præciseringer (ChatGPT 06/11 kl. 09:31 lokal; før en eventuel integration)

1. Signaturen beviser kontrol over nøglen, ikke ejerens identitet eller forståelse. Den offentlige nøgle skal knyttes
   til ejeren gennem en separat, betroet registrering; en ændring af allowed_signers må ikke i sig selv give en ny nøgle
   godkendelsesret (allowed_signers ligger i et repo, som assistenten kan skrive i). En passphrase er ikke nok, hvis
   assistenten kan nå den oplåste nøgle eller signeringsprocessen (fx en ssh-agent på denne maskine).
2. Hashkæden opdager ændringer i loggen, men ikke at hele loggen erstattes med en ældre gyldig version (rollback). Før
   integration kræves en betroet kontrol af seneste logtilstand, som samme proces ikke kan omskrive (fx et
   kontrolpunkt uden for maskinen).
