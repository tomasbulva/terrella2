"""Server-side validation: is this instance correct for this scene?

Run on every generated instance before it is published, and on any instance
loaded from cache after the diorama, rules or generator version changed.
"""
from __future__ import annotations

from datetime import datetime

from .check import check
from .context_rules import effective_attrs
from .generate import SCHEMA, TYPES, _min_presses
from .model import Scene, WorldContext
from .predicates import Evaluator

REQUIRED = ("schema", "id", "type", "seed", "diorama", "tier", "context", "valid_from",
            "valid_until", "prompt", "spawns", "solution", "reward_tags")


def answer_attempt(instance: dict) -> dict:
    """The canonical correct attempt. Used by tests, validation and support tooling."""
    t, s = instance["type"], instance["solution"]
    if t == "riddle":
        return {"select": s["answer"]}
    if t == "trail":
        return {"selects": list(s["answers"])}
    if t == "seek":
        return {"found": list(s["targets"])}
    if t == "viewpoint":
        return {"eye": list(s["pose"]["eye"]), "look_at": list(s["pose"]["look_at"])}
    if t == "pattern":
        return {"presses": _solve_pattern(s)}
    raise ValueError(t)


def _solve_pattern(s: dict) -> list[str]:
    from itertools import combinations
    cells, nbrs = s["cells"], s["neighbors"]
    for k in range(0, len(cells) + 1):
        for combo in combinations(cells, k):
            state = list(s["start"])
            idx = {c: i for i, c in enumerate(cells)}
            for p in combo:
                for c in [p] + nbrs.get(p, []):
                    state[idx[c]] = not state[idx[c]]
            if state == list(s["target"]):
                return list(combo)
    raise ValueError("pattern unsolvable")


def validate(instance: dict, scene: Scene) -> list[str]:
    errs: list[str] = []
    missing = [k for k in REQUIRED if k not in instance]
    if missing:
        return [f"missing fields: {missing}"]
    if instance["schema"] != SCHEMA:
        errs.append(f"unknown schema {instance['schema']}")
    t = instance["type"]
    if t not in TYPES:
        return errs + [f"unknown type {t}"]
    if instance["tier"] not in (1, 2, 3):
        errs.append("tier out of range")
    if instance["diorama"].get("recipe_hash") != scene.recipe_hash:
        errs.append("instance was generated for a different diorama build")
        return errs
    try:
        ctx = WorldContext.from_dict(instance["context"])
    except Exception as e:  # noqa: BLE001 - report, don't crash validation
        return errs + [f"bad context: {e}"]
    if datetime.fromisoformat(instance["valid_until"]) <= datetime.fromisoformat(instance["valid_from"]):
        errs.append("empty validity window")
    if instance.get("context_bound") and (
        datetime.fromisoformat(instance["valid_until"]) > datetime.fromisoformat(ctx.phase_ends_at)
    ):
        errs.append("context-bound puzzle outlives its phase")

    ents = scene.by_id()
    ev = Evaluator(scene, effective_attrs(scene, ctx))
    s, pr = instance["solution"], instance["prompt"]

    def need(eid: str, what: str) -> bool:
        if eid not in ents:
            errs.append(f"{what}: unknown entity {eid}")
            return False
        if not ev.present(eid):
            errs.append(f"{what}: entity {eid} is not present in this context")
            return False
        return True

    if t == "riddle":
        if need(s["answer"], "answer"):
            m = ev.matches(pr["clue"])
            if m != [s["answer"]]:
                errs.append(f"riddle not uniquely solvable: matches {m}")
    elif t == "trail":
        if len(pr["clues"]) != len(s["answers"]) or len(s["answers"]) < 2:
            errs.append("trail clue/answer count mismatch")
        else:
            for i, (c, a) in enumerate(zip(pr["clues"], s["answers"])):
                if not need(a, f"step {i}"):
                    continue
                m = ev.matches(c)
                if m != [a]:
                    errs.append(f"trail step {i} not unique: matches {m}")
                if i > 0 and not any(p["op"] == "near_id" and p["id"] == s["answers"][i - 1]
                                     for p in c["predicates"]):
                    errs.append(f"trail step {i} does not chain from step {i - 1}")
            if len(set(s["answers"])) != len(s["answers"]):
                errs.append("trail revisits an entity")
    elif t == "seek":
        tg = s["targets"]
        if not tg or len(set(tg)) != len(tg):
            errs.append("seek targets empty or duplicated")
        for a in tg:
            if need(a, "seek target") and "hide_spot" not in ents[a].tags:
                errs.append(f"seek target {a} is not a hide spot")
        if sorted(sp["anchor"] for sp in instance["spawns"]) != sorted(tg):
            errs.append("seek spawns do not match targets")
    elif t == "pattern":
        cells = s["cells"]
        for c in cells:
            need(c, "pattern cell")
        if not (len(s["start"]) == len(s["target"]) == len(cells)):
            errs.append("pattern state length mismatch")
        for c, ns in s["neighbors"].items():
            for n in ns:
                if c not in s["neighbors"].get(n, []):
                    errs.append(f"pattern neighbours not symmetric: {c}-{n}")
        if not errs and _min_presses(s["start"], s["target"], cells, s["neighbors"]) < 1:
            errs.append("pattern unsolvable or already solved")
    elif t == "viewpoint":
        pose = s["pose"]
        if need(pose["target"], "viewpoint target"):
            dx, dy, dz = (pose["eye"][i] - pose["look_at"][i] for i in range(3))
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            import math
            pitch = math.degrees(math.asin(dy / dist)) if dist else 0.0
            cam = scene.camera
            if not (cam.dist_min - 0.01 <= dist <= cam.dist_max + 0.01):
                errs.append(f"viewpoint distance {dist:.1f} outside camera limits")
            if not (cam.pitch_min - 0.05 <= pitch <= cam.pitch_max + 0.05):
                errs.append(f"viewpoint pitch {pitch:.1f} outside camera limits")

    if not errs:
        res = check(instance, answer_attempt(instance))
        if not res["solved"]:
            errs.append("checker rejects the canonical answer")
    return errs
