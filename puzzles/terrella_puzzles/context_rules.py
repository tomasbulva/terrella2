"""Context-derived state: what the world looks like right now.

The renderer and the puzzle library must agree on which lamps are lit or which
roofs are white, otherwise a clue like "the lit window" points at nothing. So
the rules live in data (`data/context_rules.json`) and both sides read them.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .model import Entity, Scene, WorldContext

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=None)
def load_rules(path: str | None = None) -> tuple[dict, ...]:
    p = Path(path) if path else DATA / "context_rules.json"
    return tuple(json.loads(p.read_text())["rules"])


def _when_matches(when: dict, ctx: WorldContext) -> bool:
    for key, allowed in when.items():
        value = getattr(ctx, key)
        if isinstance(allowed, list):
            if value not in allowed:
                return False
        elif value != allowed:
            return False
    return True


def _entity_matches(match: dict, e: Entity) -> bool:
    if "kind" in match and e.kind not in match["kind"]:
        return False
    if "tag" in match and match["tag"] not in e.tags:
        return False
    for k, v in match.get("attrs", {}).items():
        if e.attrs.get(k) != v:
            return False
    return True


def effective_attrs(scene: Scene, ctx: WorldContext, rules=None) -> dict[str, dict[str, Any]]:
    """Base attrs overlaid with context-derived attrs, per entity id. Later rules win."""
    rules = load_rules() if rules is None else rules
    out: dict[str, dict[str, Any]] = {}
    for e in scene.entities:
        attrs = dict(e.attrs)
        for r in rules:
            if _when_matches(r["when"], ctx) and _entity_matches(r["match"], e):
                attrs.update(r["set"])
        out[e.id] = attrs
    return out


def derived_keys(rules=None) -> frozenset[str]:
    """Attribute names that depend on context (so a clue using them expires)."""
    rules = load_rules() if rules is None else rules
    return frozenset(k for r in rules for k in r["set"])
