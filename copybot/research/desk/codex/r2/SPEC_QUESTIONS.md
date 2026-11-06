# Nye specifikationsspørgsmål — v1.1

1. **Afsnit 5: identisk payload versus identisk talrepræsentation.**
   `(hid, family, variants, alpha)` sammenlignes som parsede Python-værdier
   med tuple-lighed. Derfor er accepteret alpha=0 og et genforsøg med alpha=0.0
   et idempotent hit, også når ts ændres. Derimod bevares 0/0.0 særskilt i
   hashpræimaget for en ny accepteret post. Dette er en valgt fortolkning;
   teksten siger ikke udtrykkeligt, om typen også skal være identisk ved
   replay. Python-lighed gør også variants=1 og 1.0/True lige ved replay af
   en allerede accepteret key; key-kontrollen har udtrykkeligt forrang over
   variants-validering. Nye keys med 1.0/True afvises fortsat. R2_24–26
   adskiller værdilighed fra hashrepræsentation. En sammenligning bør
   klassificere en anden replay-konvention som specifikationsspørgsmål.

2. **Afsnit 1: overlappende fejlkoder og stier.** Alle uafhængigt afgørlige
   fejl samles. Et ikke-heltals ts/avail_ts/window-tid giver både BAD_TYPE og
   BAD_TIME. Ved listed_from/delisted_at bruges BAD_VALUE og BAD_TIME for
   tilsvarende typefejl, fordi medlemsskemaets typekrav står i BAD_VALUE.
   Typekorrekte tider uden for intervallet giver BAD_TIME alene, medmindre
   medlemsrelationen også brydes. Værdiintervaller kontrolleres efter deres
   typekrav; en fejlbehæftet container giver fejl ved containerens sti, ikke
   fiktive manglende børn. UNKNOWN_SIGNAL betyder, at nøglen ikke findes i
   nogen tilgængelig observations signals-dict, også hvis andre fejl findes.
   Mapping-stier er `universe.A.listed_from` og
   `observations[0].signals.s.value`. start>=end rapporteres på `window`;
   senere gentaget hid på `hypotheses[i].hid`; forkert topniveau på tom sti.
   Specifikationen fastlægger ikke alle disse sti- og overlapkonventioner.

3. **Afsnit 1: lock-fejl ved manglende/ugyldige komponenter.** En manglende
   eller forkert digest giver LOCK_MISMATCH på `lock.protocol_sha256` eller
   `lock.data_sha256`, én fejl pr. komponent. Manglende protokolfelter gør
   protokollåsen ukontrollerbar og derfor mismatched, samtidig med de
   almindelige skemafejl. En lock, der ikke er et objekt, giver én fejl på
   `lock`. Ekstra lock-nøgler afvises ikke: lock er ikke blandt objekterne
   nævnt under UNKNOWN_FIELD. Hashen bruger rå inputfelter før default for
   embargo og før filtrering. For tilladte numeriske IEEE-værdier i input
   bruges v1's præcise json.dumps-defaults i lock-præimaget; outputkodning
   afviser fortsat ikke-endelige værdier.

4. **Afsnit 3–4: operationernes parenteser og repræsenterbarhed.** S
   beregnes som fsum([gamma_0, 2*fsum(vægt_k*gamma_k)]), direkte efter
   formlens parenteser. At flade ud til én fsum kan give anden afrunding
   nær S=0; status har ingen flydende tolerance. Endelige inputtal kan
   desuden være så store, at produkter/summer overflyder, eller så små, at
   de underflyder til S=0. Specifikationen angiver ingen fejlkode eller
   skaleringsalgoritme for dette. De store/små R2-cases holder produkter
   repræsenterbare og kontrollerer skala-invarians. Der indføres ingen ny
   fejlkode, clipping, regularisering eller udvidet tolerance for at skjule
   dette hul. Fuld numerisk fail-closed-adfærd for alle tænkelige endelige
   Python-tal kan ikke udledes af teksten alene.

5. **Afsnit 6: filnavn ved null fixture_id og ugyldig JSON.** Ved manglende
   eller ugyldigt fixture_id er feltet null i INVALID_INPUT; CLI'en bruger
   inputfilens stem som outputfilnavn. Det er ikke angivet i specifikationen.
   `evaluate` validerer den parsede værdi; syntaktisk ugyldig JSON fejler i
   parseren før evaluate, uden en ny opfundet fejlkode. Atomisk skrivning
   bevarer en tidligere outputfil, hvis kodning eller erstatning fejler.
