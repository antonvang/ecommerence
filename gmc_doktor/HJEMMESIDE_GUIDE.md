# Hjemmeside: sådan kommer den online (til den voksne)

Hjemmesiden er skrevet færdig (`site/webshopdoktoren.html`). Den hostes gratis hos **Cloudflare**. Det eneste, der mangler, er de ting, kun I kan gøre: oprette firmaet, en mail, købe domænet og oprette en Cloudflare-konto. Claude kan ikke oprette konti, logge ind eller betale.

Det tager cirka en time i alt. Selve hostingen er gratis. Kun domænet koster penge.

## 1. Firmaet (ca. 15 minutter, gratis)
- Opret en enkeltmandsvirksomhed med navnet **Webshopdoktoren** på **virk.dk** med MitID.
- Har du allerede en virksomhed, kan du i stedet tilføje "Webshopdoktoren" som binavn.
- Navnet var ledigt i CVR-registret, da vi tjekkede 13/10.

## 2. Firmaets Gmail (ca. 5 minutter, gratis)
- Opret en ny Gmail kun til firmaet, fx `webshopdoktoren.dk@gmail.com`, hvis den er ledig.

## 3. Domænet (ca. 10 minutter)
- Køb **webshopdoktoren.dk** hos en dansk domæneudbyder. I skal kun bruge domænet, ikke et webhotel.
- Registrér det i firmaets navn, og betal med den voksnes eller firmaets kort.
- Domænet var ledigt, da vi tjekkede 13/10.

## 4. Cloudflare-konto (ca. 5 minutter, gratis)
- Opret en gratis konto på **cloudflare.com** med firmaets Gmail.

## 5. Send oplysningerne til Claude
Skriv til Claude:
- CVR-nummer
- firmaets adresse
- firmaets Gmail
- om firmaet er momsregistreret (ja eller nej)

Så laver Claude den færdige fil, `index.html`, med alle oplysningerne udfyldt. Siden må først gå online, når oplysningerne er der, fordi en dansk virksomhed skal vise navn, adresse, CVR og mail.

## 6. Læg siden op hos Cloudflare (ca. 10 minutter, Claude hjælper)
- Log ind på Cloudflare i Chrome. Claude må ikke logge ind for jer.
- Opret et nyt **Pages**-projekt med navnet `webshopdoktoren`, og vælg at uploade filer direkte (uden Git).
- Upload mappen med `index.html`. Claude kan gøre det for jer, når I er logget ind og har sagt ja.
- Så ligger siden på `webshopdoktoren.pages.dev`.

## 7. Kobl domænet på (ca. 10 minutter, plus ventetid)
- I Pages-projektet: vælg **Custom domains**, og tilføj `webshopdoktoren.dk`.
- Cloudflare viser to navneservere. Skriv dem ind hos domæneudbyderen, der hvor domænets navneservere står.
- Det kan tage nogle timer, før webshopdoktoren.dk virker.

## 8. Sidste skridt
- Skriv `webshopdoktoren.dk` under **Indstillinger → Hjemmeside** i opkalds-dashboardet. Så kommer den med nederst i alle mails.

## Senere
- Når de første kunder er hjulpet, kan I bede dem om en anmeldelse, fx på Trustpilot. Det må kun være rigtige kunder.
