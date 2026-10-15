import unittest

from terrella_puzzles import generate, load_catalog, pick_rewards
from terrella_puzzles.collectibles import eligible

from .helpers import contexts, scene

NOW = "2026-10-15T18:45:00+02:00"


class CollectiblesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.scene = scene()
        cls.ctx = contexts()

    def inst(self, ctx="autumn_dusk_rain", **kw):
        return generate(self.scene, self.ctx[ctx], **kw)

    def test_every_context_has_a_reward(self):
        for name in self.ctx:
            for t in ("riddle", "seek", "viewpoint"):
                g = pick_rewards(self.inst(name, ptype=t), self.catalog, {}, "u1", NOW)
                self.assertTrue(g)

    def test_deterministic_and_idempotent(self):
        inst = self.inst()
        a = pick_rewards(inst, self.catalog, {}, "u1", NOW)
        b = pick_rewards(inst, self.catalog, {}, "u1", NOW)
        self.assertEqual(a, b)

    def test_first_solve_in_a_diorama_grants_stamp_once(self):
        inst = self.inst()
        g = pick_rewards(inst, self.catalog, {}, "u1", NOW)
        self.assertEqual(g[-1]["collectible_id"], "stamp:dio_nl_amsterdam_prinsengracht")
        g2 = pick_rewards(inst, self.catalog, {"stamp:dio_nl_amsterdam_prinsengracht": 1}, "u1", NOW)
        self.assertEqual(len(g2), 1)

    def test_prefers_unowned_until_pool_exhausted(self):
        inst = self.inst()
        tags = set(inst["reward_tags"])
        pool = {d["id"] for d in self.catalog if d["category"] != "stamp" and eligible(d, tags)}
        inv: dict[str, int] = {}
        got = []
        for i in range(len(pool)):
            # Same puzzle, different users, so the draw varies; inventory carries over.
            g = pick_rewards(inst, self.catalog, inv, f"u{i}", NOW)[0]
            self.assertFalse(g["duplicate"])
            inv[g["collectible_id"]] = 1
            got.append(g["collectible_id"])
        self.assertEqual(set(got), pool)
        dup = pick_rewards(inst, self.catalog, inv, "ux", NOW)[0]
        self.assertTrue(dup["duplicate"])
        self.assertEqual(dup["count_after"], 2)

    def test_weather_charms_need_weather(self):
        snow = next(d for d in self.catalog if d["id"] == "charm.snowflake")
        self.assertFalse(eligible(snow, set(self.inst("summer_day")["reward_tags"])))
        self.assertTrue(eligible(snow, set(self.inst("winter_night_snow")["reward_tags"])))

    def test_variant_from_context(self):
        inst = self.inst("winter_night_snow")
        inv = {d["id"]: 1 for d in self.catalog if d["id"] != "postcard.nl_canal"}
        g = pick_rewards(inst, self.catalog, inv, "u1", NOW)[0]
        self.assertEqual(g["collectible_id"], "postcard.nl_canal")
        self.assertEqual(g["variant"], "phase:night")

    def test_grants_carry_only_coarse_location(self):
        g = pick_rewards(self.inst(), self.catalog, {}, "u1", NOW)[0]
        self.assertEqual(len(g["geocell"]), 5)
        self.assertNotIn("lat", g)
