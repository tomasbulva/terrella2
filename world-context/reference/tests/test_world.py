import copy
import datetime as dt
import json
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reference"))
sys.path.insert(0, str(ROOT / "testdata"))

from terrella_world import astro, coarsen, decide, derive_scene_state, parse_response, request_url  # noqa: E402

PALETTE = json.loads((ROOT / "palette" / "default.json").read_text())
GOLDEN = sorted((ROOT / "testdata" / "golden").glob("*.json"))
SCENE_SCHEMA = json.loads((ROOT / "schema" / "scene-state.v1.schema.json").read_text())
INPUT_SCHEMA = json.loads((ROOT / "schema" / "world-inputs.v1.schema.json").read_text())


def ts(iso):
    return dt.datetime.fromisoformat(iso).timestamp()


# --- astronomy ---------------------------------------------------------------------

@pytest.mark.parametrize("lat,lon,off,day", [
    (52.37, 4.89, 7200, "2026-06-21"), (52.37, 4.89, 3600, "2026-12-21"),
    (-33.87, 151.21, 39600, "2026-01-10"), (1.29, 103.85, 28800, "2026-03-01"),
    (37.77, -122.42, -25200, "2026-10-15"), (64.15, -21.94, 0, "2026-03-20"),
])
def test_sun_events_match_astral(lat, lon, off, day):
    astral_sun = pytest.importorskip("astral.sun")
    from astral import LocationInfo
    tz = dt.timezone(dt.timedelta(seconds=off))
    ref = astral_sun.sun(LocationInfo(latitude=lat, longitude=lon).observer, date=dt.date.fromisoformat(day), tzinfo=tz)
    ev = astro.sun_events(dt.datetime.fromisoformat(day + "T12:00:00").replace(tzinfo=tz).timestamp(), lat, lon, off)
    for k_ours, k_ref in (("sunrise", "sunrise"), ("sunset", "sunset"), ("solar_noon", "noon")):
        assert abs(ev[k_ours] - ref[k_ref].timestamp()) < 30, k_ours


def test_sun_position_matches_ephem():
    ephem = pytest.importorskip("ephem")
    for lat, lon in ((52.37, 4.89), (-33.87, 151.21), (69.65, 18.96)):
        for h in range(0, 48, 5):
            t = ts("2026-03-10T00:00:00+00:00") + h * 3600
            o = ephem.Observer(); o.lat, o.lon = str(lat), str(lon)
            o.date = ephem.Date(dt.datetime.fromtimestamp(t, dt.timezone.utc).replace(tzinfo=None))
            s = ephem.Sun(o)
            az, el = astro.sun_position(t, lat, lon)
            if math.degrees(s.alt) > 1:  # below the horizon ephem and NOAA treat refraction differently
                assert abs(el - math.degrees(s.alt)) < 0.1
                assert abs((az - math.degrees(s.az) + 180) % 360 - 180) < 0.1


def test_moon_within_lighting_tolerance():
    ephem = pytest.importorskip("ephem")
    for h in range(0, 24 * 30, 37):
        t = ts("2026-01-01T00:00:00+00:00") + h * 3600
        o = ephem.Observer(); o.lat, o.lon = "52.37", "4.89"
        o.date = ephem.Date(dt.datetime.fromtimestamp(t, dt.timezone.utc).replace(tzinfo=None))
        m = ephem.Moon(o)
        _, el = astro.moon_position(t, 52.37, 4.89)
        _, frac = astro.moon_phase(t)
        assert abs(el - math.degrees(m.alt)) < 2.5
        assert abs(frac - m.phase / 100) < 0.03


def test_polar_night_and_midnight_sun():
    assert astro.sun_events(ts("2026-12-15T12:00:00+01:00"), 69.65, 18.95, 3600)["polar"] == "night"
    assert astro.sun_events(ts("2026-06-21T12:00:00+02:00"), 69.65, 18.95, 7200)["polar"] == "day"


def test_direction_convention():
    # +X east, +Y up, -Z north
    assert astro.direction(90, 0) == pytest.approx([1, 0, 0], abs=1e-9)
    assert astro.direction(0, 0) == pytest.approx([0, 0, -1], abs=1e-9)
    assert astro.direction(0, 90) == pytest.approx([0, 1, 0], abs=1e-9)


# --- weather + derive ----------------------------------------------------------------

def test_request_url_is_single_coarse_call():
    url = request_url(52.3512345, 4.9)
    assert "latitude=52.35&" in url and "past_hours=6" in url and "forecast_hours=48" in url
    assert "timeformat=unixtime" in url and "wind_speed_unit=ms" in url


def test_parse_converts_current_to_hourly_rate():
    resp = json.loads((ROOT / "testdata" / "openmeteo" / "amsterdam_winter_snow_morning.json").read_text())
    wx = parse_response(resp, resp["current"]["time"])
    cur = next(s for s in wx["samples"] if s.get("current"))
    assert cur["precip_mm_h"] == pytest.approx(resp["current"]["precipitation"] * 4)
    assert [s["t"] for s in wx["samples"]] == sorted(s["t"] for s in wx["samples"])


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_golden(path):
    g = json.loads(path.read_text())
    assert derive_scene_state(g["inputs"], g["now"], PALETTE) == g["expected"]


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_schemas(path):
    jsonschema = pytest.importorskip("jsonschema")
    g = json.loads(path.read_text())
    jsonschema.validate(g["inputs"], INPUT_SCHEMA)
    jsonschema.validate(g["expected"], SCENE_SCHEMA)


def test_scene_is_valid_every_hour_for_a_year_including_no_weather():
    jsonschema = pytest.importorskip("jsonschema")
    v = jsonschema.Draft202012Validator(SCENE_SCHEMA)
    for lat, lon in ((52.35, 4.9), (-54.8, -68.3), (78.2, 15.6), (0.0, 0.0)):
        inputs = {"location": {"lat": lat, "lon": lon}, "weather": None}
        for h in range(0, 24 * 365, 7):
            v.validate(derive_scene_state(inputs, ts("2026-01-01T00:00:00+00:00") + h * 3600, PALETTE))


def test_southern_hemisphere_seasons_flip():
    inputs = {"location": {"lat": -33.85, "lon": 151.2, "utc_offset_s": 39600}, "weather": None}
    s = derive_scene_state(inputs, ts("2026-01-15T12:00:00+11:00"), PALETTE)["season"]
    assert s["name"] == "summer" and s["foliage"] > 0.9


def test_override_forces_weather():
    g = json.loads((ROOT / "testdata" / "golden" / "amsterdam_summer_noon_clear.json").read_text())
    s = derive_scene_state(g["inputs"], g["now"], PALETTE, {"weather": {"code": 75, "snowfall_cm_h": 2.0, "temp_c": -2}})
    assert s["weather"]["precipitation"]["type"] == "snow" and s["meta"]["source"] == "override"


def test_stale_cache_degrades_gracefully():
    g = json.loads((ROOT / "testdata" / "golden" / "amsterdam_summer_noon_clear.json").read_text())
    last = g["inputs"]["weather"]["samples"][-1]["t"]
    assert derive_scene_state(g["inputs"], last + 3600, PALETTE)["meta"]["source"] == "forecast"
    assert derive_scene_state(g["inputs"], last + 4 * 3600, PALETTE)["meta"]["source"] == "fallback"


# --- policy --------------------------------------------------------------------------

def _wx(fetched_at, lat=52.35, lon=4.9, horizon_h=48):
    return {"fetched_at": fetched_at, "lat": lat, "lon": lon, "samples": [{"t": fetched_at + horizon_h * 3600, "code": 0}]}


def test_coarsen_snaps_to_grid():
    assert coarsen(52.3712, 4.8952) == (52.35, 4.9)


@pytest.mark.parametrize("kwargs,fetch,reason", [
    ({"location": None, "weather": None}, False, "no_location"),
    ({"weather": None}, True, "empty"),
    ({"weather": _wx(0)}, False, "fresh"),
    ({"weather": _wx(-3700)}, True, "stale"),
    ({"weather": _wx(0, lat=52.6)}, True, "moved"),
    ({"weather": _wx(-600, horizon_h=10)}, True, "horizon"),
    ({"weather": None, "online": False}, False, "offline"),
    ({"weather": None, "last_attempt_at": -600, "consecutive_failures": 1}, False, "backoff"),
    ({"weather": None, "last_attempt_at": -1000, "consecutive_failures": 1}, True, "empty"),
    ({"weather": None, "last_attempt_at": -3000, "consecutive_failures": 3}, False, "backoff"),
])
def test_policy(kwargs, fetch, reason):
    args = {"location": {"lat": 52.35, "lon": 4.9}, **kwargs}
    d = decide(0, **args)
    assert (d["fetch"], d["reason"]) == (fetch, reason)
    assert d["next_check_at"] > 0
