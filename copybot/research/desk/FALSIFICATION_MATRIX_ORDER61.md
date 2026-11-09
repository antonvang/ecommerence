# FALSIFICATION_MATRIX: ordre 60/61 (2026-11-09 kl. 13:22 lokal)

Kun design og readiness. Intet er låst, der er ikke hentet data, og ingen alfa er brugt. Kilder: de enkelte designnoter i
`research/desk/`.

## 1. Kandidater

| Hypotese | Primært endepunkt | Kill-regel | Data til rådighed? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| **K05** negRisk v2: ≥ 20 episoder/uge med ≥ 1 c/sæt netto ved 100 sæt, bekræftet efter 60 s (`K05_NEGRISK_V2_DESIGN.md`) | netto USDC pr. eksekverbar episode (S1-fyld, inkl. legging) | 0 episoder på 7 gyldige dage, < 40 på 28 dage eller median netto ≤ 0 → FALSIFIED; dækning < 90 % → INVALID | Nej (ny separat proces; clob, gamma og docs DNS-blokeret) | ny proces/stream, dateret lås + VERIFIED_OWNER_APPROVAL (D5); fase B W0-α | fase A kill-tjek 12-07 og 12-28 (deploy tidligst 11-30) | **Betinget GO, kun beskrivende fase A (α = 0).** NO-GO alfa. Sandsynligvis FALSIFIED (~85 %) og lille gevinst |
| **K04** HLP-vault mod DTB3 (`K04_HLP_VAULT_DESIGN.md`) | middel af ln(1+r_d) − rf_d over 182 døgn, NW-t | middel ≤ 0 ved dag 182; KILL_TAIL ved fald ≥ 10 % eller udbetalingspause > 24 t; ≤ −2 % ved dag 91 → stop | Nej (ny datalinje via eksisterende HL-afsender; historik kasseres) | lås + D5 + datalinje-ja + W0-α (optaget) | 2027-05-31 | **NO-GO** alfa (styrke 0,03–0,21; hale uprissat). Beskrivende log kun på eksplicit ejer-ja |
| **K10** short efter Monitoring Tag, BTC-hedget (`K10_MONITORING_TAG_DESIGN.md`) | gennemsnit af netto over de første 20 mønter | ≤ 0 → FALSIFIED; M1F's Y ≥ 0 → STOPPED_FUTILE; ≥ 3/10 rammer −100 % → KILL_TAIL | Delvis (hændelser ja; priser efter 11-14 og lås) | lås + D5 + W0-α (optaget); K10-D lås + D5, α = 0 | K10-D ~2027-05; K10 ~2027-09..2028-03 | **NO-GO nu.** Betinget K10-D (α = 0) før M1F kører |
| **U4** H1 08:30-RV (`U4_0830_PREREG_DRAFT.md`) | d₁₅ = ln RV₁₅(udgivelse) − ln RV₁₅(kontrol), månedsklynge-t, Holm 5/15/60 | øvre 95 % af exp(d̄₁₅) < 1,25 → FAIL; < 20 hændelser eller < 10 klynger → INSUFFICIENT_DATA | BTC: ja (22 cachede 1m-filer, explore0); XAU: nej | direktørbeslutning + dateret lås + D5 | BTC tidligst 14/11 (realistisk efter D5) | **PREREG_READY.** Lås NO-GO under ordre 61. Beskrivende, ingen strategi |
| **U1** ORB15-QQQ (`orb15/ORB15_GO_NO_GO.md`) | netto pr. handelsdag | øvre 95 % ≤ 0 → FALSIFIED | Nej (ny 1m-stream) | stream + VERIFIED_OWNER_APPROVAL | ~2027-05 | **NO-GO** (gebyr 8–10 bp mod 6–8 bp brutto) |
| **U2** fomo 30 s-kopi (`fomo/GO_NO_GO_RECOMMENDATION.md`) | følgerens netto pr. signal | øvre 95 % ≤ 0 → FALSIFIED | Nej (Solana-værter + POST) | værter + POST-undtagelse + stream | 7 dage efter start | **NO-GO** (oktober-data negative) |

## 2. Readiness for milepælene

| Dato | Hvad | Status | Kilde |
|---|---|---|---|
| 12/11 ≥ 17:11:51 UTC | STRAKS 7 d | KLAR (dry-run OK, NOT_DUE-vagt, pins OK, ingen DNS-afhængighed) | `MILESTONE_DRYRUN_60AC.md` |
| 14/11 | gate-status | KLAR (`gate_status.py`; preview: 6 READY, 8 kræver D-godkendelse, 6 NOT_DUE, 7 BLOCKED, 2 WITHDRAWN) | `GATE_STATUS_PREVIEW_2026-11-14.md` |
| 19/11 ≥ 00:35 / 20:51:09 UTC | HFC-1 14 d + PAR-BOG | KLAR | `MILESTONE_DRYRUN_60AC.md` |
| 20/11 ≥ 09:55:07 UTC | S1 | KLAR; forventet INSUFFICIENT_OBSERVATION (0 nye overgange) | `S1_READINESS_2026-11-20.md` |

## 3. Reelle blokeringer

1. **D5 ejernøgle** mangler. Uden den kan ingen lås gøres verificeret (`OWNER_KEY_GUIDE_D5.md`).
2. **Lokal DNS** (192.168.1.3) blokerer data-api.binance.vision, data.binance.vision, clob.polymarket.com,
   gamma-api.polymarket.com og docs.polymarket.com. Konsekvenser: 9 carry-konti STALE, pm_lp skriver intet, HFC-1-
   kohorter mangler, K05 kan ikke starte. Omgås ikke.
3. **W0-alfa** (0,0375) er reserveret til andre (D6). Ingen kandidat kan få bekræftende alfa uden en ejerbeslutning.
4. "Få overgange" i S1 er ikke kvantificeret. Direktøren afgør, hvis tallet er ≥ 1.

## 4. Anbefaling af næste prioritet

1. Kør milepælene 12/11, 14/11, 19/11 og 20/11 efter procedurerne. Det er den eneste ægte evidens i sigte.
2. U4 H1 (BTC, explore0) er den billigste næste test, der kan låses: data er cachet, der er ingen ny stream, og dommen
   kan falde hurtigt efter lås. Den kræver kun D5 og direktørens beslutning. Den er beskrivende, ikke en strategi.
3. K05 fase A kun, hvis DNS-blokeringen ophører, og D5 findes.
4. K04 og K10 venter (styrke og alfa).
