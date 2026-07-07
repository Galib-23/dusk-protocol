"""
Dusk Protocol — thesis metrics from the app's event log.

Pulls dusk_logs from the deployed server (or a local CSV) and computes,
per device and mode:

  1. camera duty cycle  — camera-on seconds / session seconds  (THE headline)
  2. battery drain      — %/30 min fitted from battery_sample series
  3. frames-to-decision — mean/median from commit events
  4. wake->commit latency and Tier-1 wake counts / timeouts

Outputs a summary table (console + summary.csv) and plots into
measurements/out/.

Usage:
  python analyze_logs.py                          # fetch from server
  python analyze_logs.py --csv logs.csv           # or a local export
  python analyze_logs.py --url https://pd.brittoo.xyz/logs.csv
"""

import argparse
import csv
import io
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_URL = "https://pd.brittoo.xyz/logs.csv"
OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
SESSION_GAP_S = 300   # a >5 min silence splits sessions


def load_rows(args):
    if args.csv:
        text = open(args.csv, encoding="utf-8").read()
    else:
        with urllib.request.urlopen(args.url, timeout=30) as r:
            text = r.read().decode()
    rows = []
    for rec in csv.DictReader(io.StringIO(text)):
        try:
            data = json.loads(rec["data"].replace(";", ",")) if rec["data"] else {}
        except json.JSONDecodeError:
            data = {}
        rows.append({
            "ts": datetime.fromisoformat(rec["ts"].replace("Z", "+00:00")),
            "device": rec["device"] or "unknown",
            "mode": rec["mode"] or "unknown",
            "event": rec["event"],
            "battery": int(rec["battery"]) if rec["battery"] not in ("", None) else None,
            **data,
        })
    rows.sort(key=lambda r: r["ts"])
    return rows


def split_sessions(rows):
    """Group rows into sessions per (device, mode), split on long gaps."""
    sessions = []
    streams = defaultdict(list)
    for r in rows:
        if r["device"] == "vps-check":
            continue
        streams[(r["device"], r["mode"])].append(r)
    for (device, mode), rs in streams.items():
        cur = [rs[0]]
        for r in rs[1:]:
            if (r["ts"] - cur[-1]["ts"]).total_seconds() > SESSION_GAP_S \
                    or r["event"] == "session_start":
                sessions.append((device, mode, cur))
                cur = []
            cur.append(r)
        sessions.append((device, mode, cur))
    return [s for s in sessions if len(s[2]) >= 2]


def drain_rate(samples):
    """Least-squares slope of battery% vs hours -> %/30min (negative = drain)."""
    pts = [(r["ts"], r["battery"]) for r in samples
           if r["event"] == "battery_sample" and r["battery"] is not None
           and r["battery"] >= 0]
    if len(pts) < 3:
        return None
    t0 = pts[0][0]
    xs = [(t - t0).total_seconds() / 3600 for t, _ in pts]
    ys = [b for _, b in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom < 1e-9:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom  # %/hour
    return slope / 2   # %/30min


def analyze(sessions):
    table = []
    for device, mode, rs in sessions:
        dur = (rs[-1]["ts"] - rs[0]["ts"]).total_seconds()
        if dur < 60:
            continue
        cam_ms = sum(r.get("camera_on_ms", 0) for r in rs if r["event"] == "camera_off")
        # an unclosed camera interval (always mode ends mid-stream): count to end
        opens = sum(1 for r in rs if r["event"] == "camera_on")
        closes = sum(1 for r in rs if r["event"] == "camera_off")
        if opens > closes:
            last_on = max(r["ts"] for r in rs if r["event"] == "camera_on")
            cam_ms += (rs[-1]["ts"] - last_on).total_seconds() * 1000
        commits = [r for r in rs if r["event"] == "commit"]
        frames = [r["frames"] for r in commits if "frames" in r]
        w2c = [r["wake_to_commit_ms"] for r in commits if "wake_to_commit_ms" in r]
        table.append({
            "device": device.split("-")[0],
            "mode": mode,
            "start": rs[0]["ts"].astimezone(timezone.utc).strftime("%m-%d %H:%M"),
            "dur_min": round(dur / 60, 1),
            "cam_on_s": round(cam_ms / 1000, 1),
            "duty_pct": round(100 * cam_ms / 1000 / dur, 1),
            "wakes": sum(1 for r in rs if r["event"] == "wake"),
            "commits": len(commits),
            "timeouts": sum(1 for r in rs if r["event"] == "timeout"),
            "frames_mean": round(sum(frames) / len(frames), 1) if frames else None,
            "w2c_ms": round(sum(w2c) / len(w2c)) if w2c else None,
            "drain_pct_30min": (r := drain_rate(rs)) and round(-r, 2),
        })
    return table


def print_table(table):
    if not table:
        print("No sessions >= 1 min found yet — run some sessions first.")
        return
    cols = list(table[0].keys())
    widths = {c: max(len(c), *(len(str(r[c])) for r in table)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in table:
        print("  ".join(str(r[c] if r[c] is not None else "-").ljust(widths[c])
                        for c in cols))

    print("\n== Mode aggregates ==")
    for mode in sorted({r["mode"] for r in table}):
        rs = [r for r in table if r["mode"] == mode]
        duty = sum(r["duty_pct"] for r in rs) / len(rs)
        drains = [r["drain_pct_30min"] for r in rs if r["drain_pct_30min"] is not None]
        drain = f"{sum(drains) / len(drains):.2f} %/30min" if drains else "n/a"
        print(f"  {mode:>7}: sessions={len(rs)}  camera duty={duty:.1f}%  drain={drain}")


def plot(sessions, table):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed — skipping plots; pip install matplotlib)")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    colors = {"always": "#d62728", "dusk": "#4747d1"}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for device, mode, rs in sessions:
        pts = [(r["ts"], r["battery"]) for r in rs
               if r["event"] == "battery_sample" and (r["battery"] or -1) >= 0]
        if len(pts) < 3:
            continue
        t0 = pts[0][0]
        ax.plot([(t - t0).total_seconds() / 60 for t, _ in pts],
                [b for _, b in pts], marker=".", alpha=0.8,
                color=colors.get(mode, "gray"), label=mode)
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax.legend(uniq.values(), uniq.keys())
    ax.set_xlabel("session time (min)")
    ax.set_ylabel("battery %")
    ax.set_title("Battery drain: always-on vs dusk")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "battery_drain.png"), dpi=150)

    fig, ax = plt.subplots(figsize=(6, 4))
    modes = sorted({r["mode"] for r in table})
    duty = [[r["duty_pct"] for r in table if r["mode"] == m] for m in modes]
    ax.bar(modes, [sum(d) / len(d) for d in duty],
           color=[colors.get(m, "gray") for m in modes])
    ax.set_ylabel("camera duty cycle (%)")
    ax.set_title("Camera-on time share per mode")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "camera_duty.png"), dpi=150)
    print(f"\nPlots -> {OUT_DIR}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    rows = load_rows(args)
    print(f"{len(rows)} events loaded")
    sessions = split_sessions(rows)
    table = analyze(sessions)
    print_table(table)

    os.makedirs(OUT_DIR, exist_ok=True)
    if table:
        with open(os.path.join(OUT_DIR, "summary.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
            w.writeheader()
            w.writerows(table)
        print(f"Summary -> {os.path.join(OUT_DIR, 'summary.csv')}")
    plot(sessions, table)


if __name__ == "__main__":
    main()
