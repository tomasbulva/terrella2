"""Generator interface. Every source of geometry (procedural Python, Blender
scripts, hosted image-to-3D APIs) implements this, so the rest of the pipeline
(cleanup, validation, export, ledger) never cares where a mesh came from."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import trimesh

from ..spec import PieceRequest, StyleSpec


@dataclass
class Part:
    """One role-tagged chunk of a piece. Role picks the palette swatch."""
    role: str
    mesh: trimesh.Trimesh
    smooth: bool = False   # False = faceted (split normals), True = smooth


@dataclass(frozen=True)
class Usage:
    """A metered unit consumed while generating. Priced later by the ledger
    against a versioned price table, so generators never hard-code prices."""
    provider: str
    model: str
    unit: str          # "cpu_second", "generation", "image", "credit", ...
    qty: float


@dataclass
class GeneratedPiece:
    parts: list[Part]
    usage: list[Usage] = field(default_factory=list)
    # Free-form provenance: prompt, model + version, input artefact ids,
    # intermediate files. Stored verbatim in the asset manifest.
    provenance: dict[str, Any] = field(default_factory=dict)


class NotConfigured(RuntimeError):
    """Raised by a generator whose backend (binary, API key) is unavailable."""


class Generator(Protocol):
    id: str          # registry key, e.g. "procedural"
    version: str     # bump when output for the same input changes; part of the cache key

    def available(self) -> bool: ...

    def estimate(self, req: PieceRequest) -> list[Usage]:
        """Expected usage before running, used for budget checks."""
        ...

    def generate(self, req: PieceRequest, style: StyleSpec, workdir: Path) -> GeneratedPiece: ...
