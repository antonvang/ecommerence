# Rekonstruktion af scanner_premium-banerne EPIC, MITO, HOT (2026-10-25 kl. 22:05)

Kun eksisterende papirdata: `sim_fills`, `sim_orders`, `events`, `risk_events` og `/api/paper2`. Ingen ny hentning.
Kapacitetsmålinger fra senere end åbningen bruges ikke.

## Hvad der skete (observeret)
| Bane | Åbnet → lukket | Ordre pr. ben | Niveauer gået | VWAP fra midten, åbning (spot / perp) | Lukning (spot / perp) |
|---|---|---|---|---|---|
| EPIC (4c87) | 10-19 21:24 → 23:41 | ca. 5 000 USD | 10 / 8, lukning 17 / 10 | 30,0 / 21,9 bp | 42,3 / 32,3 bp |
| MITO (7af2) | 10-20 03:37 → 04:00 | ca. 5 000 USD | 6 / 5, lukning 6 / 4 | 29,3 / 24,0 bp | 29,6 / 17,3 bp |
| HOT (9e96) | 10-20 02:18 → 03:00 | ca. 5 000 USD | 3 / 5, lukning 3 / 6 | 40,9 / 11,9 bp | 31,1 / 11,2 bp |

- Hver bane lavede **én runde**. "17–45 fills" var bogniveauer i to ordrer pr. ben, ikke mange handler.
- Bogens alder ved fill: bogen blev læst ca. 0,3 s efter ordretidspunktet. Den var frisk.
- Udløser var en perp-præmie på 0,50–0,62 % i to scanninger (ændring 12 punkt 2).
- EPIC blev sat på pause ved lukningen (3 spread-anomalier) og trukket tilbage. MITO blev trukket tilbage ved
  afnoteringen. HOT var flad i 2 døgn.
- **Forringelse undervejs:** kun EPIC blev tydeligt dyrere ved lukningen (spot 30 → 42 bp, perp 22 → 32 bp). MITO var
  uændret, og HOT blev billigere. Tabet skyldes bogens dybde ved hver ordre, ikke gentagne handler.

## Afstemning mod labbens egen opdeling (`/api/paper2`)
| Bane | Total | Gebyrer | Afstand fra midt (fills) = spread/slippage | Pris/basis | Funding | Kontrol |
|---|---|---|---|---|---|---|
| EPIC | −62,22 | −19,27 | −60,52 | +17,57 | 0,00 | −19,27 − 60,52 + 17,57 = −62,22 |
| MITO | −68,58 | −20,05 | −50,24 | 0,00 | +1,70 | = −68,59 (afrunding) |
| HOT | −66,88 | −20,02 | −47,55 | +0,69 | 0,00 | = −66,88 |

Summen af |fill − midt| · mængde fra `sim_fills` er præcis lig labbens `spread_slippage` (bog + 0,02 %-tillæg).
Gebyrerne er identiske. Alt er realiseret (urealiseret 0).

## Hvad der mangler for en fuld årsagsforklaring
- **Ordrebøgerne er ikke gemt.** Kun de niveauer, en ordre faktisk gik igennem, kan ses. Salgssiden ved åbningen og
  bogen mellem de to ordrer kendes ikke. Rundturen ved åbningen er derfor et **estimat** (2 × summen af benenes VWAP,
  symmetri antaget).
- Om præmien (signalet) faktisk lukkede som forudsagt: `price_basis` er positiv for EPIC (+17,57), så præmien gik den
  rigtige vej, men langt fra nok til at dække 80 USD i omkostninger. Et præmie-forløb pr. minut for coinet er ikke gemt.

## Kontrafaktisk (estimat, ikke realiseret)
Ændring 25's gate ved åbningen: EPIC 104, MITO 107 og HOT 106 bp > 46 bp, så alle tre stoppes. De 11 øvrige baner
(11–30 bp) passerer. Tab undgået ≈ 197,7 af 221,2 USD (89 %), forudsat at intet andet var åbnet i stedet.
