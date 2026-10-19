# Handover: Copybot session moves to the Linux PC (2026-10-19)

Read this first. It replaces the context of the Windows desktop session that ran 2026-10-16..19. This directory
(`copybot/handover/`) lives only on branch `claude/a8-wip` and is removed before that branch is merged.

## 1. Standing rules (from the user; never relax them)

- **Linux PC `HP-USDT` is the only runtime and test host.** The live lab is `~/ecommerence/copybot` on branch
  `claude/why-cant-we-do-this-wh3ohb`. It is production: never edit, test in, or check out other commits in it.
  Develop in a separate worktree or clone; test in throwaway worktrees
  (`git -C ~/ecommerence worktree add -q --detach ~/t-<name> <commit>`; remove it afterwards).
- **Deploy** only after the full suite is green at the exact commit:
  1. push to `claude/why-cant-we-do-this-wh3ohb`;
  2. in `~/ecommerence`: `git pull --ff-only`;
  3. `cd copybot && python3 -m lab stop --reason "deploy <hash>: ..."`;
  4. wait for the fleet and `START_LAB.sh` to exit;
  5. `setsid nohup ./START_LAB.sh >> data/lab/start.log 2>&1 < /dev/null &`;
  6. if `lab/watch.py` changed, restart the watcher: kill its pid (find it by cwd), then
     `setsid nohup ./START_WATCH.sh >> data/lab/watch.log 2>&1 < /dev/null &`;
  7. verify processes (by cwd), events and the dashboard.
- **Extend the existing system** (fleet agents, `lab/jobs.py`, `lab/pipeline.py`, gates, paper engine, Mars
  dashboard). No parallel pipeline and no dashboard redesign. Never weaken, bypass or rewrite a gate (S7, protocols,
  holdout, frozen parameters, hashes).
- **Protocol changes** need a dated amendment in `research/PROTOCOL_V3.md`, written, approved by the user and
  committed before any code. Never change thresholds, windows or dates to get better results.
- **The user types every human step themselves**, in a real terminal: family approvals (`approve-family`,
  `confirm-family`), revivals (`lab approve ... DISCOVERED` + `lab confirm`), holdout approvals and S7.
  The code refuses these when `CLAUDECODE` is set, so never try to work around that.
- Paper trading only: no real money, no live orders, no autostart, cron or timers, and no S7 bypass.
- Never run sudo or change system, network or security settings; the user does that.
- Never show or commit credentials (`config.local.json`, the Helius key).
- The pm_lp collector (`python3 -u -m research.pm_lp collect --approved`, pid in `ps`) is external. Never touch it.
- On a critical error or protocol conflict: stop that action and report it.
- Report truthfully: no fake successes and no invented numbers. Unverifiable checks are reported as unresolved.
- The user writes Danish; answer in Danish.

## 2. Dates that gate work

| Date (UTC) | What |
| --- | --- |
| 2026-10-24 00:00 | Amendment 9: last moment to fetch family spot files (train3/validation3) for an approved family |
| 2026-10-24..11-27 | pm_lp critical window: no non-critical deploys and no new network load; family downloads blocked until 11-28 |
| 2026-10-25 ~06:40 | S7 earliest opening if there is no incident (human decision; no autostart) |
| 2026-10-31..11-13 | pm_lp holdout |
| 2026-11-01..2027-04-30 | Amendment 7 forward-test window (10 FWD_ ledgers, live since 2026-10-18 20:15) |
| 2027-05-07 | MVRV forward verdict (cohort fwd202611, N=1) and FWD archive replay |

## 3. Live state at handover (deployed `20347cb`, 2026-10-18 22:57 UTC)

- Amendment 9 is live. The full suite at `20347cb` passed: 431 tests OK, 1 skipped.
  - Funding is booked in simulated paper ledgers from T_F = 2026-10-18 22:58:11 UTC (`paper.funding_started`).
    The 00:00 UTC settlement should be booked after 01:00 UTC in `sim_funding`. **Not yet verified.**
  - The balance overview reconciles: 34/34 checks, and `/api/balance` matches. At 22:58 UTC:

    | Block | Capital | Equity | P&L |
    | --- | --- | --- | --- |
    | Formal (shadow only) | 10 000 | 9 964.40 | −35.60 |
    | Forward (10 ledgers, 39 positions) | 100 000 | 100 178.87 | +178.87 |
    | Combined (simulated) | 110 000 | 110 143.27 | +143.27 |

    Fees and slippage are included. Funding is not in these numbers yet; T_F came after the mark.
  - `scan_digest|2026-10-17` ran in report-1:
    - 72 series, 247 observations;
    - 71 NO_ACTION, each with a reason;
    - 1 INVESTIGATE: `pricing_constraint/2|perp_premium|BRUSDT`, 6 clock hours, median 9.5x the 0.09 % cost reference.
      It is advisory only. The next step would be a family draft that the user approves.
    - Dossiers come only from scanner `market.event` INVESTIGATE decisions; so far there are only 3 NO_ACTION.
- Re-check everything with `python3 copybot/handover/verify_balance.py`, run from `~/ecommerence/copybot`. It is read-only
  and works on a backup copy of the live database.

## 4. Work in progress: amendment 8 phases A3-A6 (families, F1 fcarry)

- **Branch `claude/a8-wip`:**
  - `20106bc`: the A3-A6 code merged onto `20347cb`. It is not deployed.
  - The verifier-findings fix commit, when the Windows session has pushed it.
- Each phase passed the full suite on its own (472 tests at A6). Three adversarial verifiers then found 16 real
  problems. They are in `A8_VERIFIER_FINDINGS.txt`, with their attack tests in `vf8_attack.py`. The 3 high ones:
  - a forged spec version registers under a family approval;
  - `lab result` plus `lab transition` writes a fake PASS that closes the family;
  - approving before all revivals strands base instances.
- A fix workflow ran on Windows with 3 sequential groups and 2 reviewers:
  - group 1, registration integrity, is done;
  - group 2 (results, paper, alpha budget) and group 3 (robustness, survivorship, `runnable_any`) are in progress.

  The fixes were written **without running tests**, because Linux was unreachable. The Windows session will push
  the cumulative fix as one commit on `claude/a8-wip`, then stop working on this branch.
- **Remaining, in this order:**
  1. In a throwaway worktree at the tip of `claude/a8-wip`, run the targeted modules (`test_lab_families`,
     `test_lab_pipeline`, `test_lab_v3`, `test_lab_promotion`, `test_lab_forward`, `test_lab_paper_runner`,
     `test_lab_command`, `test_lab_jobs`, `test_lab_job_robustness`, `test_lab_step1`, `test_lab_scanresearch`,
     `test_lab_paper_funding`). Then run the FULL suite:
     `COPYBOT_WATCH_NOTIFY=0 python3 -m unittest discover -s tests` under nohup with an exit file, about 7 minutes.
  2. Adapt `vf8_attack.py` so every attack must now be refused, then run it. Every finding must be closed.
  3. Run a fresh adversarial review against the protocol (amendments 7-9 and design `research/AENDRING8_DESIGN.md`).
  4. Merge into `claude/why-cant-we-do-this-wh3ohb` without the `handover/` directory. Deploy **before 2026-10-24
     00:00 UTC**, and restart the watcher if `watch.py` changed.
  5. Give the user the exact terminal commands. The user types them; you never do.
     - 4 revivals: each is SUPPRESSED -> DISCOVERED via `python3 -m lab approve <E_fcarry__...> DISCOVERED --reason ...`
       then `python3 -m lab confirm <code>`. The reason acknowledges graveyard L13 and why the instance is
       materially different.
     - Then `python3 -m lab approve-family fcarry --reason ...` and `python3 -m lab confirm-family`.
     - Revival comes **before** approve-family (amendment 8 point 6).
  6. The fleet registers the base batch and fetches about 720 spot files (2 at a time) before 10-24, then screens.
     Verify live: jobs, verdicts, alpha_ledger, and that the catalogue, MVRV and FWD ledgers are unchanged.
- **Open decisions for the user.** Report them; do not decide them alone.
  - Amendment 8 point 18 pins only the family file and its module after registration. The engine code (pipeline,
    backtest) is recorded but not pinned. A stricter pin needs a dated amendment and would fail every later step
    after the first engine commit.
  - The placebo test is weak for low-turnover family rules: block shuffling raises turnover 17-52x. This is not a
    gate change; it is a proposal for a later amendment, such as turnover-matched placebos.
  - Holdout attribution is only recorded, not gated, because point 16 adds no holdout gate.
- **Later:**
  - amendment 11 (decisional edge decay) before the first PAPER_TRADING;
  - the remaining step-1 audit items: paper marks under hold or FAIL_CLOSED, G5.2.

## 5. Useful facts

- Fleet: supervisor plus 16 agents; job queue with leases, dependencies and `HEAVY_SLOTS=2`. Dashboard and web on port
  8770 (`python3 -m lab web --port 8770`); watcher `python3 -m lab watch --port 8770`.
- Registry: append-only, hash-chained SQLite `data/lab/lab.db` (WAL). Read the live database only with
  `file:...?mode=ro` or a backup-API copy.
- Protocol: `research/PROTOCOL_V3.md`, amendments 1-9 plus the 2026-10-19 clarification of amendment 9.
  Family files are in `research/families/`.
