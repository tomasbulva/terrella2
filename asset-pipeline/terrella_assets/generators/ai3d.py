"""AI generator: prompt -> concept image -> image-to-3D -> raw mesh.

Two pluggable stages behind small interfaces. Real providers are stubs: they
declare their metering unit and the env var they would need, and refuse to
run. Nothing here makes a network call. The `mock` providers produce a
deterministic lumpy mesh so the cost/provenance path is exercised in tests.

Per the project brief, image-to-3D is best used for small single objects
(kit pieces), not whole dioramas, so that one hallucination can only spoil
one replaceable piece.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import trimesh

from ..spec import ROLES, PieceRequest, StyleSpec
from .base import GeneratedPiece, NotConfigured, Part, Usage


def build_prompt(req: PieceRequest, style: StyleSpec) -> str:
    """Single source of the prompt text so it is reproducible and recorded."""
    colours = ", ".join(f"{r} {c}" for r, c in sorted(style.palette.items()))
    detail = ", ".join(f"{k}={v}" for k, v in sorted(req.params.items()) if k != "role")
    return (
        f"A single {req.kind.replace('_', ' ')} game asset for a cozy miniature diorama, "
        f"style '{style.name}'. {style.notes} "
        f"Isolated object, centred, plain white background, flat even lighting, no cast or painted-in shadows, "
        f"slightly exaggerated storybook proportions, chunky readable shapes. "
        f"Palette: {colours}. {('Details: ' + detail + '.') if detail else ''}"
    ).replace("  ", " ").strip()


# ---------------------------------------------------------------- interfaces

@dataclass
class StageResult:
    path: Path
    usage: list[Usage]
    meta: dict


class ImageProvider(Protocol):
    id: str
    model: str
    def generate(self, prompt: str, out: Path, seed: int) -> StageResult: ...


class MeshProvider(Protocol):
    id: str
    model: str
    def generate(self, image: Path, out: Path, seed: int) -> StageResult: ...


@dataclass
class _Stub:
    """A real provider we have not wired yet. Declares what it would bill."""
    id: str
    model: str
    env: str
    unit: str

    def _refuse(self):
        if not os.environ.get(self.env):
            raise NotConfigured(f"{self.id}: set {self.env} to enable (not wired: no paid calls in this build)")
        raise NotConfigured(f"{self.id}: HTTP client not implemented yet; refusing to call a paid API")

    def generate(self, *_args, **_kw) -> StageResult:
        self._refuse()


# Unit names line up with prices.toml. Models listed are the ones the brief
# names; versions are placeholders until wired.
IMAGE_PROVIDERS = {
    "gemini-image": _Stub("gemini-image", "nano-banana", "GEMINI_API_KEY", "image"),
}
MESH_PROVIDERS = {
    "hi3d": _Stub("hi3d", "hi3d", "HI3D_API_KEY", "generation"),
    "hunyuan3d": _Stub("hunyuan3d", "hunyuan3d-3", "HUNYUAN_API_KEY", "generation"),
    "trellis2-local": _Stub("trellis2-local", "trellis.2", "TRELLIS_ENDPOINT", "gpu_second"),
}


class MockImageProvider:
    id, model = "mock", "mock-image-1"

    def generate(self, prompt: str, out: Path, seed: int) -> StageResult:
        from PIL import Image
        h = hashlib.sha256(f"{prompt}|{seed}".encode()).digest()
        Image.new("RGB", (64, 64), tuple(h[:3])).save(out)
        return StageResult(out, [Usage("mock", self.model, "image", 1)], {"prompt_sha256": h.hex()})


class MockMeshProvider:
    id, model = "mock", "mock-3d-1"

    def generate(self, image: Path, out: Path, seed: int) -> StageResult:
        # Over-dense on purpose (~5k tris) so cleanup has to decimate, like real output.
        rng = np.random.default_rng(int.from_bytes(hashlib.sha256(image.read_bytes()).digest()[:4], "little") + seed)
        m = trimesh.creation.icosphere(subdivisions=4, radius=0.5)
        m.vertices *= (1.0, 1.6, 1.0)
        m.vertices += rng.normal(0, 0.02, m.vertices.shape)
        m.apply_translation((0.3, 0.9, -0.2))     # off-centre and floating, like real output
        m.export(out)
        return StageResult(out, [Usage("mock", self.model, "generation", 1)], {})


IMAGE_PROVIDERS["mock"] = MockImageProvider()
MESH_PROVIDERS["mock"] = MockMeshProvider()


class AIGenerator:
    """`generator = "ai3d:<mesh>"` or `"ai3d:<mesh>+<image>"` in a kit file."""
    version = "0.1.0"

    def __init__(self, mesh: str, image: str | None = None):
        self.mesh = MESH_PROVIDERS[mesh]
        self.image = IMAGE_PROVIDERS[image or ("mock" if mesh == "mock" else "gemini-image")]
        self.id = f"ai3d:{mesh}+{self.image.id}"

    def style_inputs(self, req: PieceRequest, style: StyleSpec) -> dict:
        # The style reaches the geometry through the prompt, so the prompt is
        # part of the cache key: a restyle regenerates (and is billed).
        return {"prompt": build_prompt(req, style)}

    def available(self) -> bool:
        return not isinstance(self.mesh, _Stub) and not isinstance(self.image, _Stub)

    def estimate(self, req: PieceRequest) -> list[Usage]:
        img_unit = getattr(self.image, "unit", "image")
        mesh_unit = getattr(self.mesh, "unit", "generation")
        return [Usage(self.image.id, self.image.model, img_unit, 1),
                Usage(self.mesh.id, self.mesh.model, mesh_unit, 1)]

    def generate(self, req: PieceRequest, style: StyleSpec, workdir: Path) -> GeneratedPiece:
        workdir.mkdir(parents=True, exist_ok=True)
        prompt = build_prompt(req, style)
        img = self.image.generate(prompt, workdir / "concept.png", req.seed)
        mesh = self.mesh.generate(img.path, workdir / "raw.glb", req.seed)
        m = trimesh.load(mesh.path, force="mesh")
        role = req.params.get("role", "wall")
        if role not in ROLES:
            raise ValueError(f"ai3d: params.role {role!r} not in {ROLES}")
        # Known gap: AI meshes carry their own texture. Until the atlas bake
        # step exists we recolour to one palette role (fine for props).
        return GeneratedPiece(
            parts=[Part(role, m, smooth=True)],
            usage=img.usage + mesh.usage,
            provenance={
                "prompt": prompt,
                "image": {"provider": self.image.id, "model": self.image.model, **img.meta},
                "mesh": {"provider": self.mesh.id, "model": self.mesh.model, **mesh.meta},
                "seed": req.seed,
                "intermediates": ["concept.png", "raw.glb"],
            },
        )
