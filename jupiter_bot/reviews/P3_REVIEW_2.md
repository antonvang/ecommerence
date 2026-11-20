# P3 execution review, round 2 (independent, adversarial)

Commit: 5a65ceb
Execution-SHA256: d5221631ed1a77316e52c69e9a537e306faa15d7679c19309a693963acbb370c

- I recomputed the hash with `python3 -m jupiter_bot.execution code-hash` at
  `5a65ceb`. It matches the value above.
- Scope: the full diff `7c23339..5a65ceb` (execution/*, tests/execution_*,
  research/lock.py). Same rules as round 1: read-only, no keys, no network, nothing
  under `~/.config`, nothing in `~/jupiter-collector`.
- Tests:
  - `python3 -m unittest discover -s jupiter_bot/tests`: 323 tests, OK.
  - The execution test modules with a stub `nacl` on `PYTHONPATH`: 136 tests, OK
    (1 skipped). The round-1 PyNaCl breakage is gone.
- Probes: `/tmp/claude-1000/-home-anton/64e74dba-157d-44f7-b4ce-5ec1e73fba4d/scratchpad/review/probe_r2.py`.
  It re-runs every round-1 probe and adds the new attacks.

## Status of round-1 findings

| # | Round-1 severity | Status | Evidence |
|---|---|---|---|
| F1 signer does not bound SOL outflow | HIGH | **Fixed** for top-level transfers. **Not fixed** for the swap amount (see N1). | S1 (transfer to attacker): refused "destination is not the wallet's own wSOL account". S3 (SELL 50 SOL): refused "SELL input above max_trade_sol". The signer's caps now come from the decoded Jupiter instruction, so N1 bypasses them too. |
| F2 wallet owner/data unchecked | HIGH | **Fixed** | P1: rejected "wallet account is not a plain System account". Checked pre and post (`verify.py:194-207`). |
| F3 on-chain floor not verified | HIGH | **Not fixed.** It now holds against honest layout mistakes but not against the adversary F3 is about. See N1. | N1 |
| F4 CPI targets unconstrained | MEDIUM | **Fixed, with notes.** Executable-account check plus `innerInstructions` allowlist, fail closed when inner instructions are missing (`verify.py:176-191, 246-252`). | P7: inner call to EVIL rejected. P7b: an empty `innerInstructions: []` is accepted (N4). |
| F5 EXPIRED on a false null status | HIGH | **Fixed.** Status context slot ≥ finalized slot, `getTransaction` null, and the wallet balances equal the VERIFIED snapshot (`engine.py:225-264`). | E1 (history-less RPC after landing): stays UNKNOWN "wallet balances changed", no second order. Residual: N3. |
| F6 absolute fee tolerance | MEDIUM | **Fixed.** Tolerance = 5,000 × signatures + this tx's priority + rent of ATAs that persist. The same figure is used after the fill. | P2 and P3 now rejected with "exact fee 5300". |
| F7 per-data-dir invariants | MEDIUM | **Fixed.** Per-wallet lock, a binding of wallet to ledger checked in `evaluate`, and signer state per wallet in the registry. | E2: the second data dir is DISARMED "wallet not bound to this ledger". |
| F8 review gate not bound to code | MEDIUM | **Partly fixed.** It now needs `Commit:` and `Execution-SHA256:` lines, and the hash is compared. The hash covers only `execution/*.py` (N2). | `gates.py:85-115` |
| F9 tests prove little | MEDIUM | **Improved.** The fake simulation and landing now read the transaction (`tx_effect`). A signature verifier can be injected. Solana SDK PDA vectors and RFC 8032 curve vectors were added. **Residual:** the fake chain reads the route arguments from the last 19 bytes, the same assumption as the code, so N1 cannot fail in the tests. There is still no recorded real `/order` transaction. | `execution_fakes.py:66-68, 168-190` |
| F10 position by wall clock | LOW | **Fixed** (`ORDER BY rowid`). | E3 gives (200000000, 40000000). |
| F11 two reads of the mandate | LOW | **Fixed** (`load_once`). | |
| F12 duplicates and PDA not checked locally | LOW | **Fixed** | P5: rejected "loaded twice". P6: rejected "not the wallet's derived ATA". `is_on_curve` matches dalek `decompress` semantics (non-canonical y reduced, x=0 accepted). Vectors from solana-program `pubkey.rs` pass. |
| F13 Rejected escapes /execute | LOW | **Fixed.** Any exception after the POST gives UNKNOWN. "Disarmed after signing" now gives UNKNOWN instead of FAILED, so no new order until it has provably expired. | |
| F14 fee dropped on a full SELL | LOW | **Fixed** (the excess is valued at the decision price, rounded against us). | |
| F15 keypair hygiene | LOW | **Fixed.** `fstat` identity check after open, parent directory checked, `/usr/bin/python3`. The immutable seed copy is documented as residual. | |
| F16 SDK / host / proxy | LOW | **Partly fixed.** `ProxyHandler({})` added. `SSL_CERT_FILE`/`SSL_CERT_DIR` still change TLS trust through the default context. The hand-rolled decoder still deviates from the handoff's "official SDK", which Anton must accept explicitly. | |
| F17 forgeable / lenient gate inputs | LOW | **Fixed** as far as possible: a malformed lock or verdict no longer crashes status, and the lock must cover all code files. Same-user forgery remains inherent. | |

## New findings

### N1 [HIGH] Jupiter arguments are read from the end of the instruction data, but the program reads them from the front
Locations:
- `execution/jupiter_ix.py:69-81` (`TRAILER.unpack(data[-19:])`)
- `execution/signer.py:305-313` (`data[-19:]`)
- the fake shares the assumption at `tests/execution_fakes.py:66-68`

`route` / `shared_accounts_route` are Anchor instructions. Borsh deserialises
`route_plan` first, then `in_amount, quoted_out_amount, slippage_bps,
platform_fee_bps`, from the front of the data. As far as I know, Anchor's
generated dispatch (`Route::deserialize(&mut &data[..])`) does not reject
unconsumed trailing bytes. This must be confirmed against the program, but the
verifier must not depend on it either way.

Scenario: a buggy or compromised `/order` response builds a valid route whose
real arguments are `quoted_out_amount = 1, slippage_bps = 10000`, then appends
19 bytes holding the "right" values.
- The verifier and the signer both read the appended bytes.
- An honest RPC simulation still shows a good fill at the simulated slot.
- On chain the floor is about 0, and Jupiter, which lands the transaction via
  `/execute`, can sandwich it.

The signer's new caps (BUY `in_amount ≤ max_trade_usdc`, SELL
`in_amount ≤ max_trade_sol`, floor ≥ bundle `min_out`) are all taken from the
same trailer, so they fall to the same trick. On the amount side, the
verifier's simulation delta check still catches an oversized real `in_amount`;
the signer has no such backstop.

Evidence (`probe_r2.py` N1):
- `data = route_prefix(in=25 USDC, quoted=1, slippage=10000) + pack(in=25 USDC, quoted=125000000, slippage=50)`.
- `jupiter_ix.decode` gives `{quoted_out_amount: 125000000, slippage_bps: 50, min_out: 124375000}`.
- `verify()`: **ACCEPTED**.
- `signer.handle` with the same message: **signed**.

Fix:
- Decode the instruction from the front and require exact consumption
  (`offset == len(data)`).
- To do that, decode `Vec<RoutePlanStep>` (`Swap` enum + `percent u8` +
  `input_index u8` + `output_index u8`) with a pinned table of the few `Swap`
  variants allowed, matched to `DEX_PROGRAMS`, each with its exact payload size.
  Reject any other variant.
- Do the same in the signer.
- Make the fake chain decode from the front, so a trailer-only decoder fails the
  tests.

Until then, F3 stays open. Fail-closed behaviour on an honest Jupiter does not
help here, because this is an adversarial input.

### N2 [MEDIUM] The review hash does not cover the code the execution path imports
`execution/gates.py:85-90`

`execution_code_sha256` hashes only `jupiter_bot/execution/*.py`. Behaviour the
verifier and engine depend on lives elsewhere and can change without
invalidating the review:
- `core.py`: the `SOL`/`USDC` mint constants that `verify.py` uses, plus
  `strict_json`, `positive_integer`, `atoms`, `timestamp`;
- `storage.py`;
- `jupiter.py` (`NoRedirect`);
- `research/strategies.py` (targets, grid);
- `marketdata/snapshot.py` and `journal.py` (staleness, price).

The signer keeps its own constants, which limits the damage, but the
verifier's mint checks and the mandate atom conversion are outside the hash.

Fix: hash `execution/*.py` plus every `jupiter_bot` module it imports
transitively (or simply all `jupiter_bot/**/*.py` except `tests/` and
`reviews/`). Optionally check that the `Commit:` value is an ancestor of HEAD.

### N3 [LOW] The balance proof used for EXPIRED ignores the read's context slot
`execution/engine.py:247-249`

`rpc.multiple_accounts(pre["addresses"])` reads at `confirmed` and discards
`context.slot`. On a load-balanced provider, a node lagging behind the landing
slot (which is more than 150 blocks before `fin_height`) would return the old
balances. Together with a history-less status node, that gives a false
"unchanged" and EXPIRED. This needs two independent faults, so the severity is
low.

Fix: pass `minContextSlot: fin_slot` (or check that `context.slot ≥ fin_slot`)
on that read, as is already done for the status query.

### N4 [LOW] An empty `innerInstructions` list passes the CPI check
`execution/verify.py:180-191`, `rpc.py:125-139`

`[]` is treated as "nothing was invoked" (P7b ACCEPTED). A real Jupiter swap
always performs CPIs (at least Token transfers), so an empty list means the RPC
is not reporting them.

Fix: require at least one inner instruction under the Jupiter instruction's
index, including a Token-program transfer.

### N5 [LOW] The allowlist and Jupiter layout are from memory and still fail closed: acceptable, but expect rejections
Locations: `config.py:121-138`, `jupiter_ix.py`

The DEX program ids I can check from my own knowledge (Whirlpool, Raydium
v4/CLMM/CPMM, Meteora DLMM/pools, Phoenix, OpenBook v2, Lifinity v2) match. A
wrong id can only cause rejection, never acceptance, because an id typed from
memory is very unlikely to be a real, different program. Nested CPIs are still
covered by the executable-account check.

Expected false rejections:
- Token-2022 is not in `INNER_ALLOWED`. Raydium CLMM/CPMM pass the Token-2022
  program and the Memo program as accounts even for classic tokens, so their
  routes will be rejected.
- Meteora pools use a vault program that is not listed.
- The rounding of the program's floor against `otherAmountThreshold`
  (`check_swap`), and whether the floor applies before or after the platform
  fee, are UNCONFIRMED.

I judge this acceptable **only** together with N1's exact-consumption decode,
and with these conditions:
- Any widening of the allowlist after DRY_RUN is a reviewed code change. N2
  makes the gate enforce that.
- DRY_RUN results must record the decoded arguments of real transactions, and
  Anton should compare them against `outAmount`/`otherAmountThreshold` before
  arming.

### N6 [LOW] `max_trade_sol` is not cross-checked against `max_trade_usdc`
`execution/mandate.py:115-118`

The signer's SELL cap is only as good as Anton's value. `"max_trade_sol": "1000"`
is accepted silently.

Fix: `check-mandate` should warn when `max_trade_sol × journal price` exceeds
`max_trade_usdc` by more than, say, 1.5×.

## Summary

Most round-1 findings are closed, and I checked each closure with the round-1
probes: F2, F5, F6, F7, F10 to F15, and F17, plus F1 for top-level transfers.
F4 is fixed with notes, F8, F9 and F16 are partly fixed, and F3 is not fixed.

Arming is blocked by one new problem in the new mechanism: N1. The Jupiter
arguments are read from the tail of the data, so an appended fake trailer
defeats both the verifier's on-chain floor check (F3) and the signer's new
amount caps (F1). Fix N1 with a front-to-back decode that requires exact
consumption, fix the fake to match, then re-review. N2 should be fixed in the
same round so the gate covers the imported modules.

Verdict: CHANGES_REQUIRED
