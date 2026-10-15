"""Inputs to the rules library: the puzzle view of a diorama, and world context.

Both are plain JSON on the wire (see SPEC.md). These dataclasses are thin,
read-only views with validation; nothing here knows about any engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

PHASES = ("night", "dawn", "day", "golden", "dusk")
WEATHERS = ("clear", "cloudy", "rain", "snow", "fog", "storm")
SEASONS = ("spring", "summer", "autumn", "winter")


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    pos: tuple[float, float, float]
    tags: frozenset[str] = frozenset()
    attrs: dict[str, Any] = field(default_factory=dict)
    parent: str | None = None
    kit_piece: str | None = None

    @staticmethod
    def from_dict(d: dict) -> "Entity":
        try:
            pos = tuple(float(v) for v in d["pos"])
            if len(pos) != 3:
                raise InputError(f"entity {d.get('id')}: pos must have 3 components")
            return Entity(
                id=str(d["id"]),
                kind=str(d["kind"]),
                pos=pos,  # type: ignore[arg-type]
                tags=frozenset(d.get("tags", ())),
                attrs=dict(d.get("attrs", {})),
                parent=d.get("parent"),
                kit_piece=d.get("kit_piece"),
            )
        except KeyError as e:
            raise InputError(f"entity missing field {e}") from None

    def dist(self, other: "Entity") -> float:
        return math.dist(self.pos, other.pos)


@dataclass(frozen=True)
class CameraLimits:
    pitch_min: float = 10.0
    pitch_max: float = 75.0
    dist_min: float = 4.0
    dist_max: float = 30.0


@dataclass(frozen=True)
class Scene:
    """Puzzle view of one built diorama (the generator's `puzzle_scene.json` sidecar)."""

    diorama_id: str
    recipe_hash: str
    style: str
    entities: tuple[Entity, ...]
    camera: CameraLimits = CameraLimits()
    landmarks: tuple[str, ...] = ()

    @staticmethod
    def from_dict(d: dict) -> "Scene":
        ents = tuple(Entity.from_dict(e) for e in d["entities"])
        ids = [e.id for e in ents]
        if len(set(ids)) != len(ids):
            raise InputError("duplicate entity ids in scene")
        known = set(ids)
        for e in ents:
            if e.parent is not None and e.parent not in known:
                raise InputError(f"entity {e.id}: unknown parent {e.parent}")
        cam = CameraLimits(**d.get("camera", {}))
        return Scene(
            diorama_id=d["diorama_id"],
            recipe_hash=d["recipe_hash"],
            style=d["style"],
            entities=ents,
            camera=cam,
            landmarks=tuple(d.get("landmarks", ())),
        )

    def by_id(self) -> dict[str, Entity]:
        return {e.id: e for e in self.entities}

    def of_kind(self, kind: str) -> list[Entity]:
        return [e for e in self.entities if e.kind == kind]


@dataclass(frozen=True)
class WorldContext:
    """Compact scene state from the world context service. All times are local ISO strings."""

    local_date: str              # "2026-10-15"
    local_time: str              # "2026-10-15T19:40:00+02:00"
    phase: str                   # night | dawn | day | golden | dusk
    phase_ends_at: str           # next sun event, local ISO
    season: str                  # hemisphere-corrected
    weather: str                 # clear | cloudy | rain | snow | fog | storm
    weather_stable_until: str    # local ISO; generator may only lean on weather until then
    snow_cover: bool = False     # ground still white after snowfall stopped
    geocell: str = ""            # coarse geohash (precision 5, ~5 km); never exact location

    @staticmethod
    def from_dict(d: dict) -> "WorldContext":
        ctx = WorldContext(**{k: d[k] for k in WorldContext.__dataclass_fields__ if k in d})
        if ctx.phase not in PHASES:
            raise InputError(f"unknown phase {ctx.phase}")
        if ctx.weather not in WEATHERS:
            raise InputError(f"unknown weather {ctx.weather}")
        if ctx.season not in SEASONS:
            raise InputError(f"unknown season {ctx.season}")
        return ctx

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def tags(self) -> list[str]:
        t = [f"phase:{self.phase}", f"weather:{self.weather}", f"season:{self.season}"]
        if self.snow_cover:
            t.append("snow_cover")
        return t
