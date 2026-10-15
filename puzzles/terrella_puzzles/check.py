"""Answer checking. Pure function of (instance, attempt): no scene, no context.

This is the part that runs on the device for instant feedback, so it is kept
tiny and is ported verbatim to GDScript (`godot/puzzle_check.gd`). Both
implementations must pass `fixtures/check_vectors.json`.

Result: {"solved": bool, "progress": float 0..1, "feedback": str}
feedback codes: "solved", "keep_going", "wrong", "warmer", "colder", "invalid"
"""
from __future__ import annotations

import math


def _result(solved: bool, progress: float, feedback: str) -> dict:
    return {"solved": solved, "progress": round(progress, 4), "feedback": feedback}


def _sub(a: list, b: list) -> list:
    return [float(a[0]) - float(b[0]), float(a[1]) - float(b[1]), float(a[2]) - float(b[2])]


def _dist(a: list, b: list) -> float:
    d = _sub(a, b)
    return math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])


def _angle_between(u: list, v: list) -> float:
    nu = math.sqrt(u[0] * u[0] + u[1] * u[1] + u[2] * u[2])
    nv = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if nu == 0.0 or nv == 0.0:
        return 180.0
    c = (u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def check(instance: dict, attempt: dict) -> dict:
    t = instance["type"]
    s = instance["solution"]

    if t == "riddle":
        pick = attempt.get("select")
        if pick is None:
            return _result(False, 0.0, "invalid")
        ok = pick == s["answer"]
        return _result(ok, 1.0 if ok else 0.0, "solved" if ok else "wrong")

    if t == "trail":
        picks = attempt.get("selects")
        if not isinstance(picks, list):
            return _result(False, 0.0, "invalid")
        answers = s["answers"]
        good = 0
        for p, a in zip(picks, answers):
            if p != a:
                break
            good += 1
        if good == len(answers):
            return _result(True, 1.0, "solved")
        # A wrong pick after the correct prefix is "wrong"; a correct but unfinished prefix is "keep_going".
        fb = "wrong" if len(picks) > good else "keep_going"
        return _result(False, good / len(answers), fb)

    if t == "seek":
        found = attempt.get("found")
        if not isinstance(found, list):
            return _result(False, 0.0, "invalid")
        targets = s["targets"]
        hit = sum(1 for tg in targets if tg in found)
        if hit == len(targets):
            return _result(True, 1.0, "solved")
        return _result(False, hit / len(targets), "keep_going")

    if t == "pattern":
        presses = attempt.get("presses")
        if not isinstance(presses, list):
            return _result(False, 0.0, "invalid")
        cells = s["cells"]
        index = {c: i for i, c in enumerate(cells)}
        state = list(s["start"])
        for p in presses:
            if p not in index:
                return _result(False, 0.0, "invalid")
            for c in [p] + list(s["neighbors"].get(p, [])):
                i = index[c]
                state[i] = not state[i]
        matching = sum(1 for a, b in zip(state, s["target"]) if a == b)
        ok = matching == len(cells)
        return _result(ok, matching / len(cells), "solved" if ok else "keep_going")

    if t == "viewpoint":
        eye, look = attempt.get("eye"), attempt.get("look_at")
        if not (isinstance(eye, list) and isinstance(look, list) and len(eye) == 3 and len(look) == 3):
            return _result(False, 0.0, "invalid")
        pose, tol = s["pose"], s["tolerance"]
        d_eye = _dist(eye, pose["eye"]) / tol["eye_m"]
        d_ang = _angle_between(_sub(look, eye), _sub(pose["look_at"], pose["eye"])) / tol["angle_deg"]
        worst = max(d_eye, d_ang)
        if worst <= 1.0:
            return _result(True, 1.0, "solved")
        # Closeness falls off over 4 tolerances; drives hot/cold feedback.
        progress = max(0.0, 1.0 - (worst - 1.0) / 3.0)
        prev = attempt.get("previous_progress")
        fb = "warmer" if prev is None or progress >= float(prev) else "colder"
        return _result(False, progress, fb)

    raise ValueError(f"unknown puzzle type {t}")
