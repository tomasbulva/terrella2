## Stand-in for dutch_houses.py: a procedural Amsterdam canal on a diorama plinth, merged into a few draw calls.
## Returns anchor points (lamps, puzzle spots, lanes) for the life and puzzle layers.
class_name CanalStreet
extends RefCounted

const LENGTH := 14.0
const CANAL_HALF := 2.1
const STREET := 1.1
const FRONT := CANAL_HALF + STREET   # house fronts sit this far from the canal centre
const DEPTH := 2.6
const PLINTH_HALF_Z := FRONT + DEPTH + 0.3
const WATER_Y := -0.32
const BED_Y := -0.9

const BRICKS := [Color(0.55, 0.22, 0.16), Color(0.45, 0.19, 0.14), Color(0.3, 0.17, 0.13), Color(0.6, 0.3, 0.2)]
const PLASTERS := [Color(0.88, 0.83, 0.7), Color(0.55, 0.6, 0.5), Color(0.47, 0.53, 0.58), Color(0.78, 0.6, 0.34), Color(0.17, 0.22, 0.2), Color(0.72, 0.42, 0.33)]
const DOORS := [Color(0.12, 0.25, 0.18), Color(0.45, 0.1, 0.1), Color(0.08, 0.08, 0.09), Color(0.15, 0.22, 0.38)]
const TRIM := Color(0.93, 0.91, 0.85)
const SLATE := Color(0.24, 0.26, 0.3)
const TERRACOTTA := Color(0.55, 0.27, 0.19)

var rng := RandomNumberGenerator.new()
var b: MeshBuilder
var anchors := {"lamps": [], "puzzle": [], "trees": []}


func build(seed: int) -> Node3D:
	rng.seed = seed
	b = Mats.builder()
	var root := Node3D.new()
	root.name = "CanalStreet"
	_plinth()
	_canal()
	for side in [-1, 1]:
		_row(side)
		_street(side)
	_bridge(3.2)
	var mi := b.build()
	mi.name = "Static"
	root.add_child(mi)
	return root


func _plinth() -> void:
	var wood := Color(0.32, 0.2, 0.13)
	b.add_box("plinth", Transform3D(Basis(), Vector3(0, -1.25, 0)), Vector3(LENGTH + 0.6, 0.7, PLINTH_HALF_Z * 2 + 0.6), wood, false)
	# Quays: brick walls toward the canal, cobbles on top.
	for side in [-1, 1]:
		var zc: float = side * (CANAL_HALF + (PLINTH_HALF_Z - CANAL_HALF) * 0.5)
		var depth: float = PLINTH_HALF_Z - CANAL_HALF
		b.add_box("quay", Transform3D(Basis(), Vector3(0, (BED_Y - 0.01) * 0.5, zc)), Vector3(LENGTH, -BED_Y + 0.01, depth), Color(0.42, 0.24, 0.18))
		# Cobbled street surface, a hair above the quay so it wins the depth test.
		var sz: float = side * (CANAL_HALF + STREET * 0.5)
		b.add_box("cobble", Transform3D(Basis(), Vector3(0, 0.01, sz)), Vector3(LENGTH, 0.02, STREET), Color(0.5, 0.47, 0.44))
		# Quay edge stones.
		b.add_box("trim", Transform3D(Basis(), Vector3(0, 0.03, side * (CANAL_HALF + 0.06))), Vector3(LENGTH, 0.06, 0.14), Color(0.62, 0.6, 0.56))


func _canal() -> void:
	b.add_box("plinth", Transform3D(Basis(), Vector3(0, BED_Y - 0.02, 0)), Vector3(LENGTH, 0.04, CANAL_HALF * 2), Color(0.12, 0.1, 0.08))
	var x0 := -LENGTH * 0.5
	var x1 := LENGTH * 0.5
	b.add_quad("water", Vector3(x0, WATER_Y, -CANAL_HALF), Vector3(x1, WATER_Y, -CANAL_HALF), Vector3(x1, WATER_Y, CANAL_HALF), Vector3(x0, WATER_Y, CANAL_HALF), Vector3.UP, Color.WHITE)
	# Cut-away resin faces where the canal leaves the plinth.
	for x in [x0, x1]:
		var n := Vector3(signf(x), 0, 0)
		b.add_quad("resin", Vector3(x, BED_Y, -CANAL_HALF), Vector3(x, BED_Y, CANAL_HALF), Vector3(x, WATER_Y, CANAL_HALF), Vector3(x, WATER_Y, -CANAL_HALF), n, Color.WHITE)
	# Water plants in the resin.
	for i in 10:
		var x := (x0 + 0.15) if i < 5 else (x1 - 0.15)
		var z := rng.randf_range(-CANAL_HALF + 0.2, CANAL_HALF - 0.2)
		b.add_blob("foliage", Transform3D(Basis().scaled(Vector3(0.06, rng.randf_range(0.15, 0.3), 0.06)), Vector3(x, BED_Y + 0.12, z)), 1.0, Color(0.2, 0.42, 0.22), 3, 5, i)


func _row(side: int) -> void:
	var x := -LENGTH * 0.5 + 0.25
	var idx := 0
	while x < LENGTH * 0.5 - 0.9:
		var w := rng.randf_range(1.0, 1.55)
		if x + w > LENGTH * 0.5 - 0.2:
			w = LENGTH * 0.5 - 0.2 - x
			if w < 0.8:
				break
		var cx := x + w * 0.5
		var base := Transform3D(Basis(), Vector3(cx, 0, side * FRONT))
		if side > 0:
			base = Transform3D(Basis(Vector3.UP, PI), Vector3(cx, 0, side * FRONT))
		_house(base, w - 0.04, idx * 7 + (1 if side > 0 else 0))
		x += w
		idx += 1


## One canal house, built straight in local space (front at z=0 facing +z), then leaned as a whole.
func _house(base: Transform3D, w: float, id: int) -> void:
	var floors := rng.randi_range(3, 5)
	var ground_h := 0.9
	var floor_h := 0.64
	var body_h := ground_h + floor_h * (floors - 1)
	var is_brick := rng.randf() < 0.55
	var wall_key := "brick" if is_brick else "plaster"
	var wall_col: Color = BRICKS[rng.randi() % BRICKS.size()] if is_brick else PLASTERS[rng.randi() % PLASTERS.size()]
	# Lean forward toward the canal, with a little sideways list: the Amsterdam look.
	var lean := rng.randf_range(0.015, 0.05)
	var list := rng.randf_range(-0.02, 0.02)
	var shear := Basis(Vector3(1, 0, 0), Vector3(list, 1, lean), Vector3(0, 0, 1))
	var xf := base * Transform3D(shear, Vector3.ZERO)

	b.add_box(wall_key, xf * _t(0, body_h * 0.5, -DEPTH * 0.5), Vector3(w, body_h, DEPTH), wall_col)
	# Plinth band and floor cornices.
	b.add_box("trim", xf * _t(0, 0.08, 0.02), Vector3(w + 0.02, 0.16, 0.06), Color(0.35, 0.33, 0.32))
	for f in range(1, floors):
		b.add_box("trim", xf * _t(0, ground_h + floor_h * (f - 1) - 0.02, 0.015), Vector3(w, 0.04, 0.04), TRIM)

	_windows(xf, w, floors, ground_h, floor_h, id)
	_gable(xf, w, body_h, wall_key, wall_col)

	# Chimney.
	if rng.randf() < 0.7:
		b.add_box("brick", xf * _t(rng.randf_range(-w * 0.3, w * 0.3), body_h + 0.55, -DEPTH * 0.6), Vector3(0.18, 0.7, 0.22), Color(0.4, 0.2, 0.15))
	# Ivy climbing some facades.
	if rng.randf() < 0.3:
		var ix := rng.randf_range(-w * 0.4, w * 0.4)
		for k in 6:
			b.add_blob("foliage", xf * _t(ix + rng.randf_range(-0.12, 0.12), 0.25 + k * 0.32, 0.04), 0.17, Color(0.18, 0.36, 0.16), 3, 6, id * 10 + k)


func _windows(xf: Transform3D, w: float, floors: int, ground_h: float, floor_h: float, id: int) -> void:
	var cols := 2 if w < 1.25 else 3
	var shutter_col: Color = DOORS[rng.randi() % DOORS.size()]
	var has_shutters := rng.randf() < 0.4
	var has_boxes := rng.randf() < 0.5
	for f in range(1, floors):
		var y := ground_h + floor_h * (f - 1) + floor_h * 0.5
		var wh := 0.44 if f == 1 else 0.4
		for c in cols:
			var x := (c - (cols - 1) * 0.5) * (w / cols)
			b.add_box("trim", xf * _t(x, y, 0.012), Vector3(0.32, wh + 0.08, 0.03), TRIM)
			b.add_box("window", xf * _t(x, y, 0.03), Vector3(0.25, wh, 0.02), Color.WHITE)
			# Glazing bars.
			b.add_box("trim", xf * _t(x, y, 0.045), Vector3(0.018, wh, 0.01), TRIM)
			b.add_box("trim", xf * _t(x, y + wh * 0.15, 0.045), Vector3(0.25, 0.018, 0.01), TRIM)
			if has_shutters:
				for s in [-1, 1]:
					b.add_box("trim", xf * _t(x + s * 0.2, y, 0.02), Vector3(0.09, wh, 0.02), shutter_col)
			if has_boxes and f == 1:
				b.add_box("wood", xf * _t(x, y - wh * 0.5 - 0.06, 0.08), Vector3(0.3, 0.07, 0.1), Color(0.3, 0.2, 0.12))
				for k in 3:
					var fc: Color = [Color(0.85, 0.2, 0.25), Color(0.95, 0.6, 0.75), Color(0.95, 0.85, 0.3)][k]
					b.add_blob("foliage", xf * _t(x - 0.09 + k * 0.09, y - wh * 0.5 - 0.01, 0.09), 0.06, fc, 3, 5, id * 100 + c * 10 + k)
	# Ground floor: door, stoep steps, shop window, lantern.
	var door_x := (w * 0.5 - 0.3) * (1 if rng.randf() < 0.5 else -1)
	b.add_box("trim", xf * _t(door_x, 0.42, 0.012), Vector3(0.36, 0.78, 0.03), TRIM)
	b.add_box("wood", xf * _t(door_x, 0.39, 0.025), Vector3(0.28, 0.7, 0.02), DOORS[rng.randi() % DOORS.size()])
	b.add_box("trim", xf * _t(door_x, 0.06, 0.12), Vector3(0.4, 0.12, 0.22), Color(0.55, 0.53, 0.5))
	var shop_x := -door_x * 0.6
	b.add_box("trim", xf * _t(shop_x, 0.5, 0.012), Vector3(w * 0.45, 0.58, 0.03), TRIM)
	b.add_box("window", xf * _t(shop_x, 0.5, 0.03), Vector3(w * 0.42, 0.52, 0.02), Color.WHITE)
	b.add_box("glow", xf * _t(door_x + 0.24, 0.72, 0.06), Vector3(0.06, 0.1, 0.06), Color.WHITE)


func _gable(xf: Transform3D, w: float, body_h: float, wall_key: String, wall_col: Color) -> void:
	var kind := rng.randi() % 4
	var roof_col := SLATE if rng.randf() < 0.6 else TERRACOTTA
	var roof_h := w * 0.75
	# Roof behind the gable, ridge running front to back.
	b.add_prism("roof", xf * _t(0, body_h, -DEPTH * 0.5 - 0.1), w + 0.06, roof_h, DEPTH - 0.1, roof_col)
	match kind:
		0:  # Step gable.
			var steps := 4
			for s in steps:
				var sw := w * (1.0 - float(s + 1) / (steps + 1))
				var sh := roof_h / steps
				b.add_box(wall_key, xf * _t(0, body_h + sh * (s + 0.5), -0.12), Vector3(sw + w / (steps + 1), sh, 0.24), wall_col)
				for side in [-1, 1]:
					b.add_box("trim", xf * _t(side * (sw + w / (steps + 1)) * 0.5, body_h + sh * (s + 1) + 0.02, -0.12), Vector3(0.1, 0.04, 0.26), TRIM)
		1:  # Neck gable with shoulders.
			b.add_prism(wall_key, xf * _t(0, body_h, -0.12), w, roof_h * 0.45, 0.24, wall_col)
			b.add_box(wall_key, xf * _t(0, body_h + roof_h * 0.62, -0.12), Vector3(w * 0.42, roof_h * 0.5, 0.24), wall_col)
			b.add_prism("trim", xf * _t(0, body_h + roof_h * 0.87, -0.12), w * 0.5, 0.18, 0.26, TRIM)
			b.add_box("window", xf * _t(0, body_h + roof_h * 0.6, 0.0), Vector3(0.18, 0.26, 0.02), Color.WHITE)
		2:  # Spout gable.
			b.add_prism(wall_key, xf * _t(0, body_h, -0.12), w, roof_h, 0.24, wall_col)
			b.add_box("window", xf * _t(0, body_h + roof_h * 0.35, 0.0), Vector3(0.2, 0.28, 0.02), Color.WHITE)
		3:  # Flat cornice.
			b.add_box(wall_key, xf * _t(0, body_h + 0.2, -0.12), Vector3(w, 0.4, 0.24), wall_col)
			b.add_box("trim", xf * _t(0, body_h + 0.42, -0.08), Vector3(w + 0.1, 0.08, 0.36), TRIM)
	# Hoisting beam.
	b.add_box("wood", xf * _t(0, body_h + roof_h * 0.45 + (0.0 if kind != 3 else -0.1), 0.12), Vector3(0.06, 0.06, 0.34), Color(0.2, 0.14, 0.1))


func _street(side: int) -> void:
	var z := side * (CANAL_HALF + 0.3)
	var x := -LENGTH * 0.5 + 1.1
	var n := 0
	while x < LENGTH * 0.5 - 0.6:
		if n % 2 == 0:
			_tree(Vector3(x, 0, z), n + (50 if side > 0 else 0))
		else:
			_lamp(Vector3(x, 0, z))
		# Bollards along the quay edge.
		for k in 3:
			b.add_cylinder("props", Transform3D(Basis(), Vector3(x + 0.35 + k * 0.25, 0, side * (CANAL_HALF + 0.12))), 0.03, 0.18, Color(0.35, 0.12, 0.1), 6)
		x += 2.3 + rng.randf_range(-0.2, 0.3)
		n += 1


func _tree(p: Vector3, id: int) -> void:
	b.add_cylinder("wood", Transform3D(Basis(), p), 0.07, 1.3, Color(0.3, 0.22, 0.16), 6)
	var crown := Color(0.28, 0.45, 0.2).lerp(Color(0.38, 0.52, 0.22), rng.randf())
	for k in 3:
		var o := Vector3(rng.randf_range(-0.25, 0.25), 1.45 + k * 0.28, rng.randf_range(-0.18, 0.18))
		b.add_blob("foliage", Transform3D(Basis().scaled(Vector3(1, 0.85, 1)), p + o), rng.randf_range(0.42, 0.55), crown, 4, 8, id * 3 + k)
	anchors["trees"].append(p)


func _lamp(p: Vector3) -> void:
	var post := Color(0.09, 0.12, 0.11)
	b.add_cylinder("props", Transform3D(Basis(), p), 0.035, 1.25, post, 6)
	b.add_box("props", Transform3D(Basis(), p + Vector3(0, 1.3, 0)), Vector3(0.16, 0.06, 0.16), post)
	b.add_box("glow", Transform3D(Basis(), p + Vector3(0, 1.39, 0)), Vector3(0.12, 0.14, 0.12), Color.WHITE)
	b.add_prism("props", Transform3D(Basis(), p + Vector3(0, 1.46, 0)), 0.2, 0.1, 0.2, post)
	anchors["lamps"].append(p + Vector3(0, 1.39, 0))


func _bridge(x: float) -> void:
	var stone := Color(0.52, 0.32, 0.24)
	var deck_y := 0.12
	b.add_box("cobble", Transform3D(Basis(), Vector3(x, deck_y, 0)), Vector3(1.3, 0.1, CANAL_HALF * 2 + 0.4), Color(0.5, 0.47, 0.44))
	# Arch: a few boxes stepping down to the water.
	for k in 5:
		var a := (k + 0.5) / 5.0 * PI
		var z := -cos(a) * CANAL_HALF
		var h := sin(a) * 0.35
		b.add_box("quay", Transform3D(Basis(), Vector3(x, deck_y - 0.05 - (0.35 - h) * 0.5 - 0.02, z)), Vector3(1.3, 0.1 + (0.35 - h), CANAL_HALF * 2 / 5.0 + 0.01), stone)
	for s in [-1, 1]:
		b.add_box("props", Transform3D(Basis(), Vector3(x + s * 0.6, deck_y + 0.25, 0)), Vector3(0.05, 0.04, CANAL_HALF * 2 + 0.4), Color(0.1, 0.12, 0.11))
		for k in 7:
			b.add_box("props", Transform3D(Basis(), Vector3(x + s * 0.6, deck_y + 0.13, -CANAL_HALF - 0.1 + k * 0.53)), Vector3(0.03, 0.22, 0.03), Color(0.1, 0.12, 0.11))
	anchors["bridge"] = Vector3(x, deck_y + 0.06, 0)


static func _t(x: float, y: float, z: float) -> Transform3D:
	return Transform3D(Basis(), Vector3(x, y, z))
