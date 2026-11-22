# Design decisions and spec deviations

The assignment brief (sections referenced as §N) is followed exactly except where listed
here. Each entry says what changed and why.

## D1. UCS and A* share one cost model (§8.3)

**Spec:** BFS = 1 per term, UCS = credits per term, A* = `1 + 0.05·credits` per term, plus a
test that A* cost == UCS cost.

**Problem:** UCS and A* would be minimising different quantities, so equal costs could not
be expected.

**Decision:** UCS and A* both use `1 + 0.05·credits` per term; UCS is A* with `h = 0`.
BFS keeps unit cost per term. The A* == UCS test is then meaningful, and the comparison
table shows A* reaching the same cost with fewer expansions.

**Heuristic:** the spec's `max(credit_bound, depth_bound)` is kept and extended with
`+ 0.05 · credit_need`, and `credit_need` includes missing elective credits. Both additions
keep it admissible and consistent (see architecture.md) while matching the shared cost model.

## D2. Rule log records the final plan only (§9, §10 Tab 2)

**Problem:** logging every eligibility check for every expanded state produces thousands of
rows per run (BFS worst), making Tab 2 unreadable and bloating `rule_log`.

**Decision:** the log contains the full rule firings (PREREQ, OFFERING, CONFLICT, PRUNED,
OK) for each term of the *chosen* plan, plus each term's combo label. Search effort is
reported as numbers in Tab 3 (expanded, generated, ms, cost).

## D3. Only maximal combos are generated (§7)

**Spec:** emit every bundle with `min_credits <= credits <= max_credits`, cap 64.

**Problem:** ~64-way branching per term risks the 1 s budget, and the cap cuts off bundles
unpredictably.

**Decision:** `valid_combos` emits only *maximal* bundles — no further eligible course could
be added without breaking the credit cap or a slot. A non-maximal bundle can never finish
in fewer terms, and the relevance filter has already removed unneeded courses.

Supporting rules:
- **Below-minimum fallback:** bundles under `min_credits` are returned only when no bundle
  reaches it (last course of a plan, or a student blocked mid-chain), so plans don't come
  back infeasible.
- **Elective limit:** optional `elective_credits_needed`; once a bundle covers it, no more
  electives are added. Without this, "maximal" would pad every term with unneeded electives.

## D4. Required courses are closed under prerequisites (§6.3)

Required = all `math` and `core` courses + `track` courses of the target track + any
transitive prerequisites of those. Gen-ed and other tracks' courses are never required and
are logged as `PRUNED`.

## D5. Rule labels in the demo script (§12.8)

The spec's demo text says "Pruned CS301: missing prerequisite CS201". Under the spec's own
rules that is a `PREREQ` result, not `PRUNED`. The README demo script uses the labels and
term counts the app actually produces (expected 3–5 terms, not the placeholder "8").

## D6. Smaller interpretations

- **Term labels:** first term is the profile's `start_term` in 2026 (Fall 2026) or 2027
  (Spring 2027); the year increments each fall.
- **"Inserted for missing prereq" badge:** shown on planned *lower-division* courses
  (number < 300) that the log names as a missing prerequisite. Flagging every missing
  prerequisite would mark nearly every chained course even for On-track (CS301, AI320, …);
  the narrower rule marks exactly Transfer's gaps (CS201, CS210, MATH210).
- **"Top-3 pruned courses" (§9):** since each `PRUNED` reason is logged once (D2), the
  summary ranks courses by how often they were held back by `PRUNED`, `PREREQ`, or
  `OFFERING`, ties broken by code.
- **UI defaults:** algorithm defaults to A\* and "Run all three algorithms" defaults to on,
  so the first Generate already fills the comparison table (the demo's headline moment).
- **"Current term" in the graph (§10 Tab 4):** a slider picks which planned term is
  "current"; earlier planned terms count as completed. Courses not required for the track
  are drawn dashed.
- **Extra test file:** `tests/test_explain.py`, beyond the four listed in §3.
- **Line length:** ruff's default rules skip E501, so it is enabled explicitly.
- **DB location:** `courseplanner.db` is anchored to the project root, not the launch
  directory. `get_connection()` / `init_db()` take an optional path so tests use `tmp_path`.
- **Track override:** choosing another track in the sidebar replans against that track's
  requirements.
- **Corequisites:** none in the catalog; the table and field exist but stay empty.
- **Python:** `requires-python = ">=3.11"`, pinned locally to 3.14 via `.python-version`.

## D7. Search details not fixed by the spec (§8)

- **Wait successor:** if no course can be taken this term (e.g. only fall-only courses
  remain in spring), the only successor is the same completed set one term later. Without
  it such states would be dead ends. Waiting is never offered when a bundle exists, since
  taking courses never delays the goal.
- **Goal test on pop** for every algorithm, so UCS and A* return least-cost plans.
- **Test direction:** the spec's "BFS plan length ≥ A* plan length" is inverted — BFS
  minimises terms, so it is never longer. Tests assert BFS length ≤ UCS (and later A*)
  length.
- **Term labels** live in `rules.term_label` because the search's log needs them before
  `explain.py` exists.

## D8. Git history beyond the 11 milestone commits (§13.3)

Additional commits, all new (never amended): a Makefile (user request), a ruff lint fix,
pinning ruff as a dev dependency, and these docs. The spec's §17 "chore: add dependencies"
step was folded into commit 1. Commits carry no `Co-Authored-By` trailer.
