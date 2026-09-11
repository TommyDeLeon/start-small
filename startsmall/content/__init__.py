"""Content model and loader.

A *track* is a subject (Python today). It has *concepts* in a prerequisite
graph and *activities* attached to concepts.

Activity kinds
  predict  show code, learner types what it prints        (graded: normalised text)
  fix      code with one bug, learner edits it            (graded: function/io tests)
  write    learner writes a small function or program     (graded: function/io tests)
  build    a tiny runnable program tying the concept      (graded: io tests; saved to collection)
  explain  learner explains in their own words            (self-checked, never counted as mastery)

Activity roles (used by the planner)
  hook       first contact: interesting outcome + prediction
  apply      use the concept in a slightly different example
  build      make something
  review     a fresh variant for later retrieval practice
  cumulative pulls several concepts together

Fields every activity must have are checked in `validate()`. Anything the
validator does not catch, `tests/test_content.py` catches by actually running
the code.
"""
from __future__ import annotations

import importlib

KINDS = {"predict", "fix", "write", "build", "explain"}
ROLES = {"hook", "apply", "build", "review", "cumulative"}

_TRACKS: dict[str, "Track"] = {}


class Track:
    def __init__(self, track_id: str, title: str, concepts: list[dict], activities: list[dict]):
        self.id = track_id
        self.title = title
        self.concepts = {c["id"]: c for c in concepts}
        self.concept_order = [c["id"] for c in concepts]
        self.activities = {a["id"]: a for a in activities}
        self.by_concept: dict[str, list[dict]] = {}
        for a in activities:
            self.by_concept.setdefault(a["concept"], []).append(a)
        validate(self)

    def concept(self, cid: str) -> dict:
        return self.concepts[cid]

    def activity(self, aid: str) -> dict:
        return self.activities[aid]

    def activities_for(self, cid: str, role: str | None = None, kind: str | None = None) -> list[dict]:
        out = self.by_concept.get(cid, [])
        if role:
            out = [a for a in out if a["role"] == role]
        if kind:
            out = [a for a in out if a["kind"] == kind]
        return out

    def prereqs_closure(self, cid: str) -> list[str]:
        seen: list[str] = []
        stack = list(self.concepts[cid]["prereqs"])
        while stack:
            p = stack.pop()
            if p not in seen:
                seen.append(p)
                stack.extend(self.concepts[p]["prereqs"])
        return seen


def validate(track: Track) -> None:
    ids = set()
    for cid, c in track.concepts.items():
        for key in ("id", "title", "summary", "prereqs", "project"):
            assert key in c, f"concept {cid} missing {key}"
        for p in c["prereqs"]:
            assert p in track.concepts, f"concept {cid} has unknown prereq {p}"
    # acyclic
    for cid in track.concepts:
        assert cid not in track.prereqs_closure(cid), f"prerequisite cycle at {cid}"
    for aid, a in track.activities.items():
        assert aid not in ids, f"duplicate activity id {aid}"
        ids.add(aid)
        assert a["kind"] in KINDS, f"{aid}: bad kind {a['kind']}"
        assert a["role"] in ROLES, f"{aid}: bad role {a['role']}"
        assert a["concept"] in track.concepts, f"{aid}: unknown concept {a['concept']}"
        for key in ("title", "hook", "prompt", "explain", "can_now", "difficulty", "minutes"):
            assert key in a, f"{aid} missing {key}"
        assert 1 <= a["difficulty"] <= 3, f"{aid}: difficulty out of range"
        if a["kind"] == "predict":
            assert "code" in a and "answer" in a, f"{aid}: predict needs code and answer"
        if a["kind"] in ("fix", "write", "build"):
            assert "solution" in a, f"{aid}: needs a reference solution"
            assert a.get("tests") or a.get("io_tests"), f"{aid}: needs tests"
        if a["kind"] == "explain":
            assert a.get("model_answer") and a.get("checklist"), f"{aid}: explain needs model_answer + checklist"
        if a["kind"] != "explain":
            assert len(a.get("hints", [])) >= 2, f"{aid}: needs at least 2 hints (conceptual, partial)"
        if "variation_of" in a:
            assert a["variation_of"] in track.activities, f"{aid}: variation_of unknown"
    for cid in track.concepts:
        roles = {a["role"] for a in track.by_concept.get(cid, [])}
        assert "hook" in roles, f"concept {cid} has no hook activity"
        assert "review" in roles, f"concept {cid} has no review activity"


def load(track_id: str = "python") -> Track:
    if track_id not in _TRACKS:
        mod = importlib.import_module(f"startsmall.content.{track_id}_track")
        _TRACKS[track_id] = Track(track_id, mod.TITLE, mod.CONCEPTS, mod.ACTIVITIES)
    return _TRACKS[track_id]


def available_tracks() -> list[str]:
    import pkgutil
    names = []
    for m in pkgutil.iter_modules(__path__):
        if m.name.endswith("_track"):
            names.append(m.name[: -len("_track")])
    return names
