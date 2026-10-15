"""Difficulty is measured on the generated puzzle, not just requested.

Scores are rough "minutes of attention" units; tiers are the player-facing
labels: 1 cozy, 2 curious, 3 clever. Thresholds are first guesses to tune
against playtest solve times (see SPEC.md, Telemetry).
"""
from __future__ import annotations

TIER_BOUNDS = (2.5, 4.5)  # score < 2.5 -> tier 1, < 4.5 -> tier 2, else 3


def tier_of(score: float) -> int:
    if score < TIER_BOUNDS[0]:
        return 1
    if score < TIER_BOUNDS[1]:
        return 2
    return 3


def riddle_score(clue: dict, near_misses: int) -> float:
    preds = clue["predicates"]
    relations = sum(1 for p in preds if p["op"] in ("near", "near_id", "parent_attr"))
    return 0.6 + 0.8 * len(preds) + 0.4 * relations + 0.35 * min(near_misses, 6)


def trail_score(clues: list[dict], near_misses: list[int]) -> float:
    # Every step after the first carries a near_id relation that narrows the search a lot,
    # so length matters more than per-step clue complexity.
    scores = [riddle_score(c, m) for c, m in zip(clues, near_misses)]
    return 0.6 * sum(scores) / len(scores) + 1.1 * (len(clues) - 2) + 0.4


def seek_score(targets: int, spots: int) -> float:
    # More tokens is longer; more empty hide spots means more places to check.
    return 0.5 * targets + 0.1 * max(0, spots - targets)


def pattern_score(min_presses: int, cells: int, mode: str) -> float:
    return 0.7 * min_presses + 0.1 * cells + (1.5 if mode == "cross" else 0.0)


def viewpoint_score(tier: int) -> float:
    return {1: 1.5, 2: 3.5, 3: 5.0}[tier]
