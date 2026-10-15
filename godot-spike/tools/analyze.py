#!/usr/bin/env python3
"""Summarise Terrella spike metric CSVs.

Usage: python3 analyze.py path/to/csvs_or_folder [...]
Groups rows into segments of constant (device, mode, renderer, variant, visible) and prints, per segment:
duration, fps, frame time, CPU, PSS, battery current and an mAh/hour estimate. Rows taken while the phone
was plugged in are dropped because battery current is meaningless then.
"""
import csv
import glob
import os
import statistics
import sys


def load(paths):
    rows = []
    for p in paths:
        files = glob.glob(os.path.join(p, "*.csv")) if os.path.isdir(p) else [p]
        for f in files:
            with open(f, newline="") as fh:
                for r in csv.DictReader(fh):
                    r["_file"] = os.path.basename(f)
                    rows.append(r)
    rows.sort(key=lambda r: (r["_file"], int(r["wall_ms"])))
    return rows


def num(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError):
        return 0.0


def pct(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def main():
    rows = load(sys.argv[1:] or ["."])
    events = [r for r in rows if r["event"]]
    samples = [r for r in rows if not r["event"]]

    print("## Start-up and errors\n")
    print("| file | event | ms |")
    print("|---|---|---|")
    for r in events:
        if r["event"] in ("first_frame", "engine_init", "service_create") or r["event"].startswith(("error", "scene_built")):
            print(f"| {r['_file']} | {r['event']} | {r['event_ms']} |")

    segs = []
    for r in samples:
        if r["plugged"] not in ("0", ""):
            continue
        key = (r["_file"], r["device"], r["mode"], r["renderer"], r["variant"], r["visible"])
        if segs and segs[-1]["key"] == key and int(r["wall_ms"]) - segs[-1]["rows"][-1]["wall_ms_i"] < 30000:
            segs[-1]["rows"].append(r)
        else:
            segs.append({"key": key, "rows": [r]})
        r["wall_ms_i"] = int(r["wall_ms"])

    print("\n## Segments (unplugged only, >= 60 s)\n")
    print("| device | mode | renderer | variant | visible | minutes | fps avg | fps p5 | frame ms | draw calls | CPU % | PSS MB | avg current mA (= mAh/h) | mAh/h (counter) | temp rise C | max thermal |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in segs:
        rs = s["rows"]
        dur = (int(rs[-1]["wall_ms"]) - int(rs[0]["wall_ms"])) / 1000.0
        if dur < 60:
            continue
        vis = rs[0]["visible"] == "1"
        fps = [num(r, "fps") for r in rs if vis]
        cur = [abs(num(r, "batt_current_ua")) / 1000.0 for r in rs]
        ma = statistics.mean(cur) if cur else 0.0
        dq = (num(rs[0], "batt_charge_uah") - num(rs[-1], "batt_charge_uah")) / 1000.0
        counter_rate = dq / (dur / 3600.0) if dur > 0 else 0.0
        _file, device, mode, renderer, variant, visible = s["key"]
        print(
            f"| {device} | {mode} | {renderer} | {variant} | {visible} | {dur / 60:.1f} | "
            f"{statistics.mean(fps) if fps else 0:.1f} | {pct(fps, 0.05):.1f} | "
            f"{statistics.mean(num(r, 'frame_ms') for r in rs):.1f} | {statistics.mean(num(r, 'draw_calls') for r in rs):.0f} | "
            f"{statistics.mean(num(r, 'cpu_pct') for r in rs):.1f} | {max(num(r, 'pss_mb') for r in rs):.0f} | "
            f"{ma:.0f} | {counter_rate:.0f} | "
            f"{num(rs[-1], 'batt_temp_c') - num(rs[0], 'batt_temp_c'):.1f} | {max(int(num(r, 'thermal_status')) for r in rs)} |"
        )
    print("\nCurrent is whole-device draw (screen included). Compare segments against each other on the same phone,"
          " same brightness, not against absolute numbers.")


if __name__ == "__main__":
    main()
