## Tiny treasure hunt: find three golden tulips hidden in the diorama. Finding all three plays a reward
## animation and grants a collectible (a golden windmill), then the hunt resets with new hiding spots.
class_name Puzzle
extends Node3D

signal progress(found: int, total: int)
signal rewarded(total_collected: int)

const TOTAL := 3

var spots: Array = []         # candidate [Node3D parent, local position]
var _tulips: Array = []
var _found := 0
var _collected := 0
var _rng := RandomNumberGenerator.new()
var _windmill: Node3D
var _blades: Node3D
var _confetti: GPUParticles3D
var _time := 0.0


func setup(candidate_spots: Array, collected: int) -> void:
	spots = candidate_spots
	_collected = collected
	_rng.randomize()
	_confetti = _make_burst(160, [Color(1, 0.3, 0.3), Color(1, 0.85, 0.2), Color(0.3, 0.7, 1), Color(0.5, 1, 0.5)], 2.2)
	_confetti.position = Vector3(0, 3.0, 0)
	add_child(_confetti)
	_windmill = _make_windmill()
	_windmill.visible = false
	add_child(_windmill)
	_spawn()


func _spawn() -> void:
	for t in _tulips:
		if is_instance_valid(t):
			t.queue_free()
	_tulips.clear()
	_found = 0
	var pool := spots.duplicate()
	pool.shuffle()
	for i in mini(TOTAL, pool.size()):
		var spot: Array = pool[i]
		var tulip := _make_tulip()
		(spot[0] as Node3D).add_child(tulip)
		tulip.position = spot[1]
		_tulips.append(tulip)
	progress.emit(_found, TOTAL)


func _make_tulip() -> Node3D:
	var b := Mats.builder()
	b.add_cylinder("foliage", Transform3D(Basis(), Vector3.ZERO), 0.012, 0.16, Color(0.3, 0.55, 0.2), 5)
	for k in 3:
		var a := TAU * k / 3.0
		b.add_blob("gold", Transform3D(Basis().scaled(Vector3(0.6, 1.2, 0.6)), Vector3(cos(a) * 0.025, 0.2, sin(a) * 0.025)), 0.045, Color.WHITE, 3, 5, k)
	var root := Node3D.new()
	root.name = "Tulip"
	var mi := b.build()
	mi.scale = Vector3.ONE * 1.6
	root.add_child(mi)
	var area := Area3D.new()
	var cs := CollisionShape3D.new()
	var sph := SphereShape3D.new()
	sph.radius = 0.45   # generous: fingers are big, tulips are small
	cs.shape = sph
	cs.position = Vector3(0, 0.25, 0)
	area.add_child(cs)
	area.set_meta("tulip", root)
	root.add_child(area)
	return root


func _make_burst(amount: int, colors: Array, life: float) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = life
	p.one_shot = true
	p.explosiveness = 0.95
	p.emitting = false
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 75.0
	pm.initial_velocity_min = 2.0
	pm.initial_velocity_max = 5.0
	pm.gravity = Vector3(0, -4.0, 0)
	pm.angular_velocity_min = -360.0
	pm.angular_velocity_max = 360.0
	var grad := Gradient.new()
	grad.colors = PackedColorArray(colors)
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	pm.color_initial_ramp = gt
	p.process_material = pm
	var q := BoxMesh.new()
	q.size = Vector3(0.09, 0.02, 0.06)
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	q.material = m
	p.draw_pass_1 = q
	return p


func _make_windmill() -> Node3D:
	var b := Mats.builder()
	b.add_cylinder("gold", Transform3D(Basis(), Vector3.ZERO), 0.35, 1.1, Color.WHITE, 8)
	b.add_cylinder("gold", Transform3D(Basis(), Vector3(0, 1.1, 0)), 0.28, 0.25, Color.WHITE, 8)
	b.add_prism("gold", Transform3D(Basis(), Vector3(0, 1.35, 0)), 0.6, 0.35, 0.6, Color.WHITE)
	var root := Node3D.new()
	root.name = "GoldenWindmill"
	root.add_child(b.build())
	var bb := Mats.builder()
	for k in 4:
		var rot := Basis(Vector3.BACK, TAU * k / 4.0)
		bb.add_box("gold", Transform3D(rot, rot * Vector3(0, 0.45, 0)), Vector3(0.12, 0.8, 0.02), Color.WHITE)
	_blades = Node3D.new()
	_blades.position = Vector3(0, 1.2, 0.36)
	_blades.add_child(bb.build())
	root.add_child(_blades)
	return root


## Returns true if the tap hit a tulip.
func try_tap(cam: Camera3D, screen_pos: Vector2) -> bool:
	var from := cam.project_ray_origin(screen_pos)
	var to := from + cam.project_ray_normal(screen_pos) * 100.0
	var q := PhysicsRayQueryParameters3D.create(from, to)
	q.collide_with_areas = true
	q.collide_with_bodies = false
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty() or not hit.collider.has_meta("tulip"):
		return false
	var tulip: Node3D = hit.collider.get_meta("tulip")
	if not _tulips.has(tulip):
		return false
	_tulips.erase(tulip)
	_found += 1
	(hit.collider as Area3D).queue_free()
	var sparkle := _make_burst(40, [Color(1, 0.9, 0.4), Color(1, 1, 1)], 1.0)
	sparkle.process_material.initial_velocity_max = 2.0
	tulip.add_child(sparkle)
	sparkle.emitting = true
	var tw := create_tween()
	tw.tween_property(tulip, "scale", Vector3.ONE * 2.2, 0.18).set_trans(Tween.TRANS_BACK)
	tw.tween_property(tulip, "scale", Vector3.ONE * 0.01, 0.35)
	tw.tween_interval(1.0)
	tw.tween_callback(tulip.queue_free)
	progress.emit(_found, TOTAL)
	if _found >= TOTAL:
		_reward()
	return true


func _reward() -> void:
	_collected += 1
	rewarded.emit(_collected)
	_confetti.restart()
	_confetti.emitting = true
	_windmill.visible = true
	_windmill.position = Vector3(0, 0.5, 0)
	_windmill.scale = Vector3.ONE * 0.01
	var tw := create_tween()
	tw.tween_property(_windmill, "scale", Vector3.ONE * 1.4, 0.6).set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)
	tw.parallel().tween_property(_windmill, "position", Vector3(0, 3.2, 0), 1.2).set_trans(Tween.TRANS_SINE)
	tw.tween_interval(6.0)
	tw.tween_property(_windmill, "scale", Vector3.ONE * 0.01, 0.5)
	tw.tween_callback(func(): _windmill.visible = false)
	tw.tween_interval(2.0)
	tw.tween_callback(_spawn)


func _process(delta: float) -> void:
	_time += delta
	for t in _tulips:
		if is_instance_valid(t):
			t.rotation.y += delta * 0.8
	if _windmill.visible:
		_windmill.rotation.y += delta * 0.6
		_blades.rotation.z += delta * 3.0
