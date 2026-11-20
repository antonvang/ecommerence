# P3 execution review (DRAFT, independent, adversarial)

- Reviewed commit: `7c23339` (branch `claude/stoic-clarke-o5weig`), working tree clean.
- Reviewer: independent Claude agent. It did not write this code. Read-only review:
  no keys, no wallet, no network calls to Jupiter or Solana.
- Scope: `jupiter_bot/execution/*` (all modules, DESIGN.md, README.md),
  `tests/execution_fakes.py`, `tests/test_execution_*.py`, `research/lock.py`,
  `research/verdict.py`, `INTERFACES.md`, `CLAUDE_HANDOFF.md` P3, `research/JUPITER_API_FACTS.md`.
- Test run: `python3 -m unittest discover -s jupiter_bot/tests` gives 282 tests, OK
  (PyNaCl not installed on this machine).
- Probes: throwaway scripts outside the repo
  (`/tmp/claude-1000/-home-anton/64e74dba-157d-44f7-b4ce-5ec1e73fba4d/scratchpad/review/probe_verify.py`,
  `probe_engine.py`, `fakenacl/`). They use the repo's own test encoder and fakes, and
  sockets are patched out.

## What holds up (checked, no finding)

- compact-u16 decoding (3-byte limit, overflow, non-canonical), v0 header math,
  signer/writable derivation, ALT order (static, then all writable, then all
  read-only), index bounds, trailing bytes and signature-count/header agreement
  in `solana_tx.py` are correct.
- Verify, sign and send act on the same bytes. The signer gets `verified.message_bytes`,
  checks their sha256 against the bundle, and the engine re-parses the signed tx
  and compares the message bytes. I found no TOCTOU between verify, signer and
  send. The ALT indexes used at verify time cannot change later, because ALTs
  are append-only.
- The EXPIRED height math holds against an understated `lastValidBlockHeight`,
  given the verify-time check `confirmed_height + 30 < lvbh`. The real expiry is
  at most the verify height + 150, and EXPIRED needs finalized height > lvbh + 150.
  F5 is about the status side of the rule, not the height side.
- Durable-nonce transactions are rejected: only System `Transfer` is allowed, so
  `AdvanceNonceAccount` is refused by both verifier and signer.
- `mandate_valid` and `private_rpc` cannot be overridden, either via `arm` or
  via a hand-edited arm file (`read_arm` rejects them).
- The RPC URL is not printed in status, dashboard, ledger or HTTP errors (host only).

## Findings

### F1 [HIGH] Signer's "independent re-check" does not bound SOL leaving the wallet
`execution/signer.py:268-274`, `signer.py:296-313`

The signer accepts a System `Transfer` from the wallet to **any** destination.
It checks each instruction against `bundle.in_amount` on its own, with no total
across instructions. For SELL it never caps `in_amount` (lamports), and its
notional is the engine-supplied `min_out`. The design (§8.4, §9 "Bug in the engine
signs something bad") relies on this layer, but in practice it gives no protection
for SOL.

Scenario: an engine or verifier bug (or a bypass of `verify`) hands the signer a
SELL message with plain top-level transfers to an attacker. The signer signs it.

Evidence (`probe_verify.py`, real `signer.handle`, fake ed25519):
- S1: 1 transfer wallet -> ATTACKER, SELL bundle: **signed**
- S2: 8 transfers x 0.125 SOL -> ATTACKER (1 SOL total): **signed**
- S3: SELL bundle `in_amount` = 50 SOL, `min_out` = 1 atom (notional 1): **signed**

Fix:
- Mirror the verifier's rules. The transfer destination must be the wallet's wSOL
  ATA. Derive the PDA in the signer; PyNaCl has
  `nacl.bindings.crypto_core_ed25519_is_valid_point` for the off-curve check.
  Alternatively, require the destination to be the account of an ATA-create
  instruction for the SOL mint in the same message.
- The sum of all transfers must be ≤ `in_amount`.
- Cap SELL `in_amount` independently, e.g. with a mandate field `max_trade_sol`
  or a floor price in the mandate.
- Add tests S1-S3.

### F2 [HIGH] The simulation check ignores the wallet account's owner, data and executable flag
`execution/verify.py:149-170` (`_view`)

For the wallet, only `lamports` is read from pre- and post-state. A route that
CPIs `System::Assign` (the wallet is a signer, and that privilege carries into
CPI) or `Allocate` on the wallet passes verification if lamports look right.
After `Assign`, the new owner program can debit all SOL at any time, and the
wallet can no longer pay fees. Neither the static rules nor the signer can see
this.

Evidence (`probe_verify.py` P1): the sim post-state has wallet owner set to
`EVIL_PROGRAM` and 64 bytes of data. `verify` **ACCEPTED** with normal deltas.

Fix: require the wallet to be System-owned with empty data and not executable,
in both pre- and post-state. For token accounts, also require the post-state
owner to be the Token program and the state to be initialised and not frozen.
Add a test.

### F3 [HIGH] The on-chain price floor is assumed, not verified (Jupiter v6 data is never decoded)
`execution/verify.py:124-125`, `DESIGN.md` §8.3 item 4 and §10.3 (lines 286, 396-398),
`JUPITER_API_FACTS.md:95-96` (marked **INFERRED**)

The design says `otherAmountThreshold` is "enforced on-chain". The verifier never
checks what the Jupiter instruction actually encodes: `in_amount`,
`quoted_out_amount`, `slippage_bps`, `platform_fee_bps` (the trailing args of
`route`/`shared_accounts_route`). Simulation shows only the outcome at the
simulated slot. Jupiter also **lands** the transaction itself via `/execute`.
A buggy or compromised API response can therefore encode a loose floor (e.g.
10,000 bps) that passes simulation and is then sandwiched. The loss per trade
can approach the whole trade amount, up to the signer's daily notional cap
(8 x max_position). Any number of Jupiter instructions is accepted (`jupiter >= 1`).
CLAUDE_HANDOFF P3 requires the price limit ("prisgrænse") to be verified
**before signing**.

Fix:
- Decode the published Jupiter v6 Anchor IDL (on-chain IDL account /
  jupiter-cpi). Accept only known route discriminators and exactly one route
  instruction.
- Require `in_amount == request.amount`, `quoted_out_amount == outAmount`,
  `slippage_bps == mandate.max_slippage_bps`, and `platform_fee_bps <= MAX_FEE_BPS`.
  Reject everything else.
- Do the same check in the signer, which can do it statically.

### F4 [MEDIUM] The program allowlist covers top-level programs only; CPI targets are unconstrained and the simulation can be evaded
`execution/verify.py:97-102`

Jupiter v6 can invoke any program passed in its account list, including
programs loaded from ALTs. The verifier never checks which executable accounts
are present, and it does not request `innerInstructions` from `simulateTransaction`.
A malicious program on the CPI path can act differently in simulation and on
chain (e.g. branch on slot or Clock), so the balance-delta check gives no
guarantee against it. Whether Jupiter v6 itself hard-codes DEX program ids per
swap variant is not in the facts file (UNCONFIRMED). If it does not, raise this
to HIGH.

Fix: fetch every resolved account and require each `executable` account to be
in a pinned, reviewed allowlist (from `/program-id-to-label`). Request
`innerInstructions: true` and check every invoked program id against the same
list. Document what remains trusted (Jupiter's upgradeable program).

### F5 [HIGH] EXPIRED trusts a null status from a possibly lagging or history-less RPC, which leads to a second order while the first has landed
`execution/engine.py:211-229`, `execution/rpc.py:276-288`

EXPIRED needs two null `getSignatureStatuses` results plus a finalized height
above lvbh + 150. The response's `context.slot` is discarded. Two causes give a
false null for a landed transaction:
- a load-balanced provider, where `getBlockHeight` hits a fresh node and the
  status query hits a lagging one;
- a provider that serves no history beyond the status cache (e.g. after the PC
  slept for hours).

The order is then EXPIRED, the fill is never booked, and the bot places a new
order. This breaks the core P3 rule: no new order while the old one can land or
has landed. The ledger position no longer matches the wallet.

Evidence (`probe_engine.py` E1): `/execute` times out but the tx landed, and the
RPC later cannot see the signature. The resolver gives `EXPIRED`, then a new
BUY is CONFIRMED. The wallet holds two BUYs, the ledger books one, and Jupiter
received 2 orders and 2 executes.

Fix:
- Use `minContextSlot` / check `context.slot` of the status response ≥ the slot
  at which finalized height passed lvbh + margin.
- Also require `getTransaction` to return null.
- Compare the wallet's lamports and USDC against a pre-order snapshot stored at
  VERIFIED. Any unexplained change means "do not expire; manual resolve".
- At `check-mandate` / DRY_RUN, prove the provider serves history (look up an
  old wallet signature).

### F6 [MEDIUM] The absolute fee tolerance makes the min-out check meaningless for small trades and allows leakage on every SELL
`execution/verify.py:178-181`, `config.py:21`. The same tolerance is used in the
post-fill anomaly check (`engine.py:271`).

`FEE_CAP_LAMPORTS` is about 4.58M lamports (base + 500k priority + 2 ATA rents)
and is subtracted whatever the transaction actually does.

Evidence (`probe_verify.py`):
- P2: a 1-USDC BUY (min_out 4,975,001 lamports) whose simulation receives only
  **400,000** lamports (8% of the quote) is ACCEPTED.
- P3: a SELL whose simulation shows 4.5M lamports extra outflow is ACCEPTED.

Because the anomaly check uses the same tolerance, such fills do not auto-disarm.

Fix: tolerance = 5,000 + the priority computed from this transaction +
ATA_RENT × (ATAs created by this transaction that still exist in the
post-state). Book an anomaly against the same exact figure.

### F7 [MEDIUM] The one-engine / one-open-order invariant and the signer caps are per `--data-dir`, but the arm file is shared
`execution/config.py:58-68`, `engine.py:313-325`, `signer_client.py:444-445`

The lock, ledger, `dry_run_ok` count and `signer-state.json` all follow
`--data-dir`. The arm file follows the mandate directory. Two invocations with
different data dirs, for example a future systemd timer and a manual run, both
run LIVE on one wallet. Each has its own open-order rule and its own daily caps.

Evidence (`probe_engine.py` E2): engine A has an UNKNOWN order open. Engine B
(same mandate and arm file, other data dir, 3 unarmed `dry-run-once`) goes LIVE
and CONFIRMS a new BUY.

Fix: derive the lock, ledger and signer state from the mandate/arm directory,
or record them in the arm file and refuse on mismatch. The signer state path
should not be caller-controlled.

### F8 [MEDIUM] The review gate is not bound to the code
`execution/gates.py:74-83`, `DESIGN.md` §10.9

Any `Verdict: APPROVED` line in `P3_REVIEW.md` satisfies the gate forever. The
design itself expects the allowlist to be widened after DRY_RUN (U3, §10.7), and
the gate would stay green after that change.

Fix: require a line `Reviewed-tree: <sha256 over jupiter_bot/execution/*.py>`
(or the git tree id) and compare it in `evaluate`. Optionally have the signer
check its own file hash.

### F9 [MEDIUM] Tests do not prove the safety claims and break in the production configuration
`tests/execution_fakes.py:192-200, 215-243, 340-352`

- The fake `simulateTransaction` and `land` ignore the transaction content.
  Every "simulation catches X" test sets `sim_effect` by hand, so these tests
  only exercise `check_deltas` arithmetic.
- `FakeSigner` returns `sha512(message)`. With PyNaCl importable, which the
  README requires for LIVE (`apt install python3-nacl`), `_verify_signature`
  rejects that value. **11 failures and 2 errors** in `test_execution_engine`
  (run with a stub `nacl` on `PYTHONPATH`, `fakenacl/`).
- Real ed25519 signing is never exercised.
- There is no test for: a static non-allowlisted program, Token-2022 accounts
  present, wallet owner change (F2), multiple Jupiter instructions, duplicate
  accounts, or signer transfer destination/total (F1).
- No test decodes a real `/order` transaction (U3).

Fix:
- Make the fake signer produce verifiable signatures, or inject the verifier.
- Add the missing negative tests.
- Add a golden-file test from a recorded DRY_RUN transaction before arming.

### F10 [LOW] `Ledger.position()` uses the wall clock, not insertion order
`execution/ledger.py:189-192`

`ORDER BY at DESC` uses the booking time. A backward clock step makes
`position()` return an older fill.

Evidence (E3): two BUYs booked with `at` 2000 then 1000 give
`position() = (100000000, 20000000)` instead of `(200000000, 40000000)`. Every
later fill builds on the wrong base.

Fix: `ORDER BY rowid DESC`.

### F11 [LOW] Mandate parsed and hashed from two separate reads
`execution/gates.py:155-156`

`load()` then `read()` can see different bytes if the file is edited mid-call.
The mode can then be LIVE (arm matches the new sha) while the engine uses the
old mandate's limits. The signer's own read of max_trade bounds the damage.

Fix: use `mandate.sha256`, or read once.

### F12 [LOW] The verifier relies on the runtime and simulation for structural rules it could check itself
`execution/solana_tx.py:195, 292-311`, `verify.py:103-114`

Duplicates between static and ALT keys are not rejected. Probe P5: the wallet
loaded again via the ALT is ACCEPTED, where the chain would answer
`AccountLoadedTwice`. ATA-create addresses are not checked to be the derived
PDA, and a SOL wrap to such an address is accepted statically (P6). Both fail
on chain today, but only because the RPC simulation says so.

Fix: reject duplicate resolved keys, and derive and compare ATA PDAs locally.

### F13 [LOW] `/execute` raising `Rejected` (e.g. a redirect) escapes `execute()`
`execution/jupiter_exec.py:189-194`

The order is left in SIGNED and the run aborts (E4). This is safe, because the
next run turns SIGNED into UNKNOWN, but it is not the documented path.

Fix: map any exception after the POST started to UNKNOWN.

Related: after "disarmed after signing" the order goes to terminal FAILED while
the signed bytes are stored in the ledger. A new order is then allowed
immediately. Consider keeping the order non-terminal until lvbh + margin.

### F14 [LOW] A full SELL drops the network fee from realised P&L
`execution/ledger.py:214-218`

`sold = min(-sol_delta, position)` caps the fee away when the whole position is
sold. This contradicts DESIGN §6 ("fees always reduce P&L"), which the daily
loss limit relies on.

Fix: book the excess as a cost valued at the fill price.

### F15 [LOW] Keypair and signer-process hygiene
`execution/signer.py:204-238`, `signer_client.py:440`

- `lstat` then `open(O_NOFOLLOW)` with no `fstat` re-check of type, owner and mode.
- The parent directory's permissions and symlinks are not checked.
- The signer runs `sys.executable`, which may be a venv, not the system python
  the README describes.
- The seed is copied into immutable `bytes` (cannot be zeroed).

Fix: `fstat` the opened fd, check the parent directory (owner and no group/other
write), and pin `/usr/bin/python3`.

### F16 [LOW] Requirement and secret-hygiene notes
- CLAUDE_HANDOFF P3 asks for Solana's official SDK. The wire format is hand-rolled
  (correct as far as I checked, but a deviation that needs Anton's explicit acceptance).
- `rpc host` is printed in status, dashboard and gate details (`gates.py:172`,
  `mandate.py:264`). Some providers use account-specific hostnames. Consider
  showing only the registrable domain.
- `urllib` honours `HTTPS_PROXY` / `SSL_CERT_FILE` from the user's environment.
  Consider an explicit SSL context and `ProxyHandler({})`.

### F17 [LOW] Gate inputs are trivially forgeable by the same user, and the lock check is lenient
`execution/gates.py:47-71`, `research/lock.py:86-100`

- Verdict files, the plan lock and the arm file are unauthenticated JSON.
  `lock.verify` passes with an empty `code_sha256`, and `load` uses non-strict JSON.
- A non-dict lock raises a `TypeError`, which `gate_p2` does not catch, so
  `status` crashes.

These gates are safeguards against mistakes, not against an attacker, and should
be described that way. Also note: the P2 holdout ends 2027-01-02, so LIVE before
then is only possible with `--override p2_holdout_pass`.

## Summary

There is no direct exploit against an honest Jupiter + honest RPC in normal
operation. But four of the stated defences do not hold:
- the signer's independent check (F1);
- the simulation's coverage of the wallet account (F2);
- the on-chain price floor (F3, with F4 behind it);
- the "never a second order while the first can land" rule under a lagging or
  history-less RPC (F5).

The tests run against fakes that share the code's assumptions, and they fail
once PyNaCl is installed (F9). Fix F1, F2, F3 and F5, add the tests from F9, and
re-review before arming.

Verdict: CHANGES_REQUIRED
