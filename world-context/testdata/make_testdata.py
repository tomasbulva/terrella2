"""Regenerate testdata: synthetic Open-Meteo responses and golden scene-state vectors.

Usage (from the project root):  python3 testdata/make_testdata.py

The Open-Meteo fixtures are synthetic but use the exact response shape of
/v1/forecast with timeformat=unixtime (see weather.request_url). The golden files carry
their own inputs, so a port only needs testdata/golden/*.json + palette/default.json.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from terrella_world import derive_scene_state, parse_response  # noqa: E402

PALETTE = json.loads((ROOT / "palette" / "default.json").read_text())


def ts(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).timestamp())


def make_response(lat, lon, offset_s, elevation, fetched_at, profile):
    """profile(t_rel_hours) -> dict of hourly values."""
    hour0 = fetched_at - fetched_at % 3600
    hourly = {k: [] for k in ("time", "temperature_2m", "relative_humidity_2m", "weather_code", "cloud_cover",
                              "wind_speed_10m", "wind_direction_10m", "precipitation", "snowfall", "visibility",
                              "snow_depth")}
    for h in range(-6, 48):
        t = hour0 + h * 3600
        v = profile(h)
        hourly["time"].append(t)
        for k in hourly:
            if k != "time":
                hourly[k].append(v.get(k))
    cur_t = fetched_at - fetched_at % 900
    cv = profile((cur_t - hour0) / 3600.0)
    current = {"time": cur_t, "interval": 900}
    for k in ("temperature_2m", "relative_humidity_2m", "weather_code", "cloud_cover", "wind_speed_10m",
              "wind_direction_10m", "visibility"):
        current[k] = cv.get(k)
    current["precipitation"] = round((cv.get("precipitation") or 0.0) / 4.0, 2)
    current["snowfall"] = round((cv.get("snowfall") or 0.0) / 4.0, 2)
    return {"latitude": lat, "longitude": lon, "generationtime_ms": 0.1, "utc_offset_seconds": offset_s,
            "timezone": "GMT", "timezone_abbreviation": "GMT", "elevation": elevation,
            "current": current, "hourly": hourly}


def base(temp, code, cloud, wind=3.0, wdir=240.0, rh=75.0, precip=0.0, snow=0.0, vis=24000.0, depth=0.0):
    return {"temperature_2m": temp, "relative_humidity_2m": rh, "weather_code": code, "cloud_cover": cloud,
            "wind_speed_10m": wind, "wind_direction_10m": wdir, "precipitation": precip, "snowfall": snow,
            "visibility": vis, "snow_depth": depth}


def amsterdam_snow(h):
    snowing = -3 <= h <= 2
    return base(-1.5 + 0.2 * h, 73 if snowing else 3, 100 if snowing else 85, wind=5.5, wdir=20,
                precip=1.2 if snowing else 0.0, snow=0.84 if snowing else 0.0, vis=1800 if snowing else 9000,
                depth=0.02 + 0.004 * max(0, min(h + 3, 6)))


def amsterdam_summer(h):
    return base(23.0 + 2 * math.sin(h / 24 * 2 * math.pi), 0 if h < 30 else 2, 4 if h < 30 else 30, wind=3.2,
                wdir=250, rh=48, vis=40000)


def sydney_rain(h):
    raining = -4 <= h <= 3
    return base(21.0, 63 if raining else 3, 100 if raining else 70, wind=7.0, wdir=160, rh=92,
                precip=3.5 if raining else 0.0, vis=6000 if raining else 20000)


def tromso_night(h):
    return base(-8.0, 0, 5, wind=1.5, wdir=110, rh=70, vis=50000, depth=0.42)


def singapore_storm(h):
    storm = -1 <= h <= 2
    return base(27.5, 95 if storm else 2, 95 if storm else 45, wind=9.0 if storm else 3.0, wdir=200, rh=88,
                precip=18.0 if storm else 0.0, vis=3000 if storm else 15000)


def amsterdam_fog(h):
    foggy = h <= 2
    return base(8.0, 45 if foggy else 2, 100 if foggy else 40, wind=0.8, wdir=90, rh=99 if foggy else 85,
                vis=300 if foggy else 12000)


AMS = (52.35, 4.9)
CASES = [
    # name, (lat, lon), offset, elevation, fetched_at, now, profile
    ("amsterdam_winter_snow_morning", AMS, 3600, 0.0, ts("2026-01-20T08:05:00+01:00"), ts("2026-01-20T08:20:00+01:00"), amsterdam_snow),
    ("amsterdam_summer_noon_clear", AMS, 7200, 0.0, ts("2026-06-21T13:10:00+02:00"), ts("2026-06-21T13:40:00+02:00"), amsterdam_summer),
    ("amsterdam_summer_forecast_10h_old", AMS, 7200, 0.0, ts("2026-06-21T13:10:00+02:00"), ts("2026-06-21T23:10:00+02:00"), amsterdam_summer),
    ("amsterdam_autumn_fog_dawn", AMS, 7200, 0.0, ts("2026-10-20T07:30:00+02:00"), ts("2026-10-20T07:50:00+02:00"), amsterdam_fog),
    ("sydney_summer_dusk_rain", (-33.85, 151.2), 39600, 20.0, ts("2026-02-10T19:50:00+11:00"), ts("2026-02-10T20:05:00+11:00"), sydney_rain),
    ("tromso_polar_night_noon", (69.65, 18.95), 3600, 10.0, ts("2026-12-15T11:30:00+01:00"), ts("2026-12-15T12:00:00+01:00"), tromso_night),
    ("singapore_thunderstorm", (1.3, 103.85), 28800, 15.0, ts("2026-03-01T15:40:00+08:00"), ts("2026-03-01T16:00:00+08:00"), singapore_storm),
    ("offline_fallback_3_days", AMS, 7200, 0.0, ts("2026-06-18T09:00:00+02:00"), ts("2026-06-21T13:40:00+02:00"), amsterdam_summer),
]


def main():
    om_dir = ROOT / "testdata" / "openmeteo"
    gold_dir = ROOT / "testdata" / "golden"
    om_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    for name, (lat, lon), offset, elev, fetched_at, now, profile in CASES:
        resp = make_response(lat, lon, offset, elev, fetched_at, profile)
        (om_dir / f"{name}.json").write_text(json.dumps(resp, indent=1) + "\n")
        inputs = {
            "schema": "terrella.world_inputs", "version": 1,
            "location": {"lat": lat, "lon": lon, "source": "device", "utc_offset_s": offset, "updated_at": fetched_at},
            "weather": parse_response(resp, fetched_at),
        }
        expected = derive_scene_state(inputs, now, PALETTE)
        golden = {"case": name, "now": now, "inputs": inputs, "expected": expected}
        (gold_dir / f"{name}.json").write_text(json.dumps(golden, indent=1) + "\n")
        print(f"{name}: {expected['time']['day_phase']}, {expected['weather']['condition']}, key={expected['light']['key']['source']}, src={expected['meta']['source']}")


if __name__ == "__main__":
    main()
