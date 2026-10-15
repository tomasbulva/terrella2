## Loads the asset pipeline's assembled diorama (glTF + puzzle_scene.json), scales it onto the spike's plinth
## size and swaps its palette material for the kit shader. Exposes lamp and hide-spot anchors like CanalStreet.
class_name KitDiorama
extends RefCounted

const GLB := "res://diorama/kit_canal.glb"
const PUZZLE := "res://diorama/kit_canal.puzzle.json"
const TARGET_WIDTH := 15.0

var anchors := {"lamps": [], "puzzle": [], "trees": []}
var draw_meshes := 0


func build() -> Node3D:
	var scene: PackedScene = load(GLB)
	if scene == null:
		return null
	var inner: Node3D = scene.instantiate()
	var root := Node3D.new()
	root.name = "KitDiorama"
	root.add_child(inner)

	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/kit.gdshader")
	var aabb := AABB()
	var first := true
	for node in inner.find_children("*", "MeshInstance3D", true, false):
		var mi: MeshInstance3D = node
		draw_meshes += 1
		var src := mi.mesh.surface_get_material(0)
		if src is BaseMaterial3D and src.albedo_texture and mat.get_shader_parameter("palette") == null:
			mat.set_shader_parameter("palette", src.albedo_texture)
		for s in mi.mesh.get_surface_count():
			mi.set_surface_override_material(s, mat)
		var box := _global_xf(mi, root) * mi.get_aabb()
		aabb = box if first else aabb.merge(box)
		first = false

	# Fit the diorama to the spike's plinth width and centre it on the origin, ground at y=0.
	var k := TARGET_WIDTH / maxf(aabb.size.x, 0.001)
	var centre := aabb.get_center()
	inner.transform = Transform3D(Basis().scaled(Vector3.ONE * k), Vector3(-centre.x * k, -aabb.position.y * k, -centre.z * k))
	_read_anchors(k, Vector3(-centre.x * k, -aabb.position.y * k, -centre.z * k))
	return root


func _global_xf(n: Node3D, stop: Node) -> Transform3D:
	var xf := n.transform
	var p := n.get_parent()
	while p and p != stop:
		if p is Node3D:
			xf = (p as Node3D).transform * xf
		p = p.get_parent()
	return xf


func _read_anchors(k: float, offset: Vector3) -> void:
	var f := FileAccess.open(PUZZLE, FileAccess.READ)
	if f == null:
		return
	var data = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		return
	for e in data.get("entities", []):
		var p: Array = e.get("pos", [0, 0, 0])
		var pos := Vector3(p[0], p[1], p[2]) * k + offset
		var kind: String = e.get("kind", "")
		if kind == "lamp":
			anchors["lamps"].append(pos + Vector3(0, 3.3 * k, 0))
		if kind == "tree":
			anchors["trees"].append(pos)
		if "hide_spot" in e.get("tags", []):
			# Tulips sit just in front of the hiding spot so they are visible from the default view.
			anchors["puzzle"].append(pos + Vector3(0, 0.02, 0.35 * k))
