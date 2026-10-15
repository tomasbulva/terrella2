"""Reference English rendering of prompts.

Puzzle instances carry structured prompts (keys + params) so clients localize;
this renderer exists for previews, logs and tests.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=None)
def _text(locale: str = "en") -> dict:
    return json.loads((DATA / f"text_{locale}.json").read_text())


def noun(kind: str) -> str:
    return _text()["nouns"].get(kind, kind.replace("_", " "))


def attr_phrase(key: str, value) -> str:
    t = _text()["attr"].get(key)
    if t is None:
        return f"with {key.replace('_', ' ')} {value}"
    if isinstance(t, dict):
        return t[str(value).lower()]
    return t.format(value=value)


def predicate_phrase(p: dict) -> str:
    tpl = _text()["templates"]
    if p["op"] == "attr":
        return attr_phrase(p["key"], p["value"])
    if p["op"] == "parent_attr":
        return tpl["parent"].format(phrase=attr_phrase(p["key"], p["value"]))
    if p["op"] == "near":
        return tpl["near"].format(noun=noun(p["kind"]))
    if p["op"] == "near_id":
        return tpl["near_id"]
    raise ValueError(p["op"])


def clue_phrase(clue: dict) -> str:
    parts = [predicate_phrase(p) for p in clue["predicates"]]
    if not parts:
        return noun(clue["subject"])
    if len(parts) == 1:
        return f"{noun(clue['subject'])} {parts[0]}"
    return f"{noun(clue['subject'])} {', '.join(parts[:-1])} and {parts[-1]}"


def render(instance: dict) -> str:
    tpl = _text()["templates"]
    t, s = instance["type"], instance["solution"]
    pr = instance["prompt"]
    if t == "riddle":
        return tpl["riddle"].format(clue=clue_phrase(pr["clue"]))
    if t == "trail":
        lines = [tpl["riddle"].format(clue=clue_phrase(pr["clues"][0]))]
        lines += [tpl["trail_step"].format(clue=clue_phrase(c)) for c in pr["clues"][1:]]
        return " ".join(lines)
    if t == "seek":
        sing, plur = _text()["tokens"][pr["token"]]
        n = len(s["targets"])
        line = tpl["seek"].format(count=n, token_plural=plur if n != 1 else sing)
        return line[0].upper() + line[1:]
    if t == "pattern":
        return tpl["pattern"].format(noun=noun(pr["kind"]), owner=pr["owner_phrase"])
    if t == "viewpoint":
        return tpl["viewpoint"]
    raise ValueError(t)
