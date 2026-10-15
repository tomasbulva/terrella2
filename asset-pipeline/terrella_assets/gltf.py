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
    uvs: np.ndarray
    indices: np.ndarray
    image_png: bytes


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
    # Bake the piece's own node transform (if any) so pieces are always in their own frame.
    node = next(n for n in js["nodes"] if "mesh" in n)
    if "matrix" in node:
        m = np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
        if not np.allclose(m, np.eye(4)):
            pos = (np.c_[pos, np.ones(len(pos))] @ m.T)[:, :3].astype(np.float32)
    img = js["images"][0]
    bv = js["bufferViews"][img["bufferView"]]
    png = binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
    return PieceMesh(
        positions=pos,
        normals=_accessor(js, binary, attr["NORMAL"]).astype(np.float32),
        uvs=_accessor(js, binary, attr["TEXCOORD_0"]).astype(np.float32),
        indices=_accessor(js, binary, prim["indices"]).astype(np.uint32).reshape(-1),
        image_png=bytes(png),
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

    def matrix(self) -> np.ndarray:
        c, s = np.cos(self.yaw), np.sin(self.yaw)
        r = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        m = np.eye(4)
        m[:3, :3] = r * np.array(self.scale)
        m[:3, 3] = self.translation
        return m


def write_scene(root: Node, meshes: dict[str, PieceMesh], palette_png: bytes, extras: dict | None = None) -> bytes:
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
                "TEXCOORD_0": add_acc(pm.uvs.astype("<f4"), 5126, "VEC2", 34962),
            },
            "indices": add_acc(pm.indices.astype("<u4"), 5125, "SCALAR", 34963),
            "material": 0,
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
        "materials": [{"name": "kit_palette", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.85}}],
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
