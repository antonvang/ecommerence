# Screening m21h: funding × 4σ-bevægelse (krypto-perps, explore0)

**Regel:** `research/PROTOCOL_V3.md` ændring 21h punkt 5, committet 2026-10-24 kl. 18:04 (4ed2876) før kode og beregning.
**Kode:** `lab/m21hscreen.py` (fd0e19d). **Kørt:** 2026-10-24 ca. kl. 18:05, kun cache, intet netværk, 11 s CPU-tid.
**Data:** 1 816 månedsfiler (klines og funding), 132 symboler, heraf 115 med fundingfiler; fillistens sha256
`f5f64a5c…2c07`. Hændelsernes sha256 `2ae7f1ae…0176`. Rådata: `FUNDING_m21h.json`. **Mærkat:** UDFORSKNING.

| Nøgle | Hændelser | Døgnklynger | Gns. (± SE) | p | 2020 / 2021 | Placebo p | Krav | Dom |
|---|---|---|---|---|---|---|---|---|
| `funding_crowd\|squeeze_24h\|m21h` | 1 162 | 312 | +0,02 % (± 0,49 %) | 0,96 | +0,12 % / −0,04 % | 0,81 | 0,46 % | **SCREEN_FAIL** |

**Udelukket (af 2 197 4σ-hændelser):** neutral funding (0 ≤ f ≤ 0,01 %) 860, ingen afregning inden for 12 t før 97,
ingen fundingfil 76, manglende kurs 2. Implementeringsdetalje, der ikke står i teksten: en hændelse med færre end 2
afregninger i holdevinduet udelukkes ("missing funding in the holding window"), så funding aldrig sættes til 0 for
manglende data. Det ramte 0 hændelser.

**Konklusion:** reglen "følg en 4σ-bevægelse med flokken, gå imod den mod flokken" giver nul på døgnniveau. Funding
før bevægelsen tilfører altså ingen målbar information om de næste 24 t ud over prisbevægelsen.

**Beskrivende, ikke testet:** hændelsesniveauet ser anderledes ud. Mod flokken (604) gav +1,53 % ved at gå imod
bevægelsen; med flokken (558) gav +0,84 % ved at følge den. Begge tal er positive, så de ophæver ikke hinanden; det
gør derimod klyngerne. Store krakdage har mange hændelser og trækker hændelsesgennemsnittet. 13,9 % af hændelserne
ligger på de 5 travleste døgn og 19,6 % i de 5 travleste mønter. "Mod flokken" overlapper 4σ-faldsmønstret, som venter
på brugerens beslutning; dette resultat afgør det ikke.

Nøglen screenes aldrig igen under m21h. Ingen lås og intet alfa er brugt.
