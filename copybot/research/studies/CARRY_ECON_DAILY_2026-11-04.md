# Daglig carry-økonomi: hvor ofte dækker funding omkostningerne? (plan kl. 14:27 lokal 11-04, før tallene)

Forslået af ChatGPT 11-04 (opgave 2), besluttet af Claude. **Beskrivende overvågning, ingen test, intet afgøres**;
ingen strategiændring. Kun `census/1`-snapshots, som lab'et har indsamlet fremadrettet siden 10-27 15:00 UTC
(ingen historisk forespørgsel), og `M2_FORWARD_LEDGER.md`.

**Tærskler (fra 27.4 B, uændrede):** break-even 12,5 % p.a. (gebyr + slippage, 14 d); M2 med margin k = 0,5:
18,8 % p.a. APR = lastFundingRate × 3 × 365.

**Univers:** U1 = alle USDT-perps i snapshottet. U2 = de mønter, carry-banerne har handlet perp-ben i (`sim_fills`
LANE_*, ikke HL), fastlagt ved første kørsel og noteret.

**Mål pr. UTC-dag (kun hele dage med ≥ 20 snapshots; færre markeres "manglende data"):**
1. Andel af U1 og U2 med dagsmiddel-APR ≥ 12,5 % og ≥ 18,8 %.
2. Pr. U2-mønt: dagsmiddel-APR.
3. Persistens (kun U1): af mønter med 72 t-middel ≥ 12,5 % ved dagens slut, andelen hvis middel over de næste 3 døgn
   (HL-holdetid) også er ≥ 12,5 %. 14-døgnspersistens (carry-holdetid) rapporteres først, når 14 dages data efter
   dagen findes.
4. Carry-starter samme dag: antal, vurderbare, og hvor mange over 12,5 % / 18,8 % (fra M2-regnskabet).

Kører første gang nu for 10-28..11-03 og derefter dagligt i 00:35 UTC-vinduet. Resultaterne tilføjes nedenfor.

## Første kørsel (kl. 14:27 lokal 11-04; 173 snapshots 10-27 15:00 .. 11-04 12:21 UTC)

U2 (17 mønter med carry-perp-ben): ADA, APE, AXS, BCH, BNB, BTC, CRV, ETC, ETH, ICP, LINK, LTC, SNX, TRX, VET, XRP, XTZ.

| Dag | Snapshots | U1 n | U1 ≥ 12,5 % | U1 ≥ 18,8 % | U1 median-APR | U2 ≥ 12,5 % | U2 højeste | Persistens 3 d (U1) |
|---|---|---|---|---|---|---|---|---|
| 10-28 | 24 | 890 | 8,0 % | 4,9 % | 4,5 % | 0/17 | 10,9 % (XRP) | 38 af 70 (54 %) |
| 10-29 | 24 | 896 | 7,4 % | 4,8 % | 3,4 % | 0/17 | 9,9 % (APE) | 41 af 69 (59 %) |
| 10-30 | 19 | | | | | | | manglende data |
| 10-31 | 11 | | | | | | | manglende data |
| 11-01 | 24 | 896 | 6,9 % | 4,8 % | 2,7 % | 0/17 | 10,9 % (6 mønter) | endnu ikke 3 d efter (huller) |
| 11-02 | 24 | 896 | 10,7 % | 7,7 % | 5,5 % | 0/17 | 10,9 % (4) | endnu ikke |
| 11-03 | 24 | 896 | 14,2 % | 10,8 % | 5,5 % | 0/17 | 10,9 % (8) | endnu ikke |

- **Ingen af carry-banernes 17 mønter** havde på nogen hel dag et dagsmiddel ≥ 12,5 %; de højeste ligger på 10,9 %
  (0,0001 pr. 8 t, Binances standardrente). Den nuværende carry-udvælgelse opererer altså i et univers, hvor
  break-even ikke nås med standardfunding.
- **I hele perp-universet** lå 7-14 % af mønterne over break-even og 5-11 % over M2's 18,8 %; stigende de seneste dage.
  Af dem, der lå over break-even på 72 t, var 54-59 % stadig over i de næste 3 døgn. De er ikke banekandidater i dag
  (andre mønter end explore0-kurvene); om de har spot-ben og likviditet, er ikke undersøgt.
- **Carry-starter:** ingen nye siden M2-regnskabet blev oprettet.
- **Manglende data:** 10-30 (19) og 10-31 (11) snapshots; årsagen er ikke undersøgt her.
- Beskrivende; afgør intet; ingen regel ændret.

## Kørsel 11-05 (kl. 01:40 lokal; dag 11-04, 24 snapshots)

| Dag | Snapshots | U1 n | U1 ≥ 12,5 % | U1 ≥ 18,8 % | U1 median-APR | U2 ≥ 12,5 % | U2 højeste | Persistens 3 d (U1) |
|---|---|---|---|---|---|---|---|---|
| 11-04 | 24 | 896 | 13,5 % | 8,0 % | 5,5 % | 1/17 | 12,7 % (BNB) | endnu ikke |

- **Første gang** én af de 17 carry-mønter (BNB) har et dagsmiddel over break-even; 12,7 % ligger under M2's 18,8 %.
  Én dag er ikke en carry-start; ingen ny start (M2-regnskabet uændret).
- Persistens for 11-01..11-03 kan endnu ikke beregnes (vinduet rører hullerne 10-30/10-31 eller er ikke udløbet).
- Beskrivende; afgør intet.
