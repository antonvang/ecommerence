# Jupiter Swap API, Solana and terms: facts for P3 (read 2026-11-20)

Audience: the engineer designing the P3 execution adapter. Every fact has a
source URL and the date it was read. **All sources were read on 2026-11-20**
unless noted otherwise. Text marked **UNCONFIRMED** could not be checked
against a primary source. Text marked **INFERRED** follows from documented
facts but is not stated anywhere. **Design note** marks my recommendations,
which are not facts.

How the sources were read: Jupiter serves every docs page as Markdown at
`<page>.md` (it advertises this for agents, see `swap/index.md`). Those pages
were fetched raw, so quotes below are verbatim. solana.com returned HTTP 429 to
automated fetches, so Solana docs were read from their official source repo
`github.com/solana-foundation/solana-com` (branch `main`, head commit
`82d49aed`, 2026-11-20T16:52Z), path `apps/docs/content/docs/en/...`. Each one
maps 1:1 to a `https://solana.com/docs/...` URL, which is the one given below.
Binance's terms pages are rendered client-side behind a bot check and could not
be read (see section 10).

Abbreviations: JD = `https://developers.jup.ag/docs`, SD = `https://solana.com/docs`.

---

## 1. Endpoints, base URL, authentication, rate limits

| Fact | Source |
|---|---|
| Base URL `https://api.jup.ag/swap/v2`. Meta-Aggregator: `GET /swap/v2/order` and `POST /swap/v2/execute`. Router: `GET /swap/v2/build`, plus landing via `tx.jup.ag` (Solana `sendTransaction`) or the legacy `POST https://api.jup.ag/tx/v1/submit`. Also `GET /swap/v2/program-id-to-label`. | JD/swap/index.md, JD/api-reference/swap/order.md, JD/api-reference/swap/execute.md, JD/api-reference/swap/program-id-to-label.md |
| "Quotes work without an API key, and one key covers every Jupiter API." | JD/swap/index.md |
| The key goes in the header `x-api-key`. OpenAPI: `securitySchemes.ApiKeyAuth: {type: apiKey, in: header, name: x-api-key}`, and `/order` and `/execute` list `security: - ApiKeyAuth: []`. | JD/api-reference/swap/order.md, execute.md |
| "A request with no `x-api-key` header is treated as keyless, not rejected." An invalid or unknown key returns 401. | JD/portal/responses.md |
| Tiers, using a **60-second sliding window**: Keyless 0.5 RPS / 30 per min (no key); Free 1 / 60; Developer 10 / 600; Launch 50 / 3,000; Pro 150 / 9,000. Keyed limits apply "**per organisation**, not per API key". | JD/portal/rate-limits.md |
| `/swap/v2/execute` has its own bucket: Keyless **20 RPS**, Free 50, Paid 100. It does not count toward the main bucket. Most other requests (Swap, Price, Tokens) share one bucket. | JD/portal/rate-limits.md, JD/swap/order-and-execute.md |
| Rate-limit headers: `x-ratelimit-remaining` (signed, can be ≤ 0), `x-ratelimit-current`, `x-ratelimit-reset` (Unix seconds when the oldest in-window request ages out). They are sent only on 200 and 429, never on 401/403/5xx. "There is no extra cooldown or lockout after a `429`." 429 body `[API Gateway] Too many requests` = plan limit; `Too many requests` = a firewall rule. | JD/portal/rate-limits.md, JD/portal/responses.md |
| Every response carries `x-api-gateway-request-id`. Log it, and quote it to support. | JD/portal/responses.md |
| Credits: `/swap/v2/order` 1, `/swap/v2/build` 1, `/swap/v2/execute` **0**. Free tier: "Unlimited credits, rate-limited only". Paid: Developer $25/mo, Launch $100/mo, Pro $500/mo. | JD/portal/plans.md |
| Keyless access replaced `lite-api.jup.ag`, which is being phased out. Developer Platform launch: 6 April 2026. Grace period for old tiers ended 30 June 2026. | JD/portal/migration.md |
| "Publishable" keys (changelog 2026-10-08) are treated like keyless requests (per-IP keyless limits, 0 credits), with attribution only. Server keys work as before. | https://developers.jup.ag/changelog/2026-10 (read via WebFetch summary, so not verbatim) |
| The API gateway runs in six AWS regions, including Frankfurt (eu-central-1). | JD/llms.txt index entry for JD/portal/latency.md |

Implications for the current code: `marketdata/quotes.py` calls `GET /swap/v2/order`
without `taker` or a key, at most once per 2.1 s. That is within the keyless
budget of 30 requests per 60 s sliding window, which is per IP (INFERRED from the
publishable-key changelog: "per-IP keyless rate limits"). Two quotes per minute
use 2 of the 30.

## 2. `GET /order`

### Request parameters (OpenAPI, JD/api-reference/swap/order.md)

| Param | Notes (from the spec) |
|---|---|
| `inputMint`, `outputMint`, `amount` | Required. `amount` is a string in the smallest unit. |
| `taker` | Public key that will sign. "If not provided, the response will contain a quote but no transaction". "Must be present if you intend to sign and execute the transaction via `/execute`". |
| `receiver` | Must differ from `taker`. A wallet, not a token account. Can add a create-ATA instruction. Disables Dflow and OKX. |
| `swapMode` | Enum `ExactIn` only. |
| `slippageBps` | 0–10000. "If not set, Jupiter automatically determines an appropriate slippage" (RTSE). |
| `referralAccount` + `referralFee` | 50–255 bps. Must be used together. |
| `payer` | Integrator gas sponsor. Must differ from `taker`. Disables Dflow and OKX. |
| `priorityFeeLamports` | Overrides the automatic priority fee. |
| `jitoTipLamports` | Jito tip. |
| `broadcastFeeType` | `maxCap` or `exactFee`. Ignored unless one of the two fee params above is set. |
| `excludeRouters` | Comma list from `metis,jupiterz,dflow,okx`. |
| `excludeDexes` | Metis only. Case-sensitive labels from `/program-id-to-label`. `/order` ignores `dexes`. |
| `maxSupportedTransactionVersion` | `"0"` (default) or `"1"`. "a ceiling, not a force": v1 only when Metis wins and the order is not gasless. |

Any optional parameter makes the response `mode: "manual"` instead of `"ultra"`.
`mode` "does not indicate which router was used" (JD/swap/order-and-execute.md).
Routing matrix from the same page: `receiver` and `payer` disable Dflow and OKX;
`excludeRouters=jupiterz` disables JupiterZ; referral params keep all four.

### Response fields (OpenAPI 200 schema, JD/api-reference/swap/order.md)

`mode`, `inputMint`, `outputMint`, `inAmount` (string), `outAmount` (string),
`inUsdValue`, `outUsdValue`, `priceImpact` (percentage points, e.g. -0.1 = -0.1%),
`swapUsdValue`, `otherAmountThreshold` ("Minimum output amount after slippage"),
`swapMode`, `slippageBps`, `priceImpactPct` (deprecated), `routePlan[]`
(`swapInfo{ammKey,label,inputMint,outputMint,inAmount,outAmount}`, `percent`,
`bps`, `usdValue`), `referralAccount`, `feeMint`, `feeBps`,
`platformFee{amount,feeBps,feeMint}`, `signatureFeeLamports`, `signatureFeePayer`,
`prioritizationFeeLamports` ("Includes priority fees and tips (Jito, Nozomi)"),
`prioritizationFeePayer`, `rentFeeLamports` ("Estimated rent fee"),
`rentFeePayer`, `swapType` ("Deprecated: use router instead"; enum `aggregator`,
`rfq`, `aggregator+rfq`, `dflow`, `okx`), `router` (`metis|jupiterz|dflow|okx`),
`transactionVersion` (0|1), `transaction`, `lastValidBlockHeight` (**string**),
`gasless` (bool), `requestId`, `totalTime`, `taker`, `quoteId` (RFQ), `maker`
(RFQ), `expireAt` (RFQ, string), `errorCode`, `errorMessage`, `error`
("Duplicate of errorMessage"). A 400 response has `{requestId, error}`.

- `transaction`: "Base64-encoded transaction. **Null** if taker is not provided.
  **Empty string** if taker is provided but transaction could not be built
  (check errorCode)." The transaction is unsigned and versioned (v0 by default).
  (JD/api-reference/swap/order.md, JD/swap/order-and-execute.md)
- `outAmount`: "Expected output amount before slippage."
  `otherAmountThreshold` is the slippage floor that the transaction enforces
  (INFERRED from "Minimum output amount after slippage").
- Expiry: "Aggregator routes (Metis, Dflow, OKX): `lastValidBlockHeight` in the
  response is the hard expiry." "RFQ routes (JupiterZ): `expireAt` is the quote
  expiry timestamp from the market maker. RFQ quotes are typically
  shorter-lived". (JD/swap/order-and-execute.md, "Transaction validity")
- Slippage: RTSE is applied at order time and "baked into the transaction".
  A fixed `slippageBps` overrides it. (JD/swap/advanced/slippage.md)
- `/order` error codes (only when `transaction == ""`). Match on `router` plus
  `errorCode`, never on the message. Aggregators (metis, dflow, okx): 1 =
  insufficient funds, 2 = insufficient SOL for gas, 3 = below the gasless
  minimum. JupiterZ: 1 = insufficient balance, 2 = missing associated token
  account, 3 = quote could not be built into a transaction.
  (JD/swap/order-and-execute.md)

Example from the docs, quote only (JD/swap/index.md):

```bash
curl "https://api.jup.ag/swap/v2/order?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000000"
```
```json
{ "router": "metis", "inAmount": "100000000", "outAmount": "11680143", "feeBps": 2, "transaction": null }
```

Observed in our own live fixtures (`tests/fixtures/live_20261120/`, quote-only,
no `taker`). Every response has `taker: null`, `slippageBps: 0`,
`otherAmountThreshold == outAmount` and all `*FeeLamports == 0`. There is no
`lastValidBlockHeight`, `expireAt` or `transactionVersion`. The responses also
contain `guaranteedPrice` and `jitOptimized`, which are **not in the OpenAPI
spec**. Code must not depend on them. `platformFee` came without `amount`. The
JupiterZ quote had `maker`, `quoteId` and `gasless: true`.

## 3. `POST /execute`

Request (JD/api-reference/swap/execute.md, JD/swap/order-and-execute.md):

```json
{ "signedTransaction": "<base64 signed tx>", "requestId": "<from /order>", "lastValidBlockHeight": "<optional string>" }
```

`lastValidBlockHeight` is described as "Optional block height for nonce validation".

Response 200: `status` (`"Success"|"Failed"`), `signature`, `slot` ("Confirmed
slot", string), `error` (present if Failed), `code`, `totalInputAmount`,
`totalOutputAmount`, `inputAmountResult`, `outputAmountResult`,
`swapEvents[]{inputMint,inputAmount,outputMint,outputAmount}`. 400:
`{error, code}`. **500: `{signature, error}`**, so a 500 can still carry a
signature.

- `signature`: "present on both success and some failures".
- Amounts: `totalInputAmount` is the amount deducted from the wallet, including
  the fee if `feeMint` is the input mint. `totalOutputAmount` is the amount
  credited to the wallet, after any fee in the output mint. The fee is
  `totalInputAmount - inputAmountResult` (fee in the input mint) or
  `outputAmountResult - totalOutputAmount` (fee in the output mint).
  Docs example: `outputAmountResult "2103"`, `totalOutputAmount "2101"`.
- What Jupiter does inside `/execute`: RTSE (at order time), its priority-fee
  strategy, "Jupiter Beam" landing over multiple RPC providers, "Confirmation
  polling", and parsing of both successful and failed transactions. "Only
  available for transactions obtained via `/order`." (JD/swap/order-and-execute.md, execute.md)
- `/execute` codes: `0` success. `-1` missing cached order ("requestId not found
  or expired"), `-2` invalid signed transaction, `-3` invalid message bytes.
  Aggregator: `-1000` failed to land, `-1001` unknown, `-1002` invalid
  transaction, `-1003` not fully signed, `-1004` invalid block height, `-1005`
  "Transaction expired before it landed (its blockhash expired, usually because
  it was signed too late)". RFQ: `-2000` failed to land, `-2001` unknown,
  `-2002` invalid payload, `-2003` quote expired, `-2004` swap rejected.
  (JD/swap/order-and-execute.md)

Idempotency and unknown outcomes:

- **UNCONFIRMED:** what `/execute` does if the same signed transaction or the
  same `requestId` is posted twice. The docs do not say. `-1` "Missing cached
  order (requestId not found or expired)" suggests the order cache is consumed
  or expires, but its lifetime is not documented.
- **UNCONFIRMED:** an HTTP timeout for `/execute`, or how long it blocks while
  "confirmation polling". Not documented. For comparison, the RFQ market-maker
  webhook side says "Swap requests have a 40-second timeout"
  (JD/swap/routing/rfq/v1/webhook-api, in JD/llms-full.txt). That is not a
  client-facing promise.
- There is **no documented status-lookup endpoint** for a `/execute` result. The
  docs only show the returned `signature` and a Solscan link.
- Chain level (primary, Solana): "The same signed transaction always produces
  the same signature—resubmitting is safe" (SD/tools/transaction-landing).
  The runtime rejects a transaction whose message hash is already in the status
  cache with `AlreadyProcessed` (SD/core/transactions/transaction-pipeline).
  The blockhash also serves for "Deduplication: prevents the same transaction
  from being processed twice" (SD/core/transactions/transaction-structure).
  So re-posting the **same signed bytes** cannot produce a second swap on chain.
  A **new** `/order` signed while the old transaction could still land can.
- The signature of a transaction is its **first** signature, which belongs to
  the **fee payer** at account index 0 (SD/core/transactions/transaction-structure).
  - When `signatureFeePayer == taker` (non-gasless), the transaction id equals
    the taker's own signature. It is known locally right after signing, before
    `/execute` (INFERRED).
  - When the order is gasless (Jupiter's gas wallet
    `gasTzr94Pmp4Gf8vknQnqxeYxdgwFjbgdJa4msYRpnB`, a JupiterZ maker, or a
    `payer`), the id is another party's signature. For JupiterZ the maker signs
    only during `/execute` (JD/swap/advanced/gasless.md), so **the transaction
    id cannot be known before `/execute` returns** (INFERRED). An `/execute`
    timeout on a JupiterZ route therefore leaves no signature to look up.

Design note (P3), not from docs:
1. Persist the intent: `requestId`, unsigned and signed bytes, the expected
   signature, `lastValidBlockHeight`/`expireAt`, and the decoded checks.
   Do this **before** the POST.
2. Accept only orders with `signatureFeePayer == taker` and `gasless == false`.
   That makes the txid computable locally. With `excludeRouters=jupiterz`, the
   docs call `signatureFeePayer == taker` "the most reliable check" for opting
   out of gasless (JD/swap/advanced/gasless.md). Cost: you lose JupiterZ quotes,
   which the docs say are "often 5-20bps better on major pairs" (JD/swap/index.md).
   This must be a stated trade-off.
3. On timeout, 5xx or a non-final answer, never call `/order` again. Poll your
   own RPC with `getSignatureStatuses([sig], {searchTransactionHistory: true})`.
   Only when a `finalized` block height is greater than `lastValidBlockHeight`
   and the status is still `null` is the order "expired, not landed". Then a new
   order may be considered. Optionally re-POST the identical bytes: on-chain
   dedup makes this safe, but what Jupiter returns is UNCONFIRMED.
4. Book a fill only from `getTransaction` (section 7): `meta.err == null` plus
   the pre/post token and lamport balances of the taker's accounts. Treat
   `/execute`'s amounts as a cross-check, not as the book of record.

## 4. Transaction contents, signers, ALTs, verification

- Format: a versioned transaction, v0 by default. v1 only if requested **and**
  Metis wins **and** the order is not gasless. Read `transactionVersion`.
  "Gasless orders are always v0." (JD/swap/advanced/transaction-versions.md)
  v0 uses Address Lookup Tables, so the verifier must resolve ALTs (section 7).
- Additional signers can be required:
  - JupiterZ: "The order transaction includes a secondary signer for the market
    maker". The taker partially signs, and the maker co-signs during `/execute`.
    Hence the docs use `partiallySignTransaction` (JD/swap/advanced/gasless.md,
    JD/swap/order-and-execute.md).
  - Automatic gasless: "The sponsor wallet `gasTzr94Pmp4Gf8vknQnqxeYxdgwFjbgdJa4msYRpnB`
    is added as a secondary signer" (JD/swap/advanced/gasless.md). Automatic
    gasless fires when the taker has < 0.01 SOL and the trade is at least about
    $10 ("dynamic"). It does not fire when `payer` or the referral params are set.
  - Integrator `payer`: signs when it is a required signer. "Match the payer by
    public key, not by position: the signer order differs between quotes."
  - Required signers are the first `header.numRequiredSignatures` static keys
    (code in JD/swap/advanced/gasless.md, matching SD/core/transactions/transaction-structure).
- Instructions beyond the swap: the docs state these for `/build`. The order is
  compute budget, then setup (always includes
  `createAssociatedTokenAccountIdempotent`, "even when the token accounts
  already exist"), the swap, cleanup (e.g. closing wSOL), other, and tip
  (JD/swap/build/common-instructions.md; JD/llms-full.txt, "Reduce Transaction
  Size"). For `/order` the transaction is pre-built, and **its exact instruction
  list is not documented (UNCONFIRMED)**. Expect ComputeBudget, ATA create
  idempotent, System/Token wSOL wrap and unwrap, the Jupiter v6 route, and
  possibly a Jito/Nozomi tip transfer (`prioritizationFeeLamports` "Includes
  priority fees and tips (Jito, Nozomi)").
- `/order` transactions cannot be modified: "JupiterZ market makers have
  last-look rights and the transaction cannot be modified" (JD/swap/index.md
  FAQ). The RFQ maker side rejects any byte change. Any client-side change
  breaks the order.
- Where the platform fee is collected: on `/build` the integrator fee "is added
  as part of the swap instruction" (JD/swap/build/index.md). For `/order`
  platform fees, **UNCONFIRMED** whether a separate transfer instruction exists.
- **No Jupiter doc describes verifying an `/order` transaction before signing.**
  The only adjacent guidance is "Validate the compute unit price before
  signing" on `/build` (JD/swap/advanced/compute-units.md). The RFQ maker side
  uses `validate_similar_fill_sanitized_message` in `jup-ag/rfq-webhook-toolkit`
  (JD/swap/routing/rfq/v1/settlement). That is a maker-side check, not a taker one.

Program IDs seen in Jupiter docs:

| Program | ID | Source |
|---|---|---|
| Jupiter v6 swap aggregator | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | JD/swap/routing/rfq/v2/streaming (in JD/llms-full.txt) |
| JupiterZ Order Engine (RFQ v1 settlement) | `61DFfeTKM7trxYcPQCM78bJ794ddZprZpAwAnLiwTpYH` | JD/swap/routing/rfq/v1/settlement |
| rfq_v2 fill program (CPI from v6) | `fd3nMFYTQjX1yr5ER8u7tPdHJB7qt8RpDpNtLQX2Br5` | JD/swap/routing/rfq/v2/streaming |
| Jupiter gas sponsor wallet (account, not a program) | `gasTzr94Pmp4Gf8vknQnqxeYxdgwFjbgdJa4msYRpnB` | JD/swap/advanced/gasless.md |
| Dflow and OKX router programs | **UNCONFIRMED**: not documented | — |

Design note, a pre-sign verifier for v0, defaulting to reject:
- The version byte is `0x80`. Reject `0x81` (v1) and legacy unless they are deliberately supported.
- `numRequiredSignatures == 1`, and static key 0 is the taker. This rejects gasless and RFQ routes.
- Every top-level `program_id_index` points to an allowlisted program: ComputeBudget, System, Token, Token-2022 (only if a mint uses it), ATA, Jupiter v6, and possibly a known tip program/transfer.
- Decode ComputeBudget `SetComputeUnitPrice` (discriminator `3`, u64 LE micro-lamports, per JD/swap/advanced/compute-units.md) and `SetComputeUnitLimit`. Cap price × limit.
- Any System `Transfer` from the taker goes only to the taker's own wSOL ATA, or to an allowlisted tip account with a capped amount.
- The taker's input/output ATAs are derived by the ATA program for the allowlisted mints.
- Resolve every ALT through RPC and rebuild the full account list.
- Simulate with `simulateTransaction` and check the taker's token deltas against `inAmount` and `otherAmountThreshold`. `routePlan[].swapInfo.inputMint/outputMint` must be within the allowlist.
- The Jupiter v6 instruction data is not decoded here (its IDL is not in the docs). Rely on simulation plus balance deltas for the amount checks.

## 5. Fees

- Platform fee on `/order` by pair: buying JUP/JLP/jupSOL from SOL/stables 0;
  pegged (LST-LST, stable-stable) 0; **SOL-Stable 2 bps**; LST-Stable 5;
  everything else 10; tokens < 24 h old 50 (JD/swap/order-and-execute.md, "Fees").
- "This fee is included in the quote and deducted automatically." Top-level
  `feeBps` is the total fee, including gasless recoup. `platformFee.feeBps` is
  Jupiter's share only. Example: 5 + 7 gasless gives `feeBps: 12`.
- Fee-mint priority: SOL, stablecoins, LSTs, bluechips, others. So for
  SOL/USDC the fee is collected in SOL, whichever side it is on. Our fixtures
  match this: `feeMint` = SOL in both directions.
- `outAmount` is net of the platform fee: "included in the quote and deducted
  automatically" (docs). Our metis fixtures show the arithmetic (see
  `DATA_SOURCES.md`).
- `/build` has "no Jupiter swap fee" (JD/swap/index.md).
- Referral: Jupiter keeps 20% of the integrator fee (50–255 bps), and no
  separate platform fee applies. If the `referralTokenAccount` for the fee mint
  is not initialised, the order executes without your fee.
- Router-specific fees (JupiterZ maker spread, Dflow, OKX): **UNCONFIRMED**.
  Nothing is documented beyond "the fee is in `feeBps`". Our JupiterZ fixture
  shows `guaranteedPrice: true`, but that field is undocumented.
- Network fees: a base fee of **5,000 lamports per signature**
  (`lamports_per_signature`, SD/core/constants-reference), plus a priority fee
  of CU price × CU limit (v0). Who pays: the `signatureFeePayer`,
  `prioritizationFeePayer` and `rentFeePayer` fields. In automatic gasless mode,
  Jupiter pays the gas and "increases the swap fee. The taker receives less
  output tokens". In JupiterZ mode the maker pays the signature and priority
  fees, and Jupiter's gas wallet can pay output-ATA rent
  (JD/swap/advanced/gasless.md).
- Without `taker`, all `*FeeLamports` fields are 0 (our fixtures). Real network
  costs only appear with a `taker` (INFERRED, consistent with DATA_SOURCES.md).

## 6. Naming, deprecation, sizes

- Swap API V2 (`api.jup.ag/swap/v2`) unifies Ultra and Metis. It launched in
  March 2026 (changelog 2026-03, via WebFetch summary). "Ultra and Metis APIs
  remain available". There is no retirement date (same source).
- Ultra to V2: base URL `https://ultra-api.jup.ag` becomes
  `https://api.jup.ag/swap/v2`, with the same `/order` and `/execute`. "The
  request parameters and response format are identical."
  (JD/swap/migration/ultra-to-order.md)
- Metis V1: `/swap/v1/quote` + `/swap/v1/swap` move to `/order` + `/execute`,
  or `/swap-instructions` moves to `/build`. Route plans report `bps` instead
  of `percent`, and "V2 instructions no longer emit fee events" (JD/swap/index.md FAQ).
- Deprecated fields: `swapType` and `priceImpactPct` (OpenAPI).
- `lite-api.jup.ag` is "progressively deprecated" (JD/portal/migration.md).
  The changelog lists "Quote V6" legacy endpoints sunset 2025-08 (changelog
  index, WebFetch summary, not verbatim).
- Transaction v1 (changelog 2026-10-08): opt-in. "v0 remains the default and is
  not deprecated" (WebFetch summary).
- Sizes: the only documented minimum is the gasless one (about $10, "dynamic";
  `errorCode` 3). `/build` has `maxAccounts` (default 64). **No general min/max
  order size for `/order` is documented (UNCONFIRMED).**
- The legal docs still use the old names. The SDK & API License Agreement §2.3
  requires labelling "Jupiter Ultra" or "Metis". The docs' legal "Labelling"
  table lists only "Self-Hosted Metis Swap API binary → Metis". Which label
  applies to `/swap/v2/order` is **UNCONFIRMED**.

## 7. Solana

### Wire format (SD/core/transactions/transaction-structure, SD/core/transactions/versioned-transactions)

- Transaction = `signatures` (compact-u16 count + N×64-byte Ed25519) + `message`.
  Max serialized size **1,232 bytes** for legacy and v0 (`PACKET_DATA_SIZE`),
  and 4,096 bytes for v1.
- Legacy message: `header` (3×u8: `num_required_signatures`,
  `num_readonly_signed_accounts`, `num_readonly_unsigned_accounts`), then
  `account_keys` (compact-u16 + N×32), `recent_blockhash` (32 bytes), and
  `instructions` (compact-u16 + each `program_id_index` u8, compact-u16 account
  indexes (u8 each), compact-u16 data length + data). Key order: signer+writable,
  signer+readonly, non-signer+writable, non-signer+readonly.
- **v0**: "a legacy message plus two things: a `0x80` version prefix byte and an
  `address_table_lookups` array appended after the instructions". Each lookup is
  `account_key` (32), `writable_indexes` (compact-u16 + N×u8) and
  `readonly_indexes` (compact-u16 + N×u8). The full key list is the static keys,
  then all ALT writable addresses, then all ALT readonly addresses ("writable
  lookups come before read-only lookups"). ALT-loaded accounts are never
  signers. An ALT holds at most 256 addresses.
- **v1** (active on mainnet per the docs): `0x81` prefix, a fixed-width layout,
  a config bitmask for CU limit, loaded-data limit and priority fee (**total
  lamports**, not a price), **no ALTs**, and **signatures at the tail**. CU
  limit and data-size limit default to **0** if unset. Readers must pass
  `maxSupportedTransactionVersion: 1` (the integer) to `getTransaction` and
  `getBlock`. Otherwise they fail with `-32015`.
- Fee payer = the first signer (index 0). The first signature is the
  transaction id.
- Legacy: https://solana.com/docs/core/transactions/transaction-structure.
  Versions: https://solana.com/docs/core/transactions/versioned-transactions.
  Source commit `82d49aed` (2026-11-20).

### Address lookup tables via RPC

- There is **no `getAddressLookupTable` JSON-RPC method**. It is a client-SDK
  helper (web3.js `connection.getAddressLookupTable`) built on `getAccountInfo`
  (INFERRED: no such page in the RPC method list; method listing read from the
  docs source tree).
- Use `getAccountInfo(<ALT address>, {encoding: "base64", commitment: "confirmed"})`
  (SD/rpc/http/getaccountinfo; `base64` is "Recommended"). Check that `owner` ==
  `AddressLookupTab1e1111111111111111111111111`.
- Account data layout, from the program source
  `solana-program/address-lookup-table` `program/src/state.rs` (main, read
  2026-11-20): `LOOKUP_TABLE_META_SIZE = 56`, then raw 32-byte addresses. The
  meta is a bincode `ProgramState::LookupTable(LookupTableMeta{deactivation_slot:
  u64, last_extended_slot: u64, last_extended_slot_start_index: u8, authority:
  Option<Pubkey>, _padding: u16})`. That is a u32 enum tag (1 = LookupTable),
  then 8+8+1+(1+32)+2 bytes = 56 (INFERRED from bincode rules).
  `LOOKUP_TABLE_MAX_ADDRESSES = 256`. "Address tables may only be used to lookup
  addresses that were extended before the current bank's slot."
- The program's only instructions are `CreateLookupTable`, `FreezeLookupTable`,
  `ExtendLookupTable`, `DeactivateLookupTable` and `CloseLookupTable`
  (`program/src/instruction.rs`). No instruction overwrites an existing entry,
  so entries at an index are append-only (INFERRED). A table can still be
  deactivated or closed between verification and landing, which would fail the
  transaction, not redirect it.

### RPC methods

- `getSignatureStatuses([sigs≤256], {searchTransactionHistory})`. Without
  `searchTransactionHistory: true`, "this method only searches the recent status
  cache". Each element is `null` or `{slot, confirmations, err, status
  (deprecated), confirmationStatus: processed|confirmed|finalized}`. `err` is an
  object such as `{"InstructionError":[idx, err]}`.
  https://solana.com/docs/rpc/http/getsignaturestatuses
- `getTransaction(sig, {commitment: confirmed|finalized (not processed),
  maxSupportedTransactionVersion: 0|1, encoding})`. "If you omit this parameter,
  only legacy transactions will be returned—any versioned transaction will
  result in an error." It returns `null` if not found. `meta` has `err`, `fee`,
  `preBalances`/`postBalances` (lamports, indexed to `accountKeys`),
  `preTokenBalances`/`postTokenBalances`, `logMessages`, `innerInstructions`,
  and `loadedAddresses{writable,readonly}`.
  https://solana.com/docs/rpc/http/gettransaction
- `getBlockHeight({commitment})` returns a u64. The default commitment is
  `finalized`. https://solana.com/docs/rpc/http/getblockheight
- Commitment levels: `processed` ("can still be rolled back"), `confirmed`
  (">two-thirds of the network's active stake" voted), `finalized` ("maximum
  lockout"). If omitted, it is "typically `finalized`". https://solana.com/docs/rpc
- Blockhash expiry: `MAX_PROCESSING_AGE` = **150 slots**
  (SD/core/constants-reference, SD/core/transactions/transaction-pipeline).
  "Transaction blockhashes remain valid for 150 slots (roughly 30 seconds at
  200ms slot times) … Use lastValidBlockHeight to determine when a blockhash has
  expired." (https://solana.com/docs/tools/transaction-landing)

### Program IDs

| Program | ID | Source |
|---|---|---|
| System | `11111111111111111111111111111111` | SD/core/programs/builtin-programs |
| Compute Budget | `ComputeBudget111111111111111111111111111111` | same |
| Address Lookup Table | `AddressLookupTab1e1111111111111111111111111` | same |
| SPL Token | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` | `solana-program/token` README + `declare_id!`; also SD/core/accounts/account-types |
| Token-2022 | `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` | `solana-program/token-2022` `declare_id!` (raw.githubusercontent.com, main) |
| Associated Token Account | `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL` | `solana-program/associated-token-account` `declare_id!` |
| Jupiter v6 aggregator | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | Jupiter docs (section 4) |
| Mints used here | SOL (wSOL) `So11111111111111111111111111111111111111112`, USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | Jupiter docs examples (JD/swap/order-and-execute.md) |

## 8. Public mainnet RPC

- The official docs now list **`https://api.mainnet.solana.com`** for mainnet
  (SD/references/clusters, SD/rpc). `api.mainnet-beta.solana.com` is no longer
  mentioned in those pages. Both hostnames answered `getBlockHeight` identically
  on 2026-11-20 at 19:18 UTC (one call each from this machine).
- Documented mainnet limits: 100 requests / 10 s / IP; 40 / 10 s / IP for a
  single RPC method; 40 concurrent connections / IP; 40 connections / 10 s / IP;
  100 MB / 30 s. "Public endpoint rate limits are subject to change."
  (https://solana.com/docs/references/clusters)
- Live response headers (2026-11-20) showed `x-ratelimit-tier: free`,
  `x-ratelimit-method-limit: 50`, `x-ratelimit-rps-limit: 250`,
  `x-ratelimit-conn-limit: 40`, `x-ratelimit-connrate-limit: 40` and
  `x-ratelimit-pubsub-limit: 5`. The window for these numbers is not stated.
  They differ from the doc table, so **the actual limits are UNCONFIRMED**.
- Suitability: "The public RPC endpoints are not intended for production
  applications. … rate limits may change without prior notice. Likewise,
  high-traffic websites may be blocked without prior notice." A 403 means the IP
  is blocked, and a 429 means it is rate limited (use `Retry-After`).
  "Never use public RPC for production" (SD/tools/transaction-landing).
- Terms: the solana.com Terms of Service (Solana Foundation, Zug; source file
  last changed 2026-01-30) cover "the www.solana.com website" and related
  services. They prohibit "any automated use of the system … data mining,
  robots" and use "in connection with any commercial endeavors except those …
  approved by us". Whether those terms cover the public RPC hosts is
  **UNCONFIRMED**. The clusters page links no separate RPC terms.
- Design note: polling a handful of signatures every 1–2 s fits within the
  documented limits. Because the endpoint can block or change without notice,
  it is a weak dependency for the "unknown outcome" path, which is exactly the
  path that must not fail. Plan for a second, independent RPC (a provider key,
  which is a user decision) before going live.

## 9–11. Terms of use (summary; see DATA_SOURCES.md for the Danish version)

### Jupiter

Documents (from GitHub `jup-ag/docs` `static/files/legal` file names, read
2026-11-20): "SDK & API License Agreement" dated **16 October 2025**, "Terms of
Use" dated **21 January 2025**, "Privacy Policy" dated 4 May 2024. Web
versions: JD/legal/sdk-api-license-agreement.md, JD/legal/terms-of-use.md.
The agreement incorporates the Terms of Use and prevails on conflict.

API agreement points relevant to this bot (quoted section numbers):

- §2.1 grants a "limited, non-exclusive, **fee-bearing**, non-transferable,
  non-sublicensable licence … solely for the purpose of Licensee's internal
  development efforts to develop products or services integrating the API …
  including … informational, comparison, or testing purpose".
- §3.2(d) forbids "sell, lease, share, transfer or sublicense the API, SDK or
  **any content obtained through the API** … to any third party".
- §3.2(e) forbids usage that "exceeds reasonable request volume" as Jupiter
  determines.
- §3.2(f) forbids "access the API or SDK for competitive analysis or
  **disseminate performance information** (including uptime, response time
  and/or benchmarks)".
- §3.2(g) forbids "use the API in conjunction with, or **combine content from the
  API with, content obtained through scraping or any other means outside the
  API**". **Red flag:** read literally, this covers journaling Jupiter quotes
  next to Binance klines and comparing them, which is the research design. Ask
  Jupiter for written consent (§2.4: info@jup.ag) before relying on it.
- §3.2(i) forbids "copy … download … the Documentation … through automated or
  other means". This session fetched docs pages as `.md` with curl. Jupiter
  publishes `.md` and `llms.txt` explicitly for agents, but the clause is broad.
  Copies were kept only in the session scratchpad.
- §5.1: "The Licensee may only access the API with the Keys issued to the
  Licensee". This sits in tension with documented keyless access.
- §6/§13.1 mention subscription fees and "a minimum term of 30 days … paid for
  in advance". The free tier exists in the portal, so this is ambiguous.
- §2.3 and §8.4 require labelling ("Jupiter Ultra"/"Metis", "Powered by
  Jupiter") visible to end users of a product.
- §7.3: the licensee must comply with all laws (licensing, KYC/AML, sanctions)
  and screen wallets.
- §8.2 is a non-disparagement clause. §13.5 gives Jupiter audit rights.
- §14: Panama law, arbitration, class-action waiver.

Terms of Use (Interface; operator named as Block Raccoon S.A.):

- §1 "Prohibited Localities": "Jupiter does not interact with digital wallets
  located in, established in, or a resident of the United States, the Republic
  of China, Singapore, Myanmar (Burma), Cote D'Ivoire (Ivory Coast), Cuba,
  Crimea and Sevastopol, Democratic Republic of Congo, Iran, Iraq, Libya, Mali,
  Nicaragua, Democratic People's Republic of Korea (North Korea), Somalia,
  Sudan, Syria, Yemen, Zimbabwe or any other state, country or region that is
  subject to sanctions enforced by the United States, the United Kingdom or the
  European Union." **Denmark and the EU are not listed.**
- No VPN or IP disguising ("Disguises or interferes in any way with the IP
  address"). No market manipulation ("spoofing and wash trading"). Taxes are
  the user's responsibility. Possible KYC/AML requests. Jupiter may geo-limit
  access at any time.
- No clause in either document explicitly allows or forbids automated or bot
  trading. The docs market the API to "trading bots and AI agents"
  (JD/swap/index.md).
- Whether Danish/EU rules (MiCA) restrict self-directed DeFi use by a private
  person is a legal question that was **not researched (UNCONFIRMED; not legal
  advice)**.

### Binance (public klines)

- Read from official API docs (GitHub `binance/binance-spot-api-docs`,
  `rest-api.md`, head `473c101d` 2026-11-18; mirrors developers.binance.com):
  - `GET /api/v3/klines` has weight 2 and `limit` default 500, max 1000.
  - For public market data "please use the base endpoint
    **https://data-api.binance.vision**", which needs no key
    (developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only,
    "Last modified: November 20, 2026", via WebFetch).
  - 429 means a rate limit was hit. 418 means an automated IP ban; bans
    "scale in duration … from 2 minutes to 3 days". 403 means a WAF block.
    `Retry-After` is in seconds.
  - The `REQUEST_WEIGHT` 6000/min figure is the docs' `exchangeInfo` example.
    The live `exchangeInfo.rateLimits` is authoritative.
- **UNCONFIRMED:** the Binance Terms of Use (https://www.binance.com/en/terms)
  and the prohibited-country list
  (https://www.binance.com/en/legal/list-of-prohibited-countries). Both pages
  are rendered client-side behind a bot check (HTTP 202 challenge), and no text
  could be read. Search snippets only: the list was "Updated: 27 February
  2024", and a Binance Square copy lists Canada, Cuba, Crimea and
  non-government-controlled Ukraine, Iran, Netherlands, North Korea, Syria, and
  USA and territories. **Denmark was not in that copy**, but the live list is
  unverified.
- **UNCONFIRMED (search snippet only):** the Binance Vision terms
  (`data.binance.vision/Binance_Vision-Terms_of_Use.pdf`) reportedly require a
  written enterprise licence for commercial use of the *historical datasets*.
  They reportedly also bar using them for live trading execution or automated
  order generation. Whether they cover `data-api.binance.vision` or
  `api.binance.com` responses is unknown. The PDF could not be fetched because
  local DNS resolves `*.binance.vision` to 0.0.0.0.
- **UNCONFIRMED / red flag (secondary sources only):** news reports say Binance
  has no MiCA authorisation after the EU transition ended on 1 July 2026, and
  that EU regulators question its service to EU users. A Danish guide says
  Binance was not in Finanstilsynet's register on 24 September 2026. This is
  relevant only if an account is used. Public market data needs no account,
  but Binance's terms may still define API use as a "Binance Service".

### GitHub (private repo)

Source: GitHub Terms of Service, "Effective date: April 27, 2026" (raw
`github/docs` `content/site-policy/github-terms/github-terms-of-service.md`,
main), and the Acceptable Use Policies (same repo).

- §E: private repo content is confidential. GitHub staff access it only for
  security, automated scanning for vulnerabilities, malware or ToS-violating
  content, support, service integrity, or legal obligations. It may be
  "compelled by law" to disclose. If private repo content is given as Input to
  AI Features, it may be used for training (opt-out per §J.3).
- §H API terms: excessive use can suspend API access. Tokens may not be shared
  to exceed rate limits.
- AUP: no "excessive automated bulk activity" or "undue burden on our servers
  through automated means". Cryptocurrency mining is explicitly listed. Hourly
  polling of a releases Atom feed is light, but GitHub's limits for anonymous
  feeds remain unknown.
- §B.3: accounts must belong to a human. Machine accounts are allowed under a
  human. Use is subject to US export and sanctions rules.
- Design note: never commit keys or wallet material (see also Jupiter §5.1 key
  secrecy). Repo privacy also bears on Jupiter §3.2(d). Committed Jupiter
  responses (`tests/fixtures/live_20261120/`) must not become public.

---

## UNCONFIRMED items (consolidated)

1. `/execute` behaviour on a duplicate signed transaction or duplicate `requestId`, and the order-cache TTL behind code `-1`.
2. The `/execute` server-side timeout and how long it blocks. There is no status-by-signature or status-by-`requestId` endpoint.
3. Exact instruction list of an `/order` transaction: tip transfers, separate fee transfer, ATA creation, wSOL wrap.
4. Program IDs of the Dflow and OKX routers, and which top-level programs their transactions use.
5. Router-specific fees beyond `feeBps` (JupiterZ maker spread, Dflow, OKX). The meaning of the undocumented `guaranteedPrice` and `jitOptimized`.
6. A general minimum or maximum order size for `/order` (only the gasless ~$10 minimum is documented).
7. That the JupiterZ transaction id is the maker's signature and unknown before `/execute` (INFERRED from fee-payer = first signature + "MM signs during /execute").
8. Which label (§2.3 "Jupiter Ultra" vs "Metis") applies to `/swap/v2/order`. How keyless use squares with §5.1 ("only … with the Keys") and the "fee-bearing"/30-day-prepaid clauses.
9. Whether §3.2(g) (combining API content with outside data) and §3.2(f) (benchmarks) are meant to cover private research that journals Jupiter quotes alongside Binance klines.
10. Actual public-RPC limits: the documented table and the live headers differ. Whether the solana.com ToS cover the RPC hosts.
11. Binance Terms of Use text, the current prohibited-country list, the Binance Vision terms, and Binance's status in Denmark/EU under MiCA.
12. The legal position of a Denmark-based individual running a self-custodial trading bot under MiCA or Danish law (not researched; not legal advice).

## Open risks for execution (P3)

- **Unknown outcome after `/execute` timeout or 5xx.** Mitigation: use only
  non-gasless, taker-fee-payer orders so the signature is known. Persist the
  signed bytes and the signature before the POST. Resolve through your own RPC
  plus `lastValidBlockHeight`. Never call `/order` again while the old
  transaction can still land.
- **Gasless can fire without asking.** Automatic sponsorship applies when the
  taker has < 0.01 SOL on trades ≥ ~$10, and it raises `feeBps`. Mitigation:
  keep the SOL balance ≥ 0.01 plus fees, and reject when
  `signatureFeePayer != taker`.
- **No official pre-sign verification spec.** We must decode v0 and resolve ALTs
  ourselves, and default to reject (section 4).
- **v1 transactions.** Never pass `maxSupportedTransactionVersion=1` unless the
  verifier supports `0x81`. Pass `maxSupportedTransactionVersion: 1` on
  `getTransaction` anyway, so reading never fails on a v1 transaction.
- **Slippage set by RTSE.** `otherAmountThreshold` is the only hard floor. Check
  it against our own limit before signing, or pass a fixed `slippageBps` (which
  makes `mode: manual`).
- **Priority fee is chosen by Jupiter.** Cap it from the ComputeBudget
  instructions. `prioritizationFeeLamports` can include Jito/Nozomi tips.
- **Public RPC** is not meant for production and can block without notice. It
  is a single point of failure for confirmation.
- **Terms risk:** Jupiter §3.2(f)/(g)/(d) against the research design and data
  sharing. Binance terms are unread.
- **API drift:** responses carry undocumented fields, and `swapType` is
  deprecated. Keep the strict, reject-on-unknown parsing as in `core.Quote.parse`.
