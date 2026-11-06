# Specifikationsspørgsmål og valgte konventioner

Historisk v1-dokument. Nye spørgsmål og aktive v1.1-valg findes i
`r2/SPEC_QUESTIONS.md`; v1.1-præciseringerne erstatter de tidligere valg,
herunder summering, embargo, validering og ledger-genafspilning.

Grundlag: `../crosscheck/EVALUATOR_SPEC.md`, version 1. Ingen anden
repository-kode er brugt som kilde. Specifikation og fixtures er ikke ændret.

1. **Afsnit 2.2–2.4 — overlappende filtreringsårsager.** Det siges ikke
   særskilt, om en række kan tælles flere gange på tværs af filtrene. Jeg følger
   den nummererede rækkefølge med stop ved første filter: off-grid først,
   derefter dubletter, derefter medlemskab. Første on-grid-række reserverer
   `(ts, asset)`, også når den senere afvises som ikke-medlem. Gentagelser af
   den tælles derfor som dubletter, ikke igen som ikke-medlemmer. Off-grid-
   gentagelser tælles hver især som off-grid. Rå on-grid-tilstedeværelse til
   afsnit 4 registreres inden de to øvrige filtre.

2. **Afsnit 3–5 — summeringsorden og flydende tal.** Rækkefølgen af assets og
   algoritmen til summering er ikke angivet. Jeg bruger universets rækkefølge
   i input-JSON, stigende gittertid og Pythons indbyggede `sum`, `/` og `math`-
   funktioner. Der afrundes ikke, og der bruges ikke `fsum`, Decimal eller
   variansklipning. Ledgers summer følger request-rækkefølgen. De præcise
   output-bytes gælder den dokumenterede Python-version; afsnit 9's tolerance
   anvendes ved sammenligning med andre implementeringer.

3. **Afsnit 5 og 8 — utilstrækkelig varians og `hac_lag`.** Afsnit 5 giver
   utilstrækkelig status både ved kort serie og ved `S <= 0`; afsnit 8 gør kun
   lag null ved kort/tom serie. Jeg beholder det beregnede lag, når `T >= 30`
   og `S <= 0`, men sætter `se`, `t`, `p_one` til null. Ved `T < 30` er alle
   fire felter null. Der indsættes ikke nulobservationer i HAC ved tomme bars;
   HAC beregnes på den komprimerede serie defineret i afsnit 4.

4. **Afsnit 6 sammenholdt med 5 — dublet af utilstrækkelig hypotese.**
   `DUPLICATE` får forrang som status. Statistikken beregnes først efter afsnit
   5, så en kort dublet stadig har null i testfelterne; en testbar dublet
   beholder numeriske testfelter. Første fingeraftryk gemmes uanset den første
   hypoteses status. Omkostning og funding er ikke dele af fingeraftrykket.

5. **Afsnit 7.4 — betydningen af `attempts`.** Det fremgår ikke udtrykkeligt,
   om afviste eller idempotente requests er forsøg i family-totalen. Jeg lader
   alle fire family-totaler dække accepterede poster alene, i overensstemmelse
   med placeringen efter konstruktionen af en post. `attempts` er dermed antal
   accepterede poster, `hypotheses` antal forskellige `hid` blandt disse.
   Afvisninger og genbrug fremgår separat af `errors` og `idempotent_hits`.

6. **Afsnit 7.3 og 8 — talrepræsentation i hashpræimage.** En JSON-inputværdi
   `0` og `0.0` kan være numerisk ens, men kodes forskelligt i Python. Jeg
   bevarer requestens parsede værdier i hashposten og normaliserer ikke
   heltal til float. SHA-256 beregnes over UTF-8 uden BOM eller afsluttende
   newline, uden `hash`-felt. Outputfiler bruger samme kodning og ingen newline.

7. **Afsnit 1 og 8 — inputvalidering uden for skemaet.** Der mangler regler
   for fx gentagne `hid`, ugyldig kadence, manglende obligatoriske felter,
   usikre `fixture_id`-filnavne og overflow ved endelige, meget store tal.
   Implementeringen forudsætter det angivne inputskema og unikke `hid` samt
   filnavnsegnede fixture-id'er; den er ikke en generel validator. `ret`,
   funding og signalværdier accepteres kun som endelige Python-tal; de tre
   tilladte IEEE-strenge behandles som ikke-endelige, hvilket giver præcis de
   foreskrevne missing-grene. Bool accepteres ikke som disse måleværdier.
   `variants` kræver præcis typen `int`, så bool og `1.0` afvises. Ledgerens
   alpha-validering bruger den udtrykkelige endelig/ikke-negativ-regel uden
   en ekstra øvre grænse. Bool-alpha ligger uden for afsnit 1's skema; den
   numeriske kontrol accepterer den, da kun variants udtrykkeligt undtager bool.
   `allow_nan=False` tilføjes som kontrol ved kodning; for skemagyldigt output
   giver det præcis de bytes, som afsnit 8 angiver.

De udtrykkelige regler om nulstilling efter huller/MISSING, finansiering med
nulposition, streng ekstremgrænse og medtagelse af historik før afnotering er
implementeret uden yderligere antagelser. Der er ingen ekstra afsluttende
likvidation eller omkostning på en MISSING-bar.
