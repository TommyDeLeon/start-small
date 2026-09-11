"""Vertical slice + failure cases, driven through the Engine exactly as the server does."""
import os
import tempfile
import time
import unittest

from startsmall.engine import DAY, Engine
from startsmall.store import Store


class EngineSlice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ss-test-")
        self.db = os.path.join(self.tmp, "t.db")
        self.store = Store(self.db)
        self.engine = Engine(self.store, "python")

    def _pass(self, engine, sid, aid):
        a = engine.track.activity(aid)
        answer = a.get("answer") or a.get("solution")
        return engine.submit(sid, aid, answer)

    def test_first_action_is_the_print_hook_and_hides_answers(self):
        home = self.engine.home()
        nxt = home["next"]
        self.assertEqual(nxt["activity"]["id"], "print.hook")
        self.assertEqual(nxt["reason"], "learn")
        for hidden in ("answer", "solution", "hints", "tests"):
            self.assertNotIn(hidden, nxt["activity"])

    def test_vertical_slice_start_submit_feedback_hints_persist_review_resume(self):
        # 1. start a prepared activity
        s = self.engine.start("small")
        sid, aid = s["session_id"], s["activity"]["id"]
        self.assertEqual(aid, "print.hook")

        # 2. wrong attempt → correct feedback with a line diff, retry allowed
        r = self.engine.submit(sid, aid, "2 + 2\n4\n2 + 2 =4")
        self.assertFalse(r["correct"])
        self.assertIn("Line 3", r["feedback"])
        self.assertTrue(r["retry_ok"])
        self.assertEqual(r["next_hint_level"], 1)

        # 3. graduated hints: 1, 2 are hints; 3 is the worked solution
        h1 = self.engine.hint(sid, aid, 1)
        h2 = self.engine.hint(sid, aid, 2)
        self.assertFalse(h1["is_solution"]); self.assertFalse(h2["is_solution"])
        self.assertNotEqual(h1["text"], h2["text"])
        h3 = self.engine.hint(sid, aid, 3)
        self.assertTrue(h3["is_solution"])
        self.assertIsNotNone(h3["follow_up"])  # a fresh application is prepared

        # 4. success after viewing the solution is recorded honestly
        r = self.engine.submit(sid, aid, "2 + 2\n4\n2 + 2 = 4")
        self.assertTrue(r["correct"])
        self.assertTrue(r["assisted"])
        self.assertIn("follow_up", r)
        att = self.store.attempts_for_activity(aid, 1)[0]
        self.assertEqual(att["solution_viewed"], 1)
        self.assertEqual(att["hints_used"], 3)
        self.assertEqual(self.store.concept_state("print")["status"], "assisted")
        self.assertEqual(self.store.list_collection(), [])  # no capability for a viewed solution

        # 5. finish saves the next step
        f = self.engine.finish(sid, enjoyment=4, frustration=2)
        self.assertTrue(f["saved"])
        self.assertIn("title", f["next_preview"])

        # 6. resume after "closing the app": a new Engine on the same file continues
        e2 = Engine(Store(self.db), "python")
        home = e2.home()
        self.assertEqual(home["next"]["activity"]["concept"], "print")
        self.assertNotEqual(home["next"]["activity"]["id"], "print.hook")  # moves on, no unchanged repeat

        # 7. a later review: force the due date into the past and see the review served
        cs = self.store.concept_state("print")
        cs["due_at"] = time.time() - 10
        self.store.save_concept_state(cs)
        nxt = e2.next_action("small")
        self.assertTrue(nxt["is_review"])
        self.assertEqual(nxt["activity"]["role"], "review")
        s2 = e2.start("small")
        r = self._pass(e2, s2["session_id"], s2["activity"]["id"])
        self.assertTrue(r["correct"]); self.assertFalse(r["assisted"])
        cs = self.store.concept_state("print")
        self.assertEqual(cs["status"], "independent")
        self.assertEqual(cs["review_stage"], 1)          # moved up one rung
        self.assertGreater(cs["due_at"], time.time() + 2 * DAY)

    def test_independent_success_never_comes_from_hints(self):
        s = self.engine.start("small")
        sid, aid = s["session_id"], s["activity"]["id"]
        self.engine.hint(sid, aid, 1)
        r = self._pass(self.engine, sid, aid)
        self.assertTrue(r["correct"]); self.assertTrue(r["assisted"])
        self.assertEqual(self.store.concept_state("print")["status"], "assisted")
        col = self.store.list_collection()
        self.assertEqual(len(col), 1)
        self.assertIn("(with a hint)", col[0]["title"])

    def test_failed_activity_is_not_repeated_unchanged(self):
        s = self.engine.start("small")
        sid, aid = s["session_id"], s["activity"]["id"]
        self.engine.submit(sid, aid, "wrong")
        self.engine.finish(sid)
        nxt = self.engine.next_action("small")
        self.assertNotEqual(nxt["activity"]["id"], aid)

    def test_micro_action_counts_as_participation_not_mastery(self):
        s = self.engine.start("micro")
        self.assertTrue(s["is_micro"])
        self.assertEqual(s["activity"]["difficulty"], 1)
        r = self._pass(self.engine, s["session_id"], s["activity"]["id"])
        self.assertTrue(r["correct"])
        st = self.store.concept_state(s["activity"]["concept"])
        self.assertNotEqual(st["status"], "independent")
        self.assertIn("(tiny action)", self.store.list_collection()[0]["title"])

    def test_too_hard_moves_to_weakest_prerequisite(self):
        # jump straight into numbers.fix while 'variables' is untouched
        s = self.engine.start("small", activity_id="numbers.fix")
        fb = self.engine.feedback(s["session_id"], "numbers.fix", "too_hard")
        self.assertEqual(fb["action"], "switch")
        self.assertEqual(self.engine.track.activity(fb["activity_id"])["concept"], "variables")

    def test_too_hard_within_concept_gives_a_smaller_step(self):
        # make print independent so the prereq is fine, then say the build is too hard
        cs = self.store.concept_state("print"); cs["status"] = "independent"; self.store.save_concept_state(cs)
        s = self.engine.start("small", activity_id="variables.build")
        fb = self.engine.feedback(s["session_id"], "variables.build", "too_hard")
        self.assertEqual(fb["action"], "switch")
        a = self.engine.track.activity(fb["activity_id"])
        self.assertEqual(a["concept"], "variables")
        self.assertLess(a["difficulty"], 2)

    def test_too_easy_and_explain_differently(self):
        s = self.engine.start("small")
        sid, aid = s["session_id"], s["activity"]["id"]
        fb = self.engine.feedback(sid, aid, "explain_differently")
        self.assertIn("text", fb); self.assertEqual(fb["source"], "curated")
        fb = self.engine.feedback(sid, aid, "too_easy")
        self.assertIn(fb["action"], ("switch", "none"))
        self.assertEqual(self.engine.feedback(sid, aid, "stop")["action"], "stop")

    def test_gentle_restart_after_gap(self):
        s = self.engine.start("small")
        self._pass(self.engine, s["session_id"], s["activity"]["id"])
        # backdate everything by 5 days
        with self.store.conn() as c:
            c.execute("UPDATE attempts SET at = at - ?", (5 * DAY,))
            c.execute("UPDATE concept_state SET due_at = due_at - ?", (5 * DAY,))
        nxt = self.engine.next_action("small")
        self.assertEqual(nxt["reason"], "restart")
        self.assertIn("Nothing is overdue", nxt["note"])
        self.assertLessEqual(nxt["activity"]["difficulty"], 2)

    def test_explain_activity_is_recorded_but_never_mastery(self):
        s = self.engine.start("small", activity_id="print.explain")
        r = self.engine.submit(s["session_id"], "print.explain", "because quotes", self_check=[0, 1])
        self.assertIsNone(r["correct"])
        self.assertIn("model_answer", r)
        self.assertEqual(self.store.concept_state("print")["status"], "seen")
        self.assertEqual(self.store.list_collection(), [])

    def test_code_activity_wrong_then_right(self):
        s = self.engine.start("small", activity_id="lists.fix")
        sid = s["session_id"]
        r = self.engine.submit(sid, "lists.fix", "def last(items):\n    return items[len(items)]\n")
        self.assertFalse(r["correct"])
        self.assertIn("IndexError", r["feedback"])
        r = self.engine.submit(sid, "lists.fix", "def last(items):\n    return items[-1]\n")
        self.assertTrue(r["correct"])
        self.assertEqual(r["outcome"]["after"], "independent")
        self.assertIn("indexing error", self.store.list_collection()[0]["title"])

    def test_crashing_code_gives_friendly_error_not_500(self):
        s = self.engine.start("small", activity_id="functions.fix")
        r = self.engine.submit(s["session_id"], "functions.fix", "def double(n:\n")
        self.assertFalse(r["correct"])
        self.assertIn("SyntaxError", r["feedback"])
        r = self.engine.submit(s["session_id"], "functions.fix", "while True:\n    pass\n")
        self.assertFalse(r["correct"])
        self.assertIn("loop that never ends", r["feedback"])

    def test_evaluation_view_shape(self):
        s = self.engine.start("small")
        self._pass(self.engine, s["session_id"], s["activity"]["id"])
        self.engine.finish(s["session_id"], enjoyment=5, frustration=1)
        ev = self.engine.evaluation()
        self.assertEqual(len(ev["days"]), 14)
        self.assertEqual(ev["summary"]["sessions"], 1)
        self.assertEqual(ev["summary"]["days_with_a_start"], 1)
        self.assertEqual(ev["summary"]["independent_rate"], 100)
        self.assertEqual(ev["summary"]["enjoyment_avg"], 5.0)
        self.assertTrue(ev["reading"])

    def test_sparks_do_not_reward_farming(self):
        s = self.engine.start("small")
        sid, aid = s["session_id"], s["activity"]["id"]
        self._pass(self.engine, sid, aid)
        self._pass(self.engine, sid, aid)
        self._pass(self.engine, sid, aid)
        self.assertEqual(self.engine.home()["sparks"], 1)


if __name__ == "__main__":
    unittest.main()
