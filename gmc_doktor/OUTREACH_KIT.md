# GMC-DOKTOR: Salgs- og outreach-kit til 7-dages testen

**Mål (låst i `FASE15_DECISION.md`, del J):**

| | Kriterium |
|---|---|
| Succes | ≥ 1 betalt ordre (≥ 495 kr.) fra en kunde uden personlig relation inden udgangen af dag 7 |
| Gyldig test | Kræver ≥ 100 opkaldsforsøg og ≥ 30 samtaler med en beslutningstager |
| Fiasko | 0 betalinger på dag 7, eller aktivitetskravet er ikke nået → **STOP** |

## 1. Hvem gør hvad

| Opgave | Hvem |
|---|---|
| Leadliste, gratis tjek, rapporter, opkaldsliste, manuskript, mailudkast og opfølgning på tal | Claude |
| Telefonopkald | **Brugeren**, eller den voksne. Claude kan ikke ringe. |
| Afsendelse af mails til personer, der har sagt ja | Brugeren, fra butikkens/den voksnes mailadresse. Claude laver udkast. |
| Faktura, betaling, aftale og konti (bank/MobilePay/Stripe, Fiverr, Shopify Partner) | **Den voksne** |
| Opslag i Facebook-grupper og på Shopify Community | Brugeren, fra egen konto og efter gruppens regler. Claude laver udkast. |

## 2. Regler for kontakt (lovligt og fair)

| Tilladt | Forbudt |
|---|---|
| **Telefon** til butikkens offentliggjorte nummer i åbningstiden | Kold **e-mail eller sms** (markedsføringsloven § 10 gælder også over for virksomheder) |
| **E-mail efter et mundtligt ja** i telefonen (log samtykket, se §5) | Kolde **DM'er** på LinkedIn, Facebook/Messenger og Instagram. Det er "elektronisk post" (Forbrugerombudsmandens spamvejledning). |
| **Personligt fremmøde** | En besked, der *beder om* samtykke via mail eller DM, er også forbudt |
| Offentlige, nyttige opslag i grupper efter gruppens regler | At fortsætte, når nogen siger nej: sig tak og notér "nej, kontakt ikke igen" |
| Svar på henvendelser, folk selv sender | – |
| Partnerskaber med bureauer (første kontakt pr. telefon eller ved fremmøde) | – |

**Spring over:**
- Enkeltmandsvirksomheder, der ser ud til at være privatpersoner på Robinsonlisten.
- Firmaer, der er reklamebeskyttet i CVR. Ekstra forsigtighed; vores kontaktdata kommer fra butikkens egen side.

**Vær ærlig:**
- Sig, at du er en ung iværksætter, og at aftalen indgås med [den voksnes virksomhed].
- Lov aldrig, at Google genåbner en konto.

## 3. Opkaldsmanuskript (ca. 2 minutter)

**Før opkaldet:** Kig i butikkens rapport, og vælg den mest konkrete fejl. Eksempler:
- "ingen fysisk adresse på siden",
- "intet link til returpolitik",
- "prisen i jeres strukturerede data passer ikke med den viste pris".

**Åbning:**
> "Hej, jeg hedder [navn]. Jeg hjælper danske Shopify-butikker med Google Shopping. Har du 30 sekunder?"

**Hook (konkret fejl):**
> "Jeg har kørt et gratis tjek af [butik] mod Googles regler for Merchant Center. Jeg fandt [3] ting, der ofte giver afviste produkter eller en suspenderet konto, fx [konkret fejl]. Kører I Google Shopping i dag, eller har I overvejet det?"

**Samtykke til mail:**
> "Må jeg sende jer rapporten på mail? Den er gratis og tager 2 minutter at læse."
>
> (Ja:) "Hvilken mail skal den til? Og er det okay, at jeg følger op på mail om et par dage?"

Notér samtykket med det samme (§5).

**Tilbud (hvis der er interesse nu, eller i opfølgningen):**
> "Vi kan rette det for jer til fast pris: 995 kroner. I betaler først, når det er rettet og sendt til gennemgang hos Google."
>
> "Vil I hellere selv rette det, kan I få auditten med en præcis rettelsesvejledning for 495 kroner."

**Afslutning:**
> "Skal jeg sende tilbuddet sammen med rapporten?"

Ved nej: "Helt fint, tak for din tid." Notér "nej".

## 4. Indvendinger

| Indvending | Svar |
|---|---|
| "Vi bruger ikke Google Shopping" | "Mange butikker står gratis i Google Shopping via 'gratis visninger'. Det kræver, at Google godkender butikken. Rapporten viser, om I er klar." |
| "Vi har et bureau" | "Godt, så kan I give rapporten til dem. Den er gratis." (Notér bureauet som en mulig partner.) |
| "Hvem er du?" | Ærligt svar: ung iværksætter, egen erfaring med Merchant Center (220 af 221 produktvarianter godkendt i egen butik), aftalen indgås med [den voksnes virksomhed]. |
| "Det er for dyrt" | "Auditten til 495 kr. giver jer præcis listen, så I kan rette det selv." |
| "Send en mail" | "Det gør jeg gerne. Må jeg sende rapporten og tilbuddet til [mail]?" (Samtykke.) |
| "Kan I garantere, at vi bliver godkendt?" | "Nej, det er altid Google, der afgør det. Vi retter de kendte årsager og sender til ny gennemgang." |

## 5. Samtykke-log (obligatorisk)

Gem i `data/consent_log.csv` (lokalt, deles ikke):

| Felt | Indhold |
|---|---|
| Tidspunkt | Dato og tid |
| Butik | Domæne |
| Person | Navn og rolle |
| Mail | Den mail, rapporten skal sendes til |
| Samtykke | Hvad der er sagt ja til: rapport og/eller opfølgning |
| Opkald | Hvem der ringede |

Uden et ja i loggen sendes der ingen mail.

## 6. Tilbud og levering

| Produkt | Pris | Indhold |
|---|---:|---|
| Gratis tjek | 0 kr. | Automatisk rapport over offentlige sider |
| Audit med rettelsesvejledning | 495 kr. | Gennemgang af rapporten, Merchant Center-diagnostik (når kunden giver adgang) og præcis rettelsesliste. Levering ≤ 48 t. |
| Fejlretning (done-for-you) | 995 kr. | Vi retter butik og feed og sender til ny gennemgang. Før/efter-rapport. Levering ≤ 48 t efter adgang. |
| Overvågning (forudbestilling) | 149 kr./md. | Ugentligt automatisk tjek og alarm ved nye fejl |

**Ingen førpris:** Vi har aldrig solgt til en højere pris, så vi skriver ikke "normalt 1.495 kr.". En førpris, der ikke har været brugt, er vildledende (markedsføringsloven).

**Levering uden adgangskoder:**
1. Kunden tilføjer vores Google-konto som bruger i Merchant Center med standardadgang.
2. Kunden opretter en Shopify-medarbejderkonto med adgang til Produkter og Onlinebutik.
3. Før ændringer eksporteres produkt-CSV. Alle ændringer logges.
4. Efter levering beder kunden Google om ny gennemgang. Vi sender før/efter-rapport, og den voksne sender fakturaen.

## 7. Mail efter samtykke (skabelon)

**Sendes kun, hvis samtykket står i loggen.** Vedhæft butikkens HTML-rapport fra `data/batch/<butik>.html`, eller indsæt de 3 vigtigste punkter.

> **Emne:** Jeres gratis Google Shopping-tjek: [butik]
>
> Hej [navn],
>
> Tak for snakken i dag. Som aftalt er her rapporten fra vores gratis tjek af [butik] mod Googles regler for Merchant Center.
>
> De 3 vigtigste punkter:
> 1. [fejl 1, fx "Ingen fuld adresse i footeren"]
> 2. [fejl 2]
> 3. [fejl 3]
>
> Vil I have hjælp, kan vi:
> - rette det for jer til fast pris, 995 kr. I betaler først, når det er rettet, og I giver kun adgang via Googles og Shopifys egne invitationer;
> - eller lave en audit med præcis rettelsesvejledning for 495 kr.
>
> Svar bare på denne mail, eller ring på [telefon].
>
> Venlig hilsen
> [navn] · [virksomhedsnavn] · CVR [nummer] · [adresse]
>
> Ønsker I ikke flere mails fra os, så svar "stop", så sletter vi jeres oplysninger.

## 8. Daglige mål i testen

| Dag | Mål |
|---|---|
| 4 | 50 opkaldsforsøg. 3 Shopify-bureauer kontaktet. 1 opslag i en gruppe. |
| 5 | Opfølgning hos alle, der har sagt ja. Første levering, hvis der er en bestilling. |
| 6 | 50 nye opkaldsforsøg. Justér manuskriptet efter indvendingerne. |
| 7 | Optælling og beslutning (`TEST_RESULT.md`) |

**Tæl hver dag:** opkaldsforsøg, samtaler med beslutningstager, ja til rapport, tilbud sendt, betalinger, skriftlig betalingsvilje og bureausvar.
