extends SceneTree
## Headless test runner: checks the GDScript port against the Python reference's
## golden vectors (testdata/golden) and the policy table.
##   godot --headless --path godot --script res://tests/run_tests.gd

const TOL := 2e-3
var _failures := 0
var _checks := 0


func _init() -> void:
	var root := ProjectSettings.globalize_path("res://").path_join("../")
	var palette: Dictionary = _load_json(root.path_join("palette/default.json"))
	_checks += 1
	if _load_json(TerrellaWorldContext.DEFAULT_PALETTE) != palette:
		_fail("addons/terrella_world/default_palette.json is out of sync with palette/default.json")
	var golden_dir := root.path_join("testdata/golden")
	var files := Array(DirAccess.get_files_at(golden_dir)).filter(func(f): return f.ends_with(".json"))
	files.sort()
	for f in files:
		var g: Dictionary = _load_json(golden_dir.path_join(f))
		var got := TerrellaSceneState.derive(g["inputs"], g["now"], palette)
		var before := _failures
		_compare(g["expected"], got, f.get_basename())
		print("%s %s" % ["ok  " if _failures == before else "FAIL", f.get_basename()])
	_test_parse(root)
	_test_policy()
	_test_adapter(root, palette)
	print("%d checks, %d failures" % [_checks, _failures])
	quit(1 if _failures > 0 else 0)


func _load_json(path: String) -> Variant:
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _fail(msg: String) -> void:
	_failures += 1
	printerr("  ", msg)


func _compare(exp: Variant, got: Variant, path: String) -> void:
	_checks += 1
	if exp is Dictionary:
		if not got is Dictionary:
			return _fail("%s: expected object" % path)
		for k in exp:
			if not got.has(k):
				_fail("%s.%s missing" % [path, k])
			else:
				_compare(exp[k], got[k], "%s.%s" % [path, k])
		for k in got:
			if not exp.has(k):
				_fail("%s.%s unexpected" % [path, k])
	elif exp is Array:
		if not got is Array or got.size() != exp.size():
			return _fail("%s: array mismatch %s vs %s" % [path, exp, got])
		for i in exp.size():
			_compare(exp[i], got[i], "%s[%d]" % [path, i])
	elif exp is float or exp is int:
		if not (got is float or got is int) or absf(float(exp) - float(got)) > TOL:
			_fail("%s: %s != %s" % [path, exp, got])
	elif exp != got:
		_fail("%s: %s != %s" % [path, exp, got])


func _test_parse(root: String) -> void:
	var resp: Dictionary = _load_json(root.path_join("testdata/openmeteo/amsterdam_winter_snow_morning.json"))
	var g: Dictionary = _load_json(root.path_join("testdata/golden/amsterdam_winter_snow_morning.json"))
	var wx := TerrellaOpenMeteo.parse_response(resp, int(g["inputs"]["weather"]["fetched_at"]))
	_compare(g["inputs"]["weather"], wx, "parse")
	_checks += 1
	if TerrellaOpenMeteo.request_url(52.35, 4.9).find("latitude=52.35&longitude=4.90&") < 0:
		_fail("request_url")


func _test_policy() -> void:
	var loc := {"lat": 52.35, "lon": 4.9}
	var wx := func(fetched: int, lat := 52.35, horizon_h := 48) -> Dictionary:
		return {"fetched_at": fetched, "lat": lat, "lon": 4.9, "samples": [{"t": fetched + horizon_h * 3600, "code": 0}]}
	var cases := [
		[TerrellaPolicy.decide(0, null, null), false, "no_location"],
		[TerrellaPolicy.decide(0, loc, null), true, "empty"],
		[TerrellaPolicy.decide(0, loc, wx.call(0)), false, "fresh"],
		[TerrellaPolicy.decide(0, loc, wx.call(-3700)), true, "stale"],
		[TerrellaPolicy.decide(0, loc, wx.call(0, 52.6)), true, "moved"],
		[TerrellaPolicy.decide(0, loc, wx.call(-600, 52.35, 10)), true, "horizon"],
		[TerrellaPolicy.decide(0, loc, null, null, 0, false), false, "offline"],
		[TerrellaPolicy.decide(0, loc, null, -600, 1), false, "backoff"],
		[TerrellaPolicy.decide(0, loc, null, -1000, 1), true, "empty"],
		[TerrellaPolicy.decide(0, loc, null, -3000, 3), false, "backoff"],
	]
	for c in cases:
		_checks += 1
		if c[0]["fetch"] != c[1] or c[0]["reason"] != c[2]:
			_fail("policy %s -> %s" % [c[2], c[0]])
	_checks += 1
	if TerrellaPolicy.coarsen(52.3712, 4.8952) != [52.35, 4.9]:
		_fail("coarsen %s" % TerrellaPolicy.coarsen(52.3712, 4.8952))


func _test_adapter(root: String, palette: Dictionary) -> void:
	var g: Dictionary = _load_json(root.path_join("testdata/golden/amsterdam_summer_noon_clear.json"))
	var state := TerrellaSceneState.derive(g["inputs"], g["now"], palette)
	var light := DirectionalLight3D.new()
	var env := Environment.new()
	env.sky = Sky.new()
	env.sky.sky_material = ProceduralSkyMaterial.new()
	TerrellaSceneAdapter.apply(state, light, env)
	_checks += 1
	# The light's -Z must point away from the sun.
	var toward_sun := TerrellaSceneState.to_vec3(state["sun"]["direction"])
	if (-light.basis.z).dot(-toward_sun) < 0.999:
		_fail("adapter: light points %s, sun at %s" % [-light.basis.z, toward_sun])
	light.free()
