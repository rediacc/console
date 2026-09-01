# The DUPLICATION angle: trigger, verdict, and what the history actually says

Status: implemented. This file records the MEASUREMENTS, and in several places they
contradict the approved plan. Where they do, the measurement wins and the plan's text is
quoted so the difference is visible rather than quietly absorbed.

Approved plan: `~/.claude/plans/let-s-make-comprehensive-plan-luminous-sparrow.md`
(four rulings: all three pieces; N=3 span-scoped seeded; ride the call and trim
SWEEP_PROMPT; unshallow then calibrate).

---

## 1. The calibration replay (plan section 10) — the piece the brief called load-bearing

### 1a. The unshallow, and what it changed

`git fetch --unshallow origin` ran once, deliberately, in a tree another session shares.
It only ADDS objects, so it cannot destroy work; that is why it was safe without an
operator ruling.

    before   101 commits, .git/shallow present, history grafted at 2026-08-28
    after  2,353 commits, no .git/shallow, history back to 2025-06-01

The graft was not a cosmetic problem. `609314a41` reported **4,531 added files** under the
shallow clone; with real history it adds **4**. Every add-rate measured before the
unshallow was wrong by three orders of magnitude on that commit.

### 1b. Month-by-month adds per family (full history)

| month | `scripts/check-*.ts` | `quality/check-*.sh` | `gates/test-*.sh` | `pre-bash/block-*.sh` |
|---|---|---|---|---|
| 2026-01 | 8 | 12 | – | – |
| 2026-02 | – | 7 | – | – |
| 2026-03 | 3 | – | – | – |
| 2026-04 | 9 | 5 | 13 | – |
| 2026-05 | 2 | 3 | 1 | – |
| 2026-06 | 1 | 1 | – | 12 |
| 2026-07 | 24 | 6 | 55 | 3 |
| 2026-08 | 55 | 38 | 58 | 16 |
| 2026-09 | 6 | 2 | 1 | – |

### 1c. The number the plan actually asked for

The plan's gate: *"If the replay shows a new shape reaches its 3rd copy less than roughly
once a month, say so plainly and re-open the depth question rather than shipping a rule
that fires twice a year."*

Adds are not that number. The number is how often a shape that was NOT in the seed reaches
its third copy — i.e. how often the gate FIRES. Measured by replaying the real
`judge()` / `normalise()` / `windows()` from `scripts/check-shape-duplication.ts` over
historical trees read straight out of the object store (`git cat-file --batch`; nothing
checked out, nothing written outside a scratchpad), at three plausible install points:

| install point | corpus at install | firings after install | window |
|---|---|---|---|
| 2026-01 | 19 files / 2,096 hashes | **211** | 8 months |
| 2026-04 | 45 files / 4,765 hashes | **177** | 5 months |
| 2026-07 | 147 files / 15,227 hashes | **79** | 2 months |

Per month, from the 2026-07 install: **74 in 2026-08, 5 in 2026-09**.

**The gate passes, and in the opposite direction from the plan's worry.** The plan feared a
rule that fires twice a year. The measurement is 74 firings in a single month. The depth
question does not re-open; all three pieces ship.

### 1d. The finding the plan did not anticipate: it OVER-fires, in bursts

The distribution is not merely above threshold, it is violently bursty and tracks the
gate-authoring waves: 0–3 firings in a quiet month (2026-03, 2026-05), 74–172 in an
authoring month. Seeded at any point, the gate accumulates a permanent red within a month
or two of the next burst.

That is the same wall the seed exists to avoid, arriving later. It is what forced the
design change in section 2a.

### 1e. `--diff-filter=D` history

Recorded for completeness: the plan wanted prior consolidations as evidence of what this
repo has already found worth merging. Deletions in these families are rare enough across
full history that they do not constitute a usable signal, and no decision here rests on
them.

---

## 2. What the measurement changed in the shipped design

### 2a. An accepted-divergence exit, because the gate had none

The judged rule has three answers — `yes`, `already`, and `no` with a named DIVERGENCE —
because `run_gate()` really is duplicated 23 times across three incompatible return
contracts and extracting it verbatim would be wrong. **The CI gate had only two**:
consolidate, or stay red forever. Its single exit was re-running `--seed`, which absorbs
every new shape at once and leaves no record — so the only way past one legitimate
divergence was a command that silently suppresses the entire gate.

Fixed in `scripts/check-shape-duplication.ts`:

- `accepted: { "<hash>": "BLOCKER: <reason>" }` in the seed file, each reason validated by
  the SAME `validateBlockerQuality` every other allowlist uses
  (`scripts/lib/blocker-validator.ts`) — 30-char minimum plus the banned-phrase list.
  Writing a second reason-checker here would have been the exact duplication this gate
  exists to catch.
- `--seed` now REFUSES over an existing seed without `--force`, and says why.
- `shapes` deliberately carries no reasons: it is one measurement taken at install, the
  same shape as `wl_reggate.py:130`. `accepted` is per-entry judgement, and judgement is
  what needs a reason.

Three controls cover it, and each was planted to prove it bites.

### 2b. `wl_shapedup` got its own model call

The plan ruled "ride the call, trim SWEEP_PROMPT", estimating ~2,300 characters freed. The
trim landed (`eb34b3a47`) and freed **62**. The five worked examples were ~700 characters
in total; the estimate was out by a factor of 37. A fix stop already carries ~17,700
characters of rubric across three calibrated sections, so a fourth object would have been
unoffset. The plan's own fallback — its own `claude -p` — is what shipped, on the
measurement rather than on preference.

It earns the call by being rare: a MECHANICAL counter gates it, and a corpus signature
(mtime+size over the four families) means an unchanged tree costs a stat sweep instead of
the counter's measured 1.10s.

---

## 3. Claims that were wrong about real code

Recorded because a plan's claim about code nobody has read is a hypothesis, and each of
these was load-bearing enough to act on.

1. **`gate-test:claude-hooks` (1,852 offline cases) does not exist.** No such npm script.
   The hook suite is `check:ci-hook-worklist-suite` -> `.claude/hooks/stop/test-worklist-v5.sh`.
2. **`git ls-tree` does not glob.** `git ls-tree -r --name-only HEAD -- 'scripts/check-*.ts'`
   returns **0** where `git ls-files` returns 103, and `:(glob)` magic is rejected outright
   by that command. A replay that trusted it would have reported a clean history having
   scanned nothing — a silent zero, the worst shape a measurement can have.
3. **The counter's `file:line` was not a file line.** `normalise()` strips comments and
   drops the blanked lines, so position N in its output is not line N of the file. A
   finding in `test-watchdog-log-capture.sh` reported `:17`; the code sits at line 46, and
   `:17` is a comment. The coordinate is the actionable half of a duplication finding, and
   it was wrong in every finding the gate had ever emitted. It also made the output LOOK
   like duplicated comment blocks, contradicting the gate's own stated exclusion. Fixed in
   `5607b136d`; found only by building a calibration fixture from the counter's output
   instead of from a survey table.
4. **Importing the counter for its exports ran the whole gate.** `main()` was called at
   module scope while the module also exported `normalise`/`windows`/`judge`/`coalesce`
   "so the controls exercise the SAME function the tree goes through". Fixed with an
   entry-point guard. Swept: 23 other `scripts/check-*.ts` both export and call `main()`
   bare, and NONE of them is imported anywhere (the apparent hits in `ci-runner/manifest.ts`
   are script-name strings, not imports), so this is the only member of the class where
   the defect is live rather than latent.

---

## 4. The calibration is NOT deterministic, and that qualifies the 14/14

The trim was re-calibrated against real haiku and returned **14/14** (five sweep fires,
three sweep controls silent, four brave fires, two brave controls silent).

Re-running the same fixtures against the same rubric does not reproduce it. Across the
samples taken on 2026-09-01:

| fixture | rule | sample A | sample B | sample C |
|---|---|---|---|---|
| `CONTROL: searched, and it is the only instance` | sweep | OK | **MISS** (fired) | OK |
| `MEASURED: leave it on its branch` | brave | OK | — | **MISS** (silent) |
| `CONTROL: the findings report is ten distinct shapes` | shapedup | **MISS** | OK (alone) | **MISS** |

Five distinct fixtures missed at least once; none missed consistently. A full 20-fixture
sample scored **17/20** where the first scored 14/14 on its 14.

**So "14/14" is one draw, not a property**, and it spans three different rules — this is
the harness's variance, not one rubric's weakness. The trim stands: the operator ruled on
it as a rubric-quality change, and the fixtures that miss are controls the rules over-fire
on rather than defects they now miss. But no claim of the form "calibrated at N/N" may omit
how many samples it rests on, and a single clean run is not evidence that a rubric change
was safe.

**Consequence: `SHAPE_PROMPT` was deliberately NOT added to
`.ci/config/rubric-calibration.json`.** That manifest exists to prove a calibrated rubric
has not changed since it was calibrated, and on this evidence `SHAPE_PROMPT` has not been
calibrated to a standard the entry would honestly assert. Adding it would record a
calibration that did not happen — the exact shape of a green that means nothing.

### 4a. A negative fixture that pointed at real duplication

The first `SHAPE_CASES` control asserted `want=silent` for "the findings report is ten
distinct shapes", citing `check-dead-css.ts:187`, `check-ssr-locale.ts:62` and
`check-svg-theme-reach.ts:60`. The model answered `consolidatable: yes` and was **right**:
those three lines are a byte-identical `check` closure, not report prose. The fixture was
wrong, not the rubric.

A negative fixture aimed at genuine duplication does not test a rubric; it tests whether
the rubric will agree with a mistake. Re-pointed at the actual bespoke report lines
(`check-dead-css.ts:353`, `check-landmarks.ts:130`, `check-ssr-locale.ts:121`), it passes.

---

## 5. What is NOT done

- **The 219-span standing backlog** (plan step 5) is seeded silent and undrained. The plan
  budgeted ~9 spans from a survey of the nine largest; the real number measured 219 spans
  (336 raw windows before coalescing), and its three headline defects turned out to be
  one, already fixed. It needs re-scoping before it is worth starting, not execution
  against the plan's estimate.
