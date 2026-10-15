"""Generator registry. Kit files name a generator by key:
    "procedural"            pure-Python primitives (always available)
    "blender"               blender/kit_pieces.py via Blender or the bpy wheel
    "blender:<script.py>"   any script following the Blender contract
    "ai3d:<mesh>[+<image>]" hosted/local image-to-3D (stubs + "mock")
"""
from __future__ import annotations

from pathlib import Path

from .ai3d import AIGenerator
from .base import GeneratedPiece, Generator, NotConfigured, Part, Usage
from .blender import BlenderGenerator
from .procedural import ProceduralGenerator

__all__ = ["get", "Generator", "GeneratedPiece", "NotConfigured", "Part", "Usage"]

_cache: dict[str, Generator] = {}


def get(key: str, kit_dir: Path | None = None) -> Generator:
    if key in _cache:
        return _cache[key]
    if key == "procedural":
        g = ProceduralGenerator()
    elif key == "blender":
        g = BlenderGenerator()
    elif key.startswith("blender:"):
        script = Path(key.split(":", 1)[1])
        if not script.is_absolute() and kit_dir is not None:
            script = kit_dir / script
        g = BlenderGenerator(script)
    elif key.startswith("ai3d:"):
        mesh, _, image = key.split(":", 1)[1].partition("+")
        g = AIGenerator(mesh, image or None)
    else:
        raise KeyError(f"unknown generator {key!r}")
    _cache[key] = g
    return g
