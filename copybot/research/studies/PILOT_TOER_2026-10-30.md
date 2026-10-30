# Pilotens tørre kørsel: beviskravet er nået (2026-10-30)

Skrevet 2026-10-30 kl. 09:48 lokal (08:48 UTC) af Claude (Mission 25, dagligt tjek). Kun læsning af
`data/pilot/ledger.jsonl` i produktionen (`python3 -m pilot status` og `report`). Tal:
`research/studies/PILOT_TOER_2026-10-30.json`.

## Regel

Ændring 29 punkt 8: tør kørsel i mindst 48 timer og mindst 20 runder uden fejl i stop-logikken. Timerne tæller fra
første til sidste tørre runde (ændring 29e punkt 4). Siden ændring 29a er piloten kun research og papir: der findes
ingen rigtig ordre-, nøgle- eller kontokode, og en grøn tør kørsel åbner ikke for noget.

## Resultat

| Krav | Målt | |
|---|---|---|
| ≥ 20 tørre runder | 22 | opfyldt |
| ≥ 48 t | 65,5 t (10-27 15:04 → 10-30 08:36 UTC) | opfyldt |
| 0 stop | 0 | opfyldt |

**Den tørre kørsel er grøn.** Processen kører videre til sine 30 runder (pid 144475); intet ændres.

## Hvad kørslen viste (simuleret mod Binances offentlige bog, 15 USDT pr. runde)

- **Taker (13 runder, 13 fyldt):** slippage mod mid ved køb median 5,5 bp (p95 14,1), ved salg 3,5 bp (p95 21,1).
  Rundturens tab inkl. gebyr og 60 s prisbevægelse: median 27,2 bp, middel 28,6, p95 76,1.
- **Maker (9 runder, 1 fyldt):** fill-rate 1/9 inden for 30 s på bedste bud. Den ene fyldte runde (D17) kostede
  16,2 bp (gebyr antaget, `fee_assumed`).
- **Samlet simuleret resultat:** −0,87 USDT over 22 runder; restbeholdning (dust) 0,29 USDT.
- **Sprungne runder (tæller ikke):** 4 tom bog (EPICUSDT i status BREAK, ændring 29d), 1 for bred spread, 0 netværk.

## Forbehold

- **Processen døde to gange** før rettelserne: tom bog (10-28 00:35 og 13:04 UTC, ændring 29d) og en netværksfejl før
  planen (10-28 20:35 UTC, ændring 29e). Ingen af dem var i stop-logikken, og intet var sendt. Pausen 10-28 20:35 til
  10-29 07:12 UTC tæller med i timerne efter 29e punkt 4. Kun 10 af de 22 runder er kørt med den nuværende kode.
- Tabet pr. rundtur blander gebyr, slippage og 60 sekunders markedsbevægelse; det er ikke en ren omkostning.
- Simulerede fills mod en offentlig bog er ikke rigtige fills (ændring 29a punkt 2). Maker-fill-raten er især usikker:
  køens position er ukendt.
- 22 runder fordelt på 7 mønter og 2 tilstande; ingen sammenligning med papirmodellen er udført her.

## Hvad det betyder

Stop-logikken og runde-maskineriet har kørt i over 48 timer uden et stop. Det er alt. Der er ingen konto, nøgle eller
rigtig handel; ændring 29a gælder. En eventuel rigtig pilot kræver en ny dateret ændring, en børs fra V1-arbejdet
(V1 forkastet for alle 5 børser 10-29) og brugerens udtrykkelige ja.
