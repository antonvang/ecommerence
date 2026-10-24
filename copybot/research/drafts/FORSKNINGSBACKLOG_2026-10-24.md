# Prioriteret forskningsbacklog — 2026-10-24

Et udkast, ikke en beslutning. Hver post er bygget på målinger fra i dag. En post, der kræver en LÅS, alfa eller data
før 2026-11-14, kræver en dateret ændring og brugerens ja, før den startes. Brugerens ja til en LÅS (2026-10-24
ca. kl. 22:43) bruges kun på en kandidat, der har bestået screeningen. Det har ingen kandidat i dag (0 PASS).

**Prioritet:** værdi (kan den give en nettofordel efter omkostninger?) × hvor hurtigt data er klar ÷ omkostning (alfa,
kalendertid, nye kilder). Alfa: k1–k4 er brugt. Næste er k5 = 0,0015625, og 0,003125 er tilbage i alt. Det rækker kun
til få låste målinger, så screeningen skal være streng.

| # | Post | Hvorfor nu | Data klar | Kræver |
|---|---|---|---|---|
| 1 | **Omkostningsbeslutning C pr. likvidt marked** (21l) | Bestemmer om rigtige omkostninger er lavere end B for BTC/ETH/TradFi; alt andet bygger på omkostningskravet | R1 "nok data" tidligst 2026-10-31 | brugerens ja pr. marked |
| 2 | **FOMC-hændelsesrapport** (`lab/eventreport.py`) | Første planlagte makrohændelse med scanner, bøger og nyheder samtidig; beskrivende | 2026-10-29 kl. 21:00 lokal tid | intet (beskrivende) |
| 3 | **Monitor for aftagende fordel, første rigtige status** (21w) | Fremadrettede konti når 14 døgn ca. 2026-11-01; M1 bliver målbar | 2026-11-01 | intet (status uden handling) |
| 4 | **Banernes univers mod kapacitetskurven** (21v) | Første kurve (tørkørsel på kopi) viser rundture på 23–245 bp ved 5 000 USD for spot-ben på HOT, EPIC, MITO, APE og AXS, mod < 1 bp for BTC og ETH. Fordelen pr. handel skal overstige det | første produktionskurve ved næste news-watch-pass | dateret ændring, hvis banernes møntfilter skal ændres (papirregel: Claudes mandat) |
| 5 | **R3 minutmakro** (`R3_MINUTMAKRO_PLAN.md`) | Hurtige makroreaktioner i TradFi-perps; de timebaserede screeninger var for grove | historik først 2026-11-14 | dateret ændring og LÅS ved PASS |
| 6 | **On-chain-børsstrømme, fremad (PIT)** (21q) | Den eneste rene PIT-kilde til strømme; de gratis historiske tal revideres | ≥ 30 dage PIT tidligst ca. 2026-11-24 | screening, derefter LÅS |
| 7 | **Fremadtests H5F/H5X/U1F/M1F** (16d/16f/17i/17j) | Låst; tæller hændelser | ved 20 hændelser pr. test | intet nyt (allerede låst) |
| 8 | **Udløbne perps i banernes univers** | EPICUSDT og MITOUSDT har status SETTLING og tomme bøger; ingen åbne positioner i dag | nu | kontrol i banens møntvalg (papirregel) |

**Lukkede retninger i dag (genåbnes ikke uden nye data eller ny mekanisme):**
- 4σ-fald: DROPPED.
- Spot–perp lead/lag (m21i): SCREEN_FAIL.
- Funding/TradFi-weekend (m21h): SCREEN_FAIL.
- Nyhedsinformation (m21j): SCREEN_FAIL.
- Generel bevægelsesscreening (m21c/m21f): SCREEN_FAIL.

**Ikke prioriteret:** betalte datakilder (PIT on-chain, tick-data). De kræver rigtige penge og dermed brugerens beslutning.
