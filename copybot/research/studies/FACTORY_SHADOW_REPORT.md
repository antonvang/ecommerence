# FACTORY_SHADOW_REPORT — syntetisk shadow run (direktørordre 47 P3, frist 14/11)

Kode `research/tools/factory_shadow.py` (+ gate-funktion, delegationsregel, survivorship-, styrke- og datogate samt
idempotent opkrævning i `research/tools/factory.py`; skip-momentum i `research/tools/hypo_engine.py`). Tests
`tests/test_research_factory_shadow.py` (6). Data `research/data/factory_shadow/report.json` + `report.md` (sha256 i
report.md). Ingen beskyttede markedsdata; laboratoriets database er kun læst (`mode=ro`); registret er stadig et
read-only lag, ingen gate i produktion, ingen deploy, ingen papirbøger.

## A. Pipeline shadow — 179 lab-transitioner genafspillet mod fabrikkens regler

Laboratoriet udførte alle 179. Fabrikken ville have tilladt 119 og blokeret 60 (28 registreringer og 32 screeninger;
de 32 screeninger har to klasser hver, derfor 92 klasser i tabellen). **0 uforklarede forskelle**; en ukendt overgang ville blive rapporteret (testet).

| Fabrikkens afgørelse | Klasse | Antal | Forklaring |
|---|---|---|---|
| ALLOW | propose / no-op / legacy | 40 / 17 / 25 | samme betydning; legacy tæller 1 forsøg (nedre grænse) og skrives ikke om |
| ALLOW | registrering via familiegodkendelse | 4 | fcarry-instanserne (family.approved, event 1985) |
| ALLOW | afgørelse med forsøgsrækker/alfa | 32 | screeningsudfald med opkrævning i ledgeren |
| ALLOW | menneskelig afgørelse | 1 | SCREEN_PASSED → REJECTED |
| BLOCK | delegated-approval | 9 | skabelongodkendelse mærket `human:anton`, men begrundelsen siger "Approved by Claude (AI assistant) on behalf of the user" |
| BLOCK | instruction-cited-approval | 19 | skabelongodkendelse mærket `human:anton`, begrundelsen citerer en generel instruks ("User instruction 2026-10-17 …'Du godkender og gør alt du har tilladelse'") |
| BLOCK | hash-at-access | 32 | laboratoriet hasher data, når det læser dem (efter SCREENING); fabrikken kræver hashes ved låsen |
| BLOCK | universe-asof-unrecorded | 32 | specs registrerer ingen point-in-time-dato for universet; survivorship kan ikke udelukkes af registreringen |

**Vigtigste fund (styring):** alle 30 skabelongodkendelser i laboratoriet blev udført af assistenten. 6 siger det
direkte, og 24 citerer en generel instruks fra ejeren. Det var i overensstemmelse med ejerens instrukser dengang, men
ingen af dem kan bevises at være ejerens egen handling ud fra registreringen, og etiketten `human:anton` alene er
ikke bevis. Fabrikken afviser derfor en godkendelse, hvis begrundelsen viser delegering (Claude, ChatGPT, Codex,
"on behalf", "User instruction"), uanset etiketten. Historikken ændres ikke. Familiegodkendelsen af fcarry ("Anton
approves F1 fcarry after reading …") består kontrollen, men dens ophav kan heller ikke verificeres ud fra teksten.

## B. Adversarial suite — 30 tilfælde med forventet udfald

**Uautoriserede ALLOW: 0. Falske BLOCK: 0.** Alle tilfælde og grunde står i report.md. Dækket:

- Godkendelse: system, claude, chatgpt og "human:anton" med en delegeret begrundelse blokeres; ejeren selv tillades.
- Frysning: manglende estimand, datasæt uden sha256, 2024-holdout og COIN-M før 28/11 blokeres; COIN-M efter 28/11
  tillades. Survivor-univers (fastlagt ved vinduets slutning) og manglende univers-dato blokeres; point-in-time-univers
  tillades.
- Test: ingen opkrævning, opkrævning før låsen, ændrede data og ændret forhåndsregistrering efter låsen blokeres; den
  legitime vej tillades.
- Regnskab: en identisk genkørsel opkræver én gang (idempotent nøgle); tilbagebetaling, ny test af REJECTED og
  promovering til papir blokeres; en ødelagt ledger og et ukendt ID blokeres (fail-closed); en afvist overgang
  efterlader posten uændret (rollback).
- Kontroltilfælde fra P2: F1 INSUFFICIENT_POWER blokeres trods syntetisk profit; F2 CONDITIONAL blokeres; F3 DEFERRED
  blokeres; F3's datogate alene blokerer før 28/11 og tillader efter.

## C. Fabrikken i stor skala — 10 verdener × 1.002 kandidater

Hver verden: 24 aktiver × 500 dage. Kandidaterne er momentum med lookback 2-200 × skip {0, 1, 2, 3, 5} (995 stærkt
korrelerede nul-varianter), kendetegnet z med lag 1-6 (ægte signal i 5 verdener med ic 0,03, nul i 5) og én skjult
look-ahead (skip −1). Hver kandidat går hele vejen: PROPOSED → test uden godkendelse (blokeret) → ejergodkendelse →
lås → opkrævning (+ identisk genkørsel) → test → afgørelse (Holm, α 0,05 over 1.002).

| Mål | Resultat |
|---|---|
| Nul-kandidater "signifikante" uden korrektion | 0-154 pr. verden (i klumper: korrelerede varianter rammer samtidig) |
| Falske valg efter Holm | **0 i alle 10 verdener** |
| Ægte signal fundet efter Holm (ic 0,03) | **0 af 5 verdener** (P1 med 50 kandidater: 37 %) |
| Skjult look-ahead fanget / falske alarmer | 10/10 / 0 af 10.010 |
| Test blokeret uden godkendelse | 1.002/1.002 i alle verdener |
| Ledger-poster pr. testet kandidat | præcis 1 (genkørsler opkrævede intet); 1.002 poster, α 0,05 i alt pr. verden |
| Survivorship: ligevægtet dagligt afkast, overlevere minus alle | +5,9 til +12,2 bp/dag i alle 10 verdener |
| N_eff (stikprøve af hver 25. kandidat, 41 stk.) | 17-22 |

## Hvad P3 viser

1. **Sikkerheden holder i de testede scenarier:** ingen uautoriseret ALLOW, ingen falske BLOCK, ingen uforklarede
   forskelle mod pipelinen, fuld sporbarhed (hver testet kandidat har præcis én ledger-post; genkørsler opkræver
   intet).
2. **Bredde koster styrke.** Med 1.002 varianter og Holm bliver ingen falsk kandidat valgt, men den ægte effekt
   forsvinder også (0 af 5 mod 37 % med 50 kandidater). Holm behandler 1.002 stærkt korrelerede varianter som 1.002
   tests. Det bekræfter direktørens P2-regel: få forhåndsregistrerede primære varianter (K = 1) frem for brede net.
3. **Survivorship er en reel, ensrettet skævhed** (+6 til +12 bp/dag i alle verdener), og registret afviser et
   univers, der er fastlagt efter vinduets start, eller hvis dato mangler.
4. **Styring:** etiketten `human:` er ikke bevis for menneskelig godkendelse. Alle 30 skabelongodkendelser i
   laboratoriet blev udført af assistenten under ejerens generelle instrukser.

## Før en eventuel integration (ikke besluttet; kræver særskilt plan og godkendelse)

- Laboratoriet hasher data ved adgang og registrerer ikke univers-datoen. En integration ville blokere alle 32
  hidtidige screeninger. Det kræver enten ændring af laboratoriets registrering (kode og deploy) eller en dateret
  overgangsregel; ingen af delene gøres uden særskilt godkendelse.
- Delegeringsreglen er tekstbaseret. En robust løsning er en godkendelseskode, som kun ejeren selv kan udløse
  (laboratoriet har allerede approve/confirm-koder med 15 minutters udløb), plus en registrering af, hvem der tastede
  den.
- UNKNOWN: verdenerne er syntetiske; rigtige markeder har strukturbrud, ændrede omkostninger og afnoteringer, som
  ikke er modelleret ud over survivorship-testen.
