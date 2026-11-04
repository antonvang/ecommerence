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
