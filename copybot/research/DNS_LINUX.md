# DNS on the Linux lab host: diagnosis and remediation plan (2026-10-18)

Host `HP-USDT` (192.168.1.108). Measured from the host itself, unprivileged. No system setting was changed.

## Diagnosis

`/etc/resolv.conf` is written by NetworkManager from DHCP on "Wired connection 1". There are no static DNS servers
and no `dns-options`. The servers, in order: `192.168.1.3`, `8.8.8.8`, `185.222.222.222`, `9.9.9.9`.
- glibc uses only the first three (MAXNS = 3). 9.9.9.9 is never asked.
- There is no local DNS cache (systemd-resolved is inactive).

**Raw UDP queries, 120 per cell** (`research/dns_diag.py`, run 12:4x UTC; read-only):

| Resolver | A lost | AAAA lost | A+AAAA on one socket lost | Median |
|---|---|---|---|---|
| 192.168.1.3 | 5/120 | 6/120 | 12/120 | 1–3 ms |
| 8.8.8.8 | 0 | 0 | 0 | 20 ms |
| 185.222.222.222 | 0 | 0 | 0 | 17 ms |
| 9.9.9.9 (not used by glibc) | 0 | 0 | 0 | 15 ms |

- 192.168.1.3 answers ping with 0/20 lost packets and refuses CHAOS queries.
- It is not the gateway (192.168.1.1), so it is probably a separate filtering DNS on the LAN.

**System resolver (glibc getaddrinfo, 120 lookups each):**

| `RES_OPTIONS` | Family | Lookups > 0.9 s | p95 | Total |
|---|---|---|---|---|
| (none, as today) | AF_UNSPEC | 11 | 5.04 s | 56.2 s |
| `single-request` | AF_UNSPEC | 11 | 5.05 s | 56.9 s |
| `timeout:1 attempts:2` | AF_UNSPEC | 11 | 1.02 s | 11.9 s |
| `single-request timeout:1 attempts:2` | AF_INET | 5 | 6 ms | 5.6 s |

- About 9 % of lookups lose their first query to 192.168.1.3 and wait for glibc's timeout before the next server
  answers.
- `single-request` does not help: the loss is plain loss, not a parallel A/AAAA problem.
- `timeout:1` cuts each stall from 5 s to 1 s.

**Effect on the lab:**

- **pm_lp collector.** Before its in-process DNS cache (PM_LP_SPEC amendment 4) only about 55 % of minutes had a
  snapshot. Since then: 50 rounds in 51 minutes, spacings 60–63 s.
- **paper-1, live passes on 2026-10-18.**
  - These are intervals between completed passes minus the 60 s wait. 113 intervals have no fleet restart inside;
    4 that span a restart are excluded, among them the 425.7 s first reported here by mistake.
  - Median 19.4 s, p90 45.9 s, maximum 148.8 s. 21 of the 113 took 30 s or more.
  - A controlled fetch of the shadow strategy's 16 symbols took 15.4–17.7 s, with or without `timeout:1`.
  - None of those 3 + 3 runs hit a 5 s stall.
  - The slow tail fits intermittent stalls but was **not** reproduced in the controlled test. The effect on paper-1
    is plausible, not proven.
  - From the commit that adds this file, the fleet logs each pass's duration (`seconds` in `periodic.done`), so it can be measured
    directly.

## Remediation plan (smallest first)

1. **Done, no privileges, per process.**
   - `START_LAB.sh`, `START_PM_LP.sh` and `START_WATCH.sh` export `RES_OPTIONS="timeout:1 attempts:2"`. It takes effect
     at the next start of each process.
   - Undo: delete the `export RES_OPTIONS=...` line and restart that process.
   - The running collector keeps its 300 s in-process lookup cache and is not restarted for this.
2. **Done 2026-10-18 with the user's approval: system-wide, reversible.** It makes every program on the host wait 1 s
   instead of 5 s.

   ```
   nmcli connection modify "Wired connection 1" ipv4.dns-options "timeout:1,attempts:2"
   nmcli device reapply eno1             # applies to the active connection without taking it down
   grep options /etc/resolv.conf         # expect: options timeout:1 attempts:2
   ```

   - `sudo` was not needed: polkit grants the logged-in desktop user `settings.modify.system` and `network-control`.
   - `reapply` updated `/etc/resolv.conf` at once, with no network gap.
   - Measured afterwards (`research/dns_diag.py 120`, `RES_OPTIONS` unset): 192.168.1.3 still loses 5–6/120
     queries, but getaddrinfo AF_UNSPEC takes 11.7 s per 120 lookups (was 56.2 s), max 1.17 s (was ~5 s).
   - glibc reloads `/etc/resolv.conf` when it changes, so already running processes are covered as well.
   - Undo: `nmcli connection modify "Wired connection 1" ipv4.dns-options ""`, then the same `reapply`.
   - Afterwards check the snapshot spacing with `python3 -m lab watch --once` and the pm_lp database.
3. **Root cause, on the network (your decision).** 192.168.1.3 is the Synology NAS (`NAS.local`, DSM on ports
   5000/5001), an ad-filtering DNS (`doubleclick.net` → `0.0.0.0`). The router (192.168.1.1) is a Synology SRM.
   - Measured 2026-10-18 with `dig +tries=1`: at 1 query/s 0/60 lost (same name) and 0/60 lost (uncached names);
     back-to-back 2/60 lost. The loss depends on the query rate, which points to a per-client rate limit in the
     NAS's DNS service rather than a faulty device. Raising or switching off that limit (needs a DSM login) is
     the likely fix. Repair the DNS service on 192.168.1.3, or stop the router from
   handing it out first via DHCP.
   - Check afterwards with `python3 research/dns_diag.py`: 192.168.1.3 should show 0 lost queries.
4. **Not recommended now.** A local caching resolver (systemd-resolved, dnsmasq). It is a larger change to the host's
   name resolution, and steps 1–3 cover the measured problem.
