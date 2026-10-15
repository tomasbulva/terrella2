## Collects flat-shaded primitives into one surface per material key, so a whole street is a handful of draw calls.
class_name MeshBuilder
extends RefCounted

var _tools := {}
var _materials := {}


func set_material(key: String, mat: Material) -> void:
	_materials[key] = mat


func _st(key: String) -> SurfaceTool:
	if not _tools.has(key):
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		_tools[key] = st
	return _tools[key]


## Godot treats clockwise triangles as front faces; flip if the winding disagrees with the outward normal.
func add_tri(key: String, p0: Vector3, p1: Vector3, p2: Vector3, n: Vector3, c: Color) -> void:
	var st := _st(key)
	if (p1 - p0).cross(p2 - p0).dot(n) > 0.0:
		var t := p1
		p1 = p2
		p2 = t
	st.set_color(c)
	st.set_normal(n)
	st.add_vertex(p0)
	st.set_color(c)
	st.set_normal(n)
	st.add_vertex(p1)
	st.set_color(c)
	st.set_normal(n)
	st.add_vertex(p2)


func add_quad(key: String, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3, col: Color) -> void:
	add_tri(key, a, b, c, n, col)
	add_tri(key, a, c, d, n, col)


func _normal(xf: Transform3D, n: Vector3) -> Vector3:
	return (xf.basis.inverse().transposed() * n).normalized()


func add_box(key: String, xf: Transform3D, size: Vector3, col: Color, skip_bottom := true) -> void:
	var h := size * 0.5
	var p := [
		Vector3(-h.x, -h.y, -h.z), Vector3(h.x, -h.y, -h.z), Vector3(h.x, h.y, -h.z), Vector3(-h.x, h.y, -h.z),
		Vector3(-h.x, -h.y, h.z), Vector3(h.x, -h.y, h.z), Vector3(h.x, h.y, h.z), Vector3(-h.x, h.y, h.z),
	]
	for i in p.size():
		p[i] = xf * p[i]
	add_quad(key, p[4], p[5], p[6], p[7], _normal(xf, Vector3.BACK), col)      # +z
	add_quad(key, p[1], p[0], p[3], p[2], _normal(xf, Vector3.FORWARD), col)   # -z
	add_quad(key, p[5], p[1], p[2], p[6], _normal(xf, Vector3.RIGHT), col)     # +x
	add_quad(key, p[0], p[4], p[7], p[3], _normal(xf, Vector3.LEFT), col)      # -x
	add_quad(key, p[7], p[6], p[2], p[3], _normal(xf, Vector3.UP), col)        # +y
	if not skip_bottom:
		add_quad(key, p[0], p[1], p[5], p[4], _normal(xf, Vector3.DOWN), col)


## Triangular prism: triangle in the local XY plane (base width w at y=0, apex at y=h), extruded along z by d.
func add_prism(key: String, xf: Transform3D, w: float, h: float, d: float, col: Color) -> void:
	var hw := w * 0.5
	var hd := d * 0.5
	var a := xf * Vector3(-hw, 0, hd)
	var b := xf * Vector3(hw, 0, hd)
	var c := xf * Vector3(0, h, hd)
	var a2 := xf * Vector3(-hw, 0, -hd)
	var b2 := xf * Vector3(hw, 0, -hd)
	var c2 := xf * Vector3(0, h, -hd)
	add_tri(key, a, b, c, _normal(xf, Vector3.BACK), col)
	add_tri(key, a2, c2, b2, _normal(xf, Vector3.FORWARD), col)
	var nl := _normal(xf, Vector3(-h, hw, 0).normalized())
	var nr := _normal(xf, Vector3(h, hw, 0).normalized())
	add_quad(key, a, c, c2, a2, nl, col)
	add_quad(key, b, b2, c2, c, nr, col)


func add_cylinder(key: String, xf: Transform3D, r: float, h: float, col: Color, seg := 8) -> void:
	for i in seg:
		var a0 := TAU * i / seg
		var a1 := TAU * (i + 1) / seg
		var p0 := Vector3(cos(a0) * r, 0, sin(a0) * r)
		var p1 := Vector3(cos(a1) * r, 0, sin(a1) * r)
		var n := _normal(xf, Vector3(cos((a0 + a1) * 0.5), 0, sin((a0 + a1) * 0.5)))
		add_quad(key, xf * p0, xf * p1, xf * (p1 + Vector3(0, h, 0)), xf * (p0 + Vector3(0, h, 0)), n, col)
		add_tri(key, xf * Vector3(0, h, 0), xf * (p0 + Vector3(0, h, 0)), xf * (p1 + Vector3(0, h, 0)), _normal(xf, Vector3.UP), col)


## Faceted low-poly blob (squashed UV sphere) for tree canopies, hedges and clouds.
func add_blob(key: String, xf: Transform3D, r: float, col: Color, rings := 4, seg := 7, seed := 0) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var verts := []
	for i in rings + 1:
		var row := []
		var phi := PI * i / rings
		for j in seg:
			var th := TAU * j / seg + (0.3 if i % 2 == 1 else 0.0)
			var jitter := 1.0 if (i == 0 or i == rings) else rng.randf_range(0.85, 1.12)
			row.append(Vector3(sin(phi) * cos(th), cos(phi), sin(phi) * sin(th)) * r * jitter)
		verts.append(row)
	for i in rings:
		for j in seg:
			var a: Vector3 = verts[i][j]
			var b: Vector3 = verts[i][(j + 1) % seg]
			var c: Vector3 = verts[i + 1][(j + 1) % seg]
			var d: Vector3 = verts[i + 1][j]
			var n := ((a + b + c + d) * 0.25).normalized()
			var wa := xf * a
			var wb := xf * b
			var wc := xf * c
			var wd := xf * d
			var wn := _normal(xf, n)
			if i > 0:
				add_tri(key, wa, wb, wc, wn, col)
			if i < rings - 1:
				add_tri(key, wa, wc, wd, wn, col)


func build() -> MeshInstance3D:
	var mesh := ArrayMesh.new()
	for key in _tools.keys():
		var st: SurfaceTool = _tools[key]
		st.commit(mesh)
		var idx := mesh.get_surface_count() - 1
		if _materials.has(key):
			mesh.surface_set_material(idx, _materials[key])
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	return mi
