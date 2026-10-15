"""derive_scene_state(inputs, now, palette) -> scene_state v1.

Pure and deterministic: no clock, no network, no I/O. Everything a renderer needs is
computed from the cached world_inputs and a timestamp, so it is cheap to call once a
minute (or every frame) and trivially testable against golden vectors.
"""
from __future__ import annotations

import datetime as _dt
import math

from . import astro, weather

SCHEMA = "terrella.scene_state"
VERSION = 1

LIVE_MAX_AGE_S = 90 * 60          # newer than this counts as "live"
HORIZON_GRACE_S = 3 * 3600        # hold the last forecast sample this long past the end
WET_DECAY_S = 2.5 * 3600          # e-folding time of surface wetness after rain stops


# --- small helpers -------------------------------------------------------------------

def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp3(a, b, t):
    return [_lerp(a[i], b[i], t) for i in range(3)]


def _smoothstep(e0, e1, x):
    t = _clamp((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def _r(x, n=4):
    return round(x, n)


def _r3(v, n=4):
    return [round(c, n) for c in v]


def _luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _desaturate(c, amount):
    y = _luma(c)
    return [_lerp(ch, y, amount) for ch in c]


def _iso(unix_s, offset_s=0):
    if unix_s is None:
        return None
    tz = _dt.timezone(_dt.timedelta(seconds=offset_s))
    return _dt.datetime.fromtimestamp(round(unix_s), tz).isoformat()


# --- palette -------------------------------------------------------------------------

def _palette_at(palette, el):
    keys = palette["sun_keys"]
    if el <= keys[0]["el"]:
        lo = hi = keys[0]
        t = 0.0
    elif el >= keys[-1]["el"]:
        lo = hi = keys[-1]
        t = 0.0
    else:
        i = next(i for i in range(1, len(keys)) if el < keys[i]["el"])
        lo, hi = keys[i - 1], keys[i]
        t = (el - lo["el"]) / (hi["el"] - lo["el"])
    out = {}
    for k in ("sun_color", "ambient_color", "sky_zenith", "sky_horizon"):
        out[k] = _lerp3(lo[k], hi[k], t)
    for k in ("sun_intensity", "ambient_intensity"):
        out[k] = _lerp(lo[k], hi[k], t)
    return out


# --- weather timeline ----------------------------------------------------------------

def _num(s, key, default):
    v = s.get(key)
    return default if v is None else v


def _sample_at(samples, t):
    """Interpolated weather sample at t. Returns (sample, status) where status is
    'ok', 'clamped' (before first / slightly after last) or 'beyond' (past the grace horizon)."""
    if not samples:
        return None, "beyond"
    if t <= samples[0]["t"]:
        return dict(samples[0]), "clamped" if t < samples[0]["t"] else "ok"
    last = samples[-1]
    if t >= last["t"]:
        return dict(last), "ok" if t == last["t"] else ("clamped" if t - last["t"] <= HORIZON_GRACE_S else "beyond")
    i = next(i for i in range(1, len(samples)) if t < samples[i]["t"])
    a, b = samples[i - 1], samples[i]
    f = (t - a["t"]) / (b["t"] - a["t"])
    out = {"t": t}
    for key, dflt in (("temp_c", 10.0), ("rh", 70.0), ("cloud", 30.0), ("precip_mm_h", 0.0),
                      ("snowfall_cm_h", 0.0), ("snow_depth_m", 0.0), ("wind_ms", 2.0)):
        va, vb = a.get(key), b.get(key)
        if va is None and vb is None:
            out[key] = None
        else:
            out[key] = _lerp(dflt if va is None else va, dflt if vb is None else vb, f)
    va, vb = a.get("visibility_m"), b.get("visibility_m")
    out["visibility_m"] = None if va is None or vb is None else _lerp(va, vb, f)
    # wind direction: interpolate the vector, not the angle
    da, db = math.radians(_num(a, "wind_dir_deg", 0.0)), math.radians(_num(b, "wind_dir_deg", 0.0))
    x = _lerp(math.sin(da), math.sin(db), f)
    y = _lerp(math.cos(da), math.cos(db), f)
    out["wind_dir_deg"] = math.degrees(math.atan2(x, y)) % 360.0
    out["code"] = (a if f < 0.5 else b)["code"]  # categorical: nearest sample
    return out, "ok"


def _recent_rain_mm(samples, t):
    """Exponentially decayed rain over the past hours, used for surface wetness."""
    acc = 0.0
    for s in samples:
        if s["t"] > t or s.get("current"):
            continue
        age = t - s["t"]
        rain = max(0.0, _num(s, "precip_mm_h", 0.0) - 10.0 * _num(s, "snowfall_cm_h", 0.0) / 7.0)
        acc += rain * math.exp(-age / WET_DECAY_S)
    return acc


def _fallback_sample(t, lat, year_phase):
    """Climatology-lite when there is no usable weather: mild, partly cloudy, seasonal temperature."""
    temperate = _smoothstep(15.0, 30.0, abs(lat))
    summer = 0.5 - 0.5 * math.cos(2 * math.pi * year_phase)
    temp = _lerp(27.0, _lerp(1.0, 21.0, summer), temperate)
    return {"t": t, "temp_c": temp, "rh": 70.0, "code": 2, "cloud": 35.0, "precip_mm_h": 0.0,
            "snowfall_cm_h": 0.0, "snow_depth_m": 0.0, "wind_ms": 2.0, "wind_dir_deg": 240.0,
            "visibility_m": None}


# --- season --------------------------------------------------------------------------

_SEASONS_NORTH = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
                  6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
_FLIP = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}


def _season(local_dt, lat):
    doy = local_dt.timetuple().tm_yday + (local_dt.hour + local_dt.minute / 60.0) / 24.0
    if lat < 0:
        doy += 182.625
    # 0 = winter solstice (Dec 21 ~ doy 355), 0.25 spring equinox, 0.5 summer solstice, 0.75 autumn equinox
    year_phase = ((doy - 355.0) / 365.25) % 1.0
    name = _SEASONS_NORTH[local_dt.month]
    if lat < 0:
        name = _FLIP[name]
    temperate = _smoothstep(15.0, 30.0, abs(lat))
    # foliage: leaves out mid-April..mid-May, colour in Oct, bare by mid-Nov (northern dates)
    leaf_out = _smoothstep(0.30, 0.40, year_phase)
    leaf_drop = 1.0 - _smoothstep(0.80, 0.88, year_phase)
    foliage = _lerp(1.0, leaf_out * leaf_drop, temperate)
    autumn = _smoothstep(0.70, 0.78, year_phase) * (1.0 - _smoothstep(0.84, 0.90, year_phase)) * temperate
    return {
        "name": name if temperate > 0.5 else "tropical",
        "year_phase": year_phase,
        "foliage": foliage,
        "autumn_tint": autumn,
    }


# --- day phase -----------------------------------------------------------------------

def _day_phase(el):
    if el < -18:
        return "night"
    if el < -12:
        return "astronomical_twilight"
    if el < -6:
        return "nautical_twilight"
    if el < astro.SUNRISE_ELEVATION:
        return "civil_twilight"
    if el < 6:
        return "golden_hour"
    return "day"


# --- main ----------------------------------------------------------------------------

def derive_scene_state(inputs: dict, now: float, palette: dict, overrides: dict | None = None) -> dict:
    """Compute the scene_state for unix time `now`.

    overrides (optional, for the explorable app / debug / puzzles):
      weather: a partial weather sample dict replacing the timeline value (e.g. {"code": 73})
    """
    overrides = overrides or {}
    loc = inputs["location"]
    lat, lon = float(loc["lat"]), float(loc["lon"])
    wx = inputs.get("weather")
    offset = loc.get("utc_offset_s")
    if offset is None:
        offset = wx["utc_offset_s"] if wx else round(lon / 15.0) * 3600
    local = _dt.datetime.fromtimestamp(now, _dt.timezone(_dt.timedelta(seconds=offset)))

    # sky bodies
    s_az, s_el = astro.sun_position(now, lat, lon)
    m_az, m_el = astro.moon_position(now, lat, lon)
    m_phase, m_illum = astro.moon_phase(now)
    ev = astro.sun_events(now, lat, lon, offset)
    season = _season(local, lat)

    # weather sample + provenance
    sample, status = (_sample_at(wx["samples"], now) if wx else (None, "beyond"))
    if status == "beyond":
        sample = _fallback_sample(now, lat, season["year_phase"])
        source = "fallback"
    elif now - wx["fetched_at"] <= LIVE_MAX_AGE_S:
        source = "live"
    else:
        source = "forecast"
    if overrides.get("weather"):
        sample = {**sample, **overrides["weather"]}
        source = "override"

    condition, ptype, code_int = weather.classify(sample["code"])
    temp = _num(sample, "temp_c", 10.0)
    cloud = _clamp(_num(sample, "cloud", 30.0) / 100.0)
    rain_rate = max(0.0, _num(sample, "precip_mm_h", 0.0))
    snow_rate = max(0.0, _num(sample, "snowfall_cm_h", 0.0))
    if ptype == "none" and (rain_rate >= 0.2 or snow_rate >= 0.1):
        ptype = "snow" if snow_rate * 7.0 >= rain_rate * 0.5 else "rain"
    if ptype == "rain" and temp <= 0.5:
        ptype = "sleet"
    if ptype == "snow" and temp >= 3.0 and snow_rate < 0.05:
        ptype = "rain"
    if ptype == "none":
        p_int = 0.0
    else:
        measured = math.sqrt(snow_rate / 3.0) if ptype == "snow" else math.sqrt(rain_rate / 10.0)
        p_int = _clamp(max(code_int, measured))
    thunder = condition == "thunderstorm"

    vis = sample.get("visibility_m")
    fog = 0.75 if condition == "fog" else 0.0
    if vis is not None:
        fog = max(fog, _clamp(1.0 - math.log10(max(vis, 1.0) / 1000.0) / math.log10(20.0)))
    fog = _clamp(max(fog, 0.25 * p_int))

    wind_ms = max(0.0, _num(sample, "wind_ms", 2.0))
    wind_from = _num(sample, "wind_dir_deg", 0.0) % 360.0
    to = math.radians(wind_from + 180.0)
    wind_vec = [math.sin(to) * wind_ms, -math.cos(to) * wind_ms]  # scene XZ, metres/second

    # surface
    recent = _recent_rain_mm(wx["samples"], now) if wx and source != "fallback" else 0.0
    wetness = _clamp(max(1.0 - math.exp(-recent / 1.5), p_int if ptype in ("rain", "sleet") else 0.0))
    depth = _num(sample, "snow_depth_m", 0.0)
    snow_cover = _clamp(max(depth / 0.03, (0.4 * p_int if ptype == "snow" else 0.0)))
    if temp > 0.0:
        wetness = max(wetness, 0.5 * snow_cover)  # melting snow is wet

    # lighting
    pal = _palette_at(palette, s_el)
    ov = palette["overcast"]
    gloom = _clamp(cloud ** 1.5 + palette["precipitation_darken"] * p_int + (palette["thunder_darken"] if thunder else 0.0))
    sun_int = pal["sun_intensity"] * (1.0 - ov["sun_dim"] * _clamp(gloom))
    sun_col = _desaturate(pal["sun_color"], ov["desaturate"] * cloud)
    amb_col = _desaturate(pal["ambient_color"], ov["desaturate"] * cloud)
    amb_int = pal["ambient_intensity"] * (1.0 + ov["ambient_gain"] * cloud) * (1.0 - 0.35 * _clamp(gloom - cloud))
    zen = _lerp3(pal["sky_zenith"], [c * _luma(pal["sky_zenith"]) / max(_luma(ov["sky_gray"]), 1e-3) for c in ov["sky_gray"]], cloud * 0.85)
    hor = _lerp3(pal["sky_horizon"], [c * _luma(pal["sky_horizon"]) / max(_luma(ov["sky_gray"]), 1e-3) for c in ov["sky_gray"]], cloud * 0.85)

    moon_up = _smoothstep(-2.0, 4.0, m_el)
    night = 1.0 - _smoothstep(-8.0, -2.0, s_el)
    moon_int = palette["moon"]["max_intensity"] * m_illum * moon_up * night * (1.0 - 0.9 * cloud)
    amb_int += palette["moon"]["night_ambient_boost"] * m_illum * moon_up * night * (1.0 - cloud)

    if sun_int >= moon_int:
        key = {"source": "sun", "direction": astro.direction(s_az, s_el), "color": sun_col, "intensity": sun_int}
    else:
        key = {"source": "moon", "direction": astro.direction(m_az, m_el), "color": palette["moon"]["color"], "intensity": moon_int}
    shadow = _clamp(1.0 - cloud * 0.9) * _smoothstep(0.0, 0.05, key["intensity"])

    stars = _clamp((1.0 - _smoothstep(-15.0, -6.0, s_el)) * (1.0 - cloud) * (1.0 - 0.6 * m_illum * moon_up))

    weather_age = None if not wx else max(0, int(now - wx["fetched_at"]) // 60)

    return {
        "schema": SCHEMA,
        "version": VERSION,
        "time": {
            "utc": _iso(now),
            "local": _iso(now, offset),
            "utc_offset_s": int(offset),
            "local_hours": _r(local.hour + local.minute / 60.0 + local.second / 3600.0),
            "day_phase": _day_phase(s_el),
            "sunrise": _iso(ev["sunrise"], offset),
            "solar_noon": _iso(ev["solar_noon"], offset),
            "sunset": _iso(ev["sunset"], offset),
            "polar": ev["polar"],
        },
        "location": {"lat": _r(lat, 2), "lon": _r(lon, 2), "source": loc.get("source", "device")},
        "sun": {"azimuth_deg": _r(s_az, 2), "elevation_deg": _r(s_el, 2), "direction": _r3(astro.direction(s_az, s_el))},
        "moon": {"azimuth_deg": _r(m_az, 2), "elevation_deg": _r(m_el, 2), "direction": _r3(astro.direction(m_az, m_el)),
                 "phase": _r(m_phase), "illumination": _r(m_illum)},
        "light": {
            "key": {"source": key["source"], "direction": _r3(key["direction"]), "color": _r3(key["color"]),
                    "intensity": _r(key["intensity"]), "shadow_strength": _r(shadow)},
            "ambient": {"color": _r3(amb_col), "intensity": _r(amb_int)},
        },
        "sky": {"zenith": _r3(zen), "horizon": _r3(hor), "star_visibility": _r(stars)},
        "weather": {
            "condition": condition,
            "wmo_code": int(sample["code"]),
            "cloud_cover": _r(cloud),
            "precipitation": {"type": ptype, "intensity": _r(p_int), "rate_mm_h": _r(rain_rate, 2)},
            "thunder": thunder,
            "fog_density": _r(fog),
            "visibility_m": None if vis is None else round(vis),
            "wind": {"speed_ms": _r(wind_ms, 2), "from_deg": _r(wind_from, 1), "vector_xz": [round(wind_vec[0], 3), round(wind_vec[1], 3)],
                     "strength": _r(_clamp(wind_ms / 15.0))},
            "temperature_c": _r(temp, 1),
            "humidity": None if sample.get("rh") is None else _r(sample["rh"] / 100.0, 3),
        },
        "surface": {"wetness": _r(wetness), "snow_cover": _r(snow_cover)},
        "season": {"name": season["name"], "year_phase": _r(season["year_phase"]),
                   "foliage": _r(season["foliage"]), "autumn_tint": _r(season["autumn_tint"])},
        "meta": {
            "source": source,
            "weather_age_min": weather_age,
            "weather_valid_until": _iso(wx["samples"][-1]["t"] + HORIZON_GRACE_S) if wx and wx["samples"] else None,
        },
    }
