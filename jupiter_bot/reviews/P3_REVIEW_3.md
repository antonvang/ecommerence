# P3 execution review, round 3 (independent, adversarial)

Commit: 7eff2b5
Execution-SHA256: 7dcbbd89836a3929204b1acfddb170a98c9d352519606e42a1463693e9285488

- I recomputed the Execution-SHA256 at `7eff2b5` with
  `python3 -m jupiter_bot.execution code-hash`. It now covers the import closure:
  28 files.
- Scope: the diff `5a65ceb..7eff2b5`, and every finding still open after round 2.
  Same rules as before: read-only, no keys, no network, nothing in `~/.config`,
  nothing in `~/jupiter-collector`.
- Tests:
  - `python3 -m unittest discover -s jupiter_bot/tests`: 333 tests, OK.
  - The execution test modules with a stub `nacl` importable: OK (1 skipped).
- Probes, all in
  `/tmp/claude-1000/-home-anton/64e74dba-157d-44f7-b4ce-5ec1e73fba4d/scratchpad/review/`:
  - `probe_r2.py`: round-1 and round-2 probes. The N1 section now stops at the
    decoder's "19 unexplained trailing bytes" rejection, which is the intended
    outcome.
  - `probe_r2_noN1.py`: the signer and engine probes from `probe_r2.py`, run
    past that point.
  - `probe_r3.py` (new): decoder attacks, differential fuzzing, end-to-end checks,
    the hash closure and the TLS context.

## Status of findings still open after round 2

| # | Status | Evidence |
|---|---|---|
| F3 / N1: on-chain floor, tail decode | **Fixed** | See the decoder analysis below. The old N1 payload is rejected with "19 unexplained trailing bytes". A floor of 0 (slippage 10000), an `in_amount` other than the order, a quote below the threshold, and two Jupiter instructions are all rejected end-to-end by `verify()`. |
| F1 (signer caps via the trailer) | **Fixed**. The caps now come from the exact-consumption decode. | S1 refused (destination), S3 refused (`max_trade_sol`). The signer copy agrees with `jupiter_ix` on every case and on 200k fuzzed inputs. |
| N2: review hash scope | **Fixed** | `execution_code_files` parses imports with `ast`, including imports inside functions, and follows them transitively. It covers `core.py`, `storage.py`, `jupiter.py`, `research/{lock,strategies}.py`, `marketdata/*` and the package `__init__` files: 28 files. I found no `importlib` or `__import__` in the closure. |
| N3: balance read slot | **Fixed**. The read is at `finalized`, and `context.slot >= fin_slot` is required (`engine.py:254-260`). | Code reading. E1 still holds: a landed order on a history-less RPC stays UNKNOWN. |
| N4: empty inner instructions | **Fixed**. At least one Token CPI under the Jupiter instruction's own index is required. | P7b is now rejected. |
| N5: allowlist and layout from memory | **Open as a note (accepted risk)**. See below. | |
| N6: `max_trade_sol` plausibility | **Fixed**. It is checked against the journal price in `mandate_valid`, and again with the fresh snapshot price in `decide()`. | Code reading. See L2 for a side effect. |
| F9: real transaction fixture | **Still open by nature**: it can only come from DRY_RUN. It is a pre-arm condition (see the end). The fake chain now reads routes front to back and ignores trailing bytes like Anchor, so the N1 regression test is meaningful. | `execution_fakes.py:63-90` |
| F16: TLS / SDK | **TLS fixed.** The context uses a fixed system CA file, so `SSL_CERT_FILE`/`SSL_CERT_DIR` are ignored (probe: 150 CAs loaded with both env vars pointing at nonexistent files). It requires TLS ≥ 1.2, keeps hostname checking, and refuses if no bundle exists. **SDK deviation** (hand-rolled decoder instead of the official Solana SDK): Anton must accept it explicitly, as before. | `probe_r3.py` |

## Decoder analysis (jupiter_ix.py and signer.decode_jupiter)

What I tried:
- **Exact consumption.** Trailing bytes, truncation, a missing `shared` id byte,
  and a count of 2^32-1 are all rejected.
- **The `id` byte.** It is opaque and accepted with any value. That is harmless,
  because it only selects Jupiter's shared-authority PDA, and the simulation and
  balance checks still apply.
- **Index games.** Every step must go 0 to 1, so multi-hop (0 to 2, 2 to 1) and
  reverse legs are rejected.
- **Percent games.** Each step must be 1..100 and they must sum to exactly 100;
  0+100 and 101 are rejected. Splits of up to 8 steps are accepted, and their
  amounts are still bounded by the simulation deltas.
- **Field values.** A bool/side value other than 0/1 is rejected, which matches
  Borsh's own bool/enum rules. Unpinned tags such as 47 (WhirlpoolSwapV2) are
  rejected.
- **Differential.** 200,000 random mutations of honest encodings gave **0
  disagreements** and **0 crashes** between the two implementations. 30,139
  mutations decoded, and both implementations decoded them identically.

**Wrong-size pinned tag (the "a wrong-size decode still consumes all bytes" attack).**
With a correct table, a Borsh parse is unique, so our reading equals the
program's. Suppose instead the pinned table were wrong for a tag:
- **The real variant has more bytes than pinned.** The program runs out of data,
  the instruction fails, and the simulation fails.
- **The real variant has fewer bytes than pinned.** This can only be one of the
  three 1-field pins (Whirlpool, Phoenix, OpenBookV2) actually being a unit
  variant. The program would then read our `percent` (1..100) as its
  `input_index`, and its arguments shifted by one byte:
  - `in_amount` and `quoted` would come out about 256 times larger;
  - `slippage` would be about `our_slippage * 256`, which is above 10000 for any
    allowed mandate value.
  - The way out would need `input_index` ∈ {0, 1}, which means percents of 0/1
    summing to 100, which needs more than 8 steps.

  I could not construct a byte string that is valid under both readings and gives
  the program a lower floor. Divergence therefore fails closed in practice, not
  only for honest inputs.

**What remains unconfirmed** (from memory, also in my own recollection): the
discriminator names, the argument order, the eight tag numbers and their field
sizes. My own recollection of the IDL agrees with all eight pins:
- 7 Raydium
- 17 Whirlpool{a_to_b}
- 25 LifinityV2
- 26 RaydiumClmm
- 28 Phoenix{side}
- 38 MeteoraDlmm
- 39 OpenBookV2{side}
- 46 RaydiumCP

An error in any of these makes honest orders fail; per the analysis above it does
not open a path. A real transaction that decodes with exact consumption in DRY_RUN
confirms the layout **for the tags it uses**.

## New / remaining findings

### L1 [LOW] Pins never seen in DRY_RUN stay unconfirmed; expect fail-closed rejections
Locations: `config.py:121-138`, `jupiter_ix.py:48-57`, `verify.py:41`

Expected false rejections:
- Token-2022 is not in `INNER_ALLOWED`. Raydium CLMM/CPMM pass the Token-2022
  and Memo programs as accounts, so those routes will be rejected as
  "executable account not on the allowlist".
- The Meteora pools vault program is not listed.
- If Jupiter's split `percent` is relative to the remaining amount rather than to
  the total, honest split routes will fail "sum to 100".

Also unconfirmed: the floor semantics in `check_swap`, i.e. the rounding and
whether `platform_fee_bps` is taken before the floor is compared.

None of these opens a path to loss (see the analysis above).

Recommendation:
- Record in DRY_RUN which tags, programs and splits were seen.
- When the allowlist is widened, treat it as a reviewed change; the hash gate now
  enforces that.
- Optionally narrow `SWAP_VARIANTS` to the tags actually observed in DRY_RUN.

### L2 [LOW] `mandate_valid`, which can never be overridden, now depends on reading the journal
`gates.py:265-278, 283-285`

`evaluate()` reads the journal for the N6 price on every call, including the
`_still_live` checks before signing and before sending. Two consequences:
- If the journal is missing, locked, or has no `binance_spot_klines` bar, the
  mandate becomes invalid and the mode turns DISARMED. In the middle of a cycle
  that safely gives FAILED (before signing) or UNKNOWN, not sent (after signing).
- The price used is the latest bar with no age limit. `decide()` re-checks at the
  fresh snapshot price, so no unsafe order can come from this.

This fails safe, but it is a liveness coupling. While the collector is down,
nothing can be signed, including FLAT exits, though staleness in `build_snapshot`
already blocks those. Document it in the operator notes.

### L3 [LOW] Residual trust carried over from DESIGN §10 (unchanged, for the record)
These are structural, not defects:
- The one RPC is trusted for ALT contents, the token-account list, the
  simulation, inner instructions and balances.
- Jupiter's upgradeable program and the allowlisted DEX programs are trusted.
- The hot key is readable by Anton's user.
- The signer caps, binding file, arm file and gate inputs can be edited by that
  same user.

## Conditions before arming (my notes; the owner decides)

1. Run at least 3 DRY_RUNs against real `/order` transactions. Each must decode
   with exact consumption (`jupiter_instruction` recorded). For each, check:
   - decoded `in_amount == amount`;
   - `quoted_out_amount` ≈ `outAmount`;
   - `slippage_bps` equals the mandate;
   - `min_out >= otherAmountThreshold`;
   - `inner_programs` are all expected.

   If anything is rejected (U3, Token-2022, an unpinned tag), any widening is a
   code change: new hash, new review.
2. Have Anton accept the hand-rolled decoder instead of the official SDK (F16),
   and the DESIGN §10 residual risks.
3. Fund the wallet only with max_position plus a small SOL reserve.

## Summary

No BLOCKER or HIGH remains.
- **F3 / N1 (on-chain floor):** fixed with an exact-consumption, front-to-back
  decode. The signer's independent copy agrees under differential fuzzing.
  Adversarial routes are rejected end-to-end.
- **F1 (signer caps):** fixed, since the caps now come from that same decode.
- **N2, N3, N4, N6 and the TLS part of F16:** fixed.
- **Remaining:** low-severity, fail-closed liveness notes and the documented
  residual trust. They are covered by the pre-arm DRY_RUN conditions above.

Verdict: APPROVED_WITH_NOTES
