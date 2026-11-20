# P3 execution adapter: design

## Kort dansk resumé (til Anton)

- Alt er bygget og testet mod falske Jupiter-, RPC- og signer-udgaver. Der er
  ingen nøgler, ingen wallet og ingen rigtige transaktioner. Standardtilstanden
  er **DISARMED**.
- Du bestemmer selv, hvornår der handles med rigtige penge. LIVE kræver fem
  ting: et gyldigt mandat, som du skriver selv, en privat RPC, en arm-fil, som
  `arm` opretter efter en indtastet sætning, mindst 3 vellykkede DRY_RUN-kørsler
  med netop dette mandat, og at alle porte er OK. En fejlende port kan du kun
  tilsidesætte med `--override` plus en ekstra indtastet sætning, og det bliver
  logget. Mandat og privat RPC kan aldrig tilsidesættes.
- Hver ordre verificeres før signering: der må kun være én signer (din wallet),
  kun kendte programmer må kaldes, og en simulering skal vise, at du højst
  bruger det beløb, du bad om, og mindst modtager minimumsbeløbet. Signeringen
  sker i en separat proces, som selv tjekker det hele igen og har sine egne
  dagsgrænser.
- Ordren skrives i ledgeren, før noget sendes. Ved timeout bliver ordren aldrig
  sendt igen og aldrig erstattet af en ny. Botten venter på, at kæden viser
  udfaldet. En handel bogføres først, når den er finalized on-chain.
- Nødstop: `python3 -m jupiter_bot.execution disarm` eller slet
  `~/.config/jupiter-bot/armed.json`. Enhver ændring i `mandate.json` slår også
  LIVE fra.
- Restrisici, du skal kende, står i afsnit 10. Den vigtigste: nøglen er en
  "hot key" i en fil på din pc. Sæt kun et beløb ind, du kan tåle at miste.

---

## 1. Scope and non-goals

In scope: SOL/USDC spot swaps through Jupiter `GET /swap/v2/order` (with
`taker`) and `POST /swap/v2/execute`. There is one wallet, one order at a time,
and one order per cycle at most. Sizing comes from the P2 strategy named in the
mandate.

Out of scope: other tokens, leverage, Token-2022, RFQ/JupiterZ, gasless,
integrator `payer`/`receiver`, `/build`, v1 transactions, and running
unattended. No timer is installed; `run-once` is written for a future systemd
timer that Anton installs himself.

Source of facts: `research/JUPITER_API_FACTS.md` (read 2026-11-20). Section
numbers below refer to it as "facts §n".

## 2. Components

| Module | Role |
|---|---|
| `config.py` | Paths and fixed hard limits. The mandate can only be stricter, never looser. |
| `mandate.py` | Strict parse of `~/.config/jupiter-bot/mandate.json`. The keypair file is only `lstat`ed here. |
| `gates.py` | The five gates, the arm file and the effective mode. All three are recomputed from files on every check. |
| `http.py` | Allowlisted HTTPS (api.jup.ag and the mandate's RPC host only). No redirects, timeouts, 4 MB cap, strict JSON. Error text names the host only. |
| `rpc.py` | JSON-RPC: getBlockHeight, getAccountInfo, getMultipleAccounts, getTokenAccountsByOwner, simulateTransaction, getSignatureStatuses, getTransaction. |
| `jupiter_exec.py` | Builds `/order` requests and checks responses strictly. Calls `/execute` and never trusts its answer for the outcome. |
| `solana_tx.py` | base58, compact-u16, legacy/v0 message decode, ALT parsing, account resolution, SPL token account layout. |
| `verify.py` | Pre-sign verification of the real transaction, including the simulation and balance-delta check. |
| `signer.py` | **Standalone** signer process (no `jupiter_bot` imports). It runs its own re-checks, has its own daily caps, and uses PyNaCl. |
| `signer_client.py` | Starts the signer as `python3 -I signer.py …` with a minimal environment and `cwd=/`. |
| `ledger.py` | `execution.db`: self-identifying (application_id `JBEX`, user_version 1), append-only (UPDATE/DELETE triggers abort). |
| `engine.py` | The resolver, decision and order life cycle, kill-switch re-checks, `arm` and `disarm`. |
| `__main__.py` | CLI: `status [--json]`, `check-mandate`, `dry-run-once`, `run-once`, `arm`, `disarm`, `resolve`. |

## 3. Modes and gates

Mode is computed fresh from files on every call (`gates.evaluate`):

- **DISARMED** (default). There is no mandate, or it is invalid or expired, or
  there is no arm file, or the arm file's `mandate_sha256` differs from the
  sha256 of the current `mandate.json` bytes. **Any edit to the mandate
  disarms.** A failing private-RPC gate, or a failing non-overridden gate while
  armed LIVE, also gives DISARMED.
- **DRY_RUN**. The arm file has `mode: DRY_RUN` (`arm --dry-run`, which needs a
  typed phrase), the mandate is valid and the RPC is private. `run-once` then
  does a dry-run cycle. `dry-run-once` does one dry-run cycle whenever the
  mandate is valid and the RPC is private, with no arming needed. A dry run
  fetches `/order` with taker = mandate wallet, runs the full verification
  including `simulateTransaction`, and records the result. It never signs and
  never calls `/execute`. If the strategy wants no trade, it probes with a BUY
  of up to max_trade (or a SELL above the reserve), so the whole path is still
  exercised.
- **LIVE**. The arm file has `mode: LIVE` for this exact mandate and wallet,
  and every gate is OK or was overridden at arm time.

Gates, as `status` shows them (`{"name","ok","detail"}`; an override shows up
as `ok: false` with `detail` starting "OVERRIDDEN …"):

| Gate | OK when | Overridable |
|---|---|---|
| `p2_holdout_pass` | `research/plan_lock.json` exists, `research.lock.verify(lock)` finds no problems, and a file in `research/verdicts/*.json` has `label: holdout`, `verdict: PASS`, `plan_sha256` equal to the lock's, and `strategy` + `params` equal to the mandate's. The loader is a seam (`verdict_loader`). | yes |
| `mandate_valid` | Strict parse OK, not expired, both SOL and USDC allowed, keypair file is a regular file (not a symlink) owned by the user, mode has no group/other bits (0600/0400), and it lies outside the repo. | **never** |
| `private_rpc` | The mandate's rpc host is not `solana.com` or `*.solana.com`. | **never** |
| `dry_run_ok` | At least 3 successful DRY_RUN records in the ledger whose `mandate_sha256` equals the current mandate's. | yes |
| `review_done` | `jupiter_bot/reviews/P3_REVIEW.md` contains a line that is exactly `Verdict: APPROVED`. | yes |

`arm` refuses without an interactive terminal (`stdin.isatty()`). It prints
the mandate summary and gates, then requires the phrase `ARM LIVE <first 8
chars of wallet>` (or `ARM DRY_RUN …`). For each failing overridable gate it
requires `--override GATE`, and then a second phrase
`OVERRIDE <gate,gate,…>`. The arm file (0600) stores mode, mandate sha256,
wallet, time and overrides. The ledger records an `arm` event and one
`override` event per gate. `disarm` deletes the arm file and needs no lock or
phrase, so it always works. The engine re-checks the mode right before signing
and right before sending, so a disarm takes effect before the next order is
signed or sent.

## 4. Mandate

JSON object with exactly these keys (anything else is rejected, duplicate keys
too):

```json
{
  "wallet_pubkey": "<base58 32-byte pubkey>",
  "keypair_path": "/home/anton/.config/jupiter-bot/keys/bot.json",
  "rpc_url": "https://<private provider host>/<key>",
  "max_trade_usdc": "25",
  "max_position_usdc": "50",
  "daily_loss_limit_usdc": "10",
  "max_slippage_bps": 50,
  "allowed_mints": ["So11111111111111111111111111111111111111112",
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"],
  "strategy": "tsmom",
  "params": {"lookback_min": 240, "rebalance_min": 240},
  "expires_at": 1800000000
}
```

Money is a **decimal string in whole USDC** (`^(0|[1-9]\d{0,11})(\.\d{1,6})?$`).
JSON numbers for money are rejected. Amounts are converted exactly to integer
atoms. Further rules: max_trade ≥ 1 USDC and ≤ max_position;
`max_slippage_bps` is an integer from 1 to 300 (hard cap). The strategy must be
in `research.strategies.STRATEGIES`, and `params` must equal one of its grid
entries. `expires_at` is Unix seconds. The URL must be HTTPS with no userinfo or
fragment and cannot be api.jup.ag. `status` and the dashboard never show
`rpc_url` (it may hold an API key) or `keypair_path`.

Note on units: INTERFACES.md says amounts are atoms unless suffixed `_usdc_dec`,
but the dashboard renders `max_*_usdc` and `today_realized_pnl_usdc` as whole
USDC numbers. The status JSON therefore reports them as USDC numbers, e.g.
`25.0`. Internally everything is integer atoms.

## 5. Order life cycle (state machine)

```
            /order + verify ok          signer ok               POST /execute
 INTENT ───────────────────▶ VERIFIED ───────────▶ SIGNED ─────────────────▶ SUBMITTED (200 Success, our sig)
   │                            │                    │  └──────────────────▶ UNKNOWN   (timeout, 5xx, 4xx, odd answer)
   │ any rejection              │ disarmed / old /   │ disarmed after signing
   ▼                            ▼ signer refused     ▼ (known not sent)
 FAILED                       FAILED               FAILED
                                                           SUBMITTED / UNKNOWN ──chain──▶ CONFIRMED | FAILED | EXPIRED
```

- **INTENT** is written (order row + event) before the first network request
  for the order. `create_intent` refuses atomically, inside the same SQLite
  write transaction, when any non-terminal order exists. So there is never a
  second order while one is open, even across processes. A file lock
  (`execution.lock`, `flock`) also keeps two engines from running at once.
- **VERIFIED** stores the requestId, wallet, out_amount, `otherAmountThreshold`,
  `lastValidBlockHeight`, the unsigned transaction, the message sha256, the
  simulated deltas and the raw order payload.
- **SIGNED** stores the signature (= transaction id, because the taker is the
  only signer and the fee payer) and the signed bytes, **before** `/execute`.
- After `/execute`: `ACCEPTED` (HTTP 200, `status: Success`, signature equal to
  ours) gives SUBMITTED. Everything else gives UNKNOWN: timeout, connection
  error, any 5xx (a 500 can carry a signature, facts §3), any 4xx, `Failed`, a
  different signature, or non-JSON. Jupiter's answer is recorded but never
  decides the outcome.
- **Resolver** (start of every `run-once`, also `resolve`):
  - INTENT/VERIFIED left by an ended process become FAILED. They were never
    signed, so they cannot land.
  - SIGNED left by an ended process becomes UNKNOWN (it may have been sent).
  - SUBMITTED/UNKNOWN: `getSignatureStatuses([sig], searchTransactionHistory: true)`.
    If the status is `finalized`, the resolver fetches
    `getTransaction(sig, finalized, maxSupportedTransactionVersion 0)` and books
    it (§6). It gives CONFIRMED when `meta.err` is null, otherwise FAILED with a
    fee-only booking. A status of processed/confirmed means wait. If there is no
    status, it reads `getBlockHeight(finalized)`. Only when that height is
    greater than `lastValidBlockHeight + 150` (safety margin, see §9 item U-lvbh)
    **and** a second status query is still null does the order become
    **EXPIRED**. Only then may a new order be created.
  - The resolver never sends anything. The bot never re-posts and never re-orders
    to "retry".
- Restart resumes from the ledger: state is the last `order_events` row, and
  `facts` is the merge of all event data.

## 6. Booking and P&L

A fill is booked only from the finalized `getTransaction`. The full key list
is `accountKeys` + `loadedAddresses.writable` + `.readonly`. Key 0 must be the
wallet, and `signatures[0]` must be our signature. SOL value delta is the
wallet's lamport delta plus the delta of wSOL token balances owned by the
wallet. USDC delta is the change in token balances owned by the wallet with the
USDC mint. `meta.fee` is recorded. The fill and the terminal state are written
in **one** SQLite transaction.

Position and cost basis are the bot's own sub-account, not the wallet balance:
- BUY: position += SOL received (net of fees), cost += USDC spent.
- SELL: sold = min(SOL spent incl. fees, position). The cost removed is the
  average cost of what was sold. realised = USDC received − cost removed.
- FEE_ONLY (landed but failed): realised = −fee valued at the decision price
  (rounded up). The position is unchanged.

Fees and ATA rent therefore always reduce P&L. `today_realized_pnl_usdc` is the
sum over fills booked in the current UTC day. When it is ≤ −daily_loss_limit,
no BUY happens until the next UTC day. A SELL toward flat is still allowed.

After booking, the actual deltas are re-checked against the order (spend ≤
input, plus the fee cap for SOL; receive ≥ threshold, minus the fee cap for
SOL). A violation is booked as it happened, flagged `anomaly`, and the bot
**auto-disarms** (it deletes the arm file and logs an `anomaly_disarmed` event).

## 7. Decision and sizing (one order per cycle)

`run-once` resolves, then stops if anything is still open (`WAIT`). Then:
- **Snapshot:** `Journal(path, readonly=True)` +
  `build_snapshot(journal, now, bars=bars_needed(params))`. `build_snapshot`
  rejects stale data, so there is no trade without fresh data. The target is
  the mandate strategy's LONG/FLAT. The price is the last close.
- **Balances:** wallet lamports and the USDC token amount via RPC.
- **LONG:** BUY min(max_trade, max_position − max(cost basis, market value),
  USDC balance). The amount must be ≥ 1 USDC, the wallet must keep ≥ 0.03 SOL
  as a fee reserve, and the daily-loss stop must not be active.
- **FLAT:** SELL the whole position if its value ≤ max_trade, otherwise a
  max_trade-sized slice. The wallet must keep the reserve. Dust below 1 USDC is
  ignored.

The 0.03 SOL reserve also keeps the wallet above Jupiter's automatic gasless
trigger of < 0.01 SOL (facts §4/open risks).

## 8. What is verified before signing, and how

### 8.1 Request (`jupiter_exec.OrderRequest.params`)
`inputMint`, `outputMint`, `amount` (integer atoms), `taker` = mandate wallet,
`slippageBps` = mandate value (explicit, so RTSE does not choose it),
`swapMode=ExactIn`, `excludeRouters=dflow,jupiterz,okx` (metis = Jupiter v6
only), `maxSupportedTransactionVersion=0`,
`priorityFeeLamports=500000&broadcastFeeType=maxCap` (Jupiter-side priority-fee
cap, facts §2).

Why only metis: JupiterZ needs a maker co-signature during `/execute`, so the
transaction id cannot be known beforehand (facts §3, UNCONFIRMED 7). Dflow and
OKX program IDs and top-level programs are undocumented (UNCONFIRMED 4), so the
program allowlist could not accept them anyway. The trade-off is that we lose
JupiterZ quotes, which are "often 5-20 bps better" (facts §4 design note).

### 8.2 Order response (`check_order`), each failure is a rejection
No `error`/`errorMessage`/non-zero `errorCode`. `router == "metis"`.
`gasless === false`. No `quoteId`/`maker`/`expireAt`. `taker`,
`signatureFeePayer` = wallet, and `prioritizationFeePayer`/`rentFeePayer` are
absent or equal to the wallet. Mints and `inAmount` equal the request.
`swapMode` is ExactIn. `slippageBps` equals the requested value.
`ceil(outAmount·(1−slippage)) ≤ otherAmountThreshold ≤ outAmount`. `feeBps` is
between 0 and 50, and `feeMint` is in the swap. `transactionVersion` is absent
or 0. `routePlan` is non-empty and every leg is SOL↔USDC only. `requestId` is
well-formed. `lastValidBlockHeight` is present. `transaction` is non-empty
base64. The quoted price is within 300 bps of the journal's last close.
Unknown extra fields are ignored, because Jupiter already sends undocumented
ones (`guaranteedPrice`, `jitOptimized`; facts §2).

### 8.3 Transaction (`verify.verify`)
1. Decode with `solana_tx.parse_transaction`. Size ≤ 1232 bytes, canonical
   compact-u16, no trailing bytes, signature count equals the header, v0 only
   (prefix 0x80; v1 0x81 and legacy are rejected).
2. `numRequiredSignatures == 1`, static key 0 = wallet (fee payer = only
   signer), the signature slot is still all zero.
3. ALTs: `getAccountInfo(table, base64, confirmed)`. The owner must be
   `AddressLookupTab1e…`, the table must be active (deactivation_slot =
   u64::MAX), and the data must be 56 + 32·n bytes. All indexes must exist. The
   account list is static, then writable, then readonly (facts §7).
4. Top-level instructions: every `program_id_index` must be a **static** key (a
   program from a table is rejected). It must be on the allowlist: System,
   ComputeBudget, SPL Token, Associated Token Account, Jupiter v6
   (`JUP6Lkb…`). Token-2022 is not needed for SOL/USDC and is not allowed.
   - ComputeBudget: only RequestHeapFrame, SetComputeUnitLimit,
     SetComputeUnitPrice and SetLoadedAccountsDataSizeLimit, each at most once.
     `ceil(price × limit / 1e6)` ≤ 500,000 lamports. With no limit given, the
     worst case of 1.4M CU is assumed.
   - ATA Create/CreateIdempotent: payer = wallet, owner = wallet, mint ∈ {input, output},
     programs System/Token.
   - System: only `Transfer`, from the wallet, to a wSOL account owned by the
     taker (created in this transaction or already existing), only when SOL is
     the input, and the total ≤ the order amount (wrapping).
   - Token: only `SyncNative` on a taker wSOL account, and `CloseAccount` of a
     taker account with destination and authority = wallet.
   - Jupiter v6: at least one instruction. **Data is not decoded** (no public
     IDL; facts §4), and its effect is checked by simulation.
5. Blockhash headroom: `getBlockHeight(confirmed) + 30 < lastValidBlockHeight`.
6. The taker's token accounts: `getTokenAccountsByOwner` (Token program; ≤ 16
   accounts). The wallet must have **no** Token-2022 accounts.
7. `getMultipleAccounts` (pre-state), then `simulateTransaction`
   (`sigVerify:false`, `replaceRecentBlockhash:false`, confirmed,
   `accounts.addresses` = wallet + every taker token account + every ATA the
   transaction creates). The simulation must have no `err`, its slot must be ≥
   the pre-state slot, and every taker token account must still be owned by
   the taker with no delegate and no close authority. Deltas (SOL value =
   lamports + wSOL):
   - BUY: USDC delta ≥ −amount, SOL delta ≥ threshold − fee cap.
   - SELL: SOL delta ≥ −(amount + fee cap), USDC delta ≥ threshold.
   - Any other mint: delta ≥ 0.
   - Fee cap = 5,000 + 500,000 + 2 × 2,039,280 lamports ≈ 0.0046 SOL.
8. Order age ≤ 25 s at signing time, and the mode is still LIVE for the same
   mandate hash.

### 8.4 Independent re-check in the signer (`signer.py`)
The signer is a separate process: `python3 -I`, env = `PATH`/`LC_ALL` only,
`cwd=/`. It **does not import jupiter_bot** (it is a second, independent
implementation). It reads the mandate and the arm file itself, so deleting the
arm file stops signing even if the engine were wrong. It reads the keypair file
itself and nobody else ever opens it. It checks:
- PyNaCl is importable, or it refuses with exit code 3. There is no home-made
  ed25519.
- The mandate keys are exact and the mandate is unexpired. The arm file is LIVE
  with sha256 = this mandate file and wallet = the mandate wallet.
- The keypair file is a regular file and not a symlink (opened with
  `O_NOFOLLOW`), owned by the uid, mode 0600/0400, and outside the repo. It is a
  64-int solana-keygen array. `SigningKey(seed).verify_key` must equal both the
  file's public half and the mandate wallet.
- The bundle's sha256 equals the message. Side and mints are consistent and
  allowed. The notional (BUY `in_amount`, SELL `min_out`) is ≤ max_trade.
- Static message rules (§8.3 steps 2 and 4, without ALT resolution: programs
  must be static, so the signer can check them without RPC).
- Daily caps, in its own state file, per UTC day: ≤ 24 signatures and signed
  notional ≤ 8 × max_position. The state file is updated (fsync + rename)
  **before** the signature is released. Re-signing identical bytes is not
  counted again (ed25519 is deterministic, so it gives the same signature).
- The key buffer is overwritten after use (best effort in Python). Errors never
  contain key material.

The engine additionally verifies the signature with PyNaCl when it is
importable, re-parses the signed transaction and checks that the message bytes
are unchanged.

## 9. Threat model and failure handling

| Threat / failure | Handling |
|---|---|
| Jupiter returns a transaction that does more than the quoted swap (extra signer, other recipient, drain via CPI, delegate approval) | §8.3: signer/fee payer check, program allowlist, decoded System/Token/ATA rules, simulation deltas over all taker accounts, owner/delegate/close-authority checks. The signer repeats the static checks. |
| Gasless/RFQ route where the txid is unknown before `/execute` | Excluded in the request; rejected on `router`, `gasless`, `signatureFeePayer`, RFQ fields and signer count. |
| `/execute` times out or returns 5xx, outcome unknown | UNKNOWN. The signature was stored before sending. The resolver polls the chain and never re-sends; a new order only after EXPIRED (finalized height > lastValid + 150 and still no status). |
| Process dies anywhere | The ledger state decides: before SIGNED it is FAILED (cannot land), at SIGNED it becomes UNKNOWN and is then resolved. A crash between booking and state cannot happen (one transaction). |
| Two engines at once | `flock` on `execution.lock`, plus the atomic one-open-order rule in `create_intent`. |
| Bug in the engine signs something bad | The signer's independent static checks, notional ≤ max_trade, and daily count/notional caps. |
| Secret leakage | The key is only read by the signer process. The RPC URL is never printed (host only). Status, dashboard and ledger hold no URL and no key path. HTTP errors name the host. |
| Stale or wrong market data | `build_snapshot` rejects stale data. The quote price must be within 300 bps of the journal close. |
| Mandate edited | The sha changes, so the mode is DISARMED immediately (engine and signer). |
| Fill does not match the order | Booked as it happened, `anomaly` flag, auto-disarm. |
| Daily loss | No BUY after realised P&L ≤ −limit until the next UTC day. |
| Public RPC | The `private_rpc` gate cannot be overridden. |

### UNCONFIRMED items that matter, and how the design copes

- **U1 (facts UNCONFIRMED 1): `/execute` with the same signed tx / requestId
  twice.** The bot never re-posts. Resolution relies only on the chain. If
  Anton ever re-posts by hand, on-chain dedup of identical bytes makes it safe
  (facts §3), but what Jupiter answers is unknown.
- **U2 (2): `/execute` server timeout, no status endpoint.** The client timeout
  is 60 s. Any non-clear answer gives UNKNOWN and chain polling. We need no
  Jupiter status endpoint because the txid is known locally.
- **U3 (3): the exact instruction list of `/order` transactions (tips, fee
  transfer, ATA, wrap).** Reject by default: a tip transfer to a Jito/Nozomi
  account, a separate fee transfer or a temporary-account wSOL flow
  (CreateAccount/InitializeAccount) is rejected. **This can make every real
  order fail verification.** DRY_RUN will show it. The fix is to widen the
  allowlist deliberately (e.g. a named tip-account list with a lamport cap),
  re-test, and review again.
- **U4 (4): Dflow/OKX programs.** Excluded by `excludeRouters`. The allowlist
  rejects them anyway.
- **U6 (6): min/max order size.** Not relied on. Gasless ~$10 minimum is
  irrelevant (gasless rejected).
- **U7 (7): JupiterZ txid.** JupiterZ is excluded.
- **U-lvbh (INFERRED): `lastValidBlockHeight` from `/order` is taken as the
  hard expiry.** We cannot tie the message blockhash to a height without an
  extra RPC method, so EXPIRED needs finalized height > lastValid **+ 150**
  (one more full blockhash lifetime). This guards against an understated value.
  Cost: about a minute more waiting.
- **U-sim (not in facts): `simulateTransaction` `accounts` post-state.** This is
  standard Solana RPC behaviour, but our provider's exact response must be
  confirmed in DRY_RUN. A missing or mismatching `accounts` array is a
  rejection.
- **U10: public RPC limits and terms.** The public RPC is not allowed at all.

## 10. Remaining risks Anton must accept before arming

1. **Hot key.** The keypair is a plaintext file readable by Anton's user.
   Process separation protects against the engine's own bugs and log or
   traceback leaks. It does **not** protect against malware running as Anton.
   Fund the wallet only with max_position + about 0.05 SOL, and keep the rest
   elsewhere.
2. **Trust in RPC and Jupiter program.** ALT contents, balances and simulation
   all come from the one RPC provider. A lying RPC could make a bad transaction
   look good. The on-chain minimum-out is enforced by the Jupiter v6 program,
   whose instruction data we do not decode. The signer's static rules and the
   small amounts bound the damage. A second independent RPC for the verifier is
   a possible later improvement.
3. **Simulation ≠ execution.** State can change between simulation and landing.
   `otherAmountThreshold` (enforced on-chain) bounds the price. Anything else
   is caught only after the fact (anomaly, then auto-disarm).
4. **Fail-closed liveness.** If the RPC is down, or an order stays UNKNOWN, the
   bot neither buys nor sells. It cannot sell during an outage. The worst case
   is holding up to max_position of SOL longer than intended.
5. **The daily loss limit is realised only.** Unrealised drawdown while LONG is
   bounded only by max_position (spot, no leverage) and the strategy's exit.
6. **Ledger position ≠ wallet balance.** Do not move funds manually while armed.
   If you do, disarm first, and expect the ledger position to be the bot's
   sub-account only.
7. **Strict verifier may reject real orders** (U3, multi-hop routes via other
   mints, priority fee above the cap in congestion). This fails safe. Expect to
   tune it after DRY_RUN, with a new review.
8. **Signer caps are local.** The same user can delete `signer-state.json`.
   They guard against bugs, not against an attacker.
9. **The review gate is a text line.** It does not bind a commit. Ask the
   reviewer to name the reviewed commit in `P3_REVIEW.md`, and re-review after
   any change to `jupiter_bot/execution/`.
10. **Clock.** UTC day, mandate expiry and order age use the system clock. Keep
    NTP on.
11. **Terms/legal (facts §9, UNCONFIRMED 8, 9, 12).** Jupiter API terms (§3.2
    clauses, keyless vs §5.1) and Danish/EU rules for a self-custodial bot are
    not settled. This is Anton's decision. It is not legal advice.
12. **PyNaCl source.** The signer runs with `python3 -I`, so PyNaCl must come
    from the system (`apt install python3-nacl`). A `pip --user` install is
    invisible to it, on purpose.

## 11. Operator procedure (Anton)

Everything below is done by Anton, by hand. The bot never creates keys.

1. **Install the official Solana CLI** (Anza/Agave) from the official docs
   (docs.anza.xyz → "Install the Solana CLI"). Check it with
   `solana-keygen --version`.
2. **Create a dedicated wallet** (new, only for this bot):
   ```
   mkdir -p ~/.config/jupiter-bot/keys && chmod 700 ~/.config/jupiter-bot/keys
   solana-keygen new --outfile ~/.config/jupiter-bot/keys/bot.json
   chmod 600 ~/.config/jupiter-bot/keys/bot.json
   solana-keygen pubkey ~/.config/jupiter-bot/keys/bot.json
   ```
   Write the seed phrase on paper, offline. Never paste it, or the file, into
   a chat, git or a log.
3. **Private RPC.** Create an account with an RPC provider (your choice) and
   use its HTTPS URL.
4. **Install PyNaCl for LIVE only:** `sudo apt install python3-nacl`.
5. **Write the mandate** `~/.config/jupiter-bot/mandate.json` (§4), then
   `chmod 600` it. Run
   `python3 -m jupiter_bot.execution check-mandate` until it prints `OK`.
6. **Fund a small amount**: e.g. 0.05 SOL (fees + reserve) plus USDC ≤
   max_position. Send from another wallet with your own tools.
7. **DRY_RUN:** `python3 -m jupiter_bot.execution dry-run-once`, 3 or more
   times, or `arm --dry-run` followed by repeated `run-once`. Read every result
   (`ok`, `error`, simulated deltas, priority fee). Check `status`: the gate
   `dry_run_ok` turns OK.
8. **Review:** an independent reviewer writes
   `jupiter_bot/reviews/P3_REVIEW.md` with the reviewed commit and a line
   `Verdict: APPROVED`.
9. **P2:** the holdout verdict must be `PASS` for the mandate's strategy and
   params, or you knowingly override with `--override p2_holdout_pass`.
10. **Arm:** `python3 -m jupiter_bot.execution arm`. Read the summary, then type
    the phrase. Run `run-once` by hand at first and watch `status`. A systemd
    timer is your later decision; it is not installed.
11. **Disarm (kill switch):** `python3 -m jupiter_bot.execution disarm`, or
    `rm ~/.config/jupiter-bot/armed.json`, or edit the mandate. Pending orders
    are still resolved (`resolve`), and nothing new is signed or sent. To get
    out completely, transfer the funds away with your own wallet tools after
    `status` shows no pending or unknown orders.
