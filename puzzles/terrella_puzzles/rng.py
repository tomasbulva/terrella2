"""Portable deterministic randomness.

Everything here is defined on 32-bit unsigned integers so it can be ported
bit-for-bit to GDScript (64-bit signed ints, masked) or any other language.
Never use Python's `random` in this package: generation must be reproducible
from a seed on every platform.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")
MASK32 = 0xFFFFFFFF


def fnv1a32(text: str) -> int:
    """FNV-1a over the UTF-8 bytes of `text`."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & MASK32
    return h


class Rng:
    """mulberry32. Small, fast, good enough for content generation."""

    def __init__(self, seed: int):
        self.state = seed & MASK32

    def next_u32(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & MASK32
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & MASK32
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & MASK32)) & MASK32
        return (t ^ (t >> 14)) & MASK32

    def below(self, n: int) -> int:
        """Uniform-ish int in [0, n). Modulo bias is irrelevant for n << 2^32."""
        if n <= 0:
            raise ValueError("n must be positive")
        return self.next_u32() % n

    def chance(self, p: float) -> bool:
        return self.next_u32() < int(p * 4294967296.0)

    def choice(self, items: Sequence[T]) -> T:
        return items[self.below(len(items))]

    def weighted(self, items: Sequence[T], weights: Sequence[int]) -> T:
        """Integer weights only, so ports don't depend on float summation order."""
        total = sum(weights)
        r = self.below(total)
        for item, w in zip(items, weights):
            if r < w:
                return item
            r -= w
        raise AssertionError("unreachable")

    def shuffled(self, items: Sequence[T]) -> list[T]:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        return self.shuffled(items)[:k]


def derive_seed(*parts: object) -> int:
    return fnv1a32("|".join(str(p) for p in parts))
