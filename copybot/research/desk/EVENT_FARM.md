# Event farm: ICT/SMC-mærkning, kæder og outcome book (kun syntetiske data)

Skrevet 2026-11-11 kl. 17:16 lokal tid (16:16 UTC) af Claude. Kode: `research/tools/event_farm.py`.
Tests: `tests/test_event_farm.py` (41 tests). Status: **værktøj, ingen hypotese, ingen strategi**. Intet er låst,
ingen alfa er brugt, ingen ledger-række er skrevet, intet er aktiveret.

## 1. Hvad videoen viser

TikTok @keyzecom, "You can't make a trading bot with Claude": en "LIT DATA FARM", der på 5-minutters charts (MNQ m.fl.)
automatisk mærker ICT/SMC-begreber (liquidity pools, sweeps, manipulation legs, inducement, MSS/CHoCH, structure breaks,
FVG/inversioner, OB-zoner, session-åbninger, rejections, displacement), sætter dem sammen i kæder ("sweep → MSS → OB
anchor → entry, tp, sl") og logger, hvad der skete bagefter, i en "outcome book". Oversigten: 98 dage, 5 instrumenter,
240.067 hændelser (≈ 490 pr. instrument-dag), dækning pr. dag, et ordforråd og en daglig "Farm study" med antal pr. type.
**Videoen viser intet afkast.** At mange mønstre kan tælles, siger intet om, at de forudsiger noget (afsnit 4).

## 2. Præcise definitioner

Alle tærskler er parametre i `DEFAULTS`. Hver hændelse har `kind`, `ts` (åbningstid for mønstrets ankerbar), `known_ts`
(lukketid for den sidste bar, mønstret skulle bruge) og `known_i`. Motoren er en strøm (`Farm.step`), der ser én bar
ad gangen. Derfor kan ingen hændelse bruge data efter `known_ts`.

| begreb | regel (standardværdi) |
|---|---|
| ATR | gennemsnitlig true range over de 14 barer *før* baren (kendt ved barens åbning); til setups/udfald de 14 til og med baren |
| swing_high/low | fraktal k = 3: højere end de k barer før og ≥ de k barer efter. Kendes først ved bar j + k. Lige høje giver én pivot |
| liquidity_pool | ny swing inden for 0,10 ATR af et aktivt niveau på samme side; hændelsen udløses ved 2 medlemmer. Niveauer udløber efter 288 barer |
| sweep_high/low | væge forbi et niveau, der var kendt før baren, og luk tilbage inden for 1 bar (`sweep_reclaim_bars`). Lukker baren hinsides, er niveauet brudt (accepteret), og der kommer ingen sweep. Én sweep pr. side pr. bar |
| bos / mss | luk forbi seneste bekræftede, ubrudte modsatte swing. Mod den hidtidige struktur-trend = `mss_*` (= CHoCH); med den eller uden trend = `bos_*` |
| displacement | krop > 1,2 ATR |
| ob_bull/bear | ved displacement: sidste modsatte bar (c < o for bull) blandt de 5 barer før; zone = barens low..high |
| fvg_bull/bear | 3-bar-gab: l[i] > h[i-2] (bull), mindst 0,10 ATR; ts = midterbaren. Udløber efter 288 barer |
| ifvg (inversion) | senere luk under en aktiv bull-FVG's bund (→ ifvg_bear) eller over en bear-FVG's top (→ ifvg_bull) |
| session_open_* | baren, hvis [ts, ts + 5 min) indeholder sessionstiden i UTC (asia 00:00, london 07:00, ny 13:30, parametre) |
| rejection | range ≥ 1,0 ATR og væge ≥ 60 % af range |
| setup (kæde) | sweep_low → første mss_bull inden for 24 barer → anker = seneste fvg_bull (ellers ob_bull), kendt mellem sweepens væge og bruddet. Indgang: zonens midte (limit), kant eller bruddets luk. Stop: sweepens yderpunkt (± buffer). Mål: 2 R. Risiko under 0,25 ATR forkastes. En sweep føder højst én kæde. Short spejlet |

**Ikke defineret:** `inducement` og `manipulation leg`. Videoen bruger ordene, men der findes ingen entydig regel, og
motoren påstår ingen.

**Outcome book.** For hver hændelse: afkast i ATR ved 1, 3, 6 og 12 barer fra lukket ved `known_i`, MFE/MAE i ATR over
den længste horisont (kun når hele vinduet findes, aldrig delvist), og netto i bps for retningsbestemte hændelser efter
`cost_bps`. For setups gælder disse regler:
- En limit fyldes til sin pris, hvis baren rører den inden for 12 barer.
- Når målet nås før fyld, annulleres setuppet (`missed`).
- På fyldbaren tæller kun stop.
- **Rammer en bar både stop og mål, regnes det som stop.** `ambiguous="target_first"` findes kun til at sætte en grænse
  for, hvad den regel koster.
- Gap gennem stop lukker ved åbningsprisen. Gap gennem mål lukker ved målet.
- Efter 48 barer lukkes ved lukkekursen (timeout). Mangler der barer, er udfaldet `incomplete` og tæller ikke med.
- Netto R = brutto R − cost_bps·entry/risk.

**Daglig study.** `study()` og `study_markdown()` giver antal pr. type og kæde, dækning pr. instrument og dag (barer /
288) og setup-udfald pr. UTC-dag (dagen for den bar, hvor hændelsen blev kendt). Outputtet er deterministisk.

## 3. Hvad motoren IKKE påstår

- At nogen hændelse eller kæde forudsiger pris. Mærkningen er **beskrivende**.
- At definitionerne er "de rigtige" ICT-definitioner. Begreberne er vage. Her har hvert begreb én præcis, testet regel
  med parametre, og ændrer man en parameter, er det en ny variant, der skal tælles med.
- At udfaldene i outcome book kan handles. Der er ingen kø, ingen delvis fyldning og ingen latenstid. Omkostningen er en
  antagelse.
- At reglerne gælder med sikkerhed på markedsdata. De er kun kørt på syntetiske barer.

## 4. Null-test på ren støj (det centrale resultat)

`python3 research/tools/event_farm.py --study` (kun stdout, intet skrives). Data: driftløs log-random walk, 3
instrumenter × 60 dage × 288 barer (51.840 barer), seed 83, ≈ 11 bps pr. bar, 60 delskridt pr. bar. Den syntetiske
kalender er 2026-01-05..2026-03-05.

- **Hændelser i støj: 49.447, dvs. 274,7 pr. instrument-dag** (videoen: ≈ 490). Pr. instrument-dag bl.a. swing 25,9 +
  26,0; FVG 30,8 + 31,4; inversioner 28,1 + 27,6; displacement 12,3 + 12,4; OB 11,9 + 11,9; sweep 9,0 + 9,0; MSS 5,2 +
  5,2; BOS 5,3 + 5,3; rejection 5,7 + 6,2; pools 1,3 + 1,3.
- **Setups i støj (standardkæden fvg_then_ob, 2 R, midte-limit): 807 = 4,5 pr. instrument-dag.** Heraf 323 fyldte
  handler (87 mål, 209 stop, 27 timeout), 401 misset, 82 uden fyld og 1 ufuldstændig. Kædetællinger pr. instrument:
  357–404 sweep→brud, 34–39 uden anker og 69–73 med for lille risiko.
- **Udfald i støj:** standardkæden gav brutto −0,070 R pr. handel (t = −0,94) og **netto −0,110 R (−4,0 bps) efter
  1 bps**. Over alle 12 varianter (anker fvg/ob × 1/2/3 R × midte/marked; 5.429 handler) var brutto −0,020 R puljet.
  Ingen variant havde |t| > 1,6. Netto ved 5 bps var negativt for alle 12 (−0,12 til −0,41 R).
- **Den "bedste" variant i støj** var fvg/rr1/mid med +0,026 R brutto (t = 0,34), men −0,009 R efter 1 bps. Sådan ser
  et selektionsartefakt ud.
- Stop-først-reglen kostede næsten intet her: kun 4 handler havde en bar, der ramte både stop og mål. Brutto med
  target_first var −0,018 R mod −0,020 R.
- validation_engine (`validate_null`):
  - lookahead **PASS**: trunkering ændrer intet.
  - multiple testing **INCONCLUSIVE**: N = 12, block-bootstrap max-t p = 0,977.
  - costs **FAIL**: −1,31 bps brutto mod 1 bps omkostning.
  - Samlet: **FAIL**.

**Konsekvens:** Mønstrene opstår i ren støj i samme størrelsesorden som i videoen, og setups tjener intet dér. Evidens
fra markedsdata skal derfor slå denne null, med samme parametre, samme regler og alle varianter talt med. Antal
hændelser og "smukke" kæder er ikke evidens.

**Fund om generatoren.** Med kun 5 delskridt pr. bar fik tilfældige limit-indgange −0,17 R (prisen springer forbi limit,
så fyldet er ugunstigt), og markedsindgange fik +0,06 R (stop fyldes præcist, selvom prisen springer forbi). Med 60
delskridt var begge ≈ 0 (−0,015 ± 0,027 og −0,007 ± 0,022). Nullen bruger derfor 60. Det samme sker på rigtige 5m-barer:
en limit- eller stopregel, der antager præcis fyldning, kan skabe skin-edge.

**Register V2 (kun i kode, ikke persisteret):** `v2_records()` laver to FUTURE-poster, der er validerede (`v2.validate`
= []):
- `EVENT_FARM_NULL_SETUPS`: 12 varianter, univers 12.
- `EVENT_FARM_NULL_EVENTS`: 23 hændelsestyper × 4 horisonter = 92 beskrivende tests.

`data_quality` er NOT_CHECKED, og `deviations` er tom.

## 5. Hvilke data den senere må køre på

Motoren læser ingen fil. Den tager en liste af barer. Hvilke data den må få, besluttes af **direktøren og ejeren**, ikke
af dette værktøj:
- **kun data, lab'et allerede har lov til**. Før hver kilde: tjek `PROTOCOL_V3` for vært-/gate-regler og
  `research/data/QUARANTINE.json`.
- **intet holdout**, og intet før 2026-11-14 (forbuddet mod historiske forespørgsler). Ingen ny feed, stream eller
  collector.
- Instrumenter som MNQ kræver en godkendt kilde, som lab'et ikke har i dag. Kryptobarer fra en allerede godkendt cache
  er en mulighed, når en gate tillader det.

En kørsel på markedsdata skal registreres på forhånd: parametre, varianter (mindst de 12 + 92 herover), omkostningsgulv
pr. venue og en sammenligning med denne null, kørt med samme kode.

## 6. Åbne punkter

- Direktøren og ejeren beslutter, om og på hvilke godkendte data motoren må køres.
- Inducement og manipulation leg mangler en præcis definition (bevidst udeladt).
- Session-tider er UTC-parametre. Sommertid for NY/London er ikke modelleret.
- Kæden accepterer i dag kun MSS (`chain_breaks=("mss",)`). BOS-kæder er en ekstra variant og skal tælles med.
- Nullen er en ren random walk. En hårdere null (fx GARCH-volatilitet eller døgnmønster i volatilitet) er ikke kørt.

## Ejerens svar (2026-11-11 kl. 17:20 lokal)

Ejeren svarede "Ja" i chatten til at køre motoren på rigtige charts. Det er et chat-ja (UNVERIFIED_ORIGIN efter D5-reglen) og ingen lås. Ingen data er hentet eller læst. Forslaget til direktøren: en beskrivende kørsel efter 14/11, kun på data lab'et allerede må læse (explore0, 2020-03..2021-12, hvis passende barer findes i cachen); aldrig 2024-holdout eller 2025+ (G04); ingen nye feeds; varianter registreres på forhånd i Register V2; nullen er fast sammenligning; ingen aktivering. Afventer direktørens afgørelse.
