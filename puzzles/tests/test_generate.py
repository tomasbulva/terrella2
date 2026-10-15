import json
import unittest
from collections import Counter

from terrella_puzzles import NoPuzzle, Scene, generate, validate
from terrella_puzzles.context_rules import effective_attrs
from terrella_puzzles.difficulty import tier_of
from terrella_puzzles.generate import TYPES
from terrella_puzzles.text import render

from .helpers import contexts, scene, scene_dict


class GenerateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = scene()
        cls.ctx = contexts()

    def test_deterministic(self):
        for c in self.ctx.values():
            a = generate(self.scene, c, slot="daily")
            b = generate(self.scene, c, slot="daily")
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_slots_differ(self):
        c = self.ctx["summer_day"]
        ids = {generate(self.scene, c, slot=f"s{i}")["id"] for i in range(20)}
        self.assertGreater(len(ids), 15)

    def test_every_type_and_tier_validates_in_every_context(self):
        for name, c in self.ctx.items():
            for t in TYPES:
                for tier in (1, 2, 3):
                    for slot in ("a", "b", "c"):
                        inst = generate(self.scene, c, slot=slot, ptype=t, tier=tier)
                        self.assertEqual(validate(inst, self.scene), [], f"{name} {t} {tier} {slot}")
                        self.assertTrue(render(inst))

    def test_measured_tier_mostly_matches_requested(self):
        c = self.ctx["autumn_dusk_rain"]
        for t in ("riddle", "trail"):
            for tier in (1, 2, 3):
                hits = sum(tier_of(generate(self.scene, c, slot=f"s{i}", ptype=t, tier=tier)["difficulty"]) == tier
                           for i in range(30))
                self.assertGreaterEqual(hits, 24, f"{t} tier {tier}: {hits}/30")

    def test_context_clues_appear_and_expire(self):
        c = self.ctx["winter_night_snow"]
        bound = [generate(self.scene, c, slot=f"s{i}", ptype="riddle", tier=3) for i in range(30)]
        bound = [b for b in bound if b["context_bound"]]
        self.assertTrue(bound, "night+snow should produce some lit/snowy clues")
        for b in bound:
            self.assertLessEqual(b["valid_until"], c.weather_stable_until)
            self.assertIn("context_clue", b["reward_tags"])

    def test_tier_one_never_uses_context(self):
        c = self.ctx["winter_night_snow"]
        for i in range(30):
            for t in ("riddle", "trail"):
                self.assertFalse(generate(self.scene, c, slot=f"s{i}", ptype=t, tier=1)["context_bound"])

    def test_absent_entities_are_never_answers(self):
        c = self.ctx["autumn_storm_night"]
        attrs = effective_attrs(self.scene, c)
        gone = {eid for eid, a in attrs.items() if a.get("present") is False}
        self.assertIn("boat_1", gone)
        for i in range(40):
            inst = generate(self.scene, c, slot=f"s{i}", ptype="riddle")
            self.assertNotIn(inst["solution"]["answer"], gone)

    def test_viewpoint_never_targets_absent_entities(self):
        # Regression: a notable unmoored boat vanishes in a storm but was still picked as the subject.
        d = scene_dict()
        for e in d["entities"]:
            if e["id"] == "boat_1":
                e["tags"] = ["notable"]
        s = Scene.from_dict(d)
        c = self.ctx["autumn_storm_night"]
        targets = set()
        for i in range(60):
            inst = generate(s, c, slot=f"s{i}", ptype="viewpoint")
            targets.add(inst["solution"]["pose"]["target"])
            self.assertEqual(validate(inst, s), [], inst["id"])
        self.assertNotIn("boat_1", targets)
        self.assertIn("boat_1", {generate(s, self.ctx["summer_day"], slot=f"s{i}", ptype="viewpoint")
                                 ["solution"]["pose"]["target"] for i in range(60)})

    def test_no_generator_uses_absent_entities(self):
        # Regression: every type must skip entities context_rules remove (unmoored boats in a storm).
        d = scene_dict()
        for e in d["entities"]:
            if e["id"] == "boat_1":
                e["tags"] = ["hide_spot", "notable"]
        s = Scene.from_dict(d)
        storm = self.ctx["autumn_storm_night"]
        for t in TYPES:
            for i in range(30):
                inst = generate(s, storm, slot=f"s{i}", ptype=t)
                self.assertEqual(validate(inst, s), [], f"{t} {inst['id']}")
                self.assertNotIn("boat_1", json.dumps(inst["solution"]), f"{t} {inst['id']}")
        seen = {a for i in range(60)
                for a in generate(s, self.ctx["summer_day"], slot=f"s{i}", ptype="seek")["solution"]["targets"]}
        self.assertIn("boat_1", seen)

    def test_seek_token_follows_weather(self):
        self.assertEqual(generate(self.scene, self.ctx["autumn_dusk_rain"], ptype="seek")["prompt"]["token"],
                         "token.rubber_duck")
        self.assertEqual(generate(self.scene, self.ctx["winter_night_snow"], ptype="seek")["prompt"]["token"],
                         "token.mitten")

    def test_default_mix_covers_all_types(self):
        c = self.ctx["summer_day"]
        seen = Counter(generate(self.scene, c, slot=f"s{i}")["type"] for i in range(80))
        self.assertEqual(set(seen), set(TYPES))

    def test_infeasible_type_falls_through(self):
        d = scene_dict()
        d["entities"] = [e for e in d["entities"] if "hide_spot" not in e["tags"]]
        s = Scene.from_dict(d)
        with self.assertRaises(NoPuzzle):
            generate(s, self.ctx["summer_day"], ptype="seek")
        for i in range(20):
            self.assertNotEqual(generate(s, self.ctx["summer_day"], slot=f"s{i}")["type"], "seek")
