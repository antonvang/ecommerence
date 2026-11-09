# Afstemning lane-rapport 2026-11-08 mod netrapport (direktørtillæg 59 B)

- Lane-rapport: `/home/anton/ecommerence/copybot/data/lab/artifacts/_lane/2026-11-08.json` (sidste mærkning med ts < 11-09 00:00:00 UTC).
- Netrapport: `/home/anton/copybot-dev/copybot/research/data/net_report/net_2026-11-09.json` (seneste mærkning ved kørslen).
- Konti: 12 / 12.
- Totaler: lane -146.74, netrapport -157.65, forskel -10.91; forklaret af mærketidspunkt -10.91.
- **Status: RECONCILED**

| Konto | Kilde | Lane netto | Lane-mærke (UTC) | Net netto | Net-mærke (UTC) | Forskel | Årsag | Mærke før dagsslut (t) |
|---|---|---|---|---|---|---|---|---|
| df98c7 | carry90 | -10.01 | 11-08 06:40:31 | -10.01 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| 4018bc | lane | -5.70 | 11-08 06:40:31 | -5.70 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| 9bb233 | straks | -106.72 | 11-08 23:00:59 | -107.96 | 11-09 00:00:48 | -1.24 | TIMING_MARK | 1.0 |
| 8593e8 | lane | -0.82 | 11-08 06:40:31 | -0.82 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| a1f395 | carry90 | -9.97 | 11-08 06:40:31 | -9.97 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| b6feb9 | pairs | -3.11 | 11-08 23:00:59 | -9.10 | 11-09 00:00:48 | -5.99 | TIMING_MARK | 1.0 |
| c841b2 | lane | -13.48 | 11-08 06:40:31 | -13.48 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| c1f595 | straks | 31.85 | 11-08 23:00:59 | 28.16 | 11-09 00:00:48 | -3.68 | TIMING_MARK | 1.0 |
| a61803 | carry90 | -11.15 | 11-08 06:40:31 | -11.15 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| a7505e | lane | -1.17 | 11-08 06:40:31 | -1.17 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| 64dccc | lane | -3.06 | 11-08 06:40:31 | -3.06 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |
| 0457b8 | lane | -13.39 | 11-08 06:40:31 | -13.39 | 11-08 06:40:31 | +0.00 | SAME_MARK | 17.3 |

## Forklaring (kl. 02:44 lokal 11-09)

- **Hele forskellen (−10,91) er timing.** Lane-rapporten værdiansætter med den sidste mærkning *før* dagsslut
  (`ts < 00:00:00`, dvs. 23:00:59). Netrapporten kørt 00:38 UTC brugte den seneste mærkning (00:00:48). Det berører
  kun de tre konti, der mærkes hver time: STRAKS-FØLG −1,24, STRAKS-MOD −3,69 og PAR-BOG −5,99. Hver netto er lig
  equity ved sin egen mærkning minus kapital (kontrolleret pr. konto).
- **Ingen bogførte poster er ændret.** Begge totaler er korrekte for deres eget tidspunkt. De må bare ikke kaldes samme
  total. Fremover angives altid mærketidspunktet ved en total.
- **Dekomponerings-forbehold i netrapporten:** netto er equity ved mærkningen. Kolonnerne for gebyrer, funding og fyld
  tæller dog alle rækker frem til kørselstidspunktet. STRAKS havde fyld kl. 00:02:52, efter mærkningen 00:00:48, så
  gebyrkolonnen (+2,00) er ikke med i netto endnu, og residualen "prisbevægelse" opsuger forskellen. Forslag uden
  ændring nu: skær kolonnerne ved `marked_at`.
- **Driftsafvigelse (ny):** de 9 lane- og carry90-konti er **ikke mærket siden 2026-11-08 06:40:31 UTC** (17,3 t før
  dagsslut). Funding skrives stadig ved 00:00, men equity fryses. Der er ikke logget nogen fejl (ingen paper.error).
  - Tidspunktet passer med DNS-blokeringens genkomst kl. 06:45:48 UTC. Spotbenene kræver sandsynligvis
    data-api.binance.vision.
  - Konsekvens: deres netto i både lane-rapport og netrapport er *forældet* (mærket 11-08 06:40), ikke dagens værdi.
  - Intet rørt (ingen genstart, ingen DNS-ændring). Status: DEGRADED.
