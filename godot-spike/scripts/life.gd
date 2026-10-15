## Moving things that make the diorama feel alive: a boat, bikes, people, ducks, drifting clouds.
class_name Life
extends Node3D

var _movers := []   # {node, axis_from, axis_to, speed, t, bob, kind}
var _clouds := []
var cloud_cover := 0.3
var _time := 0.0


## kit_mode: the pipeline diorama has its own canal layout, so only clouds (and its own static props) are used.
func setup(seed: int, kit_mode := false) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	if kit_mode:
		for i in 6:
			_add_cloud(rng, i)
			_clouds[i].node.position.y += 2.5   # kit houses are taller than the stand-in
		return
	_add_boat(rng)
	for i in 4:
		_add_bike(rng, i)
	for i in 7:
		_add_person(rng, i)
	for i in 4:
		_add_duck(rng, i)
	for i in 6:
		_add_cloud(rng, i)


func _mi(b: MeshBuilder, name: String) -> MeshInstance3D:
	var mi := b.build()
	mi.name = name
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	return mi


func _add_boat(rng: RandomNumberGenerator) -> void:
	var b := Mats.builder()
	var hull := Color(0.18, 0.28, 0.38)
	b.add_box("wood", Transform3D(Basis(), Vector3(0, 0.05, 0)), Vector3(1.5, 0.16, 0.5), hull)
	b.add_box("wood", Transform3D(Basis(), Vector3(0, 0.14, 0)), Vector3(1.4, 0.03, 0.42), Color(0.55, 0.38, 0.22))
	b.add_box("trim", Transform3D(Basis(), Vector3(-0.15, 0.3, 0)), Vector3(0.6, 0.28, 0.36), Color(0.9, 0.88, 0.8))
	b.add_box("window", Transform3D(Basis(), Vector3(-0.15, 0.33, 0.185)), Vector3(0.45, 0.1, 0.01), Color.WHITE)
	b.add_box("window", Transform3D(Basis(), Vector3(-0.15, 0.33, -0.185)), Vector3(0.45, 0.1, 0.01), Color.WHITE)
	b.add_box("roof", Transform3D(Basis(), Vector3(-0.15, 0.46, 0)), Vector3(0.66, 0.04, 0.42), Color(0.5, 0.2, 0.15))
	var boat := Node3D.new()
	boat.name = "Boat"
	boat.add_child(_mi(b, "Mesh"))
	add_child(boat)
	_movers.append({"node": boat, "from": Vector3(-8.5, CanalStreet.WATER_Y + 0.02, 0.7), "to": Vector3(8.5, CanalStreet.WATER_Y + 0.02, 0.7), "speed": 0.45, "t": rng.randf(), "bob": 0.02, "kind": "boat"})


func _add_bike(rng: RandomNumberGenerator, i: int) -> void:
	var b := Mats.builder()
	var frame: Color = [Color(0.1, 0.1, 0.1), Color(0.6, 0.12, 0.1), Color(0.15, 0.3, 0.45), Color(0.85, 0.82, 0.7)][i % 4]
	for x in [-0.14, 0.14]:
		b.add_cylinder("props", Transform3D(Basis(Vector3.RIGHT, PI * 0.5), Vector3(x, 0.11, 0.01)), 0.1, 0.02, Color(0.08, 0.08, 0.08), 10)
	b.add_box("props", Transform3D(Basis(), Vector3(0, 0.18, 0)), Vector3(0.28, 0.025, 0.025), frame)
	b.add_box("props", Transform3D(Basis(Vector3.BACK, 0.4), Vector3(-0.05, 0.24, 0)), Vector3(0.025, 0.16, 0.025), frame)
	# Rider.
	var shirt: Color = Color.from_hsv(rng.randf(), 0.45, 0.75)
	b.add_box("plaster", Transform3D(Basis(), Vector3(-0.04, 0.42, 0)), Vector3(0.1, 0.2, 0.12), shirt)
	b.add_blob("plaster", Transform3D(Basis(), Vector3(-0.02, 0.58, 0)), 0.055, Color(0.9, 0.75, 0.62), 3, 6, i)
	b.add_box("plaster", Transform3D(Basis(), Vector3(-0.03, 0.27, 0)), Vector3(0.06, 0.14, 0.1), Color(0.2, 0.22, 0.3))
	var bike := Node3D.new()
	bike.name = "Bike%d" % i
	bike.add_child(_mi(b, "Mesh"))
	add_child(bike)
	var side := -1.0 if i % 2 == 0 else 1.0
	var z := side * (CanalStreet.CANAL_HALF + 0.5)
	var dir := 1.0 if i < 2 else -1.0
	var from := Vector3(-7.0 * dir, 0.02, z)
	var to := Vector3(7.0 * dir, 0.02, z)
	_movers.append({"node": bike, "from": from, "to": to, "speed": rng.randf_range(0.5, 0.75), "t": rng.randf(), "bob": 0.005, "kind": "bike"})


func _add_person(rng: RandomNumberGenerator, i: int) -> void:
	var b := Mats.builder()
	var coat: Color = Color.from_hsv(rng.randf(), rng.randf_range(0.3, 0.6), rng.randf_range(0.35, 0.8))
	b.add_box("plaster", Transform3D(Basis(), Vector3(0, 0.27, 0)), Vector3(0.12, 0.26, 0.1), coat)
	b.add_box("plaster", Transform3D(Basis(), Vector3(0, 0.08, 0)), Vector3(0.09, 0.16, 0.07), Color(0.18, 0.18, 0.22))
	b.add_blob("plaster", Transform3D(Basis(), Vector3(0, 0.47, 0)), 0.06, Color(0.92, 0.78, 0.64).darkened(rng.randf() * 0.5), 3, 6, i + 20)
	if rng.randf() < 0.4:
		b.add_box("props", Transform3D(Basis(), Vector3(0, 0.55, 0)), Vector3(0.13, 0.03, 0.13), Color(0.15, 0.1, 0.08))
	var p := Node3D.new()
	p.name = "Person%d" % i
	p.add_child(_mi(b, "Mesh"))
	add_child(p)
	var side := -1.0 if i % 2 == 0 else 1.0
	var z := side * (CanalStreet.FRONT - 0.18)
	var dir := 1.0 if rng.randf() < 0.5 else -1.0
	_movers.append({"node": p, "from": Vector3(-6.8 * dir, 0.02, z), "to": Vector3(6.8 * dir, 0.02, z), "speed": rng.randf_range(0.14, 0.22), "t": rng.randf(), "bob": 0.012, "kind": "walk"})


func _add_duck(rng: RandomNumberGenerator, i: int) -> void:
	var b := Mats.builder()
	b.add_blob("plaster", Transform3D(Basis().scaled(Vector3(1.4, 0.7, 1)), Vector3(0, 0, 0)), 0.06, Color(0.45, 0.35, 0.25), 3, 6, i)
	b.add_blob("plaster", Transform3D(Basis(), Vector3(0.07, 0.06, 0)), 0.035, Color(0.1, 0.35, 0.18), 3, 6, i + 5)
	b.add_box("trim", Transform3D(Basis(), Vector3(0.11, 0.055, 0)), Vector3(0.04, 0.012, 0.02), Color(0.95, 0.6, 0.1))
	var d := Node3D.new()
	d.name = "Duck%d" % i
	d.add_child(_mi(b, "Mesh"))
	add_child(d)
	var z := rng.randf_range(-1.6, 1.6)
	var dir := 1.0 if rng.randf() < 0.5 else -1.0
	_movers.append({"node": d, "from": Vector3(-6.5 * dir, CanalStreet.WATER_Y + 0.02, z), "to": Vector3(6.5 * dir, CanalStreet.WATER_Y + 0.02, z - 0.3 * dir), "speed": rng.randf_range(0.05, 0.09), "t": rng.randf(), "bob": 0.01, "kind": "duck"})


func _add_cloud(rng: RandomNumberGenerator, i: int) -> void:
	var b := Mats.builder()
	for k in 4:
		b.add_blob("plaster", Transform3D(Basis().scaled(Vector3(1.3, 0.8, 1.0)), Vector3(k * 0.55 - 0.8, rng.randf_range(-0.1, 0.2), rng.randf_range(-0.3, 0.3))), rng.randf_range(0.45, 0.7), Color(0.97, 0.97, 1.0), 4, 8, i * 10 + k)
	var c := b.build()
	c.name = "Cloud%d" % i
	c.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	c.position = Vector3(rng.randf_range(-9, 9), rng.randf_range(6.5, 8.0), rng.randf_range(-4, 4))
	add_child(c)
	_clouds.append({"node": c, "speed": rng.randf_range(0.12, 0.25), "rank": float(i) / 6.0})


func _process(delta: float) -> void:
	_time += delta
	for m in _movers:
		m.t = fmod(m.t + delta * m.speed / maxf(m.from.distance_to(m.to), 0.01), 1.0)
		var node: Node3D = m.node
		var p: Vector3 = m.from.lerp(m.to, m.t)
		var bob: float = sin(_time * (9.0 if m.kind == "walk" else 2.0) + m.t * 40.0) * m.bob
		node.position = p + Vector3(0, absf(bob) if m.kind == "walk" else bob, 0)
		var dir: Vector3 = (m.to - m.from).normalized()
		node.rotation.y = atan2(-dir.z, dir.x)
		if m.kind == "boat":
			node.rotation.z = sin(_time * 1.3) * 0.02
		# Fade in/out at the plinth edges by hiding.
		node.visible = absf(p.x) < (8.0 if m.kind == "boat" else 6.9)
	for c in _clouds:
		var n: Node3D = c.node
		n.position.x += delta * c.speed
		if n.position.x > 11.0:
			n.position.x = -11.0
		n.visible = c.rank < cloud_cover
