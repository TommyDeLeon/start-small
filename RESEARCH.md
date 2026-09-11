# RESEARCH.md — what the design rests on, and how much weight it can bear

This maps each mechanism in start-small to the evidence behind it, what that
evidence does *not* show, and where the mechanism lives in the code.

**How the sources were read (2026-09-11).** I fetched and read the full text
of Ryan & Deci (2000) and Dunlosky et al. (2013) from the PDFs. Sailer &
Homner (2020) was read from the publisher page. Roediger & Karpicke (2006),
Lally et al. (2010), Deci, Koestner & Ryan (1999), Gollwitzer & Sheeran
(2006), Cepeda et al. (2008), Kornell, Hays & Bjork (2009) and Hanus & Fox
(2015) were read at **abstract / summary level** (publisher abstracts and
secondary write-ups; PubMed and Wiley blocked full-text fetches). Kalyuga et
al. (2003) and the worked-example literature are cited from secondary
summaries only. Claims below are labelled accordingly. Nothing here is
invented; where I could not verify a number I say so.

Two labels are used throughout:

- **Demonstrated** — a finding from the cited primary research, with its
  stated scope.
- **Hypothesis** — a design choice that is *consistent with* the research but
  not directly tested by it. Treat these as things to watch in the two-week
  view, not as facts.

---

## 1. Intrinsic motivation: autonomy, competence, relatedness

**Source.** Ryan & Deci (2000), *American Psychologist* 55(1), 68–78.
[PDF](https://selfdeterminationtheory.org/SDT/documents/2000_RyanDeci_SDT.pdf).
Read in full.

**Demonstrated (per the review).** Optimal challenge, positive
performance feedback and freedom from demeaning evaluation increase intrinsic
motivation; these effects are mediated by perceived competence, and
competence feedback only helps when accompanied by a sense of autonomy
(internal locus). Controlling teaching lowers initiative and learning,
especially for conceptual work. Much of this is from lab experiments and
classroom field studies; the review states intrinsic motivation only applies
to activities that already hold some interest.

**Limitation.** The paper is a theory review, not a meta-analysis. Effects
were mostly measured on short "free-choice" tasks; it does not tell us how
much any single design choice matters for a self-directed adult learning
Python at home.

**Implementation.**
- Autonomy: every session has a visible *Stop*, *Finish here*, *too hard*,
  *too easy* and *explain differently*; nothing is locked behind the
  motivational features (`static/app.js`, `engine.feedback`).
- Competence feedback that is informational, not evaluative: feedback names
  the exact line or failing test (`grader.py`) and the "You can now …" line
  states a capability, never a score (`engine._capability_line`).
- No demeaning evaluation: wrong answers get "Not quite. Line 3: …", never a
  grade, streak loss or comparison (`app.js` submit()).
- Relatedness is the weakest leg here: a single-user local app cannot supply
  it. Hypothesis: the warm, specific wording helps a little. Not tested.

## 2. External rewards: when they undermine

**Source.** Deci, Koestner & Ryan (1999), *Psychological Bulletin* 125(6),
627–668. Abstract-level. 128 experiments. Engagement-, completion- and
performance-contingent tangible rewards undermined free-choice intrinsic
motivation (d = −0.40, −0.36, −0.28); positive verbal feedback *enhanced* it
(d = 0.33 free-choice, 0.31 self-report). Tangible rewards were more harmful
for children than college students.

**Limitation.** Mostly lab tasks that were interesting to begin with; the
undermining effect is about *expected, tangible* rewards. A cosmetic counter
is not a tangible reward, but it is expected, so caution is warranted.

**Implementation.**
- Primary reward is informational feedback and the capability collection
  (`store.collection`) — the thing the meta-analysis says helps.
- "Sparks" are optional (Settings), cosmetic, secondary, and follow a
  transparent rule: one per activity passed with no hints, once on first pass
  and once on review; repeats earn nothing (`engine._sparks`). Hypothesis:
  at this size they are harmless. If the two-week view shows engagement up
  and understanding flat, turn them off first.
- No points for clicks, no daily bonus, no loot mechanics.

## 3. Gamification: small, mixed, novelty-prone

**Sources.**
- Sailer & Homner (2020), *Educational Psychology Review* 32, 77–112.
  [Link](https://link.springer.com/article/10.1007/s10648-019-09498-w).
  Read from the publisher page. 40 experiments / 38 papers, 2013–2017.
  Cognitive g = 0.49 [0.30, 0.69], motivational g = 0.36 [0.18, 0.54],
  behavioural g = 0.25 [0.04, 0.46]. Heterogeneity I² = 51–84%. **When
  restricted to methodologically rigorous studies, the motivational and
  behavioural effects were not significant.** Longer interventions (> 1
  month) had larger motivational effects than one-day ones; game fiction and
  "competition + collaboration" helped behavioural outcomes. Behavioural
  outcomes were mostly measured *during* the intervention.
- Hanus & Fox (2015), *Computers & Education* 80, 152–161. Abstract-level.
  A 16-week classroom study: the badge + leaderboard section showed *lower*
  motivation, satisfaction and empowerment over time than the control.

**Limitation.** School and university samples, short durations, and the
authors themselves say the ingredients of successful gamification are
unresolved. Nothing here supports "gamify and they will come" for a solo
adult.

**Implementation.** Gamification is deliberately thin: no leaderboard, no
badges-for-attendance, no streaks. The one game-like element with support in
Sailer & Homner (fiction) appears only as project themes — cave game,
receipts, batch renamer — that keep the learning task central.
Hypothesis: small runnable projects give the "interesting outcome" that SDT
says intrinsic motivation needs. Watch enjoyment and return rate.

## 4. Retrieval practice and the testing effect

**Sources.**
- Roediger & Karpicke (2006), *Psychological Science* 17(3), 249–255.
  Abstract-level. Prose passages; repeated study beat testing at 5 minutes,
  but testing beat restudy at 2 days and 1 week, while restudy *raised
  confidence* more. Undergraduates, no feedback.
- Dunlosky et al. (2013), *PSPI* 14(1), 4–58. Read in full. Practice testing
  rated **high utility**: "demonstrated across an impressive range of
  practice-test formats, kinds of material, learner ages, outcome measures,
  and retention intervals." Distributed practice also high utility.
  Self-explanation, elaborative interrogation and interleaving: moderate.
  Summarising, highlighting, rereading, keyword mnemonic, imagery: low.
- Kornell, Hays & Bjork (2009), *JEP:LMC* 35, 989–998. Abstract-level.
  Unsuccessful retrieval attempts followed by feedback produced better
  retention than presentation-only, even when the attempt was guaranteed to
  fail.

**Limitation.** Most testing-effect work is on verbal/factual material with
undergraduates. Transfer to *procedural* skill (writing code) is plausible
and Dunlosky notes breadth, but the effect sizes for programming specifically
are not established by these sources.

**Implementation.**
- Every activity is an attempt before an explanation: predict, fix, write.
  The explanation only appears after a submission (`app.js` submit →
  showExplanation).
- Wrong guesses are framed as useful (Kornell et al.) — the UI says so, and
  the hint ladder starts only after an attempt.
- Later retrieval: each concept has `review` activities served on the
  schedule below, always a *different* item from the one first learned
  (`engine.pick_review`).
- The over-confidence finding is why "solution viewed" and "with a hint" are
  recorded and shown, and why the collection labels them.

## 5. Distributed practice and the spacing schedule

**Sources.** Dunlosky et al. (2013) (high utility; "works across students of
different ages, with a wide variety of materials … over long delays").
Cepeda et al. (2008), *Psychological Science* 19, 1095–1102. Abstract-level.
1,350+ participants, facts, gaps up to 3.5 months, tests up to 1 year: the
optimal gap was roughly 20–40% of a 1-week retention interval, falling to
5–10% of a 1-year interval.

**Limitation.** Cepeda's material was facts, not skills. The optimal gap
depends on how long you want to remember; no source gives an optimum for
"remember how loops work indefinitely while still learning new things."

**Implementation.** A simple expanding ladder — 1, 3, 7, 14, 30 days
(`engine.REVIEW_DAYS`). An independent review success moves up one rung, an
assisted success holds, a failure drops one rung and never below 1 day, so
there is no growing backlog (`engine._update_mastery`). **These numbers are
design defaults, not derived optima.** The ladder is the one place I would
most expect to tune after two weeks of data.

## 6. Worked examples, faded guidance, expertise reversal

**Sources.** Secondary summaries of Sweller & Cooper (1985) and Kalyuga,
Ayres, Chandler & Sweller (2003), *Educational Psychologist* 38(1). Not read
in primary form. The claim: novices learn more from studying worked examples
than from unguided problem solving; as knowledge grows the advantage reverses
(expertise reversal), so guidance should fade. Dunlosky (2013, read) rates
self-explanation moderate and notes self-explanation effects shrink when
learners can consult provided explanations before trying (Schworm & Renkl,
2006).

**Limitation.** Cited from secondary sources; effect sizes not verified here.

**Implementation.**
- Hint ladder: conceptual hint → partial example → full worked solution
  (`engine.hint`), each level logged.
- After a worked solution, a fresh small application is *required* before
  the concept can progress (`engine.follow_up`; `app.js` "Do the fresh
  version"). A viewed solution can never produce "independent".
- Fading: the planner reduces assistance by serving variations and
  cumulative challenges once a concept is independent
  (`engine.pick_next_in_concept`, `role: cumulative`).
- Self-explanation prompts (`kind: explain`) come *after* an attempt and
  are self-checked against a model answer; they are recorded as
  participation, never as mastery.

## 7. Habit formation, cues, implementation intentions

**Sources.**
- Lally, van Jaarsveld, Potts & Wardle (2010), *EJSP* 40, 998–1009.
  Abstract + secondary summaries. 96 volunteers, daily behaviour in a fixed
  context for 12 weeks; **82 gave enough data and only 39 fit the curve
  well.** Among those, median 66 days to 95% of asymptotic automaticity,
  range 18–254. Missing one day did not materially impair formation.
- Gollwitzer & Sheeran (2006), *Advances in Experimental Social Psychology*
  38, 69–119. Abstract-level. 94 tests; if-then plans ("when X, I will Y")
  improved goal attainment, d = 0.65.

**Limitation.** Lally's 66 days is a median over 39 people doing simple
health behaviours, self-reported; it is not a target and not a promise.
Gollwitzer's effect is across many goal types; the size for "open an app
and learn" is unknown.

**Implementation.**
- One editable cue line, shown on the home screen: "after opening my laptop
  → open this and press Start small" (`settings.cue`). That is the
  implementation intention; the app does nothing else with it.
- Missed days: no streak, no backlog. After ≥ 2 days away the planner serves
  a warm-up on something already answered correctly, with the note that
  nothing piled up (`engine.next_action` restart branch) — consistent with
  the missed-day finding.
- Reminders are off by default, opt-in, one dismissible message per day,
  never in quiet hours, and installed by nobody but you (`remind.py`).
  Hypothesis: a cue plus a prepared tiny action lowers the start cost enough
  to matter. Measured by "days with a start".

## 8. Curiosity and appropriate challenge

**Source.** Ryan & Deci (2000) on optimal challenge (read). Loewenstein's
information-gap account is *not* cited as evidence here because I did not
read it in this session.

**Implementation (hypothesis).** Each concept opens with a hook — an
interesting outcome or concrete question — and a prediction. Difficulty
adapts on explicit signals only: "too hard" goes to the weakest direct
prerequisite, then to an easier activity in the same concept
(`engine.feedback`). Response speed is stored but never used to judge
ability.

## 9. What is *not* claimed

- No claim about dopamine, addiction, or "effortless" learning.
- No claim that these mechanisms, shown mostly with students on verbal
  material, transfer at the same strength to an adult learning to program
  alone. The two-week view exists to check whether they do *for you*.
- No causal claims from the two-week view: it is one person's log, with no
  control condition.

## 10. How to read the two-week view against this

| Signal | Likely reading | What to adjust |
|---|---|---|
| Starts up, independent-on-fresh-variations flat | Engagement without understanding (Sailer & Homner's caution) | Turn sparks off; lean on explain-differently and variations; slow the planner |
| Frustration ≥ 4 average | Challenge above optimum (SDT) | Shorter sessions; use "too hard" freely; add smaller steps to the concept |
| Reviews fail after long gaps | Ladder too aggressive for this material | Shorten `REVIEW_DAYS` |
| Many worked solutions viewed | Hints not scaffolding enough | Add an intermediate hint to those activities |
| Few starts, high enjoyment when started | Start cost, not the activity, is the barrier | Cue and micro action; consider the reminder script |
