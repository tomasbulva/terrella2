"""Pure-Python procedural kit pieces (trimesh primitives).

No Blender needed, so it runs in CI and on the backend. Deliberately simple,
storybook-proportioned shapes; the Blender generator is where richer pieces
(bevels, the dutch_houses.py lean/ivy logic) live. Every piece is built in
metres, +Y up, front facing +Z, before the cleanup stage applies the pivot.
"""
from __future__ import annotations

import time
import zlib
from pathlib import Path
from typing import Callable

import numpy as np
import trimesh

from ..spec import PieceRequest, StyleSpec
from .base import GeneratedPiece, Part, Usage


# ---------------------------------------------------------------- primitives

def box(w: float, h: float, d: float, x: float = 0, y: float = 0, z: float = 0) -> trimesh.Trimesh:
    """Box with its bottom centre at (x, y, z)."""
    m = trimesh.creation.box(extents=(w, h, d))
    m.apply_translation((x, y + h / 2, z))
    return m


def cyl(r: float, h: float, x: float = 0, y: float = 0, z: float = 0, sections: int = 10,
        axis: str = "y") -> trimesh.Trimesh:
    m = trimesh.creation.cylinder(radius=r, height=h, sections=sections)  # along Z, centred
    if axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, (1, 0, 0)))
        m.apply_translation((x, y + h / 2, z))
    else:
        m.apply_translation((x, y, z + h / 2))
    return m


def cone(r: float, h: float, x: float = 0, y: float = 0, z: float = 0, sections: int = 10) -> trimesh.Trimesh:
    m = trimesh.creation.cone(radius=r, height=h, sections=sections)       # base at z=0
    m.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, (1, 0, 0)))
    m.apply_translation((x, y, z))
    return m


def blob(r: float, x: float, y: float, z: float, rng: np.random.Generator, squash: float = 0.85) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=1, radius=r)
    m.vertices *= (1.0, squash, 1.0)
    m.vertices += rng.normal(0, r * 0.08, m.vertices.shape)   # lumpy, not a ball
    m.apply_translation((x, y, z))
    return m


def merge(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return trimesh.util.concatenate(meshes)


# ---------------------------------------------------------------- pieces
# Each builder returns a list of Parts. `p` = request params, `rng` seeded.

PieceFn = Callable[[dict, np.random.Generator], list[Part]]
PIECES: dict[str, PieceFn] = {}


def piece(kind: str):
    def deco(fn: PieceFn) -> PieceFn:
        PIECES[kind] = fn
        return fn
    return deco


@piece("window")
def window(p: dict, rng: np.random.Generator) -> list[Part]:
    w, h = p.get("width", 0.9), p.get("height", 1.5)
    fw, depth = 0.08, 0.10                         # frame width, frame depth
    cols, rows = p.get("bars_x", 2), p.get("bars_y", 3)
    frame = [
        box(w, fw, depth, 0, 0, depth / 2), box(w, fw, depth, 0, h - fw, depth / 2),
        box(fw, h, depth, -(w - fw) / 2, 0, depth / 2), box(fw, h, depth, (w - fw) / 2, 0, depth / 2),
    ]
    bars = []
    for i in range(1, cols):
        bars.append(box(0.03, h - 2 * fw, 0.04, -w / 2 + i * w / cols, fw, 0.05))
    for j in range(1, rows):
        bars.append(box(w - 2 * fw, 0.03, 0.04, 0, fw + j * (h - 2 * fw) / rows, 0.05))
    glass = box(w - 2 * fw, h - 2 * fw, 0.01, 0, fw, 0.03)
    sill = box(w + 0.16, 0.06, 0.18, 0, -0.06, 0.09)
    parts = [Part("window_frame", merge(frame + bars)), Part("glass", glass), Part("stone", sill)]
    if p.get("shutters", False):
        sw = w / 2
        shutters = [box(sw, h, 0.04, -(w / 2 + sw / 2 + 0.02), 0, 0.02),
                    box(sw, h, 0.04, (w / 2 + sw / 2 + 0.02), 0, 0.02)]
        parts.append(Part("wood", merge(shutters)))
    if p.get("flower_box", False):
        parts += flower_box({"width": w + 0.1, "z": 0.12, "y": -0.30}, rng)
    return parts


@piece("flower_box")
def flower_box(p: dict, rng: np.random.Generator) -> list[Part]:
    w, y, z = p.get("width", 0.9), p.get("y", 0.0), p.get("z", 0.12)
    trough = box(w, 0.22, 0.24, 0, y, z)
    n = max(3, int(w / 0.15))
    flowers = [blob(0.08, -w / 2 + (i + 0.5) * w / n, y + 0.26, z + rng.uniform(-0.05, 0.05), rng)
               for i in range(n)]
    leaves = [blob(0.10, -w / 2 + (i + 0.5) * w / n, y + 0.20, z, rng) for i in range(0, n, 2)]
    return [Part("wood", trough), Part("flower", merge(flowers), smooth=True),
            Part("foliage", merge(leaves), smooth=True)]


@piece("door")
def door(p: dict, rng: np.random.Generator) -> list[Part]:
    w, h, steps = p.get("width", 1.0), p.get("height", 2.2), int(p.get("stoep_steps", 2))
    sh = 0.17 * steps
    frame = [box(0.1, h, 0.12, -(w + 0.1) / 2, sh, 0.06), box(0.1, h, 0.12, (w + 0.1) / 2, sh, 0.06),
             box(w + 0.3, 0.14, 0.14, 0, sh + h, 0.07)]
    leaf = box(w, h, 0.06, 0, sh, 0.03)
    transom = box(w - 0.1, 0.35, 0.02, 0, sh + h - 0.4, 0.065)
    stoep = [box(w + 0.6, 0.17, 0.35 * (steps - i), 0, 0.17 * i, 0.35 * (steps - i) / 2) for i in range(steps)]
    parts = [Part("window_frame", merge(frame)), Part("door", leaf), Part("glass", transom)]
    if stoep:
        parts.append(Part("stone", merge(stoep)))
    if p.get("lantern", True):
        parts.append(Part("metal", merge([box(0.04, 0.04, 0.2, w / 2 + 0.3, sh + h - 0.3, 0.1),
                                          box(0.14, 0.24, 0.14, w / 2 + 0.3, sh + h - 0.45, 0.22)])))
    return parts


@piece("shutter_pair")
def shutter_pair(p: dict, rng: np.random.Generator) -> list[Part]:
    w, h = p.get("width", 0.9), p.get("height", 1.5)
    slats = []
    for side in (-1, 1):
        cx = side * (w / 4 + 0.01)
        slats.append(box(w / 2, h, 0.03, cx, 0, 0.015))
        for k in range(int(h / 0.12)):
            slats.append(box(w / 2 - 0.08, 0.025, 0.02, cx, 0.06 + k * 0.12, 0.04))
    return [Part("wood", merge(slats))]


@piece("chimney")
def chimney(p: dict, rng: np.random.Generator) -> list[Part]:
    w, d, h = p.get("width", 0.5), p.get("depth", 0.4), p.get("height", 1.0)
    body = box(w, h, d)
    cap = box(w + 0.1, 0.08, d + 0.1, 0, h)
    pots = [cyl(0.07, 0.25, -w / 4, h + 0.08, 0, sections=8), cyl(0.07, 0.2, w / 4, h + 0.08, 0, sections=8)]
    return [Part("wall_alt", body), Part("stone", cap), Part("roof", merge(pots), smooth=True)]


@piece("bollard")
def bollard(p: dict, rng: np.random.Generator) -> list[Part]:
    # Amsterdammertje: tapered post with a ball-ish top.
    post = cyl(0.07, 0.75, sections=10)
    collar = cyl(0.09, 0.05, y=0.62, sections=10)
    top = cyl(0.06, 0.08, y=0.75, sections=10)
    return [Part("metal", merge([post, collar, top]), smooth=True)]


@piece("street_lamp")
def street_lamp(p: dict, rng: np.random.Generator) -> list[Part]:
    h = p.get("height", 3.4)
    base = cyl(0.12, 0.4, sections=10)
    pole = cyl(0.05, h - 0.4, y=0.4, sections=8)
    head = merge([cone(0.22, 0.25, y=h + 0.45, sections=8), cyl(0.06, 0.08, y=h + 0.69, sections=8)])
    lamp = box(0.22, 0.38, 0.22, 0, h + 0.05)
    return [Part("metal", merge([base, pole, head]), smooth=True), Part("glass", lamp)]


@piece("tree")
def tree(p: dict, rng: np.random.Generator) -> list[Part]:
    h = p.get("height", 6.0)
    species = p.get("species", "round")       # round | cone
    trunk_h = h * 0.45
    trunk = cone(0.22, trunk_h * 1.6, sections=8)          # tapered trunk
    trunk.vertices[:, 1] = np.minimum(trunk.vertices[:, 1], trunk_h)
    if species == "cone":
        crowns = [cone(h * 0.28 * (1 - k * 0.25), h * 0.32, y=trunk_h * 0.6 + k * h * 0.2, sections=9)
                  for k in range(3)]
        return [Part("trunk", trunk), Part("foliage", merge(crowns))]
    n = int(p.get("crown_blobs", 5))
    crowns, alts = [], []
    for i in range(n):
        a = 2 * np.pi * i / n + rng.uniform(-0.3, 0.3)
        r = h * rng.uniform(0.16, 0.22)
        (alts if i % 3 == 2 else crowns).append(
            blob(r, np.cos(a) * h * 0.14, trunk_h + h * 0.18 + rng.uniform(-0.3, 0.6), np.sin(a) * h * 0.14, rng))
    crowns.append(blob(h * 0.24, 0, trunk_h + h * 0.32, 0, rng))
    parts = [Part("trunk", trunk), Part("foliage", merge(crowns), smooth=True)]
    if alts:
        parts.append(Part("foliage_alt", merge(alts), smooth=True))
    return parts


@piece("gable_step")
def gable_step(p: dict, rng: np.random.Generator) -> list[Part]:
    """Stepped gable top for a canal-house facade (wall pivot, sits on the
    facade's top edge). Steps narrow symmetrically to a crowning block."""
    w, steps, step_h, t = p.get("width", 5.0), int(p.get("steps", 3)), p.get("step_height", 0.7), 0.3
    wall, trim = [], []
    for i in range(steps + 1):
        sw = w * (1 - i / (steps + 1.4))
        wall.append(box(sw, step_h, t, 0, i * step_h, t / 2))
        trim.append(box(sw + 0.12, 0.08, t + 0.1, 0, (i + 1) * step_h - 0.04, t / 2))
    return [Part("wall", merge(wall)), Part("trim", merge(trim))]


@piece("bike")
def bike(p: dict, rng: np.random.Generator) -> list[Part]:
    r = 0.33
    rot = trimesh.transformations.rotation_matrix(np.pi / 2, (0, 1, 0))
    wheels = []
    for x in (-0.52, 0.52):
        t = trimesh.creation.torus(major_radius=r, minor_radius=0.025, major_sections=14, minor_sections=4)
        t.apply_transform(rot)
        t.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 0, 1)))
        t.apply_translation((x, r, 0))
        wheels.append(t)
    frame = [box(1.0, 0.04, 0.04, 0, 0.62, 0), box(0.04, 0.5, 0.04, -0.15, r, 0),
             box(0.04, 0.55, 0.04, 0.42, r, 0), box(0.5, 0.04, 0.04, 0.42, 0.88, 0)]
    saddle = box(0.22, 0.06, 0.12, -0.15, 0.84, 0)
    return [Part("metal", merge(wheels + frame)), Part("wood", saddle)]


@piece("slab")
def slab(p: dict, rng: np.random.Generator) -> list[Part]:
    """Unit box (1 x 1 x 1, bottom centre at origin) in one role. Scaled per
    instance by the assembler for house bodies, quays, water, plinths."""
    return [Part(p.get("role", "wall"), box(1.0, 1.0, 1.0))]


@piece("facade")
def facade(p: dict, rng: np.random.Generator) -> list[Part]:
    """Unit-width, unit-height front wall slab (depth 0.3 m) with a plinth
    band and a cornice line. Scaled non-uniformly per house; the role picks
    the house colour."""
    d = p.get("depth", 0.3)
    return [Part(p.get("role", "wall"), box(1.0, 1.0, d, 0, 0, d / 2)),
            Part("stone", box(1.0, 0.05, d + 0.04, 0, 0, (d + 0.04) / 2))]


@piece("roof_gable")
def roof_gable(p: dict, rng: np.random.Generator) -> list[Part]:
    """Unit pitched roof: 1 wide (x), 1 tall (y), 1 deep (z, running back from
    the facade, -z). Ridge runs front to back, as on canal houses."""
    tri = np.array([[-0.5, 0, 0], [0.5, 0, 0], [0, 1, 0]])
    v = np.vstack([tri, tri + (0, 0, -1)])
    f = np.array([[0, 1, 2], [3, 5, 4], [0, 3, 4], [0, 4, 1], [1, 4, 5], [1, 5, 2], [2, 5, 3], [2, 3, 0]])
    m = trimesh.Trimesh(v, f, process=True)
    m.fix_normals()
    return [Part("roof", m)]


@piece("boat")
def boat(p: dict, rng: np.random.Generator) -> list[Part]:
    L, W = p.get("length", 5.0), p.get("width", 1.8)
    hull = box(L, 0.6, W)
    v = hull.vertices
    v[:, 2] *= np.where(v[:, 1] < 0.3, 0.75, 1.0)                       # tumblehome
    v[:, 0] = np.where(np.abs(v[:, 0]) > L / 2 - 1e-6, v[:, 0] * np.where(v[:, 1] < 0.3, 0.85, 1.0), v[:, 0])
    hull.vertices = v
    cabin = box(L * 0.35, 0.5, W * 0.6, -L * 0.1, 0.6, 0)
    seats = box(L * 0.3, 0.12, W * 0.7, L * 0.25, 0.4, 0)
    return [Part(p.get("role", "door"), hull), Part("trim", cabin), Part("wood", seats)]


# ---------------------------------------------------------------- generator

class ProceduralGenerator:
    id = "procedural"
    version = "0.1.0"

    def available(self) -> bool:
        return True

    def estimate(self, req: PieceRequest) -> list[Usage]:
        return [Usage("local", "procedural", "cpu_second", 0.05)]

    def generate(self, req: PieceRequest, style: StyleSpec, workdir: Path) -> GeneratedPiece:
        if req.kind not in PIECES:
            raise KeyError(f"procedural: unknown kind {req.kind!r}; known: {sorted(PIECES)}")
        t0 = time.process_time()
        rng = np.random.default_rng([req.seed, zlib.crc32(req.name.encode())])
        parts = PIECES[req.kind](dict(req.params), rng)
        _wobble(parts, style.wobble * float(req.params.get("wobble_scale", 1.0)), rng,
                lock_back=req.pivot == "wall")
        cpu = time.process_time() - t0
        return GeneratedPiece(
            parts=parts,
            usage=[Usage("local", "procedural", "cpu_second", round(cpu, 4))],
            provenance={"builder": f"procedural.{req.kind}", "params": dict(req.params), "seed": req.seed},
        )


def _wobble(parts: list[Part], amp: float, rng: np.random.Generator, lock_back: bool) -> None:
    """'Nothing perfectly straight': one shared low-frequency displacement
    field over all parts so attached parts stay attached. Wall pieces keep
    their back plane flat so they sit flush on a facade."""
    if amp <= 0:
        return
    k = rng.uniform(0.6, 1.6, size=(3, 3))
    ph = rng.uniform(0, 2 * np.pi, size=(3, 3))
    for part in parts:
        v = part.mesh.vertices.copy()
        d = np.zeros_like(v)
        for axis in range(3):
            d[:, axis] = amp * sum(np.sin(k[axis, j] * v[:, j] + ph[axis, j]) for j in range(3)) / 3
        if lock_back:
            d[:, 2] = np.where(v[:, 2] <= 1e-4, 0.0, d[:, 2])
        part.mesh.vertices = v + d
