"""hostprobe (director orders 89 and 91): a tiny local log of the host's state, so that the next freeze leaves a trace.

Every 10 s one JSON line is appended to ~/hostprobe/YYYY-MM-DD.jsonl and flushed to disk (fsync): load, CPU %, memory,
pressure (PSI), CPU temperature, throttle counters and the disk queue. Every 60 s the five heaviest processes by CPU are
added, every 600 s the SSD temperature from UDisks2.

It reads /proc, /sys and one D-Bus property only. No network, no database, nothing inside the copybot checkouts, no
root. It changes nothing on the host. Installed and started by the owner (research/ops/hostprobe/INSTALL.md).
"""
import glob
import json
import os
import subprocess
import sys
import time

INTERVAL, TOP_EVERY, SSD_EVERY = 10, 6, 60          # ticks: every 10 s, every 60 s, every 600 s
DISK = "sda"
SSD_DBUS = ("org.freedesktop.UDisks2", "/org/freedesktop/UDisks2/drives/SAMSUNG_SSD_830_Series_S0Z2NSAC804909",
            "org.freedesktop.UDisks2.Drive.Ata", "SmartTemperature")


def read(path, root="/"):
    try:
        with open(os.path.join(root, path.lstrip("/")), encoding="ascii", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def cpu_times(root="/"):
    line = (read("/proc/stat", root) or "").split("\n", 1)[0].split()
    if not line or line[0] != "cpu":
        return None
    v = [int(x) for x in line[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v), idle


def cpu_pct(prev, cur):
    if not prev or not cur or cur[0] <= prev[0]:
        return None
    total, idle = cur[0] - prev[0], cur[1] - prev[1]
    return round(100.0 * (total - idle) / total, 1)


def meminfo(root="/"):
    out = {}
    for line in (read("/proc/meminfo", root) or "").splitlines():
        k, _, rest = line.partition(":")
        if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Dirty", "Writeback"):
            out[k] = int(rest.split()[0]) // 1024        # MB
    return out


def pressure(root="/"):
    out = {}
    for kind in ("cpu", "io", "memory"):
        txt = read(f"/proc/pressure/{kind}", root) or ""
        for line in txt.splitlines():
            parts = dict(p.split("=") for p in line.split()[1:] if "=" in p)
            if line.startswith("some") and "avg10" in parts:
                out[f"{kind}_some10"] = float(parts["avg10"])
            if line.startswith("full") and "avg10" in parts:
                out[f"{kind}_full10"] = float(parts["avg10"])
    return out


def temps(root="/"):
    out = {}
    for name_file in glob.glob(os.path.join(root, "sys/class/hwmon/hwmon*/name")):
        d = os.path.dirname(name_file)
        name = (read(name_file, "/") or "").strip()
        for inp in sorted(glob.glob(os.path.join(d, "temp*_input"))):
            label = (read(inp.replace("_input", "_label"), "/") or os.path.basename(inp)).strip()
            raw = (read(inp, "/") or "").strip()
            if raw.lstrip("-").isdigit():
                out[f"{name}:{label}"] = int(raw) / 1000
    return out


def throttles(root="/"):
    total = {}
    for f in glob.glob(os.path.join(root, "sys/devices/system/cpu/cpu*/thermal_throttle/*_count")):
        raw = (read(f, "/") or "").strip()
        if raw.isdigit():
            key = os.path.basename(f)
            total[key] = total.get(key, 0) + int(raw)
    return total


def disk(root="/", dev=DISK):
    for line in (read("/proc/diskstats", root) or "").splitlines():
        p = line.split()
        if len(p) > 13 and p[2] == dev:
            return {"reads": int(p[3]), "writes": int(p[7]), "in_flight": int(p[11]), "io_ms": int(p[12])}
    return None


def top_processes(root="/", n=5, hz=os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100):
    rows = []
    for stat in glob.glob(os.path.join(root, "proc/[0-9]*/stat")):
        txt = read(stat, "/")
        if not txt or ")" not in txt:
            continue
        name = txt[txt.index("(") + 1:txt.rindex(")")]
        f = txt[txt.rindex(")") + 2:].split()
        try:
            cpu_s = (int(f[11]) + int(f[12])) / hz
            rss_mb = int(f[21]) * 4096 // (1024 * 1024)
        except (IndexError, ValueError):
            continue
        rows.append({"pid": int(stat.split(os.sep)[-2]), "name": name[:32], "cpu_s": round(cpu_s, 1),
                     "rss_mb": rss_mb})
    rows.sort(key=lambda r: (-r["cpu_s"], r["pid"]))
    return rows[:n]


def ssd_temp():
    try:
        r = subprocess.run(["busctl", "get-property", *SSD_DBUS], capture_output=True, text=True, timeout=5)
        kelvin = float(r.stdout.split()[1])
        return round(kelvin - 273.15, 1)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def sample(tick, prev_cpu, root="/", now=None, ssd=ssd_temp):
    cur = cpu_times(root)
    load = (read("/proc/loadavg", root) or "").split()
    rec = {"ts": round(now if now is not None else time.time(), 1), "load1": float(load[0]) if load else None,
           "procs_running": int(load[3].split("/")[0]) if len(load) > 3 else None, "cpu_pct": cpu_pct(prev_cpu, cur),
           "mem": meminfo(root), "psi": pressure(root), "temp": temps(root), "throttle": throttles(root),
           "disk": disk(root)}
    if tick % TOP_EVERY == 0:
        rec["top"] = top_processes(root)
    if tick % SSD_EVERY == 0:
        rec["ssd_c"] = ssd()
    return rec, cur


def append(out_dir, rec):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, time.strftime("%Y-%m-%d.jsonl", time.gmtime(rec["ts"])))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def main(argv=None):
    out_dir = (argv or sys.argv[1:] or [os.path.expanduser("~/hostprobe")])[0]
    tick, prev = 0, cpu_times()
    while True:
        start = time.time()
        rec, prev = sample(tick, prev)
        append(out_dir, rec)
        tick += 1
        time.sleep(max(1.0, INTERVAL - (time.time() - start)))


if __name__ == "__main__":
    main()
