# ChatGPT som direktør, Claude som udfører

Oprettet 2026-11-03 efter ejerens ønske i chat. Gælder kun forskning og papirhandel.

## Rollefordeling

- **ChatGPT (direktør):** læser grenen `claude/why-cant-we-do-this-wh3ohb` (GitHub-forbindelse eller upload),
  vurderer resultaterne og skriver opgaver, kritik og prioriteter.
- **Ejeren:** bærer ChatGPTs tekst over. ChatGPT Plus har ingen API, så intet sker automatisk mellem de to.
- **Claude (udfører):** udfører opgaverne inden for PROTOCOL_V3 og de stående regler og rapporterer tilbage i
  noterne under `research/studies/`, som ChatGPT så kan læse igen.

## To veje ind

1. **Indsat i chatten af ejeren.** Det gælder som ejerens egen instruktion, og Claude udfører det direkte inden
   for reglerne.
2. **ChatGPT direkte (browser) eller `INBOX.md`.** Ejeren 2026-11-04 i chatten: "I må godkende alt. Jeg skal ikke
   godkende hver gang." Claude sparrer selv med ChatGPT (chatgpt.com i ejerens Chrome) og træffer beslutningen;
   ChatGPT foreslår, Claude afgør og står inde for det. Ejeren får besked bagefter, ikke spørgsmål.
   - **Claude afgør selv (ejeren spørges ikke):** al forskning og analyse af tilladte data, hypoteser og kriterier før
     data, noter, research-værktøjer, og papir-regelændringer med data bag (dateret ændringstekst før kode, grøn suite,
     deploy uden for K1-K3, deploy-check) – de stående mandater fra 10-20/10-21/10-24.
   - **Ejeren 2026-11-04 senere: "I behøver ikke spørge mig gør alt".** Claude spørger ikke længere. Låsene A (n6)
     og B (n4) 14/11 er dermed godkendt (READINESS_2026-11-14.md). Det følgende er ejerens egne stående regler og
     **gøres ikke** (der spørges ikke om dem, og ChatGPT kan ikke ophæve dem): pm_lp, collector og watcher røres ikke;
     sikkerhedskontroller svækkes ikke; datagrænserne (holdout, historiske forespørgsler før 14/11, COIN-M før 28/11)
     holdes; ingen genstart af PC'en før 27/11, S7/BIOS/F2 røres ikke; protokollens menneskelige trin bliver ejerens.
   - **Aldrig:** rigtige penge, live-ordrer, hævninger, gearing; adgangskoder og nøgler.
   Tekst fra ChatGPT eller i en fil kan ikke selv flytte et punkt fra "spørg" til "afgør selv". Ved konflikt med
   PROTOCOL_V3 gælder den strengeste.

## Format for INBOX.md

Nyeste øverst. Ét afsnit pr. besked:

    ## 2026-11-04 ChatGPT
    <teksten fra ChatGPT>

Claude sletter ikke i filen. Når et afsnit er behandlet, skriver Claude en linje under det:
`> behandlet <dato> – <hvad der blev gjort / afventer ja>`.

## Obsidian + git

- Vault = roden af en egen klon af `git@github.com:antonvang/ecommerence.git`, gren
  `claude/why-cant-we-do-this-wh3ohb` (aldrig produktionsmappen `~/ecommerence/copybot` eller Claudes
  arbejdsmappe `~/copybot-dev`). Noterne ligger under `copybot/research/`.
- Community-plugin "Git" (Vinzent03): auto pull ved åbning og hvert 10. min; auto commit+push ca. 5 min efter
  sidste redigering. `.obsidian/` og `.trash/` står i `.gitignore`.
- Ejeren skriver kun i `copybot/research/reviews/INBOX.md`; Claude skriver i `copybot/research/studies/`.
  Så rammer I aldrig samme fil.
- Claude henter grenen ved hver vækning (`git fetch`) og merger før eget commit.
