# D5 ejernøgle: registrering (2026-11-09 kl. 17:22 lokal)

- **Nøgle:** ED25519, kommentar `copybot`. Fingeraftryk `SHA256:lSdgtWU21pKqM1NLjrt5SytMIsj7N4lQ9R9IYfx4PJ4`.
- **Oprettet af ejeren på en separat bærbar** (ejerens udsagn i chatten 2026-11-09). Den private nøgle har aldrig været på
  lab-pc'en; Claude har hverken set, lavet eller brugt den.
- **Offentlig nøgle** i `research/owner/allowed_signers` (principal `owner`, namespace `copybot-approval`). Claude har
  tjekket, at fingeraftrykket af den modtagne offentlige nøgle er identisk med det, ejeren oplyste.

## Uafhængigt anker (direktørens krav, ordre 53/54-A)

Claude kan skrive i repo'et, så denne fil er ikke nok alene. Ejeren skal selv skrive fingeraftrykket til direktøren
(ChatGPT) fra sin egen konto.

**Status: PENDING_INDEPENDENT_ANCHOR.** Fingeraftrykket stod endnu ikke i direktørsamtalen, da registreringen blev
skrevet. Indtil direktøren har bekræftet det, giver nøglen ingen VERIFIED_OWNER_APPROVAL.

## Testsignatur (ingen godkendelse)

`research/owner/d5_test_statement.json` er en kanonisk erklæring med template `D5_KEY_REGISTRATION_TEST`. Den låser
intet og godkender intet. Den udløber 7 dage efter udstedelse. Ejeren signerer den på den bærbare:

```
printf '%s' '<indholdet af d5_test_statement.json, præcis>' > stmt.json
ssh-keygen -Y sign -f copybot_owner -n copybot-approval stmt.json
cat stmt.json.sig
```

Ejeren sender indholdet af `stmt.json.sig` (en "BEGIN SSH SIGNATURE"-blok; den er offentlig og ufarlig). Lab'et
verificerer den med `owner_approval.verify`.

**Tilbagekaldelse:** linjen fjernes fra `allowed_signers`.

## Testunderskrift verificeret (2026-11-11 kl. 19:34 lokal)

- Ejeren underskrev `d5_test_statement.json` på sin bærbare og sendte signaturen; den ligger i `research/owner/d5_test_statement.json.sig`.
- Lab'et verificerede den 2026-11-11 18:34:02 UTC med `research/tools/owner_approval.verify` mod `research/owner/allowed_signers` (sha256 `c6d949e3…`), namespace `copybot-approval`, principal `owner`: **ACCEPTED**, ingen grunde. Afgørelsen står i den hash-kædede `research/owner/approval_log.jsonl` (første række, hash `d6c279776139…`).
- Erklæringen er kun en test af nøglen. Den låser intet og godkender intet.
- **Status: PENDING_INDEPENDENT_ANCHOR**, indtil direktøren bekræfter, at ejeren selv har skrevet fingeraftrykket fra sin telefon. Først derefter kan status ændres, og kun af direktøren.

## FINGERPRINT_MATCH_CONFIRMED (2026-11-11 kl. 19:41 lokal, direktørbeslutning 95)

- Ejeren sendte selv fingeraftrykket i direktørchatten fra sin telefon ("SHA256:lSdgtWU21pKqM1NLjrt5SytMIsj7N4lQ9R9IYfx4PJ4 copybot (ED25519)", aflæst med `ssh-keygen -lf` på den bærbare). Det matcher `allowed_signers` og nøglen bag den verificerede testsignatur.
- Direktøren registrerer FINGERPRINT_MATCH_CONFIRMED, men sætter ikke D5 til ANCHORED, fordi kanalens uafhængighed ikke kan verificeres fra chatten.
- **Status: PENDING_INDEPENDENT_ANCHOR.** G15 BLOCKED. Ingen lås, ingen dataadgang.

## D5 = ANCHORED (2026-11-11 kl. 19:46 lokal, direktørbeslutning 97)

- **D5: ANCHORED.**
- **Metode:** OWNER_ATTESTATION + FINGERPRINT_MATCH + VERIFIED_TEST_SIGNATURE.
- **Dato:** 2026-11-11. **Reference:** direktørbeslutning 97 (kriteriet blev fastsat i beslutning 96).
- Ejeren skrev selv fra sin telefon i direktørchatten, at han oprettede ED25519-nøglen på sin bærbare, at den private nøgle aldrig har været på lab-pc'en eller tilgængelig for Claude, og at han selv aflæste fingeraftrykket med `ssh-keygen` og sendte det fra sin telefon. Fingeraftrykket matcher `allowed_signers`, og testsignaturen er verificeret (ACCEPTED, `approval_log.jsonl`).
- Signatur og auditlog er bevaret uændret.
- Det er en dokumenteret ejererklæring og nøglekontrol, ikke en teknisk undersøgelse af ejerens enheder.
- **G15 evalueres selvstændigt.** Ingen automatisk protokollås, ingen automatisk dataadgang, ingen produktionsændringer, ingen live-handel.

## Erklæring til underskrift: event farm fremadrettet papirbog (2026-11-12 kl. 15:33 lokal)

- Direktørbeslutning 106 godkendte tekst 104 (`research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.md`, sha256 `396cf90c…`) som grundlag for ejerens filkontrol og D5-underskrift.
- Erklæringen `research/owner/ef_forward_104_statement.json` (template `EVENT_FARM_FORWARD_104`, blob = tekstens sha256, udløber efter 6 døgn) venter på ejerens underskrift efter hans egen sha256-kontrol på den bærbare.
- En underskrift aktiverer intet af sig selv: G15, G31, 5m-strømmen og commit i `PROTOCOL_V3.md` skal stadig bestås.
