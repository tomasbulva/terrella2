"""Blender-scripted generator.

Runs a Blender Python script headless and reads back the GLB it exports. The
contract a script must follow (see blender/kit_pieces.py):

    <blender> -b --python-exit-code 1 -P script.py -- --request req.json --out raw.glb

  * req.json is the PieceRequest as JSON (name, kind, params, seed) plus the
    style wobble value.
  * The script builds the piece in metres, +Z up (Blender), front facing -Y,
    and exports GLB with "+Y up" (the default), so the result arrives in the
    pipeline's glTF frame: +Y up, front +Z.
  * Each object's *material name* is its palette role ("wall", "glass", ...).
    Objects with a custom property smooth=1 are smooth shaded.

Blender can come from a `blender` binary on PATH (or $BLENDER) or the `bpy`
pip wheel; with the wheel the script runs under plain `python`. That is how
dutch_houses.py plugs in later: wrap its piece builders behind this contract.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import trimesh

from ..spec import ROLES, PieceRequest, StyleSpec
from .base import GeneratedPiece, NotConfigured, Part, Usage

DEFAULT_SCRIPT = Path(__file__).resolve().parents[2] / "blender" / "kit_pieces.py"


def blender_command() -> list[str] | None:
    exe = os.environ.get("BLENDER") or shutil.which("blender")
    if exe:
        return [exe, "-b", "--factory-startup", "--python-exit-code", "1", "-P"]
    if importlib.util.find_spec("bpy") is not None:
        return [sys.executable]
    return None


class BlenderGenerator:
    id = "blender"
    version = "0.1.0"

    def __init__(self, script: Path | None = None, timeout_s: int = 600):
        self.script = Path(script) if script else DEFAULT_SCRIPT
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return blender_command() is not None and self.script.exists()

    def estimate(self, req: PieceRequest) -> list[Usage]:
        return [Usage("local", "blender", "cpu_second", 5.0)]

    def generate(self, req: PieceRequest, style: StyleSpec, workdir: Path) -> GeneratedPiece:
        cmd = blender_command()
        if cmd is None:
            raise NotConfigured("blender: no `blender` binary on PATH/$BLENDER and no `bpy` module")
        workdir.mkdir(parents=True, exist_ok=True)
        req_path, out_path = workdir / "request.json", workdir / "raw.glb"
        req_path.write_text(json.dumps({
            "name": req.name, "kind": req.kind, "params": req.params, "seed": req.seed,
            "wobble": style.wobble,
        }))
        argv = cmd + [str(self.script), "--", "--request", str(req_path), "--out", str(out_path)]
        t0 = time.monotonic()
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout_s)
        wall = time.monotonic() - t0
        (workdir / "blender.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        if proc.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"blender failed ({proc.returncode}); see {workdir / 'blender.log'}")
        return GeneratedPiece(
            parts=parts_from_glb(out_path),
            usage=[Usage("local", "blender", "cpu_second", round(wall, 2))],
            provenance={"builder": f"blender:{self.script.name}:{req.kind}", "params": dict(req.params),
                        "seed": req.seed, "script_sha256": _sha256(self.script)},
        )


def parts_from_glb(path: Path) -> list[Part]:
    """Load a GLB and group geometry by material name (= palette role)."""
    scene = trimesh.load(path, force="scene")
    by_role: dict[str, list[trimesh.Trimesh]] = {}
    smooth_roles: set[str] = set()
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        g = scene.geometry[geom_name]
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        mat = getattr(getattr(g.visual, "material", None), "name", None) or "wall"
        role = mat.split(".")[0]
        if role not in ROLES:
            role = "wall"
        m = g.copy()
        m.apply_transform(transform)
        by_role.setdefault(role, []).append(m)
        extras = (scene.graph.transforms.node_data.get(node, {}) or {}).get("extras") or {}
        if extras.get("smooth"):
            smooth_roles.add(role)
    return [Part(role, trimesh.util.concatenate(ms), smooth=role in smooth_roles)
            for role, ms in by_role.items()]


def _sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()
