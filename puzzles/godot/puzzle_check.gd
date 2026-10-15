## Port of terrella_puzzles/check.py. Pure logic: no nodes, no scene access.
## Must pass fixtures/check_vectors.json (run godot/tests/run_vectors.gd).
## Result: {"solved": bool, "progress": float 0..1, "feedback": String}
class_name PuzzleCheck
extends RefCounted


static func _result(solved: bool, progress: float, feedback: String) -> Dictionary:
	return {"solved": solved, "progress": snappedf(progress, 0.0001), "feedback": feedback}


static func _sub(a: Array, b: Array) -> Vector3:
	return Vector3(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2]))


static func _angle_between(u: Vector3, v: Vector3) -> float:
	if u.length() == 0.0 or v.length() == 0.0:
		return 180.0
	return rad_to_deg(acos(clampf(u.dot(v) / (u.length() * v.length()), -1.0, 1.0)))


static func check(instance: Dictionary, attempt: Dictionary) -> Dictionary:
	var t: String = instance["type"]
	var s: Dictionary = instance["solution"]
	match t:
		"riddle":
			if not attempt.has("select") or attempt["select"] == null:
				return _result(false, 0.0, "invalid")
			var ok: bool = attempt["select"] == s["answer"]
			return _result(ok, 1.0 if ok else 0.0, "solved" if ok else "wrong")

		"trail":
			var picks = attempt.get("selects")
			if not picks is Array:
				return _result(false, 0.0, "invalid")
			var answers: Array = s["answers"]
			var good := 0
			for i in range(mini(picks.size(), answers.size())):
				if picks[i] != answers[i]:
					break
				good += 1
			if good == answers.size():
				return _result(true, 1.0, "solved")
			var fb := "wrong" if picks.size() > good else "keep_going"
			return _result(false, float(good) / answers.size(), fb)

		"seek":
			var found = attempt.get("found")
			if not found is Array:
				return _result(false, 0.0, "invalid")
			var targets: Array = s["targets"]
			var hit := 0
			for tg in targets:
				if tg in found:
					hit += 1
			if hit == targets.size():
				return _result(true, 1.0, "solved")
			return _result(false, float(hit) / targets.size(), "keep_going")

		"pattern":
			var presses = attempt.get("presses")
			if not presses is Array:
				return _result(false, 0.0, "invalid")
			var cells: Array = s["cells"]
			var index := {}
			for i in range(cells.size()):
				index[cells[i]] = i
			var state: Array = s["start"].duplicate()
			var neighbors: Dictionary = s["neighbors"]
			for p in presses:
				if not index.has(p):
					return _result(false, 0.0, "invalid")
				var flips: Array = [p]
				flips.append_array(neighbors.get(p, []))
				for c in flips:
					var i: int = index[c]
					state[i] = not state[i]
			var target: Array = s["target"]
			var matching := 0
			for i in range(cells.size()):
				if state[i] == target[i]:
					matching += 1
			var solved := matching == cells.size()
			return _result(solved, float(matching) / cells.size(), "solved" if solved else "keep_going")

		"viewpoint":
			var eye = attempt.get("eye")
			var look = attempt.get("look_at")
			if not (eye is Array and look is Array and eye.size() == 3 and look.size() == 3):
				return _result(false, 0.0, "invalid")
			var pose: Dictionary = s["pose"]
			var tol: Dictionary = s["tolerance"]
			var d_eye := _sub(eye, pose["eye"]).length() / float(tol["eye_m"])
			var d_ang := _angle_between(_sub(look, eye), _sub(pose["look_at"], pose["eye"])) / float(tol["angle_deg"])
			var worst := maxf(d_eye, d_ang)
			if worst <= 1.0:
				return _result(true, 1.0, "solved")
			var progress := maxf(0.0, 1.0 - (worst - 1.0) / 3.0)
			var prev = attempt.get("previous_progress")
			var fb := "warmer" if prev == null or progress >= float(prev) else "colder"
			return _result(false, progress, fb)

	push_error("unknown puzzle type %s" % t)
	return _result(false, 0.0, "invalid")
