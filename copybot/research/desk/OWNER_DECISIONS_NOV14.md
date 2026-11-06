# Ejerbeslutninger til 14/11 og frem til 28/11 (direktørordre 52 P1)

**Skrevet 2026-11-06 kl. 14:38 UTC. Listen beder om noget, men udfører intet.** Ingen af punkterne udføres af
assistenten:
- Claude låser ikke uden udtrykkeligt ja.
- Claude signerer aldrig, laver eller bruger aldrig ejerens nøgle og kører aldrig `approve-template`.
- Claude aktiverer ingen strøm.

**Grundregel:** Tages en beslutning ikke, går den pågældende undersøgelse **ikke videre**. Der findes ingen
standardværdi, ingen automatisk godkendelse og ingen "stiltiende ja". Gates og flag står i
`research/desk/GATE_MATRIX.json`, og id'erne AMB-xx står i `NOV14_READINESS.md` afsnit 11.

Om tidligere godkendelser:
- Ejerens "I behøver ikke spørge mig gør alt" (2026-11-04) er en generel instruks.
- Efter OWNER_APPROVAL_P0 tæller en generel instruks aldrig som godkendelse af en bestemt skabelon. Alle historiske
  skabelongodkendelser er UNVERIFIED_ORIGIN.
- Om PROTOCOL_V3-låsene A og B kræver en verificeret signatur, står ingen steder (AMB-29). Listen kræver derfor mindst
  et udtrykkeligt ja pr. lås.

## Før eller senest 14/11

| # | Beslutning / handling | Frist (UTC) | Flag i matrixen | Hvis den ikke tages |
|---|---|---|---|---|
| D1 | **Lås A:** udtrykkeligt ja til at indsætte MISSION27_3 6b + 7d ordret som næste ledige ændring ("metode n6"). Valgfrit: med verificeret signatur | når som helst; virkning tidligst 2026-11-14 00:00 | `owner_confirms_lock_A` | A låses ikke, `n6_funding.py run` nægter fortsat, og ingen n6-data åbnes. X3 kan heller ikke køre 28/11 |
| D2 | **Lås B:** (a) ejerens formulering af 6c punkt 1, fordi den nævner den karantænerede parliste (AMB-18). Universet skal bygges fra et nyt `market/all` under 38 B, og Binance-krydsningens kilde og as-of skal angives (AMB-19). (b) Udtrykkeligt ja til låsen | samme | `owner_resolves_B_point1`, `owner_confirms_lock_B` | B låses ikke, Upbit-værten forbliver lukket, og ingen n4-data åbnes |
| D3 | **F2-kalibrering:** kvittering for, at en kalibreringsspec (kun effektstørrelse og varians; udviklingsinformation; aldrig validering) må åbne explore0-filerne. Afgørelse af AMB-02 (23/24 afkast), 03 (365 rækker/dage), 04 (opvarmning), 05 (dækning), 06 (EWMA-start), 07 (HAR ≤ 0), 08 (vægte) og 10 (vinduesgrænse), eller en udtrykkelig udsættelse af dem | før kalibreringen; tidligst 2026-11-14 00:00 | `owner_ack_f2_calibration` (+ `f2_calibration_spec_committed`) | Ingen F2-kalibrering; F2 forbliver CONDITIONAL. C1 kan ikke få en RV-konvention |
| D5 | **Ejernøgle** (FACTORY_SECURITY P1 ejerhandling 1-3): lav nøglen uden for denne maskine; offentliggør fingeraftrykket et sted, assistenten ikke kan skrive; signér rodposten | ingen fast frist; forudsætning for D4, D6, D7 og D8 | `owner_key_registered` | Ingen ny skabelon kan godkendes verificeret: F2-bekræftelse, C1, F3, LIQPROXY1 og FUNDFRAG1 står stille |

Rækkefølge 14/11 med D1 og D2:
1. `date -u`.
2. Lås A og commit.
3. Lås B og commit.
4. Kalibreringsspec (D3) og commit.
5. Identitetsmanifester.
6. Indlæsere og syntetiske tests med grøn suite.
7. Én kørsel A (X1/X2), én B og én F2-kalibrering.

Mangler et punkt, springes kun det over. Resten fortsætter.

## Efter 14/11 (ingen af dem er nødvendige 14/11)

| # | Beslutning / handling | Frist (UTC) | Flag | Hvis den ikke tages |
|---|---|---|---|---|
| D4 | **F2-evalueringsvindue:** separat godkendelse af vindue, styrke (efter kalibreringen) og en låst, versioneret protokol. Signeret | efter kalibreringen; ingen fast frist | `owner_signed_f2_template`, `f2_window_approved`, `f2_lock_amendment_committed` | Ingen F2-bekræftelse; train3/validation3 åbnes ikke for F2 |
| D6 | **W0-rangering:** vælg højst 3 af F2, F3, LIQPROXY1 og FUNDFRAG1 (α_F 0,0125 hver; 0,0375 tilbage). LIQPROXY1 forbliver en hypotese under W0; ingen omklassificering til måling for at undgå multipel-test-korrektion (ordre 52). Signeret | før den første W0-opkrævning (tidligst ved en fremadtests evaluering; LIQPROXY1 og FUNDFRAG1 planlagt 2026-12-07) | `owner_signed_alpha_ranking`, `w0_rank_includes_<id>` | Ingen W0-opkrævning, altså ingen fremadtest for nogen af de fire. Programstoppet i ændring 8 punkt 15 er uændret |
| D7 | **C1-aktivering:** (a) godkend en fremadrettet 1h-kline-strøm (vært, endpoint, kadence) eller lad C1 være inaktiv (AMB-13); (b) godkend `c1_config/2` (AMB-12); (c) ankringsmetode for head-hashen uden for assistentens skriveadgang; (d) dateret PROTOCOL_V3-ændring. Signeret | ingen fast frist; første EWMA-mål tidligst 2027-01-04 og HAR 2027-12-15 ved aktivering 14/11 | `owner_signed_c1_activation`, `fwd_kline_stream_approved`, `c1_config_v2_frozen`, `c1_amendment_committed`, `external_anchor_ready` | C1 forbliver READY_NOT_ACTIVE; ingen rigtig prognose skrives. Hver dags udsættelse flytter de første datoer en dag |

## 28/11

| # | Beslutning / handling | Frist (UTC) | Flag | Hvis den ikke tages |
|---|---|---|---|---|
| D8 | **F3:** fastlæg observationsenheden (afhængighed mellem mønter, udløb og overlappende positioner), adskil kalibrering (2 udløb) fra evaluering, og godkend en signeret skabelon. AMB-27 | tidligst 2026-11-28 00:00 | `owner_signed_f3_template`, `f3_observation_unit_locked`, `f3_lock_amendment_committed` | F3 forbliver DEFERRED; ingen COIN-M-data for F3 (A's X3 er uafhængig af D8) |
| D9 | **Genstart eller systemopdatering:** om og hvornår. Regel B gælder til og med 2026-11-27 (AMB-26). pm_lp's egne trin først | tidligst 2026-11-28 00:00 | `owner_requests_restart` | Ingen genstart; værten kører videre |

## Andre punkter, der ikke blokerer milepælene

| # | Beslutning / handling | Frist | Hvis den ikke tages |
|---|---|---|---|
| D10 | **S2** efter S1-evalueringen (tidligst 2026-11-20 09:55:07 UTC). Kun ejeren; Claude aktiverer aldrig S2 | ingen | S2 forbliver NO-GO. S1 fortsætter eller afsluttes som shadow-job |
| D11 | Signér legacy-manifestets digest og kontrolpunkter for auditloggen (FACTORY_SECURITY ejerhandling 4-5) | ingen | Kontrolpunkterne beskytter ikke; legacy-undtagelsen er ubundet. Ingen milepæl stopper |
| D12 | Valgfrit: bekræft de fail-closed læsninger af datoerne for HFC-1 (08/11 beskrivende, AMB-21), STRAKS (17:01:51 UTC, AMB-24) og PAR (20:41:09 UTC, AMB-25) | før den pågældende rapport | Den senere, fail-closed tid bruges; rapporterne er beskrivende og kræver ingen ejerhandling |

## Hvad ejeren ikke skal gøre

- give Claude nøgler, passphrases eller en oplåst ssh-agent på maskinen;
- godkende "alt", "*" eller en hel familie i én erklæring (OWNER_APPROVAL_P0 afviser det);
- røre pm_lp før dens egne datoer.
