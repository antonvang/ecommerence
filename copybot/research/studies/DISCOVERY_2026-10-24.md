# Discovery 2026-10-24: Upbit-noteringer som ny begivenhedskilde (kun læsning, negativt)

Undersøgt 2026-10-24 ca. 00:15–00:40 lokal tid. Intet her er en hypotese, en lås eller en afgørelse.

## Spørgsmål

Forskningskøen er tom (kataloget er brugt, alle SCREEN_PASS under ændring 17 er afgjort). Kan Upbits KRW-noteringer
(en kendt koreansk noteringseffekt) blive en ny begivenhedstype i ændring 17's pipeline?

## Hvad blev målt

- Kilde: `https://api-manager.upbit.com/api/v1/announcements?os=web&category=trade` (uden nøgle). 41 sider à 20,
  `total_count` 802, ældste meddelelse 2017-10-27. Hentet til scratchpad, ikke til laboratoriet.
- Adgangsgrænse: Cloudflare svarer `error code: 1015` efter ca. 10 hurtige kald; med 5–10 s mellemrum og pauser gik
  alle 41 sider igennem.
- KRW-noteringsmeddelelser ("KRW … 디지털 자산 추가" / "신규 거래지원") pr. år: 2017 1, 2020 0, 2021 4, 2022 6,
  2023 12, 2024 37, 2025 85, 2026 78.
- I udforskningsvinduet 2020–21 (explore0) findes kun 4 meddelelser med 10 mønter (2021-10-15 SOL, MATIC, NU;
  2021-10-27 1INCH, AAVE, MASK; 2021-11-18 ALGO, AUDIO; 2021-12-15 NEAR, YGG). Arkivet er tydeligvis ufuldstændigt før
  2023 (Upbit noterede langt flere mønter i 2020–21).

## Konklusion

Ikke testbar under protokollen: screening må kun bruge explore0, og ændring 17's UNTESTABLE-regel kræver ≥ 15
hændelser med data. 2022–2023 er brugt (train3/validation3), 2024 er holdout, 2025+ er reserveret; ingen af dem må
bruges til at screene en ny kilde. Ingen kode, ingen ændring. Kilden kan blive relevant som fremadtest (som H5F), hvis
en dateret ændring låser den, før data findes; med 78–85 noteringer om året ville 15 hændelser tage ca. 2–3 måneder.

## Opfølgning samme nat: Coinbase-noteringer (ændring 17g) — screenet, alle 9 SCREEN_FAIL

Kilde: CoinMetrics' katalog (første handel pr. Coinbase USD-marked; allerede tilladt vært; `api.exchange.coinbase.com`
blev ikke tilføjet, fordi den også er en handelsvært). Engangskørslen i produktionen (2026-10-24 ca. 01:37) gemte 254
`cb_listing` og 254 `cb_none`; 121 begivenheder i explore0. Screenet automatisk af pipelinen (hændelser
`research.hypothesis_screen`, ca. 01:46–01:53), explore0, ændring 17's uændrede tjek:

| Udfald | n | gennemsnit | p (tosidet) |
|---|---|---|---|
| ar_1d | 35 | +0,26 % | 0,94 |
| ar_7d | 35 | −2,9 % | 0,60 |
| far_1d | 40 | +1,1 % | 0,74 |
| far_7d | 40 | −6,7 % | 0,20 |
| fund_7d | 33 | ≈ 0 | 0,99 |
| sar_1d | 68 | +1,25 % | 0,61 |
| sar_7d | 68 | −4,2 % | 0,30 |
| vol_3d | 33 | −16 % | 0,021 |
| volume_1d | 33 | +25 % | 0,037 |

Ingen når p ≤ 0,005; intet udkast, ingen lås. Perp-udfaldene dækker kun 33–40 af 121 mønter (de fleste havde ingen
USD-M-perp i 2020–21). Fortolkning (ikke en test): handelsstarten på Coinbase flytter ikke Binance-kursen målbart;
en eventuel effekt ligger ved annonceringen, som denne kilde ikke har tidspunktet for. Efter ændring 17 punkt 4
screenes nøglerne aldrig igen under m17g.
