"""Declarative clue predicates, evaluated against a scene in a given context.

A clue is `{"subject": <kind>, "predicates": [...]}`; an entity answers the
clue when its kind matches and every predicate holds. Predicate ops:

  {"op": "attr", "key": k, "value": v}                 entity.attrs[k] == v
  {"op": "parent_attr", "key": k, "value": v}          parent's attrs[k] == v
  {"op": "near", "kind": k, "within": r}               some other entity of kind k within r
  {"op": "near_id", "id": i, "within": r}              entity i within r (trail steps)
"""
from __future__ import annotations

from typing import Any

from .model import Scene


class Evaluator:
    def __init__(self, scene: Scene, attrs: dict[str, dict[str, Any]]):
        self.scene = scene
        self.attrs = attrs
        self.ents = scene.by_id()

    def present(self, eid: str) -> bool:
        return self.attrs[eid].get("present", True) is not False

    def holds(self, eid: str, p: dict) -> bool:
        e = self.ents[eid]
        op = p["op"]
        if op == "attr":
            return self.attrs[eid].get(p["key"]) == p["value"]
        if op == "parent_attr":
            return e.parent is not None and self.attrs[e.parent].get(p["key"]) == p["value"]
        if op == "near":
            return any(
                o.kind == p["kind"] and o.id != eid and self.present(o.id) and e.dist(o) <= p["within"]
                for o in self.scene.entities
            )
        if op == "near_id":
            return p["id"] != eid and e.dist(self.ents[p["id"]]) <= p["within"]
        raise ValueError(f"unknown predicate op {op}")

    def matches(self, clue: dict) -> list[str]:
        return [
            e.id
            for e in self.scene.entities
            if e.kind == clue["subject"]
            and self.present(e.id)
            and all(self.holds(e.id, p) for p in clue["predicates"])
        ]

    def near_misses(self, clue: dict) -> int:
        """Entities of the subject kind failing exactly one predicate: the 'distractors'."""
        n = 0
        for e in self.scene.entities:
            if e.kind != clue["subject"] or not self.present(e.id):
                continue
            fails = sum(not self.holds(e.id, p) for p in clue["predicates"])
            if fails == 1:
                n += 1
        return n
