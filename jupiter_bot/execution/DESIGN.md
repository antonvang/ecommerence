# P3 execution adapter: design

Revision 2, 2026-11-20. This revision fixes the findings F1–F17 from
`reviews/P3_REVIEW_DRAFT.md`; §12 maps each finding to its change.

## Kort dansk resumé (til Anton)

- Alt er bygget og testet mod falske Jupiter-, RPC- og signer-udgaver. Der er
  ingen nøgler, ingen wallet og ingen rigtige transaktioner. Standardtilstanden
  er **DISARMED**.
- LIVE kræver: et gyldigt mandat, som du skriver selv, en privat RPC, en
  arm-fil, som `arm` opretter efter en indtastet sætning, mindst 3 vellykkede
  DRY_RUN-kørsler med netop dette mandat, og et review, der er bundet til
  præcis den kode, der kører. En fejlende port kan du kun tilsidesætte med
  `--override` plus en ekstra sætning, og det logges. Mandat og privat RPC kan
  aldrig tilsidesættes.
- Hver ordre verificeres før signering:
  - der må kun være én signer, nemlig din wallet;
  - Jupiters swap-instruktion afkodes, så beløb, slippage og minimumspris
    tjekkes direkte i transaktionen;
  - kun kendte programmer må kaldes, også inde i swappen;
  - en simulering skal vise, at du højst bruger dit beløb plus det præcise
    gebyr, og at walletten forbliver en almindelig konto.
- Signeringen sker i en separat proces, som selv tjekker alt igen. Den lofter
  også selv, hvor meget SOL der kan forlade walletten (`max_trade_sol` i
  mandatet).
- Ordren skrives i ledgeren, før noget sendes. Ved timeout sendes intet igen,
  og der laves ingen ny ordre. En ordre bliver kun EXPIRED på positivt bevis:
  RPC'en er opdateret, transaktionen findes ikke, og saldoen er uændret. Ellers
  forbliver den UNKNOWN, og botten venter.
- Én wallet hører til én ordrebog og har én lås, også hvis man bruger et andet
  `--data-dir`.
- Nødstop: `python3 -m jupiter_bot.execution disarm` eller slet
  `~/.config/jupiter-bot/armed.json`. Enhver ændring i `mandate.json` slår også
  LIVE fra.
- **Vigtigt:** Jupiters instruktionsformat og listen over DEX-programmer er
  gengivet fra hukommelsen, ikke fra en officiel kilde, du har her. Begge skal
  bekræftes med en rigtig DRY_RUN, før du armerer (afsnit 9, U-ix og U-dex).
  Nøglen er en "hot key": sæt kun et beløb ind, du kan tåle at miste.

---

## 1. Scope and non-goals

In scope: SOL/USDC spot swaps through Jupiter `GET /swap/v2/order` (with
`taker`) and `POST /swap/v2/execute`. One wallet, one order at a time, at most
one order per cycle. Sizing comes from the P2 strategy named in the mandate.

Out of scope: other tokens, leverage, Token-2022, RFQ/JupiterZ, gasless,
integrator `payer`/`receiver`, `/build`, v1 transactions, unattended operation
(no timer is installed; `run-once` is written for one that Anton may install).

Facts come from `research/JUPITER_API_FACTS.md`, read 2026-11-20 ("facts §n").

## 2. Components

| Module | Role |
|---|---|
| `config.py` | Paths, fixed hard limits, the pinned program allowlist for CPIs, and the wallet registry dir. |
| `mandate.py` | Strict parse of `mandate.json`, read once (parse and sha256 from the same bytes). Only `lstat` on the keypair file and its directory. |
| `gates.py` | Gates, arm file, wallet→ledger binding, effective mode, and the code hash for the review gate. |
| `http.py` | Allowlisted HTTPS only: api.jup.ag and the mandate RPC host. No redirects, environment proxies ignored, timeouts, 4 MB cap, strict JSON. |
| `rpc.py` | JSON-RPC: getBlockHeight, getEpochInfo, getAccountInfo, getMultipleAccounts (optionally with `dataSlice`), getTokenAccountsByOwner, simulateTransaction (`innerInstructions: true`), getSignatureStatuses (with context slot), getTransaction. |
| `jupiter_exec.py` | Builds the `/order` request and checks the response strictly. Calls `/execute`; any doubt is UNKNOWN. |
| `jupiter_ix.py` | Decodes the Jupiter v6 route instruction arguments (F3). |
| `solana_tx.py` | base58, compact-u16, legacy/v0 decode, ALTs, account resolution with duplicate rejection, SPL token layout, ed25519 curve test, `create/find_program_address`, ATA derivation. |
| `verify.py` | Pre-sign verification of the real transaction (§8.3). |
| `signer.py` | **Standalone** signer process. It imports nothing from jupiter_bot, has its own decoder and PDA code, its own caps, and uses PyNaCl. |
| `signer_client.py` | Runs `/usr/bin/python3 -I signer.py` with a minimal environment and `cwd=/`. |
| `ledger.py` | `execution.db`: self-identifying (application_id `JBEX`, user_version 1) and append-only. |
| `engine.py` | Resolver, decision, order life cycle, kill-switch re-checks, arm/disarm/force-expire, and the wallet-wide locks. |
| `__main__.py` | CLI: `status [--json]`, `check-mandate`, `dry-run-once`, `run-once`, `arm`, `disarm`, `resolve`, `force-expire ORDER_ID`, `code-hash`. |

Wallet-wide files (F7) live in `~/.config/jupiter-bot/wallets/`, whatever
`--data-dir` or `--mandate` says:
- `<wallet>.lock`: one `flock` per wallet;
- `<wallet>.json`: which ledger owns this wallet;
- `<wallet>.signer-state.json`: the signer's daily caps.

## 3. Modes and gates

The mode is recomputed from files on every call (`gates.evaluate`):

- **DISARMED** is the default. Any of these gives DISARMED:
  - no mandate, or an invalid or expired one;
  - no arm file, or one that belongs to another mandate sha256 (**any edit
    disarms**);
  - a public RPC;
  - the wallet is not bound to *this* ledger (F7);
  - armed LIVE, but a non-overridden gate is failing.
- **DRY_RUN**: an arm file with mode DRY_RUN for this exact mandate, wallet
  bound to this ledger. `run-once` then does dry-run cycles. `dry-run-once`
  works whenever the mandate is valid and the RPC private, without arming.
  A dry run never signs and never calls `/execute`. It records the decoded
  Jupiter instruction, the invoked programs and the exact expected fee, so you
  can inspect a real transaction.
- **LIVE**: an arm file with mode LIVE for this exact mandate, wallet bound to
  this ledger, and all gates OK or overridden at arm time.

| Gate | OK when | Overridable |
|---|---|---|
| `p2_holdout_pass` | `plan_lock.json` is a dict and `research.lock.verify` finds no problems. `verify` now also rejects an empty or partial `code_sha256` (F17). A verdict file in `research/verdicts/` has `label: holdout`, `verdict: PASS`, the lock's `plan_sha256`, and the mandate's strategy + params. A malformed lock or verdict never crashes `status`. | yes |
| `mandate_valid` | Strict parse, unexpired, both mints allowed. Keypair file is regular, not a symlink, yours, 0600/0400, outside the repo; its directory is yours, not a symlink, not group/other-writable. | **never** |
| `private_rpc` | rpc host is not `solana.com` / `*.solana.com`. | **never** |
| `dry_run_ok` | ≥ 3 successful DRY_RUNs with the current mandate sha256 in this ledger. | yes |
| `review_done` | `reviews/P3_REVIEW.md` has exactly one `Commit: <git sha>` line and exactly one `Execution-SHA256: <hash>` line, and the hash equals `execution_code_sha256(repo)` **now**, plus a line `Verdict: APPROVED` (F8). The hash is sha256 over `name NUL sha256(file) LF` for every `jupiter_bot/execution/*.py`, sorted. `python3 -m jupiter_bot.execution code-hash` prints it. | yes |

`arm` needs an interactive terminal and the phrase `ARM LIVE <wallet[:8]>`, or
`ARM DRY_RUN …`. Failing overridable gates need `--override GATE` plus the
phrase `OVERRIDE <gates>`. Overrides are logged in the ledger and shown in the
gate detail as "OVERRIDDEN …", still with `ok: false`.

`arm` binds the wallet to this ledger (`wallets/<wallet>.json`). If the wallet
is already bound to another ledger, it refuses. Moving to another data dir is
a deliberate manual step: delete that binding file, but only when no order is
open in the old ledger. `disarm` needs no lock and no phrase. The engine
re-checks the mode right before signing and right before sending.

## 4. Mandate

Exactly these keys; anything else, or a duplicate key, is rejected:

```json
{
  "wallet_pubkey": "<base58 32-byte pubkey>",
  "keypair_path": "/home/anton/.config/jupiter-bot/keys/bot.json",
  "rpc_url": "https://<private provider host>/<key>",
  "max_trade_usdc": "25",
  "max_trade_sol": "0.15",
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

- USDC amounts are decimal strings in whole USDC (≤ 6 decimals).
- `max_trade_sol` is a decimal string in SOL (≤ 9 decimals). It is **new in
  revision 2 (F1)**: the signer cannot know the SOL price, so the mandate
  itself caps the SOL input of every SELL. Set it to about max_trade_usdc ÷ the
  current SOL price, plus a margin. A SELL larger than that is never signed
  (the engine also sizes SELLs ≤ `max_trade_sol`).
- JSON numbers for money are rejected.
- max_trade_usdc ≥ 1 and ≤ max_position_usdc.
- slippage is an integer from 1 to 300.
- strategy and params must be an entry of the P2 grid.
- `rpc_url` and `keypair_path` are never shown in status or the dashboard.

Status reports USDC amounts as whole-USDC numbers, which is what the
dashboard renders. Internally everything is integer atoms.

## 5. Order life cycle

```
 INTENT ──/order+verify──▶ VERIFIED ──signer──▶ SIGNED ──/execute──▶ SUBMITTED (200 Success, our sig)
   │ reject                  │ disarmed/old/       │      └────────▶ UNKNOWN (timeout, 5xx, 4xx, odd, any error)
   ▼                         ▼ signer refused      └─ disarmed before send ─▶ UNKNOWN (not sent, but kept open)
 FAILED                    FAILED
                                       SUBMITTED / UNKNOWN ──chain──▶ CONFIRMED | FAILED | EXPIRED
```

- INTENT is written before any request for the order. `create_intent` refuses
  atomically while any order is open. The data-dir lock **and** the wallet
  lock are held for run-once, dry-run-once, resolve, arm and force-expire.
- VERIFIED stores:
  - requestId, wallet, amounts, `lastValidBlockHeight`, unsigned tx, message sha256;
  - the decoded swap, invoked programs, the exact network fee and expected fee,
    and the ATAs that persist;
  - the pre-order wallet view (SOL value and per-mint balances), which the
    EXPIRED rule needs.
- SIGNED stores the signature (the txid; taker = only signer = fee payer) and
  the signed bytes, before `/execute`.
- If the bot is disarmed after signing, the order goes to **UNKNOWN**, not
  FAILED. It was not sent, but the order stays open until it provably expired,
  so no second order can race it (F13).
- `/execute` never decides the outcome. Any exception, including a refused
  redirect, gives UNKNOWN (F13).

**Resolver.** It never sends anything. Orders left at INTENT/VERIFIED become
FAILED (never signed). Orders left at SIGNED become UNKNOWN. Then, for each
SUBMITTED/UNKNOWN order:
1. Run `getEpochInfo(finalized)`, which gives the finalized slot and block
   height from one response, then `getSignatureStatuses([sig], searchTransactionHistory)`.
2. If the status is finalized: run `getTransaction`, then book (§6). A
   processed/confirmed status means wait.
3. If there is no status, EXPIRED needs **all** of the following (F5).
   Otherwise the order stays UNKNOWN and the reason is reported:
   - the finalized height is greater than `lastValidBlockHeight + 150`;
   - the status answer's context slot is ≥ that finalized slot (a lagging
     node is not believed);
   - `getTransaction(sig, finalized)` returns null (if it returns the
     transaction, it is booked);
   - a second status query is still null, again with a context slot ≥ the
     finalized slot;
   - the wallet's SOL value and token balances are **exactly** the VERIFIED
     snapshot. An RPC without history cannot hide a landed swap, because the
     swap would have changed the balances.
4. When balances changed, for example a landed swap the RPC forgot, or a
   deposit: the order stays UNKNOWN and an `expiry_blocked` event is logged.
   The fix is an RPC with full history, then `resolve`. Or, after checking the
   wallet history by hand, `force-expire ORDER_ID`. That command needs a
   terminal and the phrase `EXPIRE <id[:8]>`, still requires the chain proof
   (height past the margin, no status), and is logged.

## 6. Booking and P&L

A fill is booked only from a finalized `getTransaction`:
- key 0 must be the wallet, and `signatures[0]` must be ours;
- SOL value is the wallet's lamports plus its wSOL; USDC is its USDC balance;
- the fill and the terminal state are written in one SQLite transaction.

The post-fill check is exact (F6): `meta.fee` must be ≤ the verified network
fee, and the deltas must satisfy the same rule as §8.3 step 9 with expected fee
= `meta.fee` + rent of persisting ATAs. A violation is booked as it happened,
flagged, and **auto-disarms**.

Position and cost basis form the bot's sub-account:
- BUY: position += SOL net of fees; cost += USDC.
- SELL: average cost; realised = USDC − cost removed. SOL spent beyond the
  position (fees on a full sell) is charged at the decision price (F14).
- FEE_ONLY (landed but failed): −fee at the decision price.

`position()` follows insertion order, never the wall clock (F10).
`today_realized_pnl_usdc` is per UTC day. At ≤ −daily_loss_limit, there are no
BUYs until the next UTC day; SELL toward flat is still allowed.

## 7. Decision and sizing

`run-once`:
1. resolve; stop if anything is still open (`WAIT`);
2. take a read-only journal snapshot, `build_snapshot(..., bars=bars_needed(params))`;
3. strategy target LONG/FLAT;
4. read wallet balances via RPC.

- **LONG**: BUY min(max_trade_usdc, max_position − max(cost, value), USDC
  balance). Needs ≥ 1 USDC, ≥ 0.03 SOL reserve, and no daily-loss stop.
- **FLAT**: SELL min(position or a max_trade-sized slice, `max_trade_sol`,
  SOL above the reserve). Dust is ignored.

## 8. What is verified before signing, and how

### 8.1 Request
`taker` = wallet, `slippageBps` = mandate, `swapMode=ExactIn`,
`excludeRouters=dflow,jupiterz,okx` (metis = Jupiter v6 only),
`maxSupportedTransactionVersion=0`, `priorityFeeLamports=500000&broadcastFeeType=maxCap`.
Only metis, because JupiterZ's txid is unknown before `/execute` and Dflow/OKX
programs are undocumented (facts UNCONFIRMED 4, 7). Trade-off: no JupiterZ
prices (said to be 5–20 bps better).

### 8.2 Order response (`check_order`)
Each of these must hold, or the order is rejected:
- no error; router metis; `gasless === false`; no RFQ fields;
- taker and `signatureFeePayer` are the wallet; other fee payers are the
  wallet or absent;
- mints, `inAmount` and ExactIn match the request; `slippageBps` equals the
  requested value;
- `floor(outAmount·(10000−slippage)/10000) ≤ otherAmountThreshold ≤ outAmount`
  (floor, the same rounding as the program);
- `feeBps` ≤ 50, and the fee mint is in the swap; v0;
- the route plan is SOL↔USDC only; `requestId` and `lastValidBlockHeight` are
  present; the transaction is non-empty base64;
- the price is within 300 bps of the journal close.

### 8.3 Transaction (`verify.verify`)
1. **Decode.** Strict decode, ≤ 1232 bytes, v0 only. Exactly one required
   signature; key 0 = wallet; the signature slot is zero.
2. **Lookup tables.** Each ALT is read via `getAccountInfo`: owner must be the
   ALT program, and the table must be active and well-formed. Account
   resolution rejects any key that appears twice, whether static+ALT or
   ALT+ALT (F12).
3. **Top-level programs.** Each must be static and one of System,
   ComputeBudget, SPL Token, ATA, Jupiter v6.
   - ComputeBudget: known instructions only, each once.
     `ceil(price × limit / 1e6)` ≤ 500,000 lamports.
   - ATA create: paid by and owned by the wallet, mint in the swap, and the
     address **equals the locally derived ATA PDA** (F12).
   - System: only `Transfer`, from the wallet to the **derived** wSOL ATA,
     only on a SELL, total ≤ the order amount.
   - Token: only `SyncNative` on the derived wSOL ATA, and `CloseAccount` of
     an own account back to the wallet.
4. **Jupiter instruction (F3).** Exactly one, of an accepted variant
   (`route`, `shared_accounts_route`). It is decoded by `jupiter_ix`:
   `in_amount` == the order; `slippage_bps` ≤ the mandate;
   `platform_fee_bps` ≤ 50; and `quoted_out·(10000−slippage)/10000` ≥
   `otherAmountThreshold`. So the floor the program enforces is checked
   before signing, not assumed.
5. **Executable accounts (F4).** `getMultipleAccounts` (no data) over every
   resolved key. Each executable account must be on the pinned allowlist
   (top-level programs + Memo + `config.DEX_PROGRAMS`).
6. **Blockhash.** `getBlockHeight(confirmed) + 30 < lastValidBlockHeight`.
7. **Taker token accounts.** At most 16, Token program only; no Token-2022
   accounts.
8. **Simulation.**
   - `getMultipleAccounts` (pre), then `simulateTransaction` (sigVerify false,
     `innerInstructions: true`, post-state of the wallet + all taker token
     accounts + created ATAs).
   - Every inner (CPI) program must be on the same allowlist. If the RPC does
     not return `innerInstructions`, the order is rejected (fail closed, F4).
   - The wallet is System-owned, has empty data and is not executable, both
     pre and post (F2).
   - Token accounts are initialised, not frozen, owned by the taker, with no
     delegate and no close authority.
9. **Exact deltas (F6).** expected_fee = 5000 × signatures + this
   transaction's own priority fee + 2,039,280 for each created ATA that still
   exists afterwards.
   - BUY: USDC spent ≤ amount, and SOL received + expected_fee ≥ threshold.
   - SELL: SOL spent ≤ amount + expected_fee, and USDC received ≥ threshold.
   - Any other mint: no decrease.
10. Order age ≤ 25 s at signing; still LIVE for the same mandate sha.

### 8.4 Independent re-check in the signer
The signer runs as `/usr/bin/python3 -I signer.py --mandate M --arm A --registry DIR`,
with env `PATH`/`LC_ALL` only and `cwd=/`. It imports nothing from
jupiter_bot. It reads the mandate, the arm file (LIVE, this mandate sha256 and
wallet) and the keypair itself. Its checks:
- **PyNaCl present.** Otherwise exit 3.
- **Keypair file.** lstat checks; directory checks; opened with `O_NOFOLLOW`;
  `fstat` of the opened fd must be the same inode, owner and mode as checked
  (F15). The derived public key must equal the mandate wallet.
- **Message (static).**
  - v0, one writable signer = wallet; programs static and allowlisted;
    ComputeBudget priority ≤ cap.
  - System transfers only on a SELL, only to the signer's **own derived wSOL
    ATA**, and their **sum** ≤ the decoded swap input (F1).
  - ATA creates at the derived PDA; SyncNative/CloseAccount only on own
    derived ATAs.
- **Jupiter instruction.** Exactly one, decoded with the signer's own code:
  in_amount == bundle; slippage ≤ mandate; fee ≤ 50 bps; floor ≥ the bundle's
  minimum.
- **Mandate bounds, not engine bounds (F1).** BUY input ≤ `max_trade_usdc`;
  SELL input ≤ `max_trade_sol`.
- **Daily caps.** ≤ 24 signatures and notional ≤ 8 × max_position per UTC
  day, in `wallets/<wallet>.signer-state.json`. The file name is derived from
  the wallet by the signer (F7), and it is updated before the signature is
  released.

## 9. Threat model, failure handling, UNCONFIRMED items

| Threat / failure | Handling |
|---|---|
| Jupiter returns a transaction that does more than the quote | §8.3 steps 1–9; the signer repeats steps 1, 3, 4 and adds mandate-derived caps. |
| A loose price floor in the route instruction (sandwich) | Decoded floor ≥ threshold ≥ mandate slippage floor, checked in the engine and the signer (F3). |
| A malicious program on the CPI path | Executable accounts and simulated inner programs must be allowlisted (F4). Residual: see §10.3. |
| Wallet reassigned or allocated by a CPI | Wallet must stay System-owned, empty and non-executable in the simulated post-state (F2). |
| `/execute` timeout or 5xx | UNKNOWN; signature stored before send; never re-sent; EXPIRED only per §5 (F5). |
| RPC lagging or without history | The status context slot must be ≥ the finalized expiry slot; getTransaction null; balances unchanged. Otherwise UNKNOWN (F5). |
| Two engines on one wallet (timer + manual, other `--data-dir`) | Wallet lock; wallet→ledger binding; per-wallet signer caps (F7). |
| Engine bug signs something bad | The signer's own decode, destination and sum rules, and mandate caps (F1). |
| Process dies anywhere | The ledger state decides; booking is atomic. |
| Mandate edited mid-read | One read: the parse and the sha256 come from the same bytes (F11). |
| Code changed after review | The review gate compares the code hash (F8). |
| Clock steps backwards | `position()` follows insertion order (F10). |
| Secret leakage | The key is read only by the signer. The RPC URL is never printed (host only). Environment proxies are ignored. |

UNCONFIRMED items that matter, and how the design copes:
- **U-ix (new, high importance): the Jupiter v6 route layout and
  discriminators.** No IDL is available locally, and the facts file says it is
  not in the docs. `jupiter_ix.py` reproduces the published Anchor IDL from
  memory: `route(route_plan, in_amount u64, quoted_out_amount u64,
  slippage_bps u16, platform_fee_bps u8)`, `shared_accounts_route(id u8, …same)`.
  The discriminators are recomputed from `sha256("global:<name>")[:8]` and
  match the values known for these two names. The token-ledger and exact-out
  variants are rejected. `route_v2` / `shared_accounts_route_v2` are also
  rejected: their argument order could not be confirmed. **Before arming:**
  run DRY_RUN against a real `/order`, read
  `detail.jupiter_instruction` (variant, in_amount, quoted_out_amount,
  slippage_bps, platform_fee_bps, min_out), and check that `in_amount` equals
  the order and that `min_out` and `slippage_bps` agree with the `/order`
  response. If the dry run fails with "discriminator …", Jupiter uses a variant
  we do not accept. Supporting it is a code change and needs a new review.
- **U-dex (new): `config.DEX_PROGRAMS`** is pinned from memory and has not been
  checked against `/swap/v2/program-id-to-label`. Unknown programs are rejected
  and named in the dry-run error. Extend the list only through a reviewed code
  change; the review gate's hash forces the re-review.
- **U-inner (new): `simulateTransaction` with `innerInstructions: true`.**
  This is a standard Agave RPC option, but your provider must support it. If it
  is missing, every order is rejected (fail closed). Confirm in DRY_RUN.
- **U3: other instructions in `/order` transactions** (tips, fee transfers,
  temporary wSOL accounts). These are rejected by default, which can make
  every order fail. DRY_RUN shows it; widening the rules needs a new review.
- **U1/U2: duplicate `/execute` and timeouts.** The bot never re-posts; the
  outcome comes only from the chain.
- **U-lvbh:** EXPIRED waits until `lastValidBlockHeight` + 150 has passed.
- **U-sim:** `simulateTransaction` `accounts` post-state must be confirmed with
  your provider in DRY_RUN.
- **U4, U7:** Dflow, OKX and JupiterZ are excluded.

## 10. Remaining risks Anton must accept before arming

1. **Hot key.** Process separation guards against bugs and leaks, not against
   malware running as you. Fund only max_position + about 0.05 SOL.
2. **The decoded Jupiter layout is unconfirmed** (U-ix). If it were wrong in a
   way that still passes, the floor check would read the wrong bytes. DRY_RUN
   against real transactions, compared with the `/order` response, is
   required before arming.
3. **Jupiter v6 is trusted.** It is an upgradeable program: it enforces the
   decoded floor on chain and moves tokens via CPI. A malicious upgrade, or an
   allowlisted DEX behaving differently on chain than in simulation (e.g.
   branching on slot), is not caught before landing. The post-fill check
   auto-disarms afterwards. Per trade, the damage is bounded by max_trade_usdc
   (BUY) or max_trade_sol (SELL). Per day it is bounded by the signer caps.
4. **One RPC is trusted.** Lookup tables, balances, simulation, inner
   instructions and status all come from one provider. A lying provider could
   pass a bad transaction through the engine. The signer's static and mandate
   bounds still hold.
5. **Fail-closed liveness.** If an order is UNKNOWN, or the RPC is down, the bot
   neither buys nor sells. It cannot exit a position during an outage.
6. **The daily loss limit is realised only.** Unrealised loss is bounded only
   by max_position.
7. **Do not move funds by hand while an order is open.** A deposit or
   withdrawal blocks EXPIRED (by design) and needs `force-expire` after you
   check by hand.
8. **The strict verifier may reject real orders** (U3, U-ix, U-dex, U-inner).
   This fails safe. Each widening is a code change, and the review gate forces
   a re-review.
9. **Local files are trusted.** Gate inputs (verdicts, plan lock, arm file,
   review file, signer caps) are unauthenticated files that you, the same
   user, can edit or delete. They guard against mistakes, not against an
   attacker (F17). The P2 holdout ends 2027-01-02, so LIVE before then needs
   `--override p2_holdout_pass`.
10. **The clock.** UTC day, expiry and order age use the system clock. Keep
    NTP on.
11. **Terms and legal.** Jupiter API terms and Danish/EU rules are open (facts
    UNCONFIRMED 8, 9, 12). This is not legal advice.
12. **PyNaCl and key memory.** The signer uses `/usr/bin/python3 -I`, so install
    `python3-nacl` via apt. PyNaCl needs the seed as an immutable `bytes` copy,
    which cannot be wiped from memory.
13. **Notes from F16.**
    - CLAUDE_HANDOFF asked for Solana's official SDK. The wire format is
      hand-rolled instead (stdlib-only rule). It is tested against Solana SDK
      PDA vectors and RFC 8032 keys. This deviation needs your explicit
      acceptance.
    - The RPC *host* is shown in status. Some providers put an account id in
      the hostname; if yours does, treat status output as private.
    - The system CA store is used. `SSL_CERT_FILE` in your environment would
      still be honoured by OpenSSL; proxies are ignored.

## 11. Operator procedure (Anton)

Everything below is done by Anton, by hand. The bot never creates keys.

1. **Install the Solana CLI.** Use the official Anza/Agave instructions
   (docs.anza.xyz), then check with `solana-keygen --version`.
2. **Create a dedicated wallet:**
   ```
   mkdir -p ~/.config/jupiter-bot/keys && chmod 700 ~/.config/jupiter-bot/keys
   solana-keygen new --outfile ~/.config/jupiter-bot/keys/bot.json
   chmod 600 ~/.config/jupiter-bot/keys/bot.json
   solana-keygen pubkey ~/.config/jupiter-bot/keys/bot.json
   ```
   Write the seed phrase on paper, offline. It must never go into a chat, git
   or a log.
3. **Get a private RPC.** It must support `simulateTransaction` with
   `innerInstructions` and keep transaction history.
4. **Install PyNaCl** (needed for LIVE only): `sudo apt install python3-nacl`.
5. **Write the mandate** `~/.config/jupiter-bot/mandate.json` (§4), `chmod 600`
   it, and run `python3 -m jupiter_bot.execution check-mandate` until it says
   `OK`.
6. **Fund a small amount:** about 0.05 SOL plus USDC ≤ max_position.
7. **DRY_RUN.** Run `dry-run-once` three or more times. For each, read `ok`,
   `error`, `jupiter_instruction`, `inner_programs`, `expected_fee` and
   `deltas`, and compare them with the `/order` response (§9 U-ix).
8. **Review.** An independent reviewer writes `jupiter_bot/reviews/P3_REVIEW.md`
   with `Commit: <sha>`, the `Execution-SHA256:` line printed by
   `python3 -m jupiter_bot.execution code-hash`, and `Verdict: APPROVED`.
9. **P2.** The holdout PASS for the mandate's strategy and params, or a
   deliberate `--override p2_holdout_pass`.
10. **Arm.** Run `python3 -m jupiter_bot.execution arm` and type the phrase.
    Then run `run-once` by hand at first and watch `status`.
11. **Disarm.** Run `disarm`, or `rm ~/.config/jupiter-bot/armed.json`, or edit
    the mandate. Open orders keep resolving (`resolve`), and nothing new is
    signed or sent.

## 12. Review findings and their fixes (revision 2)

| Finding | Change | Tests |
|---|---|---|
| F1 signer did not bound SOL outflow | Transfers only to the signer's own derived wSOL ATA; their sum ≤ the decoded swap input; SELL input ≤ new mandate key `max_trade_sol`; BUY input ≤ max_trade_usdc, from the decoded instruction. | `test_execution_signer` `test_sol_outflow_is_bounded` (probes S1–S3), `test_bundle_limits` |
| F2 wallet owner/data unchecked | Pre and post: System owner, empty data, not executable. Token accounts initialised and not frozen. | `test_execution_verify.WalletAccount` (probe P1) |
| F3 price floor assumed | `jupiter_ix` decode in both engine and signer; exactly one route; in_amount/slippage/fee/floor checks; recorded in DRY_RUN. | `JupiterInstruction`, `test_dry_run_records_decoded_instruction_for_review` |
| F4 CPI unconstrained | Executable-account allowlist, inner-instruction allowlist; fail closed without `innerInstructions`. | `test_execution_verify.Programs` |
| F5 EXPIRED on a null status | Epoch-info slot, context slot ≥ finalized, getTransaction null, re-check, unchanged balances; `force-expire`. | `ExpiryEvidence` (probe E1 + lagging node) |
| F6 fixed fee tolerance | Exact expected fee per transaction, at verify and post-fill. | `ExactFee` (probes P2, P3), `test_fee_above_verified_is_an_anomaly` |
| F7 per-data-dir invariants | Wallet lock, wallet→ledger binding, per-wallet signer state. | `WalletWide` (probe E2) |
| F8 review not bound to code | Commit + Execution-SHA256 lines; hash recomputed. | `test_review_gate_is_bound_to_the_code` |
| F9 tests vs nacl | Signature-verifier seam; the fake chain derives effects from the tx; new negative tests; the suite passes with a stub `nacl`. | the whole suite, run twice |
| F10 position by clock | ORDER BY rowid. | `test_position_follows_insertion_not_the_clock` |
| F11 two reads | `mandate.load_once`. | covered by status/gate tests |
| F12 duplicates, PDAs | Duplicate rejection; pure-Python `find_program_address` (Solana SDK vectors) and ATA checks in engine and signer. | `DerivedAddresses`, `Structure` |
| F13 redirect escapes | Any exception after the POST started gives UNKNOWN; disarm after signing gives UNKNOWN. | `test_execute_redirect_is_unknown_not_a_crash` |
| F14 full-sell fee dropped | Excess SOL charged at the decision price. | `test_full_sell_books_the_fee_beyond_the_position` |
| F15 keypair hygiene | fstat after open, directory checks, `/usr/bin/python3`. | `test_keypair_directory_permissions` |
| F16 notes | Documented in §10.13. Proxies ignored. | — |
| F17 lock leniency | `lock.verify` rejects empty/partial code hashes and malformed records; malformed lock does not crash status. | `test_malformed_lock_does_not_crash_status`, `test_lock_verify_rejects_empty_or_partial_code_hashes` |
