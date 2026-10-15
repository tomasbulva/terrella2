"""Input specs: style spec, per-piece requests and mobile budgets.

A kit file (TOML) holds one style spec plus the list of pieces to build. The
style spec only drives colour (the palette atlas), never geometry, so a
hallucinated or re-generated style can change how a kit looks but cannot
break a mesh. Geometry is driven by the piece kind, its params and the seed.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Palette roles every generator may tag geometry with. The engine shader keys
# off the same names (e.g. "glass" gets interior mapping + night emission,
# up-facing texels of any role get snow), so keep this list stable and append
# only. Index = swatch slot in the palette atlas.
ROLES: tuple[str, ...] = (
    "wall", "wall_alt", "trim", "roof", "window_frame", "glass", "door",
    "metal", "wood", "stone", "foliage", "foliage_alt", "trunk", "flower",
    "water", "ground",
)

# Pivot conventions, all in metres, glTF +Y up, front faces +Z.
#   base:  origin at the bottom centre of the bounding box (trees, lamps, props)
#   wall:  origin at bottom centre of the back face; the piece sits on a wall
#          at z=0 and protrudes along +Z (windows, doors, shutters)
#   center: origin at the bounding-box centre (rarely needed)
PIVOTS = ("base", "wall", "center")


@dataclass(frozen=True)
class Budget:
    max_tris: int = 800
    max_materials: int = 1
    max_extent_m: float = 12.0


@dataclass(frozen=True)
class StyleSpec:
    """Output of the 'seed image -> vision model -> style spec' step."""
    name: str
    palette: dict[str, str]                     # role -> "#rrggbb"
    wobble: float = 0.015                        # storybook irregularity, metres
    notes: str = ""
    source: dict[str, Any] = field(default_factory=dict)  # provenance of the spec itself

    def colour(self, role: str) -> tuple[int, int, int]:
        hexv = self.palette.get(role) or self.palette.get("wall", "#cccccc")
        hexv = hexv.lstrip("#")
        return int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)


@dataclass(frozen=True)
class PieceRequest:
    name: str                 # unique within the kit, dotted "<category>.<variant>", e.g. "window.tall"
    kind: str                 # generator-specific piece kind, e.g. "window"
    generator: str            # registry key, e.g. "procedural", "blender", "ai3d:mock"
    pivot: str = "base"
    target_height_m: float | None = None   # scale-normalise to this height
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    budget: Budget = field(default_factory=Budget)
    tags: tuple[str, ...] = ()
    kit: str = ""             # filled by load_kit

    @property
    def slug(self) -> str:
        """Catalog slug, e.g. "nl_canal.window.tall" (^[a-z0-9][a-z0-9._-]{0,159}$)."""
        return f"{self.kit}.{self.name}"

    @property
    def category(self) -> str:
        return self.name.split(".")[0]


@dataclass(frozen=True)
class KitSpec:
    name: str
    version: str
    style: StyleSpec
    pieces: tuple[PieceRequest, ...]


def _budget(d: dict[str, Any] | None, default: Budget) -> Budget:
    if not d:
        return default
    return Budget(
        max_tris=int(d.get("max_tris", default.max_tris)),
        max_materials=int(d.get("max_materials", default.max_materials)),
        max_extent_m=float(d.get("max_extent_m", default.max_extent_m)),
    )


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,159}$")


def load_kit(src: str | Path | dict) -> KitSpec:
    """From a TOML path, or from the same structure as a dict (a job's input)."""
    raw = src if isinstance(src, dict) else tomllib.loads(Path(src).read_text())
    kit = raw["kit"]
    st = raw["style"]
    unknown = set(st["palette"]) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown palette roles: {sorted(unknown)}; allowed: {ROLES}")
    style = StyleSpec(
        name=st["name"], palette=dict(st["palette"]), wobble=float(st.get("wobble", 0.015)),
        notes=st.get("notes", ""), source=dict(st.get("source", {})),
    )
    default_budget = _budget(raw.get("budget"), Budget())
    pieces = []
    seen = set()
    for p in raw["piece"]:
        if not SLUG_RE.match(f"{kit['name']}.{p['name']}"):
            raise ValueError(f"{p['name']!r}: kit + piece name must form a catalog slug [a-z0-9._-]")
        if p["name"] in seen:
            raise ValueError(f"duplicate piece name {p['name']!r}")
        seen.add(p["name"])
        pivot = p.get("pivot", "base")
        if pivot not in PIVOTS:
            raise ValueError(f"{p['name']}: pivot must be one of {PIVOTS}")
        pieces.append(PieceRequest(
            name=p["name"], kind=p["kind"], generator=p.get("generator", "procedural"),
            pivot=pivot, target_height_m=p.get("target_height_m"),
            params=dict(p.get("params", {})), seed=int(p.get("seed", kit.get("seed", 0))),
            budget=_budget(p.get("budget"), default_budget), tags=tuple(p.get("tags", ())),
            kit=kit["name"],
        ))
    return KitSpec(name=kit["name"], version=str(kit["version"]), style=style, pieces=tuple(pieces))
