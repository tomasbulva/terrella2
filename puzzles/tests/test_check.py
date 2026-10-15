import json
import unittest

from terrella_puzzles import answer_attempt, check, generate
from terrella_puzzles.generate import TYPES

from .helpers import ROOT, contexts, scene


class CheckVectorsTest(unittest.TestCase):
    """The conformance suite every port must pass."""

    def test_vectors(self):
        v = json.loads((ROOT / "fixtures/check_vectors.json").read_text())
        for c in v["cases"]:
            got = check(v["instances"][c["instance_id"]], c["attempt"])
            self.assertEqual(got, c["expected"], c["name"])

    def test_vectors_are_current(self):
        """Fails if generation changed without regenerating the vectors (tools/make_check_vectors.py)."""
        v = json.loads((ROOT / "fixtures/check_vectors.json").read_text())
        s, ctx = scene(), contexts()
        for inst in v["instances"].values():
            fresh = generate(s, ctx_by_time(ctx, inst["context"]["local_time"]), slot="vectors",
                             ptype=inst["type"], tier=inst["tier"])
            self.assertEqual(fresh, inst, inst["id"])


def ctx_by_time(ctxs, t):
    return next(c for c in ctxs.values() if c.local_time == t)


class CheckBehaviourTest(unittest.TestCase):
    def test_canonical_answers_solve_everything(self):
        s, ctx = scene(), contexts()
        for c in ctx.values():
            for t in TYPES:
                for tier in (1, 2, 3):
                    inst = generate(s, c, slot="x", ptype=t, tier=tier)
                    self.assertTrue(check(inst, answer_attempt(inst))["solved"], f"{t}{tier}")

    def test_progress_bounded(self):
        s, c = scene(), contexts()["summer_day"]
        inst = generate(s, c, ptype="viewpoint", tier=3)
        for dx in (0, 1, 3, 10, 100):
            eye = list(inst["solution"]["pose"]["eye"])
            eye[0] += dx
            r = check(inst, {"eye": eye, "look_at": inst["solution"]["pose"]["look_at"]})
            self.assertTrue(0.0 <= r["progress"] <= 1.0)
