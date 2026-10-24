# Screening m21i: spot–perp lead/lag og omkostningsregimer (krypto, explore0)

**Regel:** `research/PROTOCOL_V3.md` ændring 21i, committet 2026-10-24 kl. 18:33 (cc568d1) før kode og beregning.
**Kode:** `lab/m21iscreen.py` (4887626). **Kørt:** 2026-10-24 ca. kl. 18:34, kun cache, intet netværk, 42 s CPU-tid.
**Data:** 2 943 månedsfiler (perp-klines, spot-klines, funding), 132 symboler, heraf 130 med spot; fillistens sha256
`5a6bc985…7fef`. Rådata: `SPOTPERP_m21i.json`. **Mærkat:** UDFORSKNING.
**Omkostningskrav:** pr. hændelse c_i = max(0,46 %, 2 · (2 · 0,040 % + RT_est(V_30d))). RT_est er et ESTIMAT fra
2026-målingen overført til 2020–21.

| Nøgle | Hændelser | Døgnklynger | Gns. (± SE) | p | 2020 / 2021 | Placebo p | Krav (gns.) | Dom |
|---|---|---|---|---|---|---|---|---|
| `spot_lead\|perp_1h\|m21i` | 4 151 | 499 | +0,108 % (± 0,053 %) | 0,039 | −0,01 % / +0,19 % | 0,57 | 0,465 % | **SCREEN_FAIL** |
| `perp_led\|move_24h\|m21i` | 2 004 | 436 | +0,09 % (± 0,35 %) | 0,79 | +0,19 % / +0,02 % | 0,31 | 0,466 % | **SCREEN_FAIL** |

Hændelsernes sha256: S1 `1f36ad3d…9709`, S2 `04a4e148…a59e`.

## S1: spot fører perpen med en time?

Efter en time, hvor spot afveg ≥ 3σ fra perpen, flyttede perpen sig i gennemsnit 0,11 % i spots retning i den næste
time. Det er statistisk svagt (p 0,039 mod kravet 0,005), findes kun i 2021 og er under en fjerdedel af kravet på
0,47 %. Indgangen er desuden ved timens lukning, altså uden forsinkelse, så resultatet er kun information. **Ikke
handelbart.** Det er i tråd med MISSION3 M3 (præmiekonvergens: reel, men en tiendedel af omkostningerne).

## S2: hvem førte bevægelsen?

Reglen "gå imod perp-førte 4σ-bevægelser, følg spot-førte" giver nul på døgnniveau. Beskrivende, ikke testet: perp-førte
bevægelser (1 190) vendte +1,41 % på hændelsesniveau, og spot-førte (814) fortsatte ikke (−0,37 %). Det er det samme
billede som 4σ-fald og m21h: på hændelsesniveau ligner det noget, men det forsvinder, når hændelserne klynges pr. døgn.

**Udelukket:** ingen spotbar 110, ingen fundingfil 39, manglende funding i holdevinduet 41, manglende kurs 3.

## Omkostningsregimer (ESTIMAT, Abdi–Ranaldo fra 1 t-barer; beskrivende, ingen test)

| Mål | Værdi |
|---|---|
| Døgn med en 4σ-hændelse mod samme mønt 30 døgn før (n 2 120) | median 1,23 % mod 0,68 %; højere på 81 % af parrene |
| Efter terciler af døgnets realiserede volatilitet (inden for mønten) | lav 0,50 %, mellem 0,77 %, høj 1,29 % |

**Pålidelighed: lav.** Estimatoren er bygget til dagsdata. På timebarer opfanger den intradag-volatilitet: niveauerne
(50–130 bp) er langt over de bogspreads, der er målt i dag (median under 5 bp i halvt spread). Kun retningen er
informativ: estimerede handelsomkostninger stiger stærkt med volatilitet og på dage med ekstreme bevægelser, netop
der hvor m21c- og m21h-mønstrene var stærkest pr. hændelse. **Konsekvens:** et signal, der lever på ekstreme dage,
skal bære højere omkostninger end et roligt gennemsnit; et fast eller rent omsætningsbaseret krav undervurderer dem.
Observerede bogdata fra scanneren (ændring 21h punkt 3, fra 2026-10-24 kl. 18:21) kan bekræfte eller afkræfte det;
en rapport tidligst efter 7 døgn.

Begge nøgler screenes aldrig igen under m21i. Ingen lås og intet alfa er brugt.
