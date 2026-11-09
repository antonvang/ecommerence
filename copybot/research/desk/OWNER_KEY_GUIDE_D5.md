# OWNER_KEY_GUIDE_D5: sådan laver ejeren sin godkendelsesnøgle (2026-11-09)

**Hvad den er:** et digitalt underskriftsstempel. Det beviser, at det er **ejeren selv**, der godkender en bestemt
forskningstest, og ikke Claude, ChatGPT eller Codex.

**Hvad den ikke er:**
- Ingen konto, ingen penge og ingen adgang til børser.
- Den gælder kun papirlaboratoriets forskningsgodkendelser.

Mekanismen er beskrevet i `research/studies/OWNER_APPROVAL_P0_2026-11-06.md`, og koden ligger i
`research/tools/owner_approval.py` (namespace `copybot-approval`, principal `owner`).

**Ejerens handling.** Claude laver, ser og bruger aldrig nøglen og indtaster aldrig adgangskoden. Ellers beviser den intet.

## 1. Lav nøglen på en ANDEN computer end lab-pc'en

Den skal ligge et sted, hvor intet program på lab-pc'en kan læse den, fx en anden bærbar. Brug **ikke** den
eksisterende `~/.ssh/id_ed25519` på lab-pc'en.

På den anden computer (Linux/macOS-terminal eller Windows PowerShell, hvor `ssh-keygen` findes):

```
ssh-keygen -t ed25519 -f copybot_owner -C copybot-owner
```

- Vælg en adgangskode, når du bliver spurgt, og del den aldrig.
- Der kommer to filer:
  - `copybot_owner` er den **private** nøgle. Den bliver på den computer, deles aldrig, og sendes ikke til nogen.
  - `copybot_owner.pub` er den **offentlige** nøgle. Den må gerne deles.

Se fingeraftrykket:

```
ssh-keygen -lf copybot_owner.pub
```

## 2. Registrér den offentlige nøgle uafhængigt

Direktørens krav (ordre 53/54-A): en ny linje i repoet er ikke nok, fordi Claude også kan skrive i repoet. Derfor skal
fingeraftrykket også stå et sted, Claude ikke kan ændre:
- Send `copybot_owner.pub` til lab'et, så den kommer i `allowed_signers` for principal `owner`.
- Skriv **selv** fingeraftrykket (linjen fra `ssh-keygen -lf`) ét uafhængigt sted, fx i en besked til ChatGPT-
  direktøren fra din egen konto, eller på papir, som du tager et billede af.
- Lab'et tjekker, at de to fingeraftryk er ens.

## 3. Sådan godkender du en test senere

1. Lab'et laver en erklæring (JSON) med testens id, præcis version og hash, en engangskode (nonce) og en udløbstid
   (højst 7 dage). Dine egne ord skal være specifikke, fx "Ja til PKT-A …", ikke "godkend alt".
2. Du kopierer filen til din anden computer og underskriver den:
   ```
   ssh-keygen -Y sign -f copybot_owner -n copybot-approval erklaering.json
   ```
   Det giver `erklaering.json.sig`.
3. Du sender `.sig`-filen tilbage. Lab'et verificerer den automatisk og afviser alt, der ikke stemmer: forkert nøgle,
   forkert version, udløbet, genbrugt kode eller ord som "på vegne af" og "gør alt".

## 4. Mister du nøglen?

Sig det til lab'et. Den offentlige nøgle fjernes fra `allowed_signers`, og du laver en ny efter samme trin.

## 5. Uafhængig ejergodkendelse (ordre 71 D)

Status er `PENDING_INDEPENDENT_ANCHOR`. Fingeraftrykket passer, men det er ikke nok: Claude kan skrive i browserchatten,
så en besked dér beviser ikke, hvem der skrev den. Et billede af papir er heller ikke kryptografisk bevis.

**Ejeren gør dette selv, på sin egen bærbare og telefon:**

1. Læs fingeraftrykket direkte fra nøglen på den bærbare: `ssh-keygen -lf copybot_owner.pub`.
2. Sammenlign det med linjen i `research/owner/D5_REGISTRATION.md`, set **på GitHub fra telefonen**, ikke via
   lab-pc'en. Det skal være tegn for tegn ens.
3. Skriv fingeraftrykket til direktøren **fra telefonen**, altså en enhed Claude ikke har adgang til, og skriv, at det er
   din D5-ejernøgle.
4. Underskriv testerklæringen på den bærbare (se `research/owner/D5_REGISTRATION.md`), og send `.sig`-blokken.

**Lab'et verificerer** med `research/tools/owner_approval.py`. Først når direktøren har bekræftet punkt 3, og
underskriften er gyldig mod den forankrede nøgle, kan status ændres, og kun af direktøren.

Den private nøgle forlader aldrig den bærbare. Testerklæringen låser og godkender intet.
