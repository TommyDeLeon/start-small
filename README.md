# start small

A local app that makes starting easy. It prepares one small next action,
you press **Start small**, you predict or fix or build one thing, you get
honest feedback and one plain-language idea, and you stop with the next
step already saved. Python is the first track; everyday tasks and other
subjects plug into the same shell.

No accounts, no services, no dependencies. Python 3.10+ and a browser.

## Get it

**Option A — download the ZIP (no git needed)**

1. On this page, click the green **Code** button → **Download ZIP**.
2. Unzip it anywhere (Desktop is fine). You get a folder called
   `start-small-main`.

**Option B — clone**

```bash
git clone https://github.com/TommyDeLeon/start-small.git
```

**Then make sure Python is installed.** Open a terminal (on Windows:
press the Windows key, type `cmd`, Enter) and run:

```bash
python --version
```

If that prints `Python 3.10` or higher, you are set. If it says Python is
not recognised, install it from [python.org/downloads](https://www.python.org/downloads/)
and tick **"Add python.exe to PATH"** in the installer, then reopen the
terminal.

## Launch

In the terminal, go into the unzipped folder and run the app:

```bash
cd path/to/start-small-main
python app.py
```

(On Windows you can also open the folder in Explorer, click the address
bar, type `cmd`, press Enter, and then run `python app.py`.)

That starts a server on `http://127.0.0.1:8765/` and opens your browser.
Leave the terminal window open while you use it. `Ctrl+C` in the terminal
stops it; nothing keeps running afterwards.

Your progress lives in `data/startsmall.db` inside the folder. It never
leaves your computer. Delete that file to start over; keep it when you
update the app.

Options: `--no-open` (don't open the browser), `--port 8766`, `--db PATH`.

## Using it

- **Start small** — the one prepared action. About two minutes. Predict what
  code prints, fix one line, or build something tiny.
- **Check** — honest feedback that names the exact line or test. Wrong
  guesses are fine; that is how the explanation lands.
- **Hint 1 → 2 → 3** — a nudge, then a partial example, then the worked
  solution. If you view the solution, you get a fresh small version to do
  on your own before the idea counts as yours.
- **Too hard / Too easy / Explain differently / Stop** — always available.
- **One more / Finish here** — after each activity. Stopping is a real
  choice, not a failure; the next step is already saved.
- **I don't feel like it** — one tiny action, then you are done. It counts
  as showing up.
- **Collection** — things you can now do. **Two weeks** — whether you are
  coming back and whether understanding is growing. **Tasks** — turn a vague
  everyday task into a physical next action with a stop point.
  **Settings** — session lengths, your cue, and switches for every
  motivational feature.

## Your first tiny session

1. `python app.py`
2. Press **Start small**. The first activity is a two-minute prediction:
   three lines of `print`, and you type what appears.
3. Guess — even a wrong guess is useful. Check. Read the line-by-line
   feedback, take a hint if you want, get it right.
4. Read "The idea" (one concept) and "You can now …" (what you just proved).
5. Press **Finish here**. Done. Next time the home screen already knows
   what comes next.

On a day you do not want to do anything, press **I don't feel like it**:
one prediction or one-line fix, then you are finished. It counts as showing
up; it is not counted as mastery, and the app says so.

## What is in the box

| Path | What it does |
|---|---|
| `app.py` | Launcher |
| `startsmall/server.py` | Stdlib HTTP server, JSON API, serves `static/` |
| `startsmall/engine.py` | Planner: next action, mastery ladder, review schedule, hints, difficulty signals, two-week evaluation |
| `startsmall/grader.py` | Grades predictions (tolerant of trailing whitespace only) and code (function tests + stdin/stdout tests) |
| `startsmall/runner.py` | Runs your code in an isolated subprocess with a timeout and a memory cap (see limits below) |
| `startsmall/store.py` | SQLite: settings, concept state, attempts, sessions, events, tasks, collection |
| `startsmall/content/python_track.py` | 10 concepts, 63 activities, prerequisite graph |
| `startsmall/ai.py` | Optional Claude helper (off by default) |
| `static/` | The UI: one HTML file, one CSS file, one JS file |
| `remind.py` | Optional reminder you run yourself; never installed |
| `tests/` | Content gate + vertical-slice tests |
| `RESEARCH.md` | Evidence, limits, and where each mechanism lives |

## How a session is built

Every activity follows the same eight steps: an interesting outcome or
question → your prediction or attempt → informative feedback → one concept
in plain language (and "explain differently") → apply it in a slightly
different example → "You can now …" → a review scheduled for later → a
clean finish with a preview of what is next.

The planner's rules, all in `engine.py`:

- **Concept order** follows prerequisites. A concept is "done" only when
  you have succeeded on a fresh activity with no hints *and* attempted its
  build project.
- **Mastery** per concept: `new → seen → assisted → independent →
  cumulative`. Success after a hint or a viewed solution is *assisted*.
  Viewing a solution can never produce *independent*; a fresh small
  application is served right after.
- **Reviews** use an expanding ladder (1, 3, 7, 14, 30 days). A miss drops
  one rung, never below one day. Nothing accumulates while you are away.
- **Too hard** goes to your weakest direct prerequisite, then to a smaller
  step on the same idea. **Too easy** goes to a bigger version or the next
  concept's hook. A failed item is never re-served unchanged straight away.
- **After a gap of two days or more**, you get a warm-up on something you
  already got right, and a note that nothing piled up.
- **Response speed is never used** to judge you.

## Running your code: what the isolation is and is not

`runner.py` runs your code in a fresh `python -I -S -B` subprocess in an
empty temp directory with a minimal environment, a 5-second wall clock, and
a 256 MB memory cap (a Windows Job Object; `RLIMIT_AS` elsewhere). Timeouts
kill the whole process tree. Output is capped.

It does **not** block network access or reads of other files. That is
acceptable here because the only code that runs is code *you* typed on
*your* machine against curated exercises. It is not a sandbox for other
people's code. If you ever want that, CodeLock's Docker judge
(`D:/Cowork/codelock/apps/judge`) is the right tool; this app deliberately
does not depend on it, because it needs Docker, Postgres and a secret just
to start.

## Optional AI help

Off by default. If you turn it on in Settings, the app can ask Claude for a
third explanation when the two curated ones did not land, and for a short
reaction to your own-words explanations. It needs the official SDK
(`pip install anthropic`) and credentials (`ANTHROPIC_API_KEY` or
`ant auth login`). Requests cost money on your account. Only the activity
text and what you typed are sent, never your progress. Everything works
without it — the curated explanations are the default, not a fallback.

## Motivational features, and turning them off

- **Collection** — a list of things you actually did ("You fixed an
  indexing error"). Entries earned with a hint or as a tiny action say so.
  Always on, because it is just a record.
- **Sparks ✦** — optional, cosmetic. One per activity passed with no hints,
  once on first pass and once on review. Repeats earn nothing. Settings.
- **Celebration animation** — optional, only on unassisted success, obeys
  `prefers-reduced-motion`. Settings.
- **Reminders** — off by default; see `remind.py`.
- Not present, on purpose: streaks, leaderboards, badges for attendance,
  loot mechanics, fabricated urgency, notification nagging.

## Everyday tasks

The Tasks page turns "work on the project" into a physical next action with
a stop point ("open the leads sheet and write one name; stop when one name
is written"). Starting it shows only that line and a clock; nothing is
graded. It records that you started, which is the outcome that matters.

## The two-week view

Days with a start, sessions, right-with-no-help rate, right-on-fresh-
variations rate, right-on-later-reviews rate, worked solutions viewed,
optional enjoyment and frustration. Plus a few plain-language readings.
Personal observations, not proof; see `RESEARCH.md` §10 for how to act on
them.

## What it covers, and what comes after

The Python track covers the first stretch of learning to program — roughly
the first six weeks of a CS50P-style course: printing, variables and
input, numbers, decisions, `for` and `while` loops, lists, functions,
string methods, and dictionaries. Ten concepts, sixty-three activities,
each ending in something small you built.

When you have worked through it and want to keep going — data structures,
algorithms, and real problem sets with a judge that runs your code against
tests — continue with **[CodeLock](https://github.com/TommyDeLeon/codelock)**,
by the same author. It picks up where this leaves off: 685 problems from
foundations through core patterns, served in prerequisite order, with
editorials and reference solutions.

## Adding a subject

Copy `startsmall/content/python_track.py` to `<name>_track.py`, keep the
shape (`TITLE`, `CONCEPTS`, `ACTIVITIES`), and run the tests. The content
gate refuses any predict activity whose stated answer differs from the real
output, any reference solution that fails its own tests, and any "fix"
whose starter already passes. Non-code subjects can use `predict` and
`explain` only.

## Tests

```bash
python -m unittest discover -s tests -t .
```

21 tests: every activity executed (`test_content.py`), and the full
vertical slice plus failure cases — wrong answers, hint honesty, solution
views, micro actions, too-hard rerouting, gentle restart, crashing and
infinite-loop code, persistence across a restart, the evaluation view, and
spark farming (`test_engine.py`).

## Known limitations

- One track (Python, 10 concepts). Later concepts (errors, files, classes)
  are not written yet; the planner rotates cumulative challenges once the
  track is done.
- Prediction grading is exact after trimming trailing whitespace. That is
  intentional — spacing is part of what is being learned — but it means a
  typo counts as wrong. The line diff shows exactly where.
- `explain` activities are self-checked. They cannot be auto-graded
  honestly, so they are recorded as participation only.
- No relatedness: it is a single-user local app.
- The review intervals and session lengths are defaults, not optima.
