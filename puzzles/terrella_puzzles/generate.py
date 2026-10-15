"""Deterministic puzzle generation from (scene, world context, slot).

Same inputs -> byte-identical instance on any machine. The seed is derived from
the diorama recipe hash, the local date and the slot name, so every player of
the same diorama gets the same daily puzzle (shareable, cacheable, generated
once per diorama per slot rather than per user).
"""
from __future__ import annotations

import math
from datetime import datetime
from itertools import combinations

from . import difficulty
from .context_rules import derived_keys, effective_attrs
from .model import Entity, Scene, WorldContext
from .predicates import Evaluator
from .rng import Rng, derive_seed

SCHEMA = "terrella.puzzle/1"
GENERATOR_VERSION = "0.1.0"
TYPES = ("riddle", "trail", "seek", "pattern", "viewpoint")

RIDDLE_SUBJECTS = ("window", "door", "lamp", "tree", "bike", "boat", "bench", "planter", "chimney")
# Attributes a player can see and a clue may name. Everything else is generator bookkeeping.
CLUE_KEYS = ("shutters", "flower_box", "lit", "curtains", "color", "gable", "snowy", "foliage", "lantern")
PARENT_KEYS = ("color", "gable", "name")
NEAR_KINDS = ("tree", "lamp", "bike", "boat", "bench", "planter", "bollard")
NEAR_RADIUS = 2.5
TRAIL_RADIUS = 7.0
MAX_PATTERN_CELLS = 12
ATTEMPTS = 24

SEEK_TOKENS = [
    # (context condition, token). First match wins; mirrors data-driven theming in SPEC.md.
    ({"weather": "snow"}, "token.mitten"),
    ({"snow_cover": True}, "token.mitten"),
    ({"weather": "rain"}, "token.rubber_duck"),
    ({"phase": "night"}, "token.firefly_jar"),
    ({"season": "autumn"}, "token.golden_acorn"),
    ({}, "token.paper_boat"),
]


class NoPuzzle(Exception):
    """The scene cannot host this puzzle type (e.g. no hide spots)."""


class _Ctx:
    """Everything a type generator needs, built once per call."""

    def __init__(self, scene: Scene, ctx: WorldContext, rng: Rng, tier: int):
        self.scene, self.ctx, self.rng, self.tier = scene, ctx, rng, tier
        self.attrs = effective_attrs(scene, ctx)
        self.ev = Evaluator(scene, self.attrs)
        self.ents = scene.by_id()
        self.derived = derived_keys()
        # Context-dependent clues ("the lit window") only from tier 2 up.
        self.allow_context = tier >= 2


# ---------------------------------------------------------------- riddles


def _candidate_predicates(g: _Ctx, e: Entity, extra: list[dict] | None = None) -> list[dict]:
    preds: list[dict] = []
    a = g.attrs[e.id]
    for k in CLUE_KEYS:
        if k in a and (g.allow_context or k not in g.derived):
            preds.append({"op": "attr", "key": k, "value": a[k]})
    if e.parent is not None:
        pa = g.attrs[e.parent]
        for k in PARENT_KEYS:
            if k in pa:
                preds.append({"op": "parent_attr", "key": k, "value": pa[k]})
    near_kinds = sorted({
        o.kind for o in g.scene.entities
        if o.kind in NEAR_KINDS and o.kind != e.kind and o.id != e.id
        and g.ev.present(o.id) and e.dist(o) <= NEAR_RADIUS
    })
    preds += [{"op": "near", "kind": k, "within": NEAR_RADIUS} for k in near_kinds]
    return preds


def _minimal_clue(g: _Ctx, target: Entity, preds: list[dict], required: list[dict]) -> dict | None:
    """Add shuffled predicates until the target is the unique match, then drop redundant ones."""
    clue = {"subject": target.kind, "predicates": list(required)}
    for p in g.rng.shuffled(preds):
        if g.ev.matches(clue) == [target.id]:
            break
        clue["predicates"].append(p)
    if g.ev.matches(clue) != [target.id]:
        return None
    for p in list(clue["predicates"]):
        if p in required:
            continue
        trial = {"subject": clue["subject"], "predicates": [q for q in clue["predicates"] if q is not p]}
        if g.ev.matches(trial) == [target.id]:
            clue = trial
    # Canonical order keeps text stable: attrs, then parent, then relations.
    order = {"attr": 0, "parent_attr": 1, "near": 2, "near_id": 3}
    clue["predicates"].sort(key=lambda p: (order[p["op"]], p.get("key", p.get("kind", ""))))
    return clue


# Derived values worth pointing at: "the lit window" at night is the point of a context clue;
# "the dark window" at noon is not.
CONTEXT_HIGHLIGHTS = {("lit", True), ("snowy", True), ("foliage", "orange"), ("foliage", "blossom"),
                      ("foliage", "bare")}


def _context_required(g: _Ctx, e: Entity) -> list[dict]:
    """At tier 2+, half the time anchor the clue on what the weather or hour changed."""
    if not g.allow_context or not g.rng.chance(0.5):
        return []
    a = g.attrs[e.id]
    hl = [k for k in CLUE_KEYS if k in g.derived and (k, a.get(k)) in CONTEXT_HIGHLIGHTS]
    return [{"op": "attr", "key": hl[0], "value": a[hl[0]]}] if hl else []


def _clue_uses_context(g: _Ctx, clue: dict) -> bool:
    return any(p.get("key") in g.derived for p in clue["predicates"])


def _riddle_targets(g: _Ctx) -> list[Entity]:
    return [
        e for e in g.scene.entities
        if e.kind in RIDDLE_SUBJECTS and g.ev.present(e.id) and len(g.scene.of_kind(e.kind)) >= 3
    ]


def _gen_riddle(g: _Ctx) -> tuple[dict, dict, dict]:
    targets = _riddle_targets(g)
    if not targets:
        raise NoPuzzle("no riddle subjects")
    best = None
    for _ in range(ATTEMPTS):
        t = g.rng.choice(targets)
        clue = _minimal_clue(g, t, _candidate_predicates(g, t), _context_required(g, t))
        if clue is None:
            continue
        score = difficulty.riddle_score(clue, g.ev.near_misses(clue))
        rank = (abs(difficulty.tier_of(score) - g.tier), 0 if _clue_uses_context(g, clue) else 1)
        cand = (rank, score, clue, t)
        if best is None or cand[0] < best[0]:
            best = cand
        if cand[0] == (0, 0) or (cand[0][0] == 0 and not g.allow_context):
            break
    if best is None:
        raise NoPuzzle("no unique riddle")
    _, score, clue, t = best
    return {"clue": clue}, {"answer": t.id}, {"score": score}


def _gen_trail(g: _Ctx) -> tuple[dict, dict, dict]:
    steps = {1: 2, 2: 3, 3: 4}[g.tier]
    targets = _riddle_targets(g)
    if not targets:
        raise NoPuzzle("no trail subjects")
    best = None
    for _ in range(ATTEMPTS):
        first = g.rng.choice(targets)
        clue = _minimal_clue(g, first, _candidate_predicates(g, first), _context_required(g, first))
        if clue is None:
            continue
        clues, answers, prev = [clue], [first.id], first
        for _ in range(steps - 1):
            near = [e for e in targets if e.id not in answers and e.kind != prev.kind
                    and e.dist(prev) <= TRAIL_RADIUS]
            if not near:
                break
            nxt = g.rng.choice(near)
            within = round(max(2.0, nxt.dist(prev) * 1.2), 1)
            rel = {"op": "near_id", "id": prev.id, "within": within}
            c = _minimal_clue(g, nxt, _candidate_predicates(g, nxt), [rel] + _context_required(g, nxt))
            if c is None:
                break
            clues.append(c)
            answers.append(nxt.id)
            prev = nxt
        if len(answers) != steps:
            continue
        score = difficulty.trail_score(clues, [g.ev.near_misses(c) for c in clues])
        rank = (abs(difficulty.tier_of(score) - g.tier),
                0 if any(_clue_uses_context(g, c) for c in clues) else 1)
        cand = (rank, score, clues, answers)
        if best is None or cand[0] < best[0]:
            best = cand
        if cand[0] == (0, 0) or (cand[0][0] == 0 and not g.allow_context):
            break
    if best is None:
        raise NoPuzzle("no trail of required length")
    _, score, clues, answers = best
    return {"clues": clues}, {"answers": answers}, {"score": score}


# ---------------------------------------------------------------- seek


def _seek_token(ctx: WorldContext) -> str:
    for cond, token in SEEK_TOKENS:
        if all(getattr(ctx, k) == v for k, v in cond.items()):
            return token
    raise AssertionError("SEEK_TOKENS must end with a catch-all")


def _gen_seek(g: _Ctx) -> tuple[dict, dict, dict]:
    spots = [e for e in g.scene.entities if "hide_spot" in e.tags and g.ev.present(e.id)]
    want = {1: 3, 2: 5, 3: 7}[g.tier]
    if len(spots) < 3:
        raise NoPuzzle("fewer than 3 hide spots")
    want = min(want, len(spots))
    chosen: list[Entity] = []
    min_sep = 3.0
    while len(chosen) < want and min_sep >= 0:
        for s in g.rng.shuffled(spots):
            if s not in chosen and all(s.dist(c) >= min_sep for c in chosen):
                chosen.append(s)
                if len(chosen) == want:
                    break
        min_sep -= 1.0  # relax spacing on cramped dioramas
    chosen.sort(key=lambda e: e.id)
    token = _seek_token(g.ctx)
    targets = [c.id for c in chosen]
    spawns = [{"anchor": t, "prop": token} for t in targets]
    score = difficulty.seek_score(len(targets), len(spots))
    return {"token": token}, {"targets": targets}, {"score": score, "spawns": spawns}


# ---------------------------------------------------------------- pattern


def _min_presses(start: list[bool], target: list[bool], cells: list[str], nbrs: dict[str, list[str]]) -> int:
    """Brute force over press subsets (order is irrelevant, pressing twice cancels)."""
    idx = {c: i for i, c in enumerate(cells)}
    masks = []
    for c in cells:
        m = 1 << idx[c]
        for n in nbrs.get(c, []):
            m |= 1 << idx[n]
        masks.append(m)
    diff = sum(1 << i for i, (a, b) in enumerate(zip(start, target)) if a != b)
    if diff == 0:
        return 0
    for k in range(1, len(cells) + 1):
        for combo in combinations(range(len(cells)), k):
            acc = 0
            for i in combo:
                acc ^= masks[i]
            if acc == diff:
                return k
    return -1


def _gen_pattern(g: _Ctx) -> tuple[dict, dict, dict]:
    groups: dict[str, list[Entity]] = {}
    for e in g.scene.entities:
        if (e.kind == "window" and e.parent and "row" in e.attrs and "col" in e.attrs
                and g.ev.present(e.id)):
            groups.setdefault(e.parent, []).append(e)
    want_cells = {1: (4, 6), 2: (4, 9), 3: (6, MAX_PATTERN_CELLS)}[g.tier]
    usable = sorted(
        (h for h, ws in groups.items() if want_cells[0] <= len(ws) <= want_cells[1]),
    )
    if not usable:
        usable = sorted(h for h, ws in groups.items() if 4 <= len(ws) <= MAX_PATTERN_CELLS)
    if not usable:
        raise NoPuzzle("no facade with 4..12 gridded windows")
    mode = "single" if g.tier == 1 else "cross"
    presses_wanted = {1: 3, 2: 3, 3: 4}[g.tier]
    for _ in range(ATTEMPTS):
        house = g.rng.choice(usable)
        ws = sorted(groups[house], key=lambda e: (e.attrs["row"], e.attrs["col"]))
        cells = [w.id for w in ws]
        pos = {(w.attrs["row"], w.attrs["col"]): w.id for w in ws}
        nbrs: dict[str, list[str]] = {}
        if mode == "cross":
            for w in ws:
                r, c = w.attrs["row"], w.attrs["col"]
                nbrs[w.id] = [pos[p] for p in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if p in pos]
        start = [bool(g.attrs[c].get("lit", False)) for c in cells]
        state = list(start)
        idx = {c: i for i, c in enumerate(cells)}
        for p in g.rng.sample(cells, presses_wanted):
            for c in [p] + nbrs.get(p, []):
                state[idx[c]] = not state[idx[c]]
        k = _min_presses(start, state, cells, nbrs)
        if k < max(2, presses_wanted - 1):
            continue
        house_attrs = g.attrs[house]
        owner = f"the house painted {house_attrs['color']}" if "color" in house_attrs else "this house"
        prompt = {"kind": "window", "owner": house, "owner_phrase": owner, "toggle_attr": "lit"}
        solution = {"cells": cells, "neighbors": nbrs, "start": start, "target": state, "mode": mode}
        return prompt, solution, {"score": difficulty.pattern_score(k, len(cells), mode), "min_presses": k}
    raise NoPuzzle("could not build a pattern with enough presses")


# ---------------------------------------------------------------- viewpoint


def _gen_viewpoint(g: _Ctx) -> tuple[dict, dict, dict]:
    subjects = [e for e in g.scene.entities
                if ("notable" in e.tags or e.id in g.scene.landmarks) and g.ev.present(e.id)]
    if not subjects:
        raise NoPuzzle("no notable entities")
    cam = g.scene.camera
    t = g.rng.choice(sorted(subjects, key=lambda e: e.id))
    yaw = g.rng.below(24) * 15.0
    pitch = cam.pitch_min + g.rng.below(int(cam.pitch_max - cam.pitch_min) + 1)
    lo, hi = cam.dist_min, min(cam.dist_max, cam.dist_min + 12.0)
    dist = lo + g.rng.below(int(hi - lo) + 1)
    cy, cp = math.radians(yaw), math.radians(pitch)
    eye = [
        round(t.pos[0] + dist * math.cos(cp) * math.sin(cy), 3),
        round(t.pos[1] + dist * math.sin(cp), 3),
        round(t.pos[2] + dist * math.cos(cp) * math.cos(cy), 3),
    ]
    tol = {1: {"eye_m": 3.0, "angle_deg": 20.0}, 2: {"eye_m": 2.0, "angle_deg": 12.0},
           3: {"eye_m": 1.2, "angle_deg": 7.0}}[g.tier]
    pose = {"target": t.id, "eye": eye, "look_at": [round(v, 3) for v in t.pos]}
    return {"target_hint": t.kind}, {"pose": pose, "tolerance": tol}, {"score": difficulty.viewpoint_score(g.tier)}


GENERATORS = {
    "riddle": _gen_riddle,
    "trail": _gen_trail,
    "seek": _gen_seek,
    "pattern": _gen_pattern,
    "viewpoint": _gen_viewpoint,
}
TYPE_WEIGHTS = {"riddle": 4, "trail": 2, "seek": 4, "pattern": 2, "viewpoint": 2}
TIER_WEIGHTS = (5, 4, 2)  # most puzzles stay cozy


# ---------------------------------------------------------------- validity


def _uses_context(prompt: dict, derived: frozenset[str]) -> bool:
    clues = prompt.get("clues") or ([prompt["clue"]] if "clue" in prompt else [])
    return any(p.get("key") in derived for c in clues for p in c["predicates"])


def _valid_until(ctx: WorldContext, context_bound: bool) -> str:
    now = datetime.fromisoformat(ctx.local_time)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    if context_bound:
        end = min(end, datetime.fromisoformat(ctx.phase_ends_at), datetime.fromisoformat(ctx.weather_stable_until))
    return end.isoformat()


# ---------------------------------------------------------------- entry point


def generate(scene: Scene, ctx: WorldContext, *, slot: str = "daily",
             tier: int | None = None, ptype: str | None = None) -> dict:
    seed = derive_seed(scene.recipe_hash, ctx.local_date, slot)
    rng = Rng(seed)
    if tier is None:
        tier = rng.weighted((1, 2, 3), TIER_WEIGHTS)
    if tier not in (1, 2, 3):
        raise ValueError("tier must be 1..3")
    if ptype is not None:
        order = [ptype]
    else:
        # Weighted shuffle: draw without replacement so infeasible types fall through.
        pool = list(TYPES)
        order = []
        while pool:
            t = rng.weighted(pool, [TYPE_WEIGHTS[p] for p in pool])
            order.append(t)
            pool.remove(t)
    last_err: Exception | None = None
    for t in order:
        g = _Ctx(scene, ctx, Rng(derive_seed(seed, t, tier)), tier)
        try:
            prompt, solution, meta = GENERATORS[t](g)
        except NoPuzzle as e:
            last_err = e
            continue
        context_bound = _uses_context(prompt, g.derived)
        reward_tags = sorted(set(ctx.tags() + [f"type:{t}", f"style:{scene.style}", f"tier:{tier}"]
                                 + (["context_clue"] if context_bound else [])))
        return {
            "schema": SCHEMA,
            "generator": GENERATOR_VERSION,
            "id": f"pz_{derive_seed(seed, t, tier):08x}",
            "type": t,
            "seed": seed,
            "slot": f"{ctx.local_date}/{slot}",
            "diorama": {"id": scene.diorama_id, "recipe_hash": scene.recipe_hash},
            "tier": tier,
            "difficulty": round(meta["score"], 2),
            "context": ctx.to_dict(),
            "context_bound": context_bound,
            "valid_from": ctx.local_time,
            "valid_until": _valid_until(ctx, context_bound),
            "prompt": prompt,
            "spawns": meta.get("spawns", []),
            "solution": solution,
            "reward_tags": reward_tags,
        }
    raise NoPuzzle(f"no feasible puzzle type: {last_err}")
