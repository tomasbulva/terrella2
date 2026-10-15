"""Minimal GLB reader/writer for assembled dioramas.

trimesh can't write what a diorama needs: true instancing (many nodes, one
mesh) and per-node `extras`. This writer does exactly that and nothing more:
  * one buffer, one palette image/texture/material shared by every mesh;
  * one mesh per kit piece, referenced by every node that places it;
  * node name = puzzle entity id (or "<entity>~<part>" / "env~<part>" for
    helper nodes), node extras = {kind, attrs, tags, kit_piece};
  * TRS transforms, hierarchy preserved.
The reader only understands the single-mesh, single-primitive GLBs that the
kit export writes.

`merge()` bakes every static mesh node into one world-space mesh (one draw
call per material instead of one per node). Each merged vertex carries
TEXCOORD_2 = (entity_index, height above its piece's pivot), so engines can
still drive per-entity state (lit windows, highlight, hide) from a small
lookup texture and sway foliage by local height.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

import numpy as np

_COMP = {5126: ("<f4", 4), 5125: ("<u4", 4), 5123: ("<u2", 2), 5121: ("u1", 1)}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


@dataclass
class PieceMesh:
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray            # TEXCOORD_0: palette swatch, constant per part
    indices: np.ndarray
    image_png: bytes
    uv2: np.ndarray | None = None        # TEXCOORD_1: box-projected, metres (for tiling detail/normal maps)
    tangents: np.ndarray | None = None   # TANGENT (xyzw), consistent with uv2
    material: str = "kit_palette"        # key into write_scene's material table
    uv3: np.ndarray | None = None        # TEXCOORD_2: (entity_index, height above piece pivot), merged meshes only

    def __post_init__(self):
        if self.uv2 is None or self.tangents is None:
            self.uv2, self.tangents = box_uv_tangents(self.positions, self.normals)


def box_uv_tangents(pos: np.ndarray, nrm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Box projection in metres plus matching tangents.

    The palette UVs (TEXCOORD_0) are constant per face, so engines that derive
    tangents from UV0 (Godot, MikkTSpace) get NaNs and normal-mapped faces
    turn white. We therefore ship explicit tangents, built from a second UV
    set that does vary: project each vertex on the plane of its dominant
    normal axis. Normal and detail maps must sample TEXCOORD_1 (Godot: UV2).
    """
    n = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    ax = np.argmax(np.abs(n), axis=1)
    sgn = np.where(n[np.arange(len(n)), ax] >= 0, 1.0, -1.0)
    U = np.zeros_like(n)
    V = np.zeros_like(n)
    # x-dominant: U along -z*sign, V up; y-dominant: U along x, V along -z*sign; z-dominant: U along x*sign, V up
    U[ax == 0] = np.c_[np.zeros((ax == 0).sum()), np.zeros((ax == 0).sum()), -sgn[ax == 0]]
    V[ax == 0] = (0, 1, 0)
    U[ax == 1] = (1, 0, 0)
    V[ax == 1] = np.c_[np.zeros((ax == 1).sum()), np.zeros((ax == 1).sum()), -sgn[ax == 1]]
    U[ax == 2] = np.c_[sgn[ax == 2], np.zeros((ax == 2).sum()), np.zeros((ax == 2).sum())]
    V[ax == 2] = (0, 1, 0)
    uv2 = np.c_[np.einsum("ij,ij->i", pos, U), -np.einsum("ij,ij->i", pos, V)]   # glTF v points down
    t = U - n * np.einsum("ij,ij->i", n, U)[:, None]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    w = np.where(np.einsum("ij,ij->i", np.cross(n, t), V) >= 0, 1.0, -1.0)
    return uv2.astype(np.float32), np.c_[t, w].astype(np.float32)


def _chunks(glb: bytes) -> tuple[dict, bytes]:
    if glb[:4] != b"glTF":
        raise ValueError("not a GLB")
    jl = struct.unpack("<I", glb[12:16])[0]
    js = json.loads(glb[20:20 + jl])
    off = 20 + jl
    binary = b""
    if off < len(glb):
        bl = struct.unpack("<I", glb[off:off + 4])[0]
        binary = glb[off + 8:off + 8 + bl]
    return js, binary


def _accessor(js: dict, binary: bytes, i: int) -> np.ndarray:
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt, size = _COMP[a["componentType"]]
    n = _NCOMP[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    if stride and stride != size * n:
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"], offset=start)
        arr = raw.reshape(a["count"], stride)[:, :size * n].copy().view(dt)
    else:
        arr = np.frombuffer(binary, dtype=dt, count=a["count"] * n, offset=start)
    return arr.reshape(a["count"], n) if n > 1 else arr.copy()


def read_piece(glb: bytes) -> PieceMesh:
    js, binary = _chunks(glb)
    if len(js.get("meshes", [])) != 1 or len(js["meshes"][0]["primitives"]) != 1:
        raise ValueError("expected a kit piece GLB with exactly one mesh and one primitive")
    prim = js["meshes"][0]["primitives"][0]
    attr = prim["attributes"]
    pos = _accessor(js, binary, attr["POSITION"]).astype(np.float32)
    node = next(n for n in js["nodes"] if "mesh" in n)
    if any(k in node for k in ("matrix", "translation", "rotation", "scale")):
        raise ValueError("kit piece mesh node must have an identity transform")
    img = js["images"][0]
    bv = js["bufferViews"][img["bufferView"]]
    png = binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
    return PieceMesh(
        positions=pos,
        normals=_accessor(js, binary, attr["NORMAL"]).astype(np.float32),
        uvs=_accessor(js, binary, attr["TEXCOORD_0"]).astype(np.float32),
        indices=_accessor(js, binary, prim["indices"]).astype(np.uint32).reshape(-1),
        image_png=bytes(png),
        uv2=_accessor(js, binary, attr["TEXCOORD_1"]).astype(np.float32) if "TEXCOORD_1" in attr else None,
        tangents=_accessor(js, binary, attr["TANGENT"]).astype(np.float32) if "TANGENT" in attr else None,
    )


@dataclass
class Node:
    name: str
    mesh: str | None = None                 # kit piece slug
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    yaw: float = 0.0                        # radians about +Y (all the assembler needs)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    extras: dict | None = None
    children: list["Node"] = field(default_factory=list)
    shear: tuple[float, float] = (0.0, 0.0)  # (x, z) offset per metre of local height: a house's list and lean.
                                            # glTF TRS can't express it, so only merged output may use it.

    def matrix(self) -> np.ndarray:
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        r = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        sh = np.array([[1.0, self.shear[0], 0.0], [0.0, 1.0, 0.0], [0.0, self.shear[1], 1.0]])
        m = np.eye(4)
        m[:3, :3] = r @ sh @ np.diag(self.scale)
        m[:3, 3] = self.translation
        return m


KIT_MATERIAL = {"name": "kit_palette", "pbrMetallicRoughness": {
    "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.85}}


def write_scene(root: Node, meshes: dict[str, PieceMesh], palette_png: bytes, extras: dict | None = None,
                materials: dict[str, dict] | None = None) -> bytes:
    """`materials` adds named materials (glTF material dicts) that meshes can
    select with PieceMesh.material; "kit_palette" is always material 0."""
    mats = {"kit_palette": KIT_MATERIAL, **(materials or {})}
    mat_index = {k: i for i, k in enumerate(mats)}
    used = []
    def walk(n: Node):
        if n.mesh and n.mesh not in used:
            used.append(n.mesh)
        for c in n.children:
            walk(c)
    walk(root)

    blob = bytearray()
    views, accessors = [], []

    def add_view(data: bytes, target: int | None) -> int:
        while len(blob) % 4:
            blob.append(0)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            v["target"] = target
        blob.extend(data)
        views.append(v)
        return len(views) - 1

    def add_acc(arr: np.ndarray, ctype: int, typ: str, target: int, minmax: bool = False) -> int:
        a = {"bufferView": add_view(arr.tobytes(), target), "componentType": ctype,
             "count": int(arr.shape[0]), "type": typ}
        if minmax:
            a["min"], a["max"] = arr.min(axis=0).tolist(), arr.max(axis=0).tolist()
        accessors.append(a)
        return len(accessors) - 1

    mesh_index, gl_meshes = {}, []
    for slug in used:
        pm = meshes[slug]
        prim = {
            "attributes": {
                "POSITION": add_acc(pm.positions.astype("<f4"), 5126, "VEC3", 34962, minmax=True),
                "NORMAL": add_acc(pm.normals.astype("<f4"), 5126, "VEC3", 34962),
                "TANGENT": add_acc(pm.tangents.astype("<f4"), 5126, "VEC4", 34962),
                "TEXCOORD_0": add_acc(pm.uvs.astype("<f4"), 5126, "VEC2", 34962),
                "TEXCOORD_1": add_acc(pm.uv2.astype("<f4"), 5126, "VEC2", 34962),
                **({"TEXCOORD_2": add_acc(pm.uv3.astype("<f4"), 5126, "VEC2", 34962)} if pm.uv3 is not None else {}),
            },
            "indices": add_acc(pm.indices.astype("<u4"), 5125, "SCALAR", 34963),
            "material": mat_index[pm.material],
        }
        mesh_index[slug] = len(gl_meshes)
        gl_meshes.append({"name": slug, "primitives": [prim]})

    img_view = add_view(palette_png, None)
    nodes: list[dict] = []

    def emit(n: Node) -> int:
        i = len(nodes)
        d: dict = {"name": n.name}
        nodes.append(d)
        if n.mesh:
            d["mesh"] = mesh_index[n.mesh]
        if any(n.translation):
            d["translation"] = [float(round(v, 5)) for v in n.translation]
        if n.yaw:
            d["rotation"] = [0.0, float(np.sin(n.yaw / 2)), 0.0, float(np.cos(n.yaw / 2))]
        if n.scale != (1.0, 1.0, 1.0):
            d["scale"] = [float(round(v, 5)) for v in n.scale]
        if any(n.shear):
            raise ValueError(f"node {n.name!r} has a shear, which glTF TRS can't express; merge() it first")
        if n.extras:
            d["extras"] = n.extras
        if n.children:
            d["children"] = [emit(c) for c in n.children]
        return i

    emit(root)
    gltf = {
        "asset": {"version": "2.0", "generator": "terrella_assets"},
        "scene": 0,
        "scenes": [{"nodes": [0], **({"extras": extras} if extras else {})}],
        "nodes": nodes,
        "meshes": gl_meshes,
        "materials": list(mats.values()),
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9728, "minFilter": 9728}],    # NEAREST: palette swatches
        "images": [{"bufferView": img_view, "mimeType": "image/png"}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = bytearray(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(blob)))
    out += struct.pack("<I", len(js)) + b"JSON" + js
    out += struct.pack("<I", len(blob)) + b"BIN\x00" + bytes(blob)
    return bytes(out)


def world_transforms(root: Node) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    def walk(n: Node, parent: np.ndarray):
        m = parent @ n.matrix()
        out[n.name] = m
        for c in n.children:
            walk(c, m)
    walk(root, np.eye(4))
    return out


def merge(root: Node, meshes: dict[str, PieceMesh], keep, entity_index: dict[str, int],
          name: str = "static") -> tuple[Node, PieceMesh | None]:
    """Bake every mesh node under `root` into one world-space mesh, except
    subtrees for which `keep(node)` is true (moving or toggled things, e.g.
    boats), which stay as instanced nodes.

    Returns a new tree and the merged mesh (or None if nothing merged):
      * entity nodes (names without "~") survive without their mesh, keeping
        transform and extras, so ids, tap targets and anchors still resolve;
      * "~" helper nodes are dropped; their geometry is in the merged mesh;
      * the merged mesh hangs off "env~<name>" under the root, with an
        identity transform relative to the root;
      * TEXCOORD_2.x = entity_index of the nearest entity ancestor (0 = env),
        TEXCOORD_2.y = height above the source piece's pivot (foliage sway);
      * only meshes with the kit_palette material are merged.
    TEXCOORD_1/tangents are recomputed in root space, so tiling detail lines
    up across pieces.
    """
    xf = world_transforms(root)
    inv_root = np.linalg.inv(xf[root.name])
    P, N, U, H, E, I = [], [], [], [], [], []
    off = 0

    def take(n: Node, eid: str):
        nonlocal off
        pm = meshes[n.mesh]
        m = inv_root @ xf[n.name]
        lin = m[:3, :3]
        P.append(pm.positions @ lin.T + m[:3, 3])
        nm = pm.normals @ np.linalg.inv(lin)          # inverse transpose, applied to row vectors
        N.append(nm / np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-12))
        U.append(pm.uvs)
        H.append(pm.positions[:, 1] * float(np.linalg.norm(lin[:, 1])))
        E.append(np.full(len(pm.positions), float(entity_index.get(eid, 0))))
        tri = pm.indices.reshape(-1, 3)
        if np.linalg.det(lin) < 0:                    # mirrored: keep front faces front
            tri = tri[:, ::-1]
        I.append(tri.reshape(-1) + off)
        off += len(pm.positions)

    def yaw_of(m: np.ndarray) -> float:
        return float(np.arctan2(-m[2, 0], m[0, 0]))  # column 0 is R*(sx,0,0); shear never touches it

    out_world: dict[int, np.ndarray] = {}            # id(out node) -> its rigid root-space matrix

    def attach(parent_out: Node, n: Node, mesh: str | None, children: list[Node]) -> Node:
        """Re-parent `n` under parent_out with a TRS-safe transform that puts its
        origin and heading where the source tree had them (shear dropped)."""
        m = inv_root @ xf[n.name]
        pw = out_world[id(parent_out)]
        local = np.linalg.inv(pw) @ np.r_[m[:3, 3], 1.0]
        yaw = yaw_of(m) - yaw_of(pw)
        o = Node(n.name, mesh, tuple(float(round(v, 5)) for v in local[:3]), yaw if abs(yaw) > 1e-9 else 0.0,
                 n.scale if mesh else (1.0, 1.0, 1.0), n.extras, children)
        parent_out.children.append(o)
        out_world[id(o)] = pw @ Node("", None, o.translation, o.yaw).matrix()
        return o

    def walk(n: Node, eid: str, parent_out: Node, sheared: bool) -> None:
        is_entity = "~" not in n.name
        eid = n.name if is_entity else eid
        sheared = sheared or any(n.shear)
        if keep(n):
            if sheared:
                raise ValueError(f"kept node {n.name!r} sits under a shear; it can't stay instanced")
            attach(parent_out, n, n.mesh, n.children)
            return
        out = attach(parent_out, n, None, []) if is_entity else parent_out
        if n.mesh and meshes[n.mesh].material == "kit_palette":
            take(n, eid)
        elif n.mesh:                                   # other materials (water, resin) stay as nodes
            if is_entity or sheared:
                raise ValueError(f"{n.name!r}: non-palette meshes must be unsheared env~ nodes")
            attach(parent_out, n, n.mesh, [])
        for c in n.children:
            walk(c, eid, out, sheared)

    new_root = Node(root.name, None, root.translation, root.yaw, root.scale, root.extras, [])
    out_world[id(new_root)] = np.eye(4)
    for c in root.children:
        walk(c, "env", new_root, any(root.shear))
    if not P:
        return new_root, None
    pos = np.vstack(P).astype(np.float32)
    nrm = np.vstack(N).astype(np.float32)
    uv2, tan = box_uv_tangents(pos, nrm)
    merged = PieceMesh(positions=pos, normals=nrm, uvs=np.vstack(U).astype(np.float32),
                       indices=np.concatenate(I).astype(np.uint32), image_png=b"", uv2=uv2, tangents=tan,
                       uv3=np.c_[np.concatenate(E), np.concatenate(H)].astype(np.float32))
    new_root.children.insert(0, Node(f"env~{name}", mesh=name))
    return new_root, merged

