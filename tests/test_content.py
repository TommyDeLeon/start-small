"""Content gate: nothing ships unless it actually runs.

* every predict activity's `answer` equals the real output of `code`
* every fix/write/build `solution` passes its own tests via the real runner
* every fix starter FAILS its tests (otherwise there is nothing to fix)
* prerequisite graph is acyclic and every prereq is defined earlier in order
* every concept has a hook and a review activity
"""
import unittest

from startsmall import content, grader, runner


class ContentGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.track = content.load("python")

    def test_prereqs_are_defined_before_use(self):
        seen = set()
        for cid in self.track.concept_order:
            for p in self.track.concepts[cid]["prereqs"]:
                self.assertIn(p, seen, f"{cid} lists prereq {p} that comes later in order")
            seen.add(cid)

    def test_predict_answers_match_real_output(self):
        for a in self.track.activities.values():
            if a["kind"] != "predict":
                continue
            with self.subTest(activity=a["id"]):
                res = runner.run_program(a["code"])
                self.assertEqual(res["error"], "", f"{a['id']} code crashed: {res['error']}")
                self.assertEqual(
                    grader.normalise_output(res["stdout"]),
                    grader.normalise_output(a["answer"]),
                    f"{a['id']}: stated answer does not match real output",
                )

    def test_reference_solutions_pass(self):
        for a in self.track.activities.values():
            if a["kind"] not in ("fix", "write", "build"):
                continue
            with self.subTest(activity=a["id"]):
                res = grader.grade(a, a["solution"])
                self.assertTrue(res["correct"], f"{a['id']} solution failed: {res['feedback']}")

    def test_fix_starters_fail(self):
        for a in self.track.activities.values():
            if a["kind"] != "fix":
                continue
            with self.subTest(activity=a["id"]):
                res = grader.grade(a, a["code"])
                self.assertFalse(res["correct"], f"{a['id']} starter already passes — no bug to fix")

    def test_every_concept_has_hook_apply_and_review(self):
        for cid in self.track.concepts:
            roles = {x["role"] for x in self.track.activities_for(cid)}
            self.assertIn("hook", roles, cid)
            self.assertIn("review", roles, cid)
            self.assertTrue({"apply", "build"} & roles, cid)

    def test_predict_grading_tolerates_trailing_whitespace_only(self):
        a = self.track.activity("print.hook")
        self.assertTrue(grader.grade(a, a["answer"] + "  \n\n")["correct"])
        self.assertFalse(grader.grade(a, a["answer"].replace(" ", ""))["correct"])
        self.assertFalse(grader.grade(a, "")["correct"])

    def test_predict_feedback_names_quote_and_comma_misconceptions(self):
        a = self.track.activity("print.hook")
        r = grader.grade(a, "'2 + 2'\n4\n'2 + 2', 4")
        self.assertFalse(r["correct"])
        self.assertIn("quote marks", r["feedback"])
        self.assertNotIn("'2 + 2'", r["feedback"].split("you wrote")[0])  # never quote the expected text
        r = grader.grade(a, "2 + 2\n4\n2 + 2 =, 4")
        self.assertIn("comma", r["feedback"])
        r = grader.grade(a, "2 + 2\n4")
        self.assertIn("Line 3 should be:  2 + 2 = 4", r["feedback"])

    def test_hints_are_graduated(self):
        for a in self.track.activities.values():
            if a["kind"] == "explain":
                continue
            with self.subTest(activity=a["id"]):
                self.assertGreaterEqual(len(a["hints"]), 2)
                self.assertTrue(all(h.strip() for h in a["hints"]))


if __name__ == "__main__":
    unittest.main()
