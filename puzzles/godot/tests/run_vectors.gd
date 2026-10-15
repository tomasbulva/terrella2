## Headless conformance run:
##   godot --headless --path puzzles/godot --script res://tests/run_vectors.gd
## Exits 0 when every case in fixtures/check_vectors.json matches.
extends SceneTree

const PuzzleCheckScript = preload("res://puzzle_check.gd")


func _init() -> void:
	var path := ProjectSettings.globalize_path("res://").path_join("../fixtures/check_vectors.json")
	var text := FileAccess.get_file_as_string(path)
	var data = JSON.parse_string(text)
	if data == null:
		printerr("cannot read %s" % path)
		quit(2)
		return
	var failures := 0
	for c in data["cases"]:
		var inst: Dictionary = data["instances"][c["instance_id"]]
		var got: Dictionary = PuzzleCheckScript.check(inst, c["attempt"])
		var exp: Dictionary = c["expected"]
		# progress is display-only; allow last-digit rounding differences between languages.
		var same: bool = got["solved"] == exp["solved"] and got["feedback"] == exp["feedback"] \
			and absf(float(got["progress"]) - float(exp["progress"])) <= 0.0001
		if not same:
			failures += 1
			printerr("FAIL %s: got %s expected %s" % [c["name"], got, exp])
	print("%d/%d vectors passed" % [data["cases"].size() - failures, data["cases"].size()])
	quit(1 if failures else 0)
