# FACTORY_SECURITY P1 — sikkerhedskomponenter i isolation (direktørordre 49 P1, frist 11/11)

Kode `research/tools/factory_security.py`, angrebstests `tests/test_research_factory_security.py` (11; kun
engangsnøgler i midlertidige mapper og syntetiske data), legacy-manifest `research/data/factory/legacy_manifest_v1.json`.
**Intet er koblet ind i laboratoriet.** Assistenten har ikke genereret, læst eller brugt ejerens private nøgle, og der
er ikke foretaget nogen ejerregistrering. Den kørende S1-observation er ikke ændret ud over den kørselslog og
dækningsrapport, direktøren krævede (beslutningslogikken er uændret).

## Komponenter og angrebstests

| Komponent | Hvad den gør | Angreb testet → afvist |
|---|---|---|
| 1. Nøglebinding (`KeyRegistry`) | Gyldige ejernøgler afledes af et signeret register, aldrig af en allowed_signers-fil. Rodnøglen accepteres kun, hvis dens fingeraftryk matcher et eksternt tillidsanker, som assistenten ikke kan skrive; hver senere tilføjelse eller tilbagekaldelse skal signeres af en nøgle, der er gyldig på det tidspunkt | rodnøgle uden for ankeret; selvtilføjet nøgle (signeret af assistentens nøgle); signatur med tilbagekaldt nøgle; omordnet register. Rotation (tilføj ny, tilbagekald gammel) virker |
| 2. Rollback-sikkert kontrolpunkt | Ejeren (eller en vidnenøgle uden for maskinen) signerer {log-id, længde, hoved-hash, tid}; en log godtages kun, hvis den forlænger det seneste signerede kontrolpunkt | ældre gyldig version (rollback/afkortning), gaffel med anden historik, kontrolpunkt signeret af assistentens nøgle, kontrolpunkt for en anden log. Forlængelse godtages |
| 3. Uforanderlig legacy-identitet | Undtagelsen er præcis de 57 tripler (exp_id, spec_commit, protokolversion) fra migration v1 (25 legacy + 32 screeninger), låst med sha256 `b308e3b5a938…` | genbrugt exp_id med anden commit, anden protokol, nyt eksperiment, manifest med en indsmuglet tripel |
| 4. Verificerbar dataidentitet | Låsen registrerer checksum pr. fil, kilde (værtens egen checksum-fil), hentetid og låsetid; ved adgang skal filens sha256 matche, og låsen skal ligge før adgangen; resultatet bærer begrænsningen `CHECKSUM_SAME_SOURCE` | ændret indhold, adgang før låsen, fil uden for låsen, ændret lås, lås før hentning af checksummer |
| 5. Point-in-time-univers | Regel fastlagt før data (noteret ≥ N dage før vinduets start, senere afnoterede med) anvendt på arkivets indeks; indeks og medlemsliste hashes ved låsen; et indeks hentet efter låsen giver status RECONSTRUCTED | afnoterede udeladt (survivorship), ændret indeks, ændret regel, rekonstrueret liste fremstillet som låst, regel skrevet efter at indekset var set. Senere afnoteret (LUNA-lignende) er med; først noteret efter starten er ude |

## Resterende manuelle ejerhandlinger (assistenten udfører ingen af dem)

1. Lav signeringsnøglen selv, på en anden enhed eller med en passphrase, assistenten aldrig får. Brug ikke
   `~/.ssh/id_ed25519` på denne maskine, og læg ikke nøglen i en ssh-agent på maskinen.
2. Offentliggør nøglens fingeraftryk et sted, assistenten ikke kan skrive (fx SSH-nøglerne på din GitHub-konto), eller
   læs det op, så det kan fastlåses uden for maskinen.
3. Signér rodposten i nøgleregistret (selvsigneret) og senere tilføjelser og tilbagekaldelser.
4. Signér kontrolpunkter for auditloggen jævnligt (eller hav en vidnenøgle uden for maskinen, der gør det).
5. Signér legacy-manifestets digest (`b308e3b5a938…`) én gang.
6. Godkend hver ny skabelon med en signeret erklæring (ordre 48 P0); en generel instruks tæller aldrig.

## Grænser (UNKNOWN)

- Tillidsankeret flytter tilliden til et eksternt sted (fx GitHub-kontoen). Er det sted kompromitteret, er bindingen
  det også.
- Kontrolpunkter beskytter kun den historik, de dækker; hændelser efter det seneste kontrolpunkt kan stadig rulles
  tilbage til kontrolpunktet. Hyppigheden bestemmer vinduet.
- `CHECKSUM_SAME_SOURCE`: en checksum fra samme vært beviser integritet, ikke at filen var uændret på låsetidspunktet.
- Arkivindekset over afnoterede symboler hentes fra samme vært som data og følger datagrænserne (tidligst 14/11).
