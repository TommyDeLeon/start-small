"""The planner: decides the one next action, grades, adapts, schedules.

Mastery ladder per concept (concept_state.status)
  new          never seen
  seen         hook attempted (right or wrong)
  assisted     succeeded with hints or after viewing a solution
  independent  succeeded on a fresh activity with no hints and no solution
  cumulative   passed a cumulative challenge independently

Review ladder (concept_state.review_stage → days until next review)
  0: 1 day, 1: 3 days, 2: 7 days, 3: 14 days, 4: 30 days (cap)
An independent success on a review moves one rung up. An assisted success
keeps the rung. A failure moves one rung down (never below 0) — no
punishment backlog, just a sooner look.

Honesty rules
  * viewing the worked solution (hint level 3) can never produce
    'independent'; the attempt is recorded with solution_viewed=1
  * a micro action counts as participation, not mastery
  * response speed is recorded but never used for decisions
"""
from __future__ import annotations

import time

from . import content, grader
from .store import Store

DAY = 86400
REVIEW_DAYS = [1, 3, 7, 14, 30]
STATUS_RANK = {"new": 0, "seen": 1, "assisted": 2, "independent": 3, "cumulative": 4}
EASIER_KINDS = ["predict", "explain", "fix", "write", "build"]  # rough effort order


def max_status(a: str, b: str) -> str:
    return a if STATUS_RANK[a] >= STATUS_RANK[b] else b


class Engine:
    def __init__(self, store: Store, track_id: str | None = None):
        self.store = store
        self.track_id = track_id or store.get_settings()["current_track"]
        self.track = content.load(self.track_id)
        # transient per-process state for the active activity, keyed by session id
        self._active: dict = {}

    # ------------------------------------------------------------ helpers
    def _states(self) -> dict[str, dict]:
        states = self.store.all_concept_states()
        for cid in self.track.concepts:
            states.setdefault(cid, self.store.concept_state(cid))
        return states

    def _rank(self, states, cid) -> int:
        return STATUS_RANK[states[cid]["status"]]

    def _prereqs_met(self, states, cid) -> bool:
        return all(self._rank(states, p) >= STATUS_RANK["assisted"] for p in self.track.concepts[cid]["prereqs"])

    def _weakest_prereq(self, states, cid) -> str | None:
        """The smallest likely missing prerequisite: the direct prereq with the lowest mastery."""
        best, best_rank = None, 99
        for p in self.track.concepts[cid]["prereqs"]:
            r = self._rank(states, p)
            if r < best_rank:
                best, best_rank = p, r
        return best if best_rank < STATUS_RANK["independent"] else None

    def _unseen_or_fresh(self, cands: list[dict], recent: list[str]) -> list[dict]:
        """Prefer activities never attempted, then ones not attempted recently."""
        never = [a for a in cands if not self.store.attempts_for_activity(a["id"], 1)]
        if never:
            return never
        return [a for a in cands if a["id"] not in recent] or cands

    def _failed_last(self, aid: str) -> bool:
        h = self.store.attempts_for_activity(aid, 1)
        return bool(h) and h[0]["correct"] == 0

    def _blank_state(self, activity_id: str) -> dict:
        return {"activity_id": activity_id, "hints": 0, "solution": False, "is_review": False,
                "is_micro": False, "is_variation": False, "started": time.time()}

    # ------------------------------------------------------------ planning
    def current_concept(self, states=None) -> str | None:
        """First concept in order whose prereqs are met and which is not yet independent."""
        states = states or self._states()
        for cid in self.track.concept_order:
            if not self._prereqs_met(states, cid):
                continue
            if self._rank(states, cid) < STATUS_RANK["independent"] or not self._build_attempted(cid):
                return cid
        return None

    def _build_attempted(self, cid: str) -> bool:
        """A concept is not 'done' until its build (the thing you make) has been tried."""
        builds = self.track.activities_for(cid, role="build")
        return all(self.store.attempts_for_activity(b["id"], 1) for b in builds)

    def due_reviews(self, states=None, now=None) -> list[str]:
        states = states or self._states()
        now = now or time.time()
        due = [cid for cid, st in states.items()
               if st["due_at"] is not None and st["due_at"] <= now
               and self._rank(states, cid) >= STATUS_RANK["assisted"]]
        due.sort(key=lambda c: states[c]["due_at"])
        return due

    def pick_review(self, cid: str, recent: list[str]) -> dict | None:
        cands = self.track.activities_for(cid, role="review")
        if not cands:
            return None
        fresh = self._unseen_or_fresh(cands, recent)
        # never re-serve the exact activity that was just failed if there is an alternative
        avoid = [a for a in fresh if not self._failed_last(a["id"])]
        return (avoid or fresh)[0]

    def pick_next_in_concept(self, cid: str, recent: list[str]) -> dict:
        """Sequence within a concept: hook → apply (explain, fix/write) → build → cumulative."""
        order = ["hook", "apply", "build", "cumulative"]
        acts = self.track.activities_for(cid)
        for role in order:
            for a in [x for x in acts if x["role"] == role]:
                hist = self.store.attempts_for_activity(a["id"], 1)
                if not hist:
                    return a
                # a failed graded activity gets a fresh look later, never immediately unchanged
                if hist[0]["correct"] == 0 and a["id"] not in recent:
                    return a
        return self.pick_review(cid, recent) or acts[0]

    def next_action(self, mode: str = "small") -> dict:
        """The one prepared next action for the home screen / session start."""
        states = self._states()
        recent = self.store.recent_activity_ids(6)
        now = time.time()

        if mode == "micro":
            return self._micro_action(states, recent)

        # gentle restart after a gap: warm up on something already understood
        last = self.store.last_attempt_at()
        gap_days = (now - last) / DAY if last else 0
        if last and gap_days >= 2:
            warm = self._warmup(states, recent)
            if warm:
                return self._pack(
                    warm, reason="restart", is_review=True,
                    note=f"It has been {int(gap_days)} days. Nothing is overdue and nothing piled up — "
                         "here is a quick warm-up on something you already got right.",
                )

        due = self.due_reviews(states, now)
        if due:
            a = self.pick_review(due[0], recent)
            if a:
                title = self.track.concepts[due[0]]["title"].lower()
                return self._pack(a, reason="review", is_review=True,
                                  note=f"A quick check on {title} — coming back later is what makes it stick.")

        cid = self.current_concept(states)
        if cid is None:
            cands = [a for a in self.track.activities.values() if a["role"] == "cumulative"]
            a = self._unseen_or_fresh(cands, recent)[0]
            return self._pack(a, reason="maintenance", is_review=True,
                              note="You have covered the whole track. Here is a challenge to keep it warm.")
        a = self.pick_next_in_concept(cid, recent)
        return self._pack(a, reason="learn")

    def _warmup(self, states, recent) -> dict | None:
        done = [cid for cid in self.track.concept_order
                if states[cid]["independent_count"] + states[cid]["assisted_count"] > 0]
        for cid in reversed(done):
            a = self.pick_review(cid, recent)
            if a and a["difficulty"] <= 2:
                return a
        return None

    def _micro_action(self, states, recent) -> dict:
        """One tiny meaningful action: a difficulty-1 prediction or one-line fix."""
        cid = self.current_concept(states) or self.track.concept_order[-1]
        pool = [a for a in self.track.activities.values()
                if a["kind"] in ("predict", "fix") and a["difficulty"] == 1
                and (self._rank(states, a["concept"]) >= STATUS_RANK["seen"] or a["concept"] == cid)]
        if not pool:
            pool = [a for a in self.track.activities.values() if a["kind"] == "predict" and a["difficulty"] == 1]
        a = self._unseen_or_fresh(pool, recent)[0]
        return self._pack(a, reason="micro", is_micro=True,
                          note="One tiny thing. Predict or fix a single line, then you are done. That counts.")

    HIDDEN = ("answer", "accept", "solution", "hints", "model_answer", "tests", "io_tests")

    def _pack(self, a: dict, reason: str, is_review=False, is_micro=False, note: str = "") -> dict:
        c = self.track.concepts[a["concept"]]
        pub = {k: v for k, v in a.items() if k not in self.HIDDEN}
        pub["hint_levels"] = len(a.get("hints", [])) + (1 if a["kind"] != "explain" else 0)
        pub["tests_preview"] = [
            t.get("label") or f"{t['fn']}({', '.join(repr(x) for x in t.get('args', []))}) → {t['expect']!r}"
            for t in a.get("tests", [])
        ][:4]
        return {
            "activity": pub,
            "concept": {"id": c["id"], "title": c["title"], "summary": c["summary"]},
            "reason": reason, "is_review": is_review, "is_micro": is_micro, "note": note,
        }

    # ------------------------------------------------------------ session
    def home(self) -> dict:
        settings = self.store.get_settings()
        states = self._states()
        nxt = self.next_action("small")
        last = self.store.last_attempt_at()
        gap_days = int((time.time() - last) / DAY) if last else None
        mastered = [self.track.concepts[c]["title"] for c in self.track.concept_order
                    if self._rank(states, c) >= STATUS_RANK["independent"]]
        in_progress = [self.track.concepts[c]["title"] for c in self.track.concept_order
                       if STATUS_RANK["seen"] <= self._rank(states, c) < STATUS_RANK["independent"]]
        return {
            "next": nxt,
            "settings": settings,
            "collection": self.store.list_collection()[:8],
            "collection_count": len(self.store.list_collection()),
            "mastered": mastered, "in_progress": in_progress,
            "concepts_total": len(self.track.concept_order),
            "due_reviews": len(self.due_reviews(states)),
            "gap_days": gap_days,
            "tasks": self.store.list_tasks()[:5],
            "track": {"id": self.track.id, "title": self.track.title},
            "sparks": self._sparks() if settings.get("sparks_enabled") else None,
        }

    def _sparks(self) -> int:
        """Transparent rule: one spark per activity passed independently (no hints, no solution),
        once as a first pass and once more as a review. Repeats earn nothing."""
        earned = set()
        for a in self.store.attempts_since(0):
            if a["correct"] == 1 and not a["hints_used"] and not a["solution_viewed"]:
                earned.add((a["activity_id"], "review" if a["is_review"] else "first"))
        return len(earned)

    def start(self, mode: str, activity_id: str | None = None) -> dict:
        session_id = self.store.start_session(mode)
        self.store.log("session_start", {"mode": mode})
        if activity_id:
            a = self.track.activity(activity_id)
            seen = bool(self.store.attempts_for_activity(activity_id, 1))
            action = self._pack(a, reason="chosen", is_review=seen)
        else:
            action = self.next_action(mode)
        st = self._blank_state(action["activity"]["id"])
        st.update(is_review=action["is_review"], is_micro=action["is_micro"])
        self._active[session_id] = st
        return {"session_id": session_id, **action}

    def serve(self, session_id: int, activity_id: str, is_variation=False, is_review=False) -> dict:
        """Put a specific activity in front of the learner inside an existing session."""
        a = self.track.activity(activity_id)
        action = self._pack(a, reason="variation" if is_variation else "next", is_review=is_review)
        st = self._blank_state(activity_id)
        st.update(is_review=is_review, is_variation=is_variation)
        self._active[session_id] = st
        return {"session_id": session_id, **action}

    def serve_next(self, session_id: int) -> dict:
        """'One more': the planner's next action inside the same session."""
        action = self.next_action("small")
        return self.serve(session_id, action["activity"]["id"], is_review=action["is_review"]) | {
            "reason": action["reason"], "note": action["note"]}

    def hint(self, session_id: int, activity_id: str, level: int) -> dict:
        a = self.track.activity(activity_id)
        st = self._active.setdefault(session_id, self._blank_state(activity_id))
        hints = a.get("hints", [])
        level = max(1, min(level, len(hints) + 1))
        st["hints"] = max(st["hints"], level)
        self.store.log("hint", {"activity": activity_id, "level": level})
        if level <= len(hints):
            return {"level": level, "text": hints[level - 1], "is_solution": False, "levels": len(hints) + 1}
        st["solution"] = True
        sol = a.get("solution") or a.get("answer") or a.get("model_answer") or ""
        follow = self.follow_up(activity_id)
        return {"level": level, "text": sol, "is_solution": True, "levels": len(hints) + 1,
                "follow_up": follow["id"] if follow else None,
                "follow_up_title": follow["title"] if follow else None}

    def follow_up(self, activity_id: str) -> dict | None:
        """After a revealed solution: a fresh, small application of the same concept."""
        a = self.track.activity(activity_id)
        recent = self.store.recent_activity_ids(6)
        pool = [x for x in self.track.activities_for(a["concept"]) if x["id"] != activity_id and x["kind"] != "explain"]
        cands = [x for x in pool if x["difficulty"] <= max(1, a["difficulty"])] or pool
        if not cands:
            return None
        return self._unseen_or_fresh(cands, recent)[0]

    def submit(self, session_id: int, activity_id: str, answer: str, self_check: list | None = None) -> dict:
        a = self.track.activity(activity_id)
        st = self._active.get(session_id) or self._blank_state(activity_id)
        result = grader.grade(a, answer)
        seconds = time.time() - st.get("started", time.time())
        correct = result["correct"]
        if a["kind"] == "explain":
            correct_int = None
            detail = {"ticked": self_check or [], "of": len(a["checklist"])}
        else:
            correct_int = 1 if correct else 0
            detail = result["detail"]
        self.store.add_attempt(
            session_id=session_id, activity_id=activity_id, concept_id=a["concept"], kind=a["kind"],
            correct=correct_int, hints_used=st["hints"], solution_viewed=1 if st["solution"] else 0,
            is_review=1 if st["is_review"] else 0, is_variation=1 if st["is_variation"] else 0,
            is_micro=1 if st["is_micro"] else 0, seconds=seconds, answer=(answer or "")[:4000], detail=detail,
        )
        self.store.bump_session(session_id)

        outcome = self._update_mastery(a, correct_int, st)
        capability = self._capability_line(a, correct_int, st)
        if capability:
            kind = {"fix": "fixed", "build": "built", "write": "built", "predict": "understood"}[a["kind"]]
            if self.store.add_collection(kind, capability, detail=a.get("can_now"),
                                         activity_id=a["id"], concept_id=a["concept"]):
                outcome["new_collection"] = {"kind": kind, "title": capability}

        resp = {
            "correct": correct, "feedback": result["feedback"], "detail": result["detail"],
            "explain": a["explain"], "explain_alt": a.get("explain_alt"), "why": a.get("why"),
            "can_now": a["can_now"] if (correct or a["kind"] == "explain") else None,
            "assisted": bool(st["hints"] or st["solution"]),
            "outcome": outcome,
        }
        if a["kind"] == "explain":
            resp["model_answer"] = a["model_answer"]
            resp["checklist"] = a["checklist"]
        if correct is False:
            resp["retry_ok"] = True
            resp["next_hint_level"] = min(st["hints"] + 1, len(a.get("hints", [])) + 1)
        # after a viewed solution, insist on a fresh application before moving on
        if st["solution"] and correct:
            f = self.follow_up(activity_id)
            if f:
                resp["follow_up"] = {"id": f["id"], "title": f["title"]}
        return resp

    def _update_mastery(self, a: dict, correct: int | None, st: dict) -> dict:
        cs = self.store.concept_state(a["concept"])
        now = time.time()
        cs["last_seen_at"] = now
        before = cs["status"]
        assisted = bool(st["hints"] or st["solution"])
        if correct is None:                       # explain: participation only
            if cs["status"] == "new":
                cs["status"] = "seen"
            if cs["due_at"] is None:
                cs["due_at"] = now + REVIEW_DAYS[0] * DAY
        elif correct == 1 and not assisted and not st["is_micro"]:
            cs["independent_count"] += 1
            if a["role"] == "cumulative":
                cs["status"] = "cumulative"
            elif cs["status"] != "cumulative":
                # one right hook prediction is 'seen'; a second independent success is 'independent'
                if a["role"] == "hook" and cs["independent_count"] < 2:
                    cs["status"] = max_status(cs["status"], "seen")
                else:
                    cs["status"] = max_status(cs["status"], "independent")
            if st["is_review"]:
                cs["review_stage"] = min(cs["review_stage"] + 1, len(REVIEW_DAYS) - 1)
            cs["due_at"] = now + REVIEW_DAYS[cs["review_stage"]] * DAY
        elif correct == 1:                        # assisted or micro success
            cs["assisted_count"] += 1
            cs["status"] = max_status(cs["status"], "assisted")
            cs["due_at"] = now + REVIEW_DAYS[cs["review_stage"]] * DAY
        else:
            cs["fail_count"] += 1
            cs["status"] = max_status(cs["status"], "seen")
            cs["review_stage"] = max(0, cs["review_stage"] - 1)
            cs["due_at"] = now + REVIEW_DAYS[0] * DAY
        self.store.save_concept_state(cs)
        return {"concept": a["concept"], "before": before, "after": cs["status"],
                "next_review_days": REVIEW_DAYS[cs["review_stage"]] if cs["due_at"] else None,
                "assisted": assisted, "micro": st["is_micro"]}

    def _capability_line(self, a: dict, correct: int | None, st: dict) -> str | None:
        """A collection entry reflects a real capability. Assisted or micro success is kept but
        labelled; a viewed solution earns nothing; explanations are attempts, not capabilities."""
        if st["solution"] or a["kind"] == "explain" or correct != 1:
            return None
        base = a["can_now"]
        if st["hints"]:
            return base + " (with a hint)"
        if st["is_micro"]:
            return base + " (tiny action)"
        return base

    def feedback(self, session_id: int, activity_id: str, signal: str) -> dict:
        """too_hard | too_easy | explain_differently | stop"""
        a = self.track.activity(activity_id)
        self.store.log("feedback", {"activity": activity_id, "signal": signal})
        states = self._states()
        recent = self.store.recent_activity_ids(6)
        if signal == "explain_differently":
            return {"text": a.get("explain_alt") or self._alt_explain(a), "source": "curated"}
        if signal == "too_hard":
            weak = self._weakest_prereq(states, a["concept"])
            if weak:
                cands = [x for x in self.track.activities_for(weak) if x["kind"] != "explain" and x["difficulty"] <= 2]
                pick = self._unseen_or_fresh(cands, recent)[0]
                return {"action": "switch", "activity_id": pick["id"], "title": pick["title"],
                        "reason": f"This leans on {self.track.concepts[weak]['title'].lower()}. "
                                  "Let's shore that up first — a smaller step."}
            easier = [x for x in self.track.activities_for(a["concept"])
                      if x["id"] != activity_id and x["kind"] != "explain"
                      and (x["difficulty"] < a["difficulty"]
                           or EASIER_KINDS.index(x["kind"]) < EASIER_KINDS.index(a["kind"]))]
            if easier:
                pick = self._unseen_or_fresh(easier, recent)[0]
                return {"action": "switch", "activity_id": pick["id"], "title": pick["title"],
                        "reason": "Here is a smaller step on the same idea."}
            return {"action": "hint", "reason": "This is already the smallest step for this idea. "
                                                "Take the first hint — that is what it is for."}
        if signal == "too_easy":
            harder = [x for x in self.track.activities_for(a["concept"])
                      if x["id"] != activity_id and x["kind"] != "explain" and x["difficulty"] > a["difficulty"]]
            if harder:
                pick = self._unseen_or_fresh(harder, recent)[0]
                return {"action": "switch", "activity_id": pick["id"], "title": pick["title"], "reason": "A bigger version."}
            nxt = self._next_concept_after(a["concept"], states)
            if nxt:
                hook = self.track.activities_for(nxt, role="hook")[0]
                return {"action": "switch", "activity_id": hook["id"], "title": hook["title"],
                        "reason": f"Moving on to {self.track.concepts[nxt]['title'].lower()}."}
            return {"action": "none", "reason": "Nothing harder is unlocked yet — finish this one and it will be."}
        if signal == "stop":
            return {"action": "stop"}
        return {"action": "none"}

    def _next_concept_after(self, cid: str, states) -> str | None:
        order = self.track.concept_order
        for c in order[order.index(cid) + 1:]:
            if all(p == cid or self._rank(states, p) >= STATUS_RANK["assisted"]
                   for p in self.track.concepts[c]["prereqs"]):
                return c
        return None

    def _alt_explain(self, a: dict) -> str:
        c = self.track.concepts[a["concept"]]
        return f"Another angle: {c['summary']} In this activity that is the whole trick — {a['explain']}"

    def finish(self, session_id: int, enjoyment=None, frustration=None) -> dict:
        self.store.end_session(session_id, enjoyment=enjoyment, frustration=frustration)
        self.store.log("session_end", {"session": session_id})
        self._active.pop(session_id, None)
        nxt = self.next_action("small")
        return {"saved": True, "next_preview": {
            "title": nxt["activity"]["title"], "concept": nxt["concept"]["title"],
            "minutes": nxt["activity"]["minutes"], "reason": nxt["reason"]}}

    # ------------------------------------------------------------ evaluation
    def evaluation(self, days: int = 14) -> dict:
        now = time.time()
        since = now - days * DAY
        attempts = self.store.attempts_since(since)
        sessions = self.store.sessions_since(since)
        events = self.store.events_since(since)
        by_day: dict[str, dict] = {}
        for i in range(days):
            d = time.strftime("%Y-%m-%d", time.localtime(now - (days - 1 - i) * DAY))
            by_day[d] = {"date": d, "started": 0, "attempts": 0, "micro": 0, "independent_ok": 0, "independent_n": 0}
        for s in sessions:
            d = time.strftime("%Y-%m-%d", time.localtime(s["started_at"]))
            if d in by_day:
                by_day[d]["started"] += 1
        for a in attempts:
            d = time.strftime("%Y-%m-%d", time.localtime(a["at"]))
            if d not in by_day:
                continue
            by_day[d]["attempts"] += 1
            if a["is_micro"]:
                by_day[d]["micro"] += 1
            if a["correct"] is not None and not a["hints_used"] and not a["solution_viewed"]:
                by_day[d]["independent_n"] += 1
                by_day[d]["independent_ok"] += a["correct"]

        graded = [a for a in attempts if a["correct"] is not None]
        indep = [a for a in graded if not a["hints_used"] and not a["solution_viewed"]]
        review_indep = [a for a in indep if a["is_review"]]
        novel_indep = [a for a in indep if a["is_review"] or a["is_variation"]
                       or self.track.activity(a["activity_id"])["role"] in ("review", "cumulative")]
        solution_views = sum(1 for a in graded if a["solution_viewed"])
        enj = [s["enjoyment"] for s in sessions if s.get("enjoyment")]
        fru = [s["frustration"] for s in sessions if s.get("frustration")]
        too_hard = sum(1 for e in events if e["kind"] == "feedback" and '"too_hard"' in (e["data"] or ""))
        too_easy = sum(1 for e in events if e["kind"] == "feedback" and '"too_easy"' in (e["data"] or ""))

        def rate(xs):
            return round(100 * sum(a["correct"] for a in xs) / len(xs)) if xs else None

        days_started = sum(1 for d in by_day.values() if d["started"])
        return {
            "days": list(by_day.values()),
            "summary": {
                "days_with_a_start": days_started,
                "sessions": len(sessions),
                "sessions_with_no_attempt": sum(1 for s in sessions if s["activities_done"] == 0),
                "micro_sessions": sum(1 for s in sessions if s["mode"] == "micro"),
                "attempts": len(graded),
                "independent_rate": rate(indep),
                "independent_review_rate": rate(review_indep),
                "novel_variation_rate": rate(novel_indep),
                "solution_views": solution_views,
                "too_hard": too_hard, "too_easy": too_easy,
                "enjoyment_avg": round(sum(enj) / len(enj), 1) if enj else None,
                "frustration_avg": round(sum(fru) / len(fru), 1) if fru else None,
            },
            "reading": self._reading(days_started, rate(indep), rate(novel_indep), fru, too_hard, len(sessions)),
        }

    @staticmethod
    def _reading(days_started, indep_rate, novel_rate, fru, too_hard, sessions) -> list[str]:
        """Plain-language observations. Personal signals, not proof of anything."""
        out = []
        if sessions == 0:
            return ["No sessions in this window yet. The first tiny session is the only thing that matters right now."]
        out.append(f"You started on {days_started} of the last 14 days. Voluntary returns are the outcome that matters most here.")
        if indep_rate is not None and novel_rate is not None:
            if indep_rate >= 70 and novel_rate < 50:
                out.append("Familiar items go well but fresh variations do not yet — that looks like recognition "
                           "more than understanding. Lean on the explanations and variations for a while.")
            elif novel_rate >= 70:
                out.append("Fresh variations are going well. That is the best available sign of real understanding.")
        if fru and sum(fru) / len(fru) >= 4:
            out.append("Frustration is running high. Consider shorter sessions (Settings), and use 'too hard' "
                       "freely — it is a signal, not a failure.")
        if too_hard >= 3:
            out.append("'Too hard' has come up several times. The planner has been pulling prerequisites forward; "
                       "if it keeps happening, the concept needs smaller steps added to the content.")
        if days_started <= 3:
            out.append("Few starts. The 'I don't feel like it' button exists for exactly those days — "
                       "one prediction still counts.")
        return out
