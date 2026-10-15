import copy
import unittest

from terrella_puzzles import InputError, Scene, generate, validate

from .helpers import contexts, scene, scene_dict


class ValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = scene()
        cls.ctx = contexts()

    def gen(self, t, ctx="autumn_dusk_rain", tier=2):
        return generate(self.scene, self.ctx[ctx], slot="v", ptype=t, tier=tier)

    def test_ambiguous_riddle_rejected(self):
        inst = self.gen("riddle")
        inst["prompt"]["clue"]["predicates"] = []
        self.assertTrue(any("not uniquely" in e for e in validate(inst, self.scene)))

    def test_wrong_answer_rejected(self):
        inst = self.gen("riddle")
        inst["solution"]["answer"] = "lamp_3" if inst["solution"]["answer"] != "lamp_3" else "lamp_2"
        self.assertTrue(validate(inst, self.scene))

    def test_other_diorama_build_rejected(self):
        inst = self.gen("seek")
        inst["diorama"]["recipe_hash"] = "sha256:other"
        self.assertTrue(any("different diorama" in e for e in validate(inst, self.scene)))

    def test_seek_target_must_be_hide_spot(self):
        inst = self.gen("seek")
        inst["solution"]["targets"][0] = "lamp_0"
        inst["spawns"][0]["anchor"] = "lamp_0"
        self.assertTrue(any("not a hide spot" in e for e in validate(inst, self.scene)))

    def test_unknown_entity_reported(self):
        inst = self.gen("trail")
        inst["solution"]["answers"][1] = "ghost"
        self.assertTrue(any("unknown entity ghost" in e for e in validate(inst, self.scene)))

    def test_broken_chain_reported(self):
        inst = self.gen("trail", tier=3)
        c = inst["prompt"]["clues"][1]
        c["predicates"] = [p for p in c["predicates"] if p["op"] != "near_id"]
        self.assertTrue(validate(inst, self.scene))

    def test_already_solved_pattern_rejected(self):
        inst = self.gen("pattern")
        inst["solution"]["target"] = list(inst["solution"]["start"])
        self.assertTrue(any("unsolvable or already solved" in e for e in validate(inst, self.scene)))

    def test_asymmetric_neighbours_rejected(self):
        inst = self.gen("pattern", tier=3)
        nb = inst["solution"]["neighbors"]
        k = next(c for c, ns in nb.items() if ns)
        nb[k] = nb[k] + [x for x in inst["solution"]["cells"] if x != k and x not in nb[k]][:1]
        self.assertTrue(any("not symmetric" in e for e in validate(inst, self.scene)))

    def test_viewpoint_outside_camera_limits(self):
        inst = self.gen("viewpoint")
        inst["solution"]["pose"]["eye"] = [inst["solution"]["pose"]["look_at"][0], 500.0, 0.0]
        self.assertTrue(validate(inst, self.scene))

    def test_context_bound_must_expire_with_phase(self):
        for i in range(40):
            inst = generate(self.scene, self.ctx["winter_night_snow"], slot=f"s{i}", ptype="riddle", tier=3)
            if inst["context_bound"]:
                break
        else:
            self.skipTest("no context-bound riddle in sample")
        inst["valid_until"] = "2026-12-23T00:00:00+01:00"
        self.assertTrue(any("outlives" in e for e in validate(inst, self.scene)))

    def test_missing_fields(self):
        self.assertTrue(validate({"type": "riddle"}, self.scene))

    def test_scene_input_errors(self):
        d = scene_dict()
        d["entities"].append(copy.deepcopy(d["entities"][0]))
        with self.assertRaises(InputError):
            Scene.from_dict(d)
        d = scene_dict()
        d["entities"][1]["parent"] = "nope"
        with self.assertRaises(InputError):
            Scene.from_dict(d)
