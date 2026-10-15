#!/usr/bin/env python3
"""Regenerates fixtures/check_vectors.json, the cross-language conformance suite.

Every port of the checker (godot/puzzle_check.gd, any server port) must return
exactly `expected` for each case. RNG vectors are included for future ports of
the generator. Run from puzzles/: python3 tools/make_check_vectors.py
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from terrella_puzzles import Scene, WorldContext, answer_attempt, check, generate  # noqa: E402
from terrella_puzzles.rng import Rng, fnv1a32  # noqa: E402

scene = Scene.from_dict(json.loads((ROOT / "fixtures/scenes/amsterdam_canal.json").read_text()))
ctxs = {k: WorldContext.from_dict(v) for k, v in json.loads((ROOT / "fixtures/contexts.json").read_text()).items()}

PLAN = [
    ("riddle", 2, "winter_night_snow"),
    ("trail", 3, "autumn_dusk_rain"),
    ("seek", 2, "summer_day"),
    ("pattern", 1, "spring_dawn_fog"),
    ("pattern", 3, "winter_night_snow"),
    ("viewpoint", 2, "autumn_storm_night"),
]

cases = []


def case(name, inst, attempt):
    cases.append({"name": name, "instance_id": inst["id"], "attempt": attempt, "expected": check(inst, attempt)})


instances = {}
for t, tier, cn in PLAN:
    inst = generate(scene, ctxs[cn], slot="vectors", ptype=t, tier=tier)
    instances[inst["id"]] = inst
    good = answer_attempt(inst)
    case(f"{t}{tier}: correct", inst, good)
    s = inst["solution"]
    if t == "riddle":
        case(f"{t}{tier}: wrong", inst, {"select": "lamp_0" if s["answer"] != "lamp_0" else "lamp_1"})
        case(f"{t}{tier}: missing", inst, {})
    elif t == "trail":
        a = s["answers"]
        case(f"{t}{tier}: prefix", inst, {"selects": a[:2]})
        case(f"{t}{tier}: wrong second", inst, {"selects": [a[0], "bollard_0"]})
        case(f"{t}{tier}: empty", inst, {"selects": []})
        case(f"{t}{tier}: not a list", inst, {"selects": a[0]})
    elif t == "seek":
        tg = s["targets"]
        case(f"{t}{tier}: partial with junk", inst, {"found": tg[:2] + ["tree_1x"]})
        case(f"{t}{tier}: unordered", inst, {"found": list(reversed(tg))})
    elif t == "pattern":
        pr = good["presses"]
        case(f"{t}{tier}: doubled press cancels", inst, {"presses": pr + [pr[0], pr[0]]})
        case(f"{t}{tier}: no presses", inst, {"presses": []})
        case(f"{t}{tier}: unknown cell", inst, {"presses": ["lamp_0"]})
    elif t == "viewpoint":
        eye, look = good["eye"], good["look_at"]
        near = [eye[0] + 0.5, eye[1], eye[2]]
        far = [eye[0] + 6.0, eye[1], eye[2]]
        farther = [eye[0] + 12.0, eye[1], eye[2]]
        case(f"{t}{tier}: within tolerance", inst, {"eye": near, "look_at": look})
        case(f"{t}{tier}: far", inst, {"eye": far, "look_at": look})
        case(f"{t}{tier}: farther, previously closer", inst,
             {"eye": farther, "look_at": look, "previous_progress": check(inst, {"eye": far, "look_at": look})["progress"]})
        case(f"{t}{tier}: looking away", inst, {"eye": eye, "look_at": [2 * eye[i] - look[i] for i in range(3)]})
        case(f"{t}{tier}: malformed", inst, {"eye": eye[:2], "look_at": look})

rng_vectors = {"fnv1a32": {s: fnv1a32(s) for s in ["", "a", "terrella", "sha256:7f1c0e2a9b|2026-10-15|daily", "ž"]}}
rng_vectors["mulberry32"] = {}
for seed in [0, 1, 7, 4294967295]:
    r = Rng(seed)
    rng_vectors["mulberry32"][str(seed)] = [r.next_u32() for _ in range(5)]

out = {"schema": "terrella.check_vectors/1", "instances": instances, "cases": cases, "rng": rng_vectors}
(ROOT / "fixtures/check_vectors.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(f"{len(cases)} cases over {len(instances)} instances")
