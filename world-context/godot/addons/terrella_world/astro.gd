class_name TerrellaAstro
## Sun and moon positions. Port of reference/terrella_world/astro.py; keep the two in sync.
## Azimuth: degrees clockwise from true north. Elevation: degrees above the horizon.
## Times: unix seconds (UTC).

const SUNRISE_ELEVATION := -0.833
const _RAD := PI / 180.0
const _E := _RAD * 23.4397


static func julian_day(unix_s: float) -> float:
	return unix_s / 86400.0 + 2440587.5


## Returns Vector2(declination_deg, equation_of_time_minutes).
static func _sun_terms(unix_s: float) -> Vector2:
	var t := (julian_day(unix_s) - 2451545.0) / 36525.0
	var l0 := fposmod(280.46646 + t * (36000.76983 + t * 0.0003032), 360.0)
	var m := 357.52911 + t * (35999.05029 - 0.0001537 * t)
	var e := 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
	var c := (sin(m * _RAD) * (1.914602 - t * (0.004817 + 0.000014 * t))
		+ sin(2.0 * m * _RAD) * (0.019993 - 0.000101 * t)
		+ sin(3.0 * m * _RAD) * 0.000289)
	var omega := 125.04 - 1934.136 * t
	var app_long := l0 + c - 0.00569 - 0.00478 * sin(omega * _RAD)
	var eps0 := 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
	var eps := eps0 + 0.00256 * cos(omega * _RAD)
	var decl := asin(sin(eps * _RAD) * sin(app_long * _RAD)) / _RAD
	var y := pow(tan(eps * _RAD / 2.0), 2)
	var l0r := l0 * _RAD
	var mr := m * _RAD
	var eqt := 4.0 / _RAD * (y * sin(2.0 * l0r) - 2.0 * e * sin(mr)
		+ 4.0 * e * y * sin(mr) * cos(2.0 * l0r)
		- 0.5 * y * y * sin(4.0 * l0r) - 1.25 * e * e * sin(2.0 * mr))
	return Vector2(decl, eqt)


static func _refraction(el: float) -> float:
	if el > 85.0:
		return 0.0
	var te := tan(el * _RAD)
	var r: float
	if el > 5.0:
		r = 58.1 / te - 0.07 / pow(te, 3) + 0.000086 / pow(te, 5)
	elif el > -0.575:
		r = 1735.0 + el * (-518.2 + el * (103.4 + el * (-12.79 + el * 0.711)))
	else:
		r = -20.772 / te
	return r / 3600.0


## Returns Vector2(azimuth_deg, elevation_deg) without refraction.
static func _az_el(lat: float, decl: float, hour_angle: float) -> Vector2:
	var la := lat * _RAD
	var de := decl * _RAD
	var ha := hour_angle * _RAD
	var sin_el := sin(la) * sin(de) + cos(la) * cos(de) * cos(ha)
	var el := asin(clampf(sin_el, -1.0, 1.0)) / _RAD
	var az := atan2(sin(ha), cos(ha) * sin(la) - tan(de) * cos(la)) / _RAD + 180.0
	return Vector2(fposmod(az, 360.0), el)


## Vector2(azimuth_deg, elevation_deg), refraction included.
static func sun_position(unix_s: float, lat: float, lon: float) -> Vector2:
	var terms := _sun_terms(unix_s)
	var minutes := fposmod(unix_s, 86400.0) / 60.0
	var tst := fposmod(minutes + terms.y + 4.0 * lon, 1440.0)
	var ae := _az_el(lat, terms.x, tst / 4.0 - 180.0)
	return Vector2(ae.x, ae.y + _refraction(ae.y))


static func _cos_h0(t: float, lat: float) -> float:
	var decl := _sun_terms(t).x
	var la := lat * _RAD
	var de := decl * _RAD
	return (sin(SUNRISE_ELEVATION * _RAD) - sin(la) * sin(de)) / (cos(la) * cos(de))


## {sunrise, solar_noon, sunset, polar} for the local day containing unix_s.
## sunrise/sunset are null in polar night ("night") or midnight sun ("day").
static func sun_events(unix_s: float, lat: float, lon: float, utc_offset_s: int) -> Dictionary:
	var local_midnight_utc := floorf((unix_s + utc_offset_s) / 86400.0) * 86400.0 - utc_offset_s
	var base := (720.0 - 4.0 * lon) * 60.0
	var mean_noon := roundf((local_midnight_utc + 43200.0 - base) / 86400.0) * 86400.0 + base
	var noon := mean_noon
	for _i in 2:
		noon = mean_noon - _sun_terms(noon).y * 60.0
	var c := _cos_h0(noon, lat)
	if absf(c) > 1.0:
		return {"sunrise": null, "solar_noon": noon, "sunset": null, "polar": "night" if c > 1.0 else "day"}
	var events := []
	for sign in [-1.0, 1.0]:
		var t: float = noon + sign * acos(c) / _RAD * 240.0
		for _i in 2:
			var ct := clampf(_cos_h0(t, lat), -1.0, 1.0)
			t = mean_noon - _sun_terms(t).y * 60.0 + sign * acos(ct) / _RAD * 240.0
		events.append(t)
	return {"sunrise": events[0], "solar_noon": noon, "sunset": events[1], "polar": null}


# --- Moon (suncalc.js low precision) ---

static func _ra_dec(l: float, b: float) -> Vector2:
	var ra := atan2(sin(l) * cos(_E) - tan(b) * sin(_E), cos(l))
	var dec := asin(sin(b) * cos(_E) + cos(b) * sin(_E) * sin(l))
	return Vector2(ra, dec)


static func _sun_ra_dec(d: float) -> Vector2:
	var m := _RAD * (357.5291 + 0.98560028 * d)
	var c := _RAD * (1.9148 * sin(m) + 0.02 * sin(2.0 * m) + 0.0003 * sin(3.0 * m))
	return _ra_dec(m + c + _RAD * 102.9372 + PI, 0.0)


## Vector3(ra, dec, distance_km)
static func _moon_coords(d: float) -> Vector3:
	var l := _RAD * (218.316 + 13.176396 * d)
	var m := _RAD * (134.963 + 13.064993 * d)
	var f := _RAD * (93.272 + 13.229350 * d)
	var rd := _ra_dec(l + _RAD * 6.289 * sin(m), _RAD * 5.128 * sin(f))
	return Vector3(rd.x, rd.y, 385001.0 - 20905.0 * cos(m))


## Vector2(azimuth_deg, elevation_deg), topocentric, refraction included.
static func moon_position(unix_s: float, lat: float, lon: float) -> Vector2:
	var d := julian_day(unix_s) - 2451545.0
	var mc := _moon_coords(d)
	var h := _RAD * (280.16 + 360.9856235 * d) + _RAD * lon - mc.x
	var ae := _az_el(lat, mc.y / _RAD, h / _RAD)
	var el := ae.y - asin(6378.14 / mc.z * cos(ae.y * _RAD)) / _RAD
	return Vector2(ae.x, el + _refraction(el))


## Vector2(phase 0..1, illuminated_fraction 0..1). Phase 0 new, 0.5 full.
static func moon_phase(unix_s: float) -> Vector2:
	var d := julian_day(unix_s) - 2451545.0
	var s := _sun_ra_dec(d)
	var m := _moon_coords(d)
	var sdist := 149598000.0
	var phi := acos(clampf(sin(s.y) * sin(m.y) + cos(s.y) * cos(m.y) * cos(s.x - m.x), -1.0, 1.0))
	var inc := atan2(sdist * sin(phi), m.z - sdist * cos(phi))
	var angle := atan2(cos(s.y) * sin(s.x - m.x), sin(s.y) * cos(m.y) - cos(s.y) * sin(m.y) * cos(s.x - m.x))
	var fraction := (1.0 + cos(inc)) / 2.0
	var phase := 0.5 + 0.5 * inc * (-1.0 if angle < 0.0 else 1.0) / PI
	return Vector2(fposmod(phase, 1.0), fraction)


## Unit vector toward the body in scene space: +Y up, +X east, -Z north (Godot forward = north).
static func direction(az_deg: float, el_deg: float) -> Vector3:
	var a := az_deg * _RAD
	var e := el_deg * _RAD
	return Vector3(cos(e) * sin(a), sin(e), -cos(e) * cos(a))
