"""DNS diagnosis on the Linux host (read-only, unprivileged; changes no setting). Run: python3 research/dns_diag.py [N]
Part 1: raw UDP loss per resolver for A, AAAA and A+AAAA sent back-to-back on one socket (what glibc does).
Part 2: getaddrinfo latency under the current resolv.conf, in child processes with different RES_OPTIONS."""
import json
import os
import random
import socket
import struct
import subprocess
import sys
import time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
HOSTS = ["data-api.polymarket.com", "clob.polymarket.com", "fapi.binance.com", "community-api.coinmetrics.io"]
SERVERS = [l.split()[1] for l in open("/etc/resolv.conf") if l.startswith("nameserver")]


def packet(name, qtype):
    tid = random.randint(0, 65535)
    q = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0" + struct.pack(">HH", qtype, 1)
    return tid, q


def raw(server, name, types, timeout=2.0):
    """Send queries for `types` back-to-back on one UDP socket; return (lost_count, seconds)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    want = {}
    t0 = time.time()
    for qt in types:
        tid, q = packet(name, qt)
        want[tid] = qt
        s.sendto(q, (server, 53))
    got = set()
    try:
        while len(got) < len(want):
            data, _ = s.recvfrom(1024)
            tid = struct.unpack(">H", data[:2])[0]
            if tid in want:
                got.add(tid)
    except socket.timeout:
        pass
    finally:
        s.close()
    return len(want) - len(got), time.time() - t0


print(f"resolv.conf servers: {SERVERS}; N={N} per cell")
for srv in SERVERS:
    for label, types in (("A", (1,)), ("AAAA", (28,)), ("A+AAAA same socket", (1, 28))):
        lost = 0
        lat = []
        for i in range(N):
            l, dt = raw(srv, HOSTS[i % len(HOSTS)], types)
            lost += l > 0
            if not l:
                lat.append(dt)
        lat.sort()
        med = f"{lat[len(lat) // 2] * 1000:.0f} ms" if lat else "-"
        print(f"  {srv:16s} {label:20s} queries with loss {lost:3d}/{N}  median {med}")

CHILD = r"""
import socket, sys, time, json
hosts = json.loads(sys.argv[1]); n = int(sys.argv[2]); fam = int(sys.argv[3])
res = []
for i in range(n):
    t = time.time()
    try:
        socket.getaddrinfo(hosts[i % len(hosts)], 443, fam, socket.SOCK_STREAM); ok = True
    except OSError:
        ok = False
    res.append((time.time() - t, ok))
print(json.dumps(res))
"""
print("getaddrinfo through the system resolver (each lookup is a fresh query; no cache on this host):")
for opts in ("", "single-request", "timeout:1 attempts:2", "single-request timeout:1 attempts:2"):
    for fam, fname in ((socket.AF_UNSPEC, "AF_UNSPEC"), (socket.AF_INET, "AF_INET")):
        env = dict(os.environ)
        env.pop("RES_OPTIONS", None)
        if opts:
            env["RES_OPTIONS"] = opts
        out = subprocess.run([sys.executable, "-c", CHILD, json.dumps(HOSTS), str(N), str(int(fam))],
                             capture_output=True, text=True, env=env, timeout=N * 12)
        r = json.loads(out.stdout)
        d = sorted(x for x, _ in r)
        slow = sum(x > 0.9 for x in d)
        fail = sum(not ok for _, ok in r)
        print(f"  RES_OPTIONS={opts or '(none)':38s} {fname:9s} median {d[len(d) // 2] * 1000:6.1f} ms  "
              f"p95 {d[int(len(d) * .95)] * 1000:7.1f} ms  max {d[-1]:5.2f} s  >0.9 s: {slow:3d}/{N}  failed {fail}  "
              f"total {sum(d):6.1f} s")
