"""Blender kit-piece builder, following the BlenderGenerator contract:

    blender -b -P kit_pieces.py -- --request req.json --out raw.glb
    python kit_pieces.py --request req.json --out raw.glb      # with the bpy wheel

Blender frame: metres, +Z up, front faces -Y (exported as glTF +Y up, front +Z).
Each object's material name is its palette role; custom prop smooth=1 marks
smooth-shaded parts. This is where pieces that benefit from Blender (curves,
bevels, modifiers) live, and where dutch_houses.py builders get wrapped.
"""
import argparse
import json
import math
import random
import sys

import bpy  # first: with the bpy wheel, bmesh/mathutils only exist after this
import bmesh
from mathutils import Matrix


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(role):
    m = bpy.data.materials.get(role) or bpy.data.materials.new(role)
    return m


def obj_from_bmesh(name, bm, role, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(material(role))
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
        ob["smooth"] = 1
    return ob


def apply_modifiers(ob):
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    for mod in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.select_set(False)


def extrude_outline(name, pts, depth, role, bevel=0.0, y0=0.0):
    """Polygon in the XZ plane (x, z), extruded along +Y from y0 (back) to
    y0+depth... then mirrored so the front faces -Y."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, y0, z)) for x, z in pts]
    face = bm.faces.new(verts)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, -depth, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ob = obj_from_bmesh(name, bm, role)
    if bevel > 0:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method = bevel, 2, "ANGLE"
        apply_modifiers(ob)
    return ob


# ---------------------------------------------------------------- pieces

def gable_bell(p, rng):
    """Bell gable (klokgevel): S-curved shoulders up to a crowned top.
    Wall pivot: back face at y=0, sits on the facade's top edge."""
    w = p.get("width", 4.6)
    h = p.get("height", 3.2)
    neck = p.get("neck_width", 1.8)
    t = 0.3
    n = 10
    right = []
    for i in range(n + 1):           # S-curve from shoulder (w/2, 0) to neck (neck/2, h*0.8)
        s = i / n
        x = neck / 2 + (w / 2 - neck / 2) * (1 - (3 * s * s - 2 * s * s * s))
        right.append((x, h * 0.8 * s))
    top = [(neck / 2 * math.cos(a), h * 0.8 + h * 0.2 * math.sin(a))
           for a in [k * math.pi / 8 for k in range(1, 8)]]   # crowning arc
    left = [(-x, z) for x, z in reversed(right)]
    outline = right + top + left
    extrude_outline("gable", outline, t, "wall", bevel=0.02)
    # trim follows the outline as a slightly larger thin shell, in front
    trim = [(x * 1.04, z + 0.06) for x, z in right + top + left]
    inner = [(x * 0.97, z) for x, z in reversed(right + top + left)]
    extrude_outline("trim", trim + inner, 0.08, "trim", y0=-t)
    # oculus window
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=0.35, segments=16)
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0),
                     matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, -t - 0.01, h * 0.5))
    obj_from_bmesh("oculus", bm, "glass")


def lantern(p, rng):
    """Lathed wall-street lantern on a post (smooth parts via Screw modifier)."""
    h = p.get("height", 3.0)
    prof = [(0.12, 0), (0.12, 0.1), (0.05, 0.25), (0.045, h - 0.1), (0.07, h), (0.0, h)]
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in prof]
    for a, b in zip(vs, vs[1:]):
        bm.edges.new((a, b))
    post = obj_from_bmesh("post", bm, "metal", smooth=True)
    m = post.modifiers.new("lathe", "SCREW")
    m.steps, m.render_steps, m.use_merge_vertices = 12, 12, True
    apply_modifiers(post)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.16, radius2=0.20, depth=0.36)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, 0, h + 0.18))
    obj_from_bmesh("glass", bm, "glass")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.28, radius2=0.02, depth=0.22)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, 0, h + 0.47))
    obj_from_bmesh("roof", bm, "metal")


PIECES = {"gable_bell": gable_bell, "lantern": lantern}


def main():
    a = args()
    req = json.load(open(a.request))
    reset()
    rng = random.Random(req["seed"])
    if req["kind"] not in PIECES:
        raise SystemExit(f"kit_pieces.py: unknown kind {req['kind']!r}; known {sorted(PIECES)}")
    PIECES[req["kind"]](req.get("params", {}), rng)
    bpy.ops.export_scene.gltf(filepath=a.out, export_format="GLB", export_yup=True,
                              export_extras=True, export_apply=True, use_selection=False)


if __name__ == "__main__":
    main()
