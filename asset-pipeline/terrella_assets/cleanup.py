"""Cleanup: make raw generator output a well-behaved mobile kit piece.

Order matters: repair -> decimate to budget -> scale -> pivot. Normals are
decided at export time from each part's smooth flag.
"""
from __future__ import annotations

import numpy as np
import trimesh

from .generators.base import Part
from .spec import PieceRequest

MIN_DECIMATE_TRIS = 64   # never decimate tiny parts (boxes, trims): it only breaks them


def repair(m: trimesh.Trimesh) -> trimesh.Trimesh:
    m = m.copy()
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    if not np.isfinite(m.vertices).all():
        raise ValueError("mesh has non-finite vertices")
    return m


def decimate(parts: list[Part], max_tris: int) -> list[Part]:
    """Spread the triangle budget over parts in proportion to their size,
    only touching parts big enough to survive it."""
    total = sum(len(p.mesh.faces) for p in parts)
    if total <= max_tris:
        return parts
    fixed = sum(len(p.mesh.faces) for p in parts if len(p.mesh.faces) <= MIN_DECIMATE_TRIS)
    flexible = total - fixed
    room = max(max_tris - fixed, 0)
    out = []
    for p in parts:
        n = len(p.mesh.faces)
        if n <= MIN_DECIMATE_TRIS or flexible == 0:
            out.append(p)
            continue
        target = max(int(n * room / flexible), MIN_DECIMATE_TRIS // 2)
        m = p.mesh.simplify_quadric_decimation(face_count=target)
        out.append(Part(p.role, repair(m), p.smooth))
    return out


def bounds(parts: list[Part]) -> np.ndarray:
    allv = np.vstack([p.mesh.vertices for p in parts])
    return np.array([allv.min(axis=0), allv.max(axis=0)])


def normalise(parts: list[Part], req: PieceRequest) -> list[Part]:
    """Uniform scale to target height, then move the origin to the pivot."""
    b = bounds(parts)
    s = 1.0
    if req.target_height_m:
        h = b[1, 1] - b[0, 1]
        if h <= 0:
            raise ValueError("cannot scale a flat piece to a height")
        s = req.target_height_m / h
    b = b * s
    cx, cz = (b[0, 0] + b[1, 0]) / 2, (b[0, 2] + b[1, 2]) / 2
    if req.pivot == "base":
        offset = np.array([-cx, -b[0, 1], -cz])
    elif req.pivot == "wall":
        offset = np.array([-cx, -b[0, 1], -b[0, 2]])
    else:
        offset = -(b[0] + b[1]) / 2
    out = []
    for p in parts:
        m = p.mesh.copy()
        m.apply_scale(s)
        m.apply_translation(offset)
        out.append(Part(p.role, m, p.smooth))
    return out


def clean(parts: list[Part], req: PieceRequest) -> list[Part]:
    parts = [Part(p.role, repair(p.mesh), p.smooth) for p in parts if len(p.mesh.faces)]
    if not parts:
        raise ValueError(f"{req.name}: generator produced no geometry")
    parts = decimate(parts, req.budget.max_tris)
    return normalise(parts, req)
