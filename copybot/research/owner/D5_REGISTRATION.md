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
