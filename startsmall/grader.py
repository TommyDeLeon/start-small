"""Grades an attempt against an activity. Pure functions plus the runner.

Result shape (all kinds):
  {"correct": bool | None, "feedback": str, "detail": {...}}
`correct` is None for `explain` activities: they are self-checked and never
count as demonstrated mastery.
"""
from __future__ import annotations

from . import runner


def normalise_output(text: str) -> str:
    """Tolerant comparison for predicted output.

    Trailing spaces on each line and trailing blank lines are ignored, because
    nobody should fail a prediction over an invisible character. Everything
    else — including the number of lines and inner spacing — must match,
    because that *is* the thing being learned.
    """
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _diff_lines(expected: str, got: str) -> str:
    """First differing line, shown without any added quote marks — adding quotes
    around the expected text would look like the quotes are part of the output."""
    e = expected.split("\n")
    g = got.split("\n")
    for i in range(max(len(e), len(g))):
        el = e[i] if i < len(e) else "(nothing — the program stops here)"
        gl = g[i] if i < len(g) else "(nothing)"
        if el != gl:
            return f"Line {i + 1} should be:  {el}   — you wrote:  {gl}"
    return ""


def _loosen(line: str) -> str:
    """What the line would be if quotes were not printed and commas became spaces."""
    parts = [p.strip() for p in line.split(",")]
    out = []
    for p in parts:
        if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
            p = p[1:-1]
        out.append(p)
    return " ".join(x for x in out if x != "") if len(parts) > 1 else (out[0] if out else "")


def _misconception(expected: str, got: str) -> str:
    """Recognise the two most common beginner misreadings of print() on the first wrong line."""
    e = expected.split("\n")
    g = got.split("\n")
    for i in range(min(len(e), len(g))):
        if e[i] == g[i]:
            continue
        if _loosen(g[i]) != e[i]:
            return ""
        has_quotes = any(q in g[i] for q in "\"'") and not any(q in e[i] for q in "\"'")
        has_comma = "," in g[i] and "," not in e[i]
        if has_quotes and has_comma:
            return (f"Line {i + 1}: two things. Quote marks are not printed — they only tell Python where "
                    "the text starts and ends. And a comma between items in print() becomes a single "
                    "space in the output, not a comma.")
        if has_quotes:
            return (f"Line {i + 1}: you included the quote marks. Python does not print them — quotes only "
                    "tell Python where the text starts and ends. Try the same line without them.")
        if has_comma:
            return (f"Line {i + 1}: close. A comma between items in print() becomes a single space in the "
                    "output, not a comma.")
        return ""
    return ""


def grade_predict(activity: dict, answer: str) -> dict:
    expected = normalise_output(activity["answer"])
    got = normalise_output(answer or "")
    accepted = [normalise_output(a) for a in activity.get("accept", [])]
    if got == expected or got in accepted:
        return {"correct": True, "feedback": "Exactly right.", "detail": {"expected": expected}}
    why = _misconception(expected, got)
    where = _diff_lines(expected, got)
    feedback = "Not quite. " + (why if why else where)
    return {
        "correct": False,
        "feedback": feedback,
        "detail": {"expected": expected, "got": got, "where": where},
    }


def grade_code(activity: dict, code: str) -> dict:
    """fix / write / build: run function tests and/or stdin→stdout tests."""
    detail: dict = {"tests": []}
    all_ok = True
    if activity.get("tests"):
        res = runner.run_function_tests(code, activity["tests"])
        if res["error"]:
            return {"correct": False, "feedback": f"Your code did not run: {res['error']}", "detail": {"error": res["error"]}}
        for t in res["tests"]:
            detail["tests"].append({
                "label": t["label"], "ok": t["ok"], "expected": t["expected"],
                "got": t["got"] if t["error"] is None else t["error"],
            })
            all_ok = all_ok and t["ok"]
    for io in activity.get("io_tests", []):
        res = runner.run_program(code, stdin_text=io.get("stdin", ""))
        if res["error"]:
            detail["tests"].append({"label": f"input {io.get('stdin', '')!r}", "ok": False,
                                    "expected": io["expect"], "got": res["error"]})
            all_ok = False
            continue
        got = normalise_output(res["stdout"])
        ok = got == normalise_output(io["expect"])
        detail["tests"].append({"label": f"input {io.get('stdin', '')!r}" if io.get("stdin") else "run",
                                "ok": ok, "expected": normalise_output(io["expect"]), "got": got})
        all_ok = all_ok and ok
    if not detail["tests"]:
        return {"correct": False, "feedback": "This activity has no tests.", "detail": detail}
    if all_ok:
        n = len(detail["tests"])
        return {"correct": True, "feedback": f"All {n} check{'s' if n != 1 else ''} passed.", "detail": detail}
    failed = [t for t in detail["tests"] if not t["ok"]]
    first = failed[0]
    fb = f"{len(failed)} of {len(detail['tests'])} checks failed. First one: {first['label']} → expected {first['expected']!s}, got {first['got']!s}."
    return {"correct": False, "feedback": fb, "detail": detail}


def grade(activity: dict, answer: str) -> dict:
    kind = activity["kind"]
    if kind == "predict":
        return grade_predict(activity, answer)
    if kind in ("fix", "write", "build"):
        return grade_code(activity, answer)
    if kind == "explain":
        return {"correct": None, "feedback": "Compare with the model answer and tick what you covered.",
                "detail": {"model_answer": activity["model_answer"], "checklist": activity["checklist"]}}
    raise ValueError(f"unknown kind {kind}")
