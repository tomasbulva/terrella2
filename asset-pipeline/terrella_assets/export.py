"""Export: palette atlas, single-material GLB, validation, cache io.

Every piece in a kit shares ONE material whose base colour is a small
palette atlas (one swatch per role). Each part's UVs point at its role's
swatch centre. Consequences:
  * one mesh, one primitive, one material per piece -> one draw call, and
    the engine can batch the whole kit;
  * re-styling a kit = swapping a 64x64 PNG, geometry untouched;
  * the shader can recover the role from the UV cell (glass -> interior
    mapping and night emission, etc.) with no extra vertex data.
Seasons/snow/time of day stay in the engine shader, not in the asset.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from .generators.base import Part
from .spec import ROLES, PieceRequest, StyleSpec

SWATCH_PX = 16
GRID = 4                           # 4x4 = 16 roles
ATLAS_PX = SWATCH_PX * GRID
assert len(ROLES) <= GRID * GRID


def role_uv(role: str) -> tuple[float, float]:
    """UV of the swatch centre, in trimesh's bottom-left convention. trimesh
    flips v on glTF export, so in the GLB (top-left origin, like the PNG)
    the cell is simply (col, row) = (i % GRID, i // GRID)."""
    i = ROLES.index(role)
    col, row = i % GRID, i // GRID
    return (col + 0.5) / GRID, 1.0 - (row + 0.5) / GRID


def palette_png(style: StyleSpec) -> bytes:
    img = Image.new("RGB", (ATLAS_PX, ATLAS_PX), (255, 0, 255))   # magenta = unused slot
    for i, role in enumerate(ROLES):
        if role in style.palette:
            col, row = i % GRID, i // GRID
            img.paste(style.colour(role), (col * SWATCH_PX, row * SWATCH_PX,
                                           (col + 1) * SWATCH_PX, (row + 1) * SWATCH_PX))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def to_single_mesh(parts: list[Part], palette: bytes) -> trimesh.Trimesh:
    vs, fs, ns, uvs = [], [], [], []
    off = 0
    for p in parts:
        m = p.mesh.copy()
        if p.smooth:
            m.merge_vertices()
        else:
            m.unmerge_vertices()             # faceted: one normal per face
        # unmerge_vertices lays vertices out face by face, so vertex k belongs to face k // 3
        n = m.vertex_normals if p.smooth else m.face_normals[np.arange(len(m.vertices)) // 3]
        vs.append(m.vertices)
        fs.append(m.faces + off)
        ns.append(n)
        uvs.append(np.tile(role_uv(p.role), (len(m.vertices), 1)))
        off += len(m.vertices)
    mat = trimesh.visual.material.PBRMaterial(
        name="kit_palette", baseColorTexture=Image.open(io.BytesIO(palette)),
        metallicFactor=0.0, roughnessFactor=0.85,
    )
    visual = trimesh.visual.TextureVisuals(uv=np.vstack(uvs), material=mat)
    return trimesh.Trimesh(vertices=np.vstack(vs), faces=np.vstack(fs), vertex_normals=np.vstack(ns),
                           visual=visual, process=False)


def write_glb(mesh: trimesh.Trimesh, name: str, path: Path, palette: bytes) -> bytes:
    """Single-node GLB via our own writer (trimesh can't emit TANGENT/TEXCOORD_1)."""
    from .gltf import Node, PieceMesh, write_scene
    uv = np.asarray(mesh.visual.uv, dtype=np.float32).copy()
    uv[:, 1] = 1.0 - uv[:, 1]                     # trimesh (bottom-left) -> glTF (top-left)
    pm = PieceMesh(positions=np.asarray(mesh.vertices, np.float32), normals=np.asarray(mesh.vertex_normals, np.float32),
                   uvs=uv, indices=np.asarray(mesh.faces, np.uint32).reshape(-1), image_png=palette)
    data = write_scene(Node(name, mesh=name), {name: pm}, palette)
    path.write_bytes(data)
    return data


def validate(parts: list[Part], mesh: trimesh.Trimesh, req: PieceRequest) -> dict:
    issues = []
    tris = len(mesh.faces)
    b = mesh.bounds
    ext = b[1] - b[0]
    if tris > req.budget.max_tris:
        issues.append(f"tris {tris} > budget {req.budget.max_tris}")
    if 1 > req.budget.max_materials:
        issues.append("material budget < 1")
    if float(ext.max()) > req.budget.max_extent_m:
        issues.append(f"extent {ext.max():.2f} m > {req.budget.max_extent_m} m")
    if req.pivot in ("base", "wall") and abs(b[0, 1]) > 1e-3:
        issues.append(f"pivot: min y {b[0, 1]:.4f} != 0")
    if req.pivot == "wall" and abs(b[0, 2]) > 1e-3:
        issues.append(f"wall pivot: back plane z {b[0, 2]:.4f} != 0")
    if not np.isfinite(mesh.vertices).all():
        issues.append("non-finite vertices")
    return {
        "ok": not issues, "issues": issues,
        "stats": {
            "tris": tris, "verts": len(mesh.vertices), "materials": 1,
            "bounds_m": np.round(b, 4).tolist(), "extent_m": np.round(ext, 4).tolist(),
            "roles": sorted({p.role for p in parts}),
        },
    }


# ----------------------------------------------------------- geometry cache
# Cleaned parts keyed by the geometry hash. A re-style or re-export is a
# cache hit and costs nothing.

def save_parts(parts: list[Part], path: Path) -> None:
    arrays = {}
    meta = []
    for i, p in enumerate(parts):
        arrays[f"v{i}"] = p.mesh.vertices
        arrays[f"f{i}"] = p.mesh.faces
        meta.append({"role": p.role, "smooth": p.smooth})
    arrays["meta"] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        np.savez_compressed(f, **arrays)


def load_parts(path: Path) -> list[Part]:
    z = np.load(path)
    meta = json.loads(bytes(z["meta"]).decode())
    return [Part(m["role"], trimesh.Trimesh(z[f"v{i}"], z[f"f{i}"], process=False), m["smooth"])
            for i, m in enumerate(meta)]
