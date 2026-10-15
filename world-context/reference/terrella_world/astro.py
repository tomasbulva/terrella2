"""Sun and moon positions. Pure math, no dependencies.

Sun: NOAA solar calculator equations (accurate to well under 0.1 deg and ~1 min
for sunrise/sunset between +/-72 deg latitude).
Moon: the low-precision series used by suncalc.js (~1 deg), plenty for lighting.

Angles: azimuth in degrees clockwise from true north, elevation in degrees above
the horizon. Times are unix seconds (UTC).
"""
from __future__ import annotations

import math

RAD = math.pi / 180.0
SUNRISE_ELEVATION = -0.833  # upper limb + standard refraction


def julian_day(unix_s: float) -> float:
    return unix_s / 86400.0 + 2440587.5


def _sun_terms(unix_s: float) -> tuple[float, float]:
    """Return (declination_deg, equation_of_time_minutes)."""
    t = (julian_day(unix_s) - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(m * RAD) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * m * RAD) * (0.019993 - 0.000101 * t)
         + math.sin(3 * m * RAD) * 0.000289)
    omega = 125.04 - 1934.136 * t
    app_long = l0 + c - 0.00569 - 0.00478 * math.sin(omega * RAD)
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(omega * RAD)
    decl = math.asin(math.sin(eps * RAD) * math.sin(app_long * RAD)) / RAD
    y = math.tan(eps * RAD / 2.0) ** 2
    l0r, mr = l0 * RAD, m * RAD
    eqt = 4.0 / RAD * (y * math.sin(2 * l0r) - 2 * e * math.sin(mr)
                       + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                       - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    return decl, eqt


def _refraction(el: float) -> float:
    """Approximate atmospheric refraction in degrees (NOAA)."""
    if el > 85.0:
        return 0.0
    te = math.tan(el * RAD)
    if el > 5.0:
        r = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
    elif el > -0.575:
        r = 1735.0 + el * (-518.2 + el * (103.4 + el * (-12.79 + el * 0.711)))
    else:
        r = -20.772 / te
    return r / 3600.0


def _az_el(lat: float, decl: float, hour_angle: float) -> tuple[float, float]:
    la, de, ha = lat * RAD, decl * RAD, hour_angle * RAD
    sin_el = math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(ha)
    el = math.asin(max(-1.0, min(1.0, sin_el))) / RAD
    az = math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(de) * math.cos(la)) / RAD + 180.0
    return az % 360.0, el


def sun_position(unix_s: float, lat: float, lon: float) -> tuple[float, float]:
    """(azimuth_deg, elevation_deg), elevation includes refraction."""
    decl, eqt = _sun_terms(unix_s)
    minutes = (unix_s % 86400.0) / 60.0
    tst = (minutes + eqt + 4.0 * lon) % 1440.0
    ha = tst / 4.0 - 180.0
    az, el = _az_el(lat, decl, ha)
    return az, el + _refraction(el)


def sun_events(unix_s: float, lat: float, lon: float, utc_offset_s: int) -> dict:
    """Sunrise, solar noon and sunset (unix s) for the local calendar day containing unix_s.

    sunrise/sunset are None during polar night or midnight sun; `polar` says which.
    """
    local_midnight_utc = math.floor((unix_s + utc_offset_s) / 86400.0) * 86400.0 - utc_offset_s
    # Mean solar noon nearest to local clock noon, then corrected by the equation of time.
    base = (720.0 - 4.0 * lon) * 60.0
    mean_noon = round((local_midnight_utc + 43200.0 - base) / 86400.0) * 86400.0 + base
    noon = mean_noon
    for _ in range(2):
        _, eqt = _sun_terms(noon)
        noon = mean_noon - eqt * 60.0

    def cos_h0(t):
        decl, _ = _sun_terms(t)
        la, de = lat * RAD, decl * RAD
        return (math.sin(SUNRISE_ELEVATION * RAD) - math.sin(la) * math.sin(de)) / (math.cos(la) * math.cos(de))

    c = cos_h0(noon)
    if abs(c) > 1.0:
        return {"sunrise": None, "solar_noon": noon, "sunset": None, "polar": "night" if c > 1.0 else "day"}
    events = []
    for sign in (-1.0, 1.0):
        # Refine with declination and equation of time at the event itself (matters near equinoxes at high latitude).
        t = noon + sign * math.acos(c) / RAD * 240.0
        for _ in range(2):
            ct = max(-1.0, min(1.0, cos_h0(t)))
            _, eqt = _sun_terms(t)
            t = mean_noon - eqt * 60.0 + sign * math.acos(ct) / RAD * 240.0
        events.append(t)
    return {"sunrise": events[0], "solar_noon": noon, "sunset": events[1], "polar": None}


# --- Moon (suncalc.js low precision) -------------------------------------------------

_E = RAD * 23.4397


def _ra_dec(l: float, b: float) -> tuple[float, float]:
    ra = math.atan2(math.sin(l) * math.cos(_E) - math.tan(b) * math.sin(_E), math.cos(l))
    dec = math.asin(math.sin(b) * math.cos(_E) + math.cos(b) * math.sin(_E) * math.sin(l))
    return ra, dec


def _sun_ra_dec(d: float) -> tuple[float, float]:
    m = RAD * (357.5291 + 0.98560028 * d)
    c = RAD * (1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m))
    l = m + c + RAD * 102.9372 + math.pi
    return _ra_dec(l, 0.0)


def _moon_coords(d: float) -> tuple[float, float, float]:
    l = RAD * (218.316 + 13.176396 * d)
    m = RAD * (134.963 + 13.064993 * d)
    f = RAD * (93.272 + 13.229350 * d)
    lon = l + RAD * 6.289 * math.sin(m)
    lat = RAD * 5.128 * math.sin(f)
    dist = 385001.0 - 20905.0 * math.cos(m)
    ra, dec = _ra_dec(lon, lat)
    return ra, dec, dist


def moon_position(unix_s: float, lat: float, lon: float) -> tuple[float, float]:
    """(azimuth_deg, elevation_deg), topocentric, with refraction."""
    d = julian_day(unix_s) - 2451545.0
    ra, dec, dist = _moon_coords(d)
    sidereal = RAD * (280.16 + 360.9856235 * d) + RAD * lon
    h = sidereal - ra
    az, el = _az_el(lat, dec / RAD, h / RAD)
    el -= math.asin(6378.14 / dist * math.cos(el * RAD)) / RAD  # topocentric parallax
    return az, el + _refraction(el)


def moon_phase(unix_s: float) -> tuple[float, float]:
    """(phase 0..1, illuminated_fraction 0..1). Phase: 0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter."""
    d = julian_day(unix_s) - 2451545.0
    s_ra, s_dec = _sun_ra_dec(d)
    m_ra, m_dec, m_dist = _moon_coords(d)
    sdist = 149598000.0
    phi = math.acos(max(-1.0, min(1.0, math.sin(s_dec) * math.sin(m_dec)
                                  + math.cos(s_dec) * math.cos(m_dec) * math.cos(s_ra - m_ra))))
    inc = math.atan2(sdist * math.sin(phi), m_dist - sdist * math.cos(phi))
    angle = math.atan2(math.cos(s_dec) * math.sin(s_ra - m_ra),
                       math.sin(s_dec) * math.cos(m_dec) - math.cos(s_dec) * math.sin(m_dec) * math.cos(s_ra - m_ra))
    fraction = (1.0 + math.cos(inc)) / 2.0
    phase = 0.5 + 0.5 * inc * (-1.0 if angle < 0 else 1.0) / math.pi
    return phase % 1.0, fraction


def direction(az_deg: float, el_deg: float) -> list[float]:
    """Unit vector toward the body in scene space: +Y up, +X east, -Z north (Godot convention)."""
    a, e = az_deg * RAD, el_deg * RAD
    return [math.cos(e) * math.sin(a), math.sin(e), -math.cos(e) * math.cos(a)]
