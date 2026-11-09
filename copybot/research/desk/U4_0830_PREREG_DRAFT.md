# U4_0830_PREREG_DRAFT: forhåndsregistreringsklart UDKAST til U4 H1 (direktørordre 61)

**Status:** UDKAST. Dette er ikke en lås og ikke en ændring af PROTOCOL_V3, og der er ikke læst data.
**Ingen handelsstrategi, ingen alfa-påstand.** H1 måler risiko (volatilitet), ikke retning eller afkast.
**Ingen nye historiske forespørgsler nu:** ingen klines, ingen kalenderhentning og ingen filer i `klines_1m/` er åbnet
eller hashet. lab.db er ikke åbnet, og `python3 -m lab` er ikke kørt.
**Skrevet:** 2026-11-09 ca. 12:25 UTC (tjekket med `date -u`).
**Grundlag:** `research/desk/US_MACRO_0830_DESIGN.md` (commit `3c75685`, sha256 `d0e1e162…baac3f`), uændret. Dette
udkast vælger én primær hypotese og fastlægger resten, så en senere lås kan kopiere teksten.

## 0. Hypotesen (én primær)

**H1:** På dage med en planlagt CPI- eller Employment Situation-udgivelse kl. 08:30 ET er BTCUSDT-perpens realiserede
log-varians i 15 minutter efter udgivelsen større end på matchede kontroldage.

- Primært endepunkt: d₁₅ = ln RV₁₅(udgivelse) − ln RV₁₅(kontrol).
- 5 og 60 minutter er sekundære vinduer i samme Holm-familie (punkt 5).
- H2 (før udgivelsen), ETH, PPI og retning er **ikke** med. Det holder multipliciteten nede.

## 1. Hændelsesliste

1. **Udgivelser:** kun BLS "Consumer Price Index" og "Employment Situation" (`lab/ingest.py` `BLS_KEEP`).
   - PPI, DOL-krav, BEA og Census er ikke med. PPI er ikke i cachen, og de andre værter er ikke tilladt.
   - På kontroldage kan der derfor ligge ukendte udgivelser. Det skævvrider mod nul, altså konservativt.
2. **Officiel kilde (tilladt vært, ændring 14):** `https://www.bls.gov/schedule/{year}/home.htm`.
   - BTC (primær, 2020-2021): de cachede filer `data/lab/market/ingest/calendar/bls-2020.json` og `bls-2021.json`
     (hentet 2026-10-20 under ændring 14, parset af `ingest.parse_bls`) bruges. Der hentes intet nyt.
   - FOMC til udelukkelse: `fomc-2020.json` og `fomc-2021.json` fra `federalreserve.gov/monetarypolicy/fomchistorical
     {year}.htm`. Alle dage med en kalenderbegivenhed tæller, også ikke-planlagte (`m21jscreen.calendar` → `days`).
   - Låsen registrerer de fire filers sha256, før de parses.
3. **Udvælgelse:** `scheduled` = sand, kl. 08:30 ET og `ts` i explore0 = [2020-03-01 00:00, 2022-01-01 00:00) UTC
   (ændring 10c). En post med et andet klokkeslæt udelukkes med årsag.
   - CPI og NFP på samme dag er én hændelse. Enheden er dagen.
   - Højst 22 + 22 = **44 udgivelsesdage** før udelukkelser. Tallet er beregnet ud fra 12 + 12 om året, ikke talt i
     kalenderen.
4. **Point-in-time:** planlagt tid og faktisk udgivelse skal være den samme.
   - Før låsen sammenholdes hver dato med BLS' arkivlister (`bls.gov/bls/news-release/cpi.htm`, `empsit.htm`).
     Det er ikke markedsdata, men det kræver direktørens ja.
   - En afvigelse udelukkes med årsag. Intet erstattes.
   - En aflyst udgivelse er ikke en hændelse, og dens dato må ikke bruges som kontrol.
5. **Udelukkelse af udgivelsesdage:** en FOMC-dag (planlagt eller ej) inden for ±1 UTC-døgn, manglende barer (punkt
   4) eller RV = 0. Hver udelukkelse skrives med årsag. Der udfyldes intet.
6. **Sommertid:** T = 08:30 i `America/New_York` (zoneinfo), omregnet til UTC for hver dato. Aldrig et fast UTC- eller
   dansk klokkeslæt. Beregnet lokalt (kun regler):

   | Periode | T i UTC |
   |---|---|
   | 2020-03-01 → 03-07 | 13:30 |
   | 2020-03-08 → 10-31 | 12:30 |
   | 2020-11-01 → 2021-03-13 | 13:30 |
   | 2021-03-14 → 11-06 | 12:30 |
   | 2021-11-07 → 12-31 | 13:30 |

   Kontroldagens T beregnes med kontroldagens egen forskydning: samme ET-klokkeslæt, ikke samme UTC-tid.

## 2. Matchet kontroldag

For hver udgivelsesdag D prøves kandidaterne i fast rækkefølge: D − 7, D + 7, D − 14, D + 14, D − 21, D + 21 døgn.
Den første kandidat, der opfylder alle krav, bruges:

- samme ugedag (følger af ±7k) og T = 08:30 ET på kandidatens egen dato;
- inden for explore0;
- ingen CPI- eller NFP-udgivelse samme UTC-døgn;
- ingen FOMC-kalenderdag inden for ±1 UTC-døgn;
- ikke en amerikansk føderal helligdag (regelbaseret liste for 2020-2021, kontrolleret før låsen, jf. designets krav 7);
- ikke en aflyst udgivelsesdato (punkt 1.4);
- ikke allerede brugt som kontrol for en tidligere udgivelse (kronologisk tildeling);
- alle barer findes (punkt 4).

Findes ingen kandidat, udelukkes D med årsagen `no_control`. Kontrolreglen ændres aldrig efter data.

## 3. Instrumenter

| Rolle | Instrument | Data | Status |
|---|---|---|---|
| **Primær** | BTCUSDT USD-M perp | Historik **kun** i explore0 (2020-03-01 → 2021-12-31, ændring 10c; G02). Først efter en dateret lås **og** fra 2026-11-14 00:00 UTC (G01). Aldrig train3/validation3 (2022-2023), holdout 2024 eller 2025+ | data findes i cachen (punkt 4) |
| **Sekundær** | XAUUSDT (TRADIFI_PERPETUAL, onboard 2025-12-11) | **Kun fremad**, fra første udgivelse efter en godkendt 1m-stream. Al historik er reserveret (G04), og arkivet ligger på DNS-blokeret vært | ingen stream: blokeret |

- XAUUSDT får sin egen rapport. Den indgår ikke i H1's afgørelse og pooles ikke med BTC.
- Holm-familien for XAU er de samme tre vinduer.
- Den eksisterende `bn_abnormal_move`-stream har XAU kun på 1 t-opløsning. Det kan ikke bruges.

## 4. Barkilde og opløsning

- **BTC:** `data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip` for 2020-03 …
  2021-12.
  - De 22 BTC-filer er allerede i `~/ecommerence/copybot/data/lab/market/klines_1m/`. De blev hentet under ændring
    24a (2026-10-27), sha256 står i `fetch_log.jsonl`, og `r3_verify` gav 44/44 OK og 0 manglende minutter.
  - **Der hentes intet nyt, og ingen vært er nødvendig.** Låsen kræver, at sha256 på disken er lig med fetch_log, før
    nogen fil åbnes. Ellers stop. Kun filnavnene er talt her: 22 BTC og 22 ETH. ETH åbnes aldrig af H1.
- **Opløsning:** 1 minut, `open_time` i ms UTC. Bar k åbner kl. T + k min. Prisen er lukkekursen C_k.
- **XAU (sekundær):** 1m-klines fra `fapi.binance.com/fapi/v1/klines` (tilladt vært, kun GET), hentet efter
  vinduet. Det kræver en ny stream (punkt 9).

## 5. Statistik og test

- **Afkast:** r_k = ln(C_k / C_{k−1}). **RV_h** = Σ_{k=0}^{h−1} r_k². Kræver barerne −1 … h−1 (bar −1 åbner T − 1 min).
- **Parret mål:** d_{h,i} = ln RV_h(D_i) − ln RV_h(kontrol_i) for h ∈ {5, 15, 60} min.
  - h = 60 rækker ind i kontantåbningen kl. 09:30 ET og mærkes "inkl. åbning".
- **Estimator:** d̄_h = gennemsnittet over gyldige hændelser.
- **Standardfejl:** klyngerobust (CR1) med klynge = udgivelsens UTC-kalendermåned (G ≈ 22). Testen er t mod t(G − 1),
  tosidet, med H0: E[d_h] = 0.
- **Følsomhed (rapporteres, afgør intet):**
  - Newey-West HAC med lag 2 i kronologisk orden;
  - fortegnsskift-test på klyngesummer (20 000 træk, seed 7);
  - 2020 og 2021 hver for sig.
- **Multiplicitet:** Holm over de tre vinduer {5, 15, 60} ved familie-α = 0,05.
  - **H1 afgøres kun på h = 15** med Holm-justeret p.
  - 5 og 60 min rapporteres med Holm-justeret p som beskrivelse.
- **Forholdstal:** exp(d̄_h) med 95 %-interval, så resultatet kan læses som "RV er x gange højere".

## 6. Styrke (ændring 32)

- σ_d = **0,7 er en fast ANTAGELSE**, skrevet før data (fra designets §6). Den er ikke estimeret på H1's egne udfald.
  Den rettes aldrig efter data (32 punkt 3). En forkert σ_d noteres som en afvigelse.
- MDE-forhold = exp((z₁₋α′/₂ + 0,842) · σ_d / √n). Normal-approksimation; med t(21) er faktoren ca. 3,46 i stedet for
  3,24 (ca. 7 % bredere).

| n gyldige | 1 test (α 0,05) | Holm, mindste p (α 0,05/3) | Holm, σ_d = 0,5 / 1,0 |
|---|---|---|---|
| 20 | 1,55× | 1,66× | 1,44× / 2,06× |
| 30 | 1,43× | 1,51× | 1,34× / 1,81× |
| 40 | 1,36× | 1,43× | 1,29× / 1,67× |
| 44 | 1,34× | 1,41× | 1,28× / 1,63× |

- Mærke (32 punkt 2, ikke-afkast-skala): **"kan kun finde effekter på ca. 1,4× eller mere"**.
- Litteraturen (Ederington & Lee 1993) taler for en stor effekt i 15 minutter i FX og renter. For BTC er effekten
  usikker (Benigno & Rosa 2023).

## 7. Udfaldsklasser (afgøres på h = 15)

| Klasse | Regel |
|---|---|
| NOT_DUE / REFUSED | før 2026-11-14 00:00 UTC, før låse-commit, eller en sha256 afviger |
| INSUFFICIENT_DATA | under 20 gyldige hændelser **eller** under 10 månedsklynger efter udelukkelser |
| PASS (beskrivende, EXPLORATORY) | Holm-justeret p₁₅ ≤ 0,05, d̄₁₅ > 0 **og** samme fortegn for d̄₁₅ i 2020 og 2021 (hver ≥ 8 hændelser) |
| FAIL (falsificeret) | den øvre 95 %-grænse for exp(d̄₁₅) er under 1,25, så en effekt på 1,25× eller mere er udelukket |
| INCONCLUSIVE | alt andet, også PASS-kravet uden samme fortegn i begge år |

- explore0 er udforskning, aldrig bevis (ændring 10). Et PASS er derfor mærket EXPLORATORY.
- R3 og J1 har allerede brugt de samme udgivelsesbarer til retning. Ingen af R3's tal bruges her til at vælge
  parametre.
- Et PASS kan højst blive grundlag for et senere risikofilter, fx ingen indgang 08:25-08:45 ET, efter sin egen
  ændring. Det er aldrig en handelsregel.

## 8. Stopregler

1. **Én kørsel.** Resultatet committes (json + md med sha256 for fil- og hændelseslisten og kodens commit), uanset
   udfald. H1 på BTC i explore0 køres aldrig igen med andre parametre.
2. **Afbryd uden resultat (REFUSED)**, hvis koden ville åbne en fil uden for 2020-03..2021-12, en ETH-fil, et
   2022+-, 2024- eller 2025+-tidsstempel, eller hvis sha256 for en fil eller en kalenderfil afviger fra låsen.
   Der hentes ikke igen uden ny godkendelse.
3. **Ingen mellemkig** for XAU. Under indsamlingen tælles kun gyldige hændelser.
   - XAU's analyse kører én gang, når der er 24 gyldige hændelser, eller 2027-12-31, alt efter hvad der kommer først.
   - Er der da under 20, er udfaldet INSUFFICIENT_DATA.
4. **Stopper streamen** (gælder kun XAU, hvis den nogensinde godkendes), registreres hullerne. Hændelser uden
   komplette barer udelukkes. Perioden forlænges ikke.

## 9. Godkendelser før lås og tidligste datoer

| Krav | Hvem | Tidligst |
|---|---|---|
| Direktøren beslutter, at H1 bliver en formel hypotese. Ordre 58/58-A og 61 tillader det ikke nu: "ingen låse" | direktør | ny ordre |
| Dateret ændring i PROTOCOL_V3 med denne tekst, committet før data. Claude låser aldrig automatisk (G28) | ejer | efter direktøren |
| **VERIFIED_OWNER_APPROVAL** til låsen. Et chat-ja er UNVERIFIED_ORIGIN. Kræver ejernøglen (D5, `owner_key_registered`) | ejer | når D5 er gjort |
| Direktørens ja til BLS-arkivtjekket (punkt 1.4) og en kontrolleret helligdagsliste | direktør | før låsen |
| BTC-kørsel på cachede filer | – | **2026-11-14 00:00 UTC** (G01) og efter låse-commit |
| XAU: ny 1m-stream. VERIFIED_OWNER_APPROVAL (ordre 58 U1, også ved alfa 0), og en ny ordre, fordi ordre 61 er NO-GO for nye streams | ejer + direktør | ingen dato |

- Alfa = 0 (beskrivende). Ingen W0-andel (G20) søges.
- Ingen deploy, så K1-K3 er ikke relevante. pm_lp, HFC-1, STRAKS, S1 og COIN-M røres ikke.
- **DNS:** den primære del bruger ingen vært. Filerne og kalenderen er cachet, så DNS-blokeringen af
  data.binance.vision er uden betydning. Den sekundære del ville bruge fapi.binance.com.

**Tidligste dom:**
- BTC: samme dag som kørslen, dvs. tidligst 2026-11-14, hvis lås og VERIFIED_OWNER_APPROVAL foreligger. Realistisk
  først efter D5.
- XAU: tidligst ca. 10 måneder efter streamstart (ca. 2 hændelser om måneden, 20 hændelser).

## 10. Falsifikationsmatrix

| Hypotese | Primært endepunkt | Kill-regel | Data til rådighed? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| U4 H1: RV efter 08:30 ET-udgivelsen er højere på CPI/NFP-dage end på matchede kontroldage (BTCUSDT perp, explore0; XAUUSDT kun fremad som sekundær) | d₁₅ = ln RV₁₅(udgivelse) − ln RV₁₅(kontrol), månedsklynge-t, Holm over 5/15/60 min, afgjort på 15 min | FAIL, hvis den øvre 95 %-grænse for exp(d̄₁₅) < 1,25. INSUFFICIENT_DATA ved < 20 hændelser eller < 10 klynger | BTC: ja, 22 cachede 1m-filer 2020-03..2021-12 og BLS/FOMC-kalender 2020-21 (≤ 44 dage). Låst indtil 14/11 og en lås. XAU: nej (ingen 1m-stream) | direktørbeslutning + dateret lås med VERIFIED_OWNER_APPROVAL (D5). XAU også stream-godkendelse og en ny ordre | BTC 2026-11-14 (realistisk efter D5). XAU ≥ 10 mdr. efter streamstart | **PREREG_READY. Lås NO-GO under ordre 61.** BTC: CONDITIONAL GO til en senere lås (EXPLORATORY, lav styrke ≥ ca. 1,4×). XAU: NO-GO nu |

## 11. Kildespor (sha256 nu)

| Fil | Commit | sha256 |
|---|---|---|
| `research/desk/US_MACRO_0830_DESIGN.md` | `3c75685` | `d0e1e1627b98b2ecf9b86926d178cbf3a229dd28d6b8a1e501bdbb6146baac3f` |
| `research/PROTOCOL_V3.md` | `ec91280` | `0a09b3e954d92c8294e1b15f27b12fbc344187562bc73f393d2dd892b2ce6c80` |
| `research/desk/GATE_MATRIX.json` | `efca77d` | `19b87e9af0cf3c979060ecd825282296a53747b806aeb0ab85bcce0b7e51da99` |
| `lab/ingest.py` (`BLS`, `BLS_KEEP`, `parse_bls`) | `daa3992` | `61d2f07f4334ab70b147dc6057d86f545a6e987562ca0c1928639882a5f4db7e` |
| `lab/m21jscreen.py` (`calendar`) | `223b92b` | `d8b04b956ee11c92db219db9fcd1865f040e823d6ec18ac382ccb6ea8a96b2ef` |
| `research/studies/R3_m24.json` (tidligere brug af samme barer) | `ab9c201` | `b4f632d2f52c07e8b8c12cdc01d6a73c825121c9c13db1ba3d910830bc778dfb` |

PROTOCOL_V3 henvisninger: §2 (vinduer), ændring 10/10c (explore0, aldrig bevis), 14 (kalender, bls.gov),
24/24a (de 44 1m-filer), 32 (styrke).
