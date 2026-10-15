import json
import unittest

from terrella_puzzles.rng import Rng, fnv1a32

from .helpers import ROOT


class RngTest(unittest.TestCase):
    def test_matches_conformance_vectors(self):
        v = json.loads((ROOT / "fixtures/check_vectors.json").read_text())["rng"]
        for text, h in v["fnv1a32"].items():
            self.assertEqual(fnv1a32(text), h, text)
        for seed, outs in v["mulberry32"].items():
            r = Rng(int(seed))
            self.assertEqual([r.next_u32() for _ in outs], outs, seed)

    def test_weighted_and_shuffle_are_deterministic(self):
        a, b = Rng(42), Rng(42)
        self.assertEqual(a.shuffled(range(20)), b.shuffled(range(20)))
        self.assertEqual([a.weighted("xyz", [1, 2, 3]) for _ in range(50)],
                         [b.weighted("xyz", [1, 2, 3]) for _ in range(50)])

    def test_below_rejects_empty(self):
        with self.assertRaises(ValueError):
            Rng(1).below(0)
