# PLAN: mutrun, a two-direction mutation runner for expensive suites
Status: done
Owner: 99ccf057
Updated: 2026-08-10

**2026-08-18: DONE. The deliverable SHIPPED, and my first note here was wrong.**
Verified on disk: `.ci/scripts/test/mutate-check.sh` (10,839 B),
`.ci/scripts/quality/check-mutate-check.sh` (4,705 B), and the id
`check:ci-mutate-check` registered at `package.json:26`. §0 below already said
this; the correction is recorded rather than quietly overwritten.

**The mistake, because it is the more useful half.** Earlier today I annotated
this plan as STRANDED -- "the source artifact is gone, so this cannot be
executed as written" -- on the strength of one true fact: the `/tmp` throwaway
in session `99ccf057`'s scratchpad no longer exists, and `find . -name 'mutrun*'`
returns nothing. Both true, and both irrelevant: the runner was never going to
keep that name, and §0 of this very file says the implementation landed BEFORE
the document did. I read the head of the file and the missing input, and did not
read the section that answered the question. A plan that opens with "Promote the
throwaway at /tmp/..." reads like unstarted work, which is exactly why §0 exists.

The lesson worth keeping is not about `/tmp`: it is that "the input is missing"
does not imply "the output was never built". Check for the artifact before
declaring the plan un-executable.

Promote the throwaway at
`/tmp/claude-1000/-home-muhammed-monorepo-console/99ccf057-20f2-48cc-bf65-a6f698562e73/scratchpad/mutrun.sh`
into a repo instrument that makes the two-direction mutation discipline the only
thing the tool knows how to do. Belongs to the program in
`agent/PLAN-trap-enforcement.md`, whose §2.2 fourth failure shape is
"a gate, probe, or suite reports clean without having run", caught by "a CI gate
with a planted defect (control-first)". This plan mechanizes the planting for the
one suite where planting by hand is expensive enough that people cut corners.

~~Nothing here is implemented.~~ Superseded by the 2026-08-18 note above and by
§0: the runner and its meta-gate SHIPPED. This line is struck rather than
deleted because it is the sentence that made two readers, including me, call
this plan unstarted.

---

## 0. What actually shipped, and how it differs from this plan

**Read this first: the implementation landed before this document did, and they are not
identical.** Two plans were written for the same problem. A planning agent produced the
long design below; while it was working, the session wrote a shorter plan and implemented
against it, and the agent's file then overwrote the shorter one. Only the code survived
that collision, so this section reconciles the two rather than pretending the design below
was followed.

Shipped, and verified against the live suite:

- `.ci/scripts/test/mutate-check.sh` -- takes `--file`, `--from`, `--to` and one or more
  `--expect-red <case-id>`, runs the suite twice, and exits 0 only when the mutant is RED
  on every named case and the baseline is GREEN.
- `.ci/scripts/quality/check-mutate-check.sh`, wired as `check:ci-mutate-check` in
  `package.json`, `scripts/ci-runner/manifest.ts` and the `quality-static` job. It drives
  all four verdicts against a miniature fixture in about 0.3s.

Where it diverges from the design below: the arms run **sequentially**, not concurrently
(§6.2), and there is **no suite registry** (§7). Both are optimisations for a tool whose
current cost is already acceptable, and neither changes the verdict semantics.

### Gate or tool?

The sections below argue this at length; the short form, since two shipped scripts cite
this heading:

It is a **developer tool, not a per-case CI gate**. Gating "every new test case must have a
proven mutation" is not implementable: the mapping from a case to the mutation that should
kill it exists only in the author's head, and running one mutation per case would mean N
times two full-suite passes. What IS gated is the instrument itself, so it cannot rot into
something that always says OK.

The honest limit, stated plainly: **nothing forces the tool's use.** It lowers the cost of
doing the right thing rather than making the wrong thing impossible, which is weaker than
every other instrument in this program.

### Two corrections this plan made to the implementation

Both were found by the planning agent and both were verified before acting:

1. **A flat sandbox copy breaks repo-root arithmetic.** The first implementation copied the
   hooks directory to a bare temp dir, which reddened case 191 (it asserts the anchor is the
   hook file's own repo) and was tolerated with a named allowlist. The sandbox now mirrors
   the repo-relative path under a real `.git` marker; measured after the fix, it runs
   669 passed / 0 failed with case 191 green, and the allowlist is deleted rather than
   documented.
2. **The same broken-filter class recurred twice in the throwaway.** The failures filter
   `^FAIL` was fixed to `^ *FAIL`, and that felt like handling the class. The summary
   filter `^(passed|failed)=` stayed broken, because the suite's totals line is indented
   too. Every totals read came back empty and was worked around rather than fixed.

## 1. What happened, and what the throwaway actually proved

Recorded in `docs/agent-reference/TRAPS.md:278-308`. A session added two cases to
`.claude/hooks/stop/test-worklist-v5.sh`, mutated the guard those cases covered,
and watched both go red. The cases were also red on the untouched tree, so the
red proved nothing: a case that can never pass goes red under every mutation,
including a mutation that changes nothing. The cause was `set -uo pipefail`
(`test-worklist-v5.sh:5`, verified today) plus an assertion of the form
`refusing-command | grep -q needle`. The refusal exits 2 by design and under
`pipefail` the pipeline carries that exit rather than grep's, so the `if` was
false while grep matched.

Only a baseline pass separates that from a real detection. Nothing in the
session's tooling made the baseline mandatory, so it was an afterthought.

**Three properties of the throwaway worth keeping.**

1. **The mutation lands in a copy.** `mutrun.sh` copies `.claude/hooks/stop` into
   the scratchpad and mutates there. Its own header explains why: an earlier
   in-tree mutation was killed by the 2-minute tool timeout before its restore
   line and left the guard neutered in the working tree
   (`docs/agent-reference/TRAPS.md:241-276`).
2. **The mutation asserts that it applied.** `assert s2 != s, "MUTATION DID NOT
   APPLY"`. A silent no-op mutation is itself a check that cannot fire.
3. **Both passes live in one script**, so the baseline is not a separate thing
   somebody has to remember.

**One defect worth fixing, verified rather than assumed.** Both of its summary
lines are `grep -E '^(passed|failed)=' "$log"`. The suite prints its summary
indented: `echo "  passed=$PASS failed=$FAIL"`
(`.claude/hooks/stop/test-worklist-v5.sh:9638`, and `pass()`/`fail()` at
`:398-405` emit `  PASS: ` and `  FAIL: ` with the same two-space indent). Run
against a real green log from today, `grep -cE '^(passed|failed)='` returns **0**
and `grep -cE '^ *passed='` returns **1**. So the runner printed an empty summary
section under every run it ever made, mutant and baseline alike. A reporting
filter that cannot match reads exactly like good news.

One correction to the brief on this point: the failures filter was already
written `grep -E '^ *FAIL'`, which does match the suite's indented `  FAIL:`
lines. The filter that could not match was the summary one. The class is the
same and the fix below covers both.

**The demand is live, and hand-editing is how it degrades.** While this plan was
being written, another session in this checkout re-pointed the same scratchpad
script at a different mutation (`wl_judge.py`, case 207). The `echo` banners
still read `163y must FAIL` while the greps look for `207`. That is not
carelessness, it is what a positional script with four hard-coded values does on
its second use. Parameters and a verdict are the fix.

---

## 2. Design principle: hold everything fixed except the mutation

A mutation run is a controlled experiment with exactly one independent variable.
Every arm must differ from every other arm in the mutation and in nothing else.

The throwaway breaks this in one place: pass 1 runs the sandbox copy, pass 2 runs
`$SRC`, the live tree. Those two arms differ in two variables, the mutation and
the location. Its green pass 2 therefore proves "the live tree is green", not
"this fixture is sound when the defect is absent", and those come apart exactly
when the sandbox is unfaithful, which is the failure the baseline is there to
catch.

**Both arms are sandboxes.** The baseline arm is a pristine copy, the mutant arm
is the same copy with the mutation applied. Sandbox fidelity becomes a separate,
per-suite question answered once (§7), not a variable smuggled into every run.

Two secondary consequences, both of which show up in the assertions:

- The two arms must produce the **same number of cases**. A mutation that changes
  the case count changed the shape of the run, not the behavior of one guard.
- Every selector naming an expected-red case must **match a real PASS line in the
  baseline arm**. A selector that names nothing is the throwaway's broken filter
  in a new costume.

---

## 3. What the tool is

`mutrun` runs one mutation experiment and prints one verdict. It has no mode in
which it runs a suite once.

### 3.1 Invocation

```
scripts/dev/mutrun.py \
    --suite worklist-v5 \
    --target .claude/hooks/stop/worklist.py \
    --old-file /path/to/old.txt   |  --old '<exact string>' \
    --new-file /path/to/new.txt   |  --new '<exact string>' \
    --expect-red 163y \
    [--expect-red <selector> ...] \
    [--allow-collateral <selector> ...] \
    [--baseline-from <run-dir>] \
    [--run-dir <dir>] \
    [--json]
```

`--suite` names a registry entry (§7), which supplies the sandbox roots, the
suite command, the output grammar and the pass floor. `--target` is repo-relative
and must resolve inside one of that entry's sandbox roots.

`--old`/`--new` accept a literal string or a file. The file forms exist because
the interesting mutations are multi-line and indentation-sensitive, and passing
those through a shell argument is how a mutation silently becomes a different
mutation. `--old-file` is the recommended form for anything longer than one line.

`--expect-red` takes a **selector**, a plain substring matched against the
suite's own case text. Not a regex: a regex in a shell argument is a second
quoting surface and the tool has no use for the extra power. Repeatable.

### 3.2 What it refuses, before any suite runs

Every one of these exits non-zero with the word REFUSED and runs nothing, so a
misuse costs seconds rather than ten minutes.

| # | Refusal | Why |
|---|---|---|
| R1 | `--target` is not inside a sandbox root of `--suite` | The mutation would land outside the copy, that is, in the live tree |
| R2 | `--old` occurs 0 times in the target | The mutation is a no-op. This is the throwaway's `assert s2 != s`, promoted to a precondition |
| R3 | `--old` occurs more than once | Ambiguous. The tool would mutate an arbitrary one of them and report the other's line in the verdict |
| R4 | `--old` equals `--new` | A no-op that survives R2 |
| R5 | No `--expect-red` given | A mutation with no predicted victim proves nothing, whatever the suite does |
| R6 | The target is not a tracked or untracked-but-not-ignored repo file | Guards a typo'd path that would otherwise create a file and mutate nothing |

### 3.3 What it refuses after mutating, still before the suite

| # | Refusal | Why |
|---|---|---|
| R7 | Re-reading the mutated file from disk does not show `--new` at the expected offset, or still shows `--old` | Never trust a writer's own report. `docs/agent-reference/TRAPS.md:273-276` is explicit: verify the file by reading it back, never from the command's output |
| R8 | The mutated file fails a syntax check (`python3 -m py_compile` for `.py`, `bash -n` for `.sh`, skipped with a recorded note for anything else) | A red produced by a `SyntaxError` is not the guard firing. It is the most convincing false positive available and it costs a full suite run to discover |

R8 is the one addition the throwaway had in some form: the TRAPS transcript of
the original in-tree run shows it printed `syntax ok` before `mutated: guard
neutered`. It is mandatory here and its result is recorded in the verdict.

---

## 4. The sandbox

### 4.1 Structure

For each arm the tool creates `<run-dir>/<arm>/` and copies every sandbox root
of the suite entry into it **at its repo-relative path**, so
`.claude/hooks/stop/worklist.py` lands at
`<run-dir>/baseline/.claude/hooks/stop/worklist.py`.

The path mirroring is not tidiness. `wl_core.py` computes the repo root by
walking up a fixed number of parents from its own location
(`_HOOK_ROOT_DEPTH = 3`, "`<repo>/.claude/hooks/stop/wl_core.py` -> parents[3] is
`<repo>`", verified today). Flattening the copy, which is what the throwaway does
with `cp -a "$SRC/." "$SB/"`, points that arithmetic at whatever happens to sit
three levels above the scratchpad.

Two more details in the same spirit:

- **A `.git` marker file is written at the arm root.** `wl_core.project_root`
  (`:309-321`) walks ancestors for `.git` and tests existence rather than
  `is_dir()`, because this repo uses worktrees where `.git` is a file. Without
  the marker, an arm resolves its project root differently from the live tree.
  A file is the faithful shape.
- **Both arms are copied from one snapshot, before either suite starts.** The
  copy is made once into a staging directory, digested, then cloned into the two
  arms, so the arms cannot differ by an edit that landed between them. This is
  not theoretical in a shared checkout: §7.3 records the suite gaining six cases
  during the writing of this plan. The digest of that snapshot is what
  `--baseline-from` compares against on reuse.
- **`__pycache__` and any `.git` directory are excluded from the copy.** Stale
  bytecode is invalidated by the mutation's mtime change so this is insurance
  rather than a fix, but a mutation experiment should not have an "unless the
  cache" clause in it.

### 4.2 The live tree is never written, and that is the whole cleanup story

The tool has **no restore step**, therefore no restore step can be skipped. This
is stronger than a careful trap, and the difference is measurable. Probed today
in the scratchpad:

- A bash script planting a file with `trap 'rm -f "$probe"' EXIT`, killed with
  `SIGTERM` while waiting on a child: exit 143, **trap ran, tree clean**. Killed
  with `SIGKILL`: **stray survives**.
- A Python script planting a file inside `try: ... finally: unlink`, killed with
  `SIGTERM`: exit -15, **`finally` did not run, stray survives**.

So cleanup-based designs have a signal-dependent correctness, and the Python one
fails on the very signal the 2-minute tool timeout sends (`Exit code 143` in
`docs/agent-reference/TRAPS.md:254-255`). A design whose correctness depends on which
signal arrives is not a design. Not touching the live tree removes the question.

The run directory defaults under the session scratchpad. A stranded run directory
is inert: it holds copies, logs, and possibly no verdict, and it never holds
anything the repo reads.

---

## 5. The verdict

### 5.1 Parsing, and the parser that cannot lie quietly

Each arm's stdout is parsed with the grammar declared by the suite entry (§7):
a summary pattern yielding `passed` and `failed`, plus a per-case pass pattern
and a per-case fail pattern. For `worklist-v5` those are `^  passed=(\d+)
failed=(\d+)$`, `^  PASS: (.*)$` and `^  FAIL: (.*)$`.

Then, before any verdict, the parser is cross-checked against the suite's own
counters. Each of these is a hard INCONCLUSIVE, never a warning:

- **C1** The summary pattern matched exactly once. Zero matches is the
  throwaway's defect. More than one match means the grammar is matching
  something else too.
- **C2** `len(fail_lines) == failed`. If the counter says 12 and the filter found
  0, the filter cannot see what the counter counts.
- **C3** `len(pass_lines) == passed`. The same check in the direction that is
  easy to forget, and the one that catches a grammar which matches a superset.
- **C4** `passed + failed >= floor` for that suite. A grammar that half-works
  produces a plausible small number, which is exactly the case the floor is
  chosen to catch (`worklist-v5` floor: 500, against 663 to 669 measured today;
  see §7.3 for why that is a range and not a number).

C1 to C4 are the mechanical form of "a reporting filter that cannot match reads
exactly like good news". They are also, deliberately, checks about the tool
itself rather than about the code under test, and they run on every arm of every
invocation.

### 5.2 The direction assertions

Let `B` be the baseline arm and `M` the mutant arm.

| Assertion | Requirement | Verdict when it fails |
|---|---|---|
| A1 | `B.failed == 0` and `B.exit == 0` | `INCONCLUSIVE: broken fixture`. This is the 2026-08-09 incident. The message says the fixture is broken, and names the baseline-red cases, rather than saying anything about the mutation |
| A2 | Every `--expect-red` selector matches at least one **PASS** line in `B` | `REFUSED: selector names no case`. A selector matching nothing green cannot be shown to go red |
| A3 | `M.exit != 0` and `M.failed >= 1` | `NOT PROVEN: the mutation changed nothing observable`. The guard has no test, or the mutation missed it |
| A4 | Every `--expect-red` selector matches at least one **FAIL** line in `M` | `NOT PROVEN: <selector> stayed green under its own defect` |
| A5 | `M.passed + M.failed == B.passed + B.failed` | `INCONCLUSIVE: the case count moved`. The mutation aborted the run or changed its shape, so the red is not localized |
| A6 | Every FAIL line in `M` matches an `--expect-red` or an `--allow-collateral` selector | `INCONCLUSIVE: collateral damage`, listing the unexpected reds. An over-broad mutation reds cases for reasons unrelated to the guard |

All six hold: `PROVEN`. The verdict line names the suite, the target, the
selectors, and the two arms' counters, on one line, first thing in the output.

A5 and A6 are the two assertions the throwaway lacked. It printed the collateral
list for a human to eyeball, which works exactly as well as eyeballing usually
works when the section above it is empty.

### 5.3 Exit codes

`0` PROVEN. `1` NOT PROVEN. `2` INCONCLUSIVE. `3` REFUSED. Distinct because a
caller polling in the background needs to know whether to fix the code, fix the
fixture, or fix the invocation, and because "not proven" and "the harness is
broken" are the two things this whole plan exists to stop conflating.

---

## 6. Background-friendliness

### 6.1 The measurement

`test-worklist-v5.sh` on this machine, green, timed today:
**`real 4m32.695s`**, 663 passed, 0 failed. That is over four minutes, not the
two the brief assumed, and it is more than double the 120000 ms default Bash
tool timeout. Two arms in sequence would be about nine minutes, which fits inside
the 600000 ms maximum only by leaving no margin.

So: every invocation of this tool on this suite is a background invocation.

### 6.2 Concurrent arms

The arms are independent by construction (separate copies, separate run
subdirectories), so the only question is whether the suite is safe against
itself. Evidence, all verified today:

- `test-worklist-v5.sh:36` creates its own fixture root, `BASE="$(mktemp -d)/hookfix"`,
  with `trap 'rm -rf "$(dirname "$BASE")"' EXIT` at `:37`. Every invocation in
  the suite pins `TMPDIR`, `CLAUDE_PROJECT_DIR` and, where it matters,
  `WORKLIST_TASKS_DIR` underneath it. Two runs therefore do not share disk
  fixtures.
- Three `HOME`-rooted paths exist in the hook and none of them collides in
  practice: `wl_core.tasks_dir` (`:581-585`) falls back to `~/.claude/tasks`, and
  `~/.claude/tasks/session-deadbeef` does not exist on this machine after a full
  run; `wl_report` (`:121-125`) and `wl_core.projects_dir` (`:342-349`) key off
  the project-root slug, which is the per-run `mktemp` path, so two runs land in
  different directories by construction.
- **Direct proof**: two pristine sandbox arms were run concurrently on a 20-core
  machine. Result recorded in §7.3.

`--parallel` is therefore the default **only** for suites whose registry entry
declares `self_concurrent: true`, and that flag is a proven fact rather than an
assumption (§7.2).

### 6.3 The interaction with `.claude/hooks/test-hooks.sh`

The brief asks whether two suite runs race because `test-hooks.sh` nests this
suite. Verified: `test-hooks.sh:421` sets
`STOP_SUITE="$DIR/stop/test-worklist-v5.sh"` and `:424` runs it as a child,
counting `grep -c "^  PASS:"` at `:425`. The nesting is real, but the nested run
gets its own `mktemp` `BASE` like any other, so **the fixtures are not shared**
and a `mutrun` arm running beside a `test-hooks.sh` run is the same case as two
plain suite runs.

One consequence for `mutrun`'s own registry: the `test-hooks` suite entry, if one
is ever added, must record that its case count *includes* the nested suite's
cases, or a mutation aimed at a `pre-bash` hook would trip A5 for reasons that
have nothing to do with the mutation.

### 6.4 The polling contract

- The run directory is created first and holds `arm/*.log` and `arm/*.err` from
  the first second, so a caller can tail progress.
- `verdict.json` is written **last**, to a temporary name in the same directory
  and then renamed. A partial verdict file is therefore impossible.
- **A missing `verdict.json` means running or killed. It never means passing.**
  Any wrapper that reads the verdict must treat absence as a non-answer, which is
  why the tool writes it rather than relying on its exit code alone: a background
  process's exit code is not always in front of the reader, and a killed run has
  one.
- One `VERDICT: ...` line on stdout, first line of the summary block, so the
  scrollback answer and the file answer are the same answer.

### 6.5 There is no `--skip-baseline`

Deliberately. Any flag that exists is used under time pressure, and this tool
exists because the baseline was skipped once. The pressure that would motivate
the flag is removed instead: concurrent arms make the two-direction run cost the
same wall time as the one-direction run it replaces.

The one legitimate reuse case, re-running a mutation minutes after a baseline,
is served by `--baseline-from <run-dir>`, which **verifies** rather than trusts:
it recomputes the digest of every file in the recorded baseline arm and refuses
if any differs from what the new arm would contain. That is reuse with proof.
The verdict records `baseline: reused from <dir>` so a reader can see it.

---

## 7. The suite registry

One entry per suite, in `scripts/dev/mutrun-suites.json` next to the tool.

```json
{
  "worklist-v5": {
    "sandbox_roots": [".claude/hooks/stop"],
    "command": [".claude/hooks/stop/test-worklist-v5.sh"],
    "summary_re": "^  passed=(?P<passed>\\d+) failed=(?P<failed>\\d+)$",
    "pass_re": "^  PASS: (?P<case>.*)$",
    "fail_re": "^  FAIL: (?P<case>.*)$",
    "floor": 500,
    "self_concurrent": true,
    "sandbox_faithful": "2026-08-10: 669/0 in two concurrent arm copies, see PLAN §7.3",
    "typical_seconds": 275
  }
}
```

Every field is a fact that costs a suite run to learn, which is the argument for
recording it rather than rediscovering it per invocation.

### 7.1 Why a per-suite grammar and not one universal parser

The two harnesses in this repo do not agree, and the repo already knows it:
`test-worklist-v5.sh` speaks `  passed=N failed=M` and `  PASS: `, while
`.claude/hooks/test-hooks.sh` speaks `PASS=n FAIL=m` and `ok   [0] `, and
`.ci/scripts/test/gates/test-claude-hooks.sh:24-38` exists precisely to translate
the second into the first. Gate tests under `.ci/scripts/test/gates/` speak a
third dialect, matched by `PASS_RE=$'^(\033\\[0;32m)?PASS:'` at
`.ci/scripts/test/run-all.sh:207`, whose comment records that this pattern was
once written `\x1b` and therefore matched nothing while the counter stayed right.
A universal parser here would be a guess. A declared grammar plus C1 to C4 makes
a wrong guess loud.

### 7.2 How `self_concurrent` is proven

`scripts/dev/mutrun.py --prove-suite <name>` runs two pristine arms concurrently
and requires both green with identical counters, then writes the result and the
date into the entry. It is the same code path as a normal run with the mutation
omitted, so the thing being proven is the thing that will be used.

`sandbox_faithful` is proven in the same command by comparing an arm's counters
against a live-tree run. This is the only place `mutrun` ever executes the live
tree, it is opt-in, it is read-only, and it happens once per suite rather than
once per mutation.

### 7.3 The measurement, taken today

Two pristine `worklist-v5` arms, copied with the §4.1 structure including the
`.git` marker, run concurrently on a 20-core machine:

```
A exit=0   passed=669 failed=0   real 4m14.597s
B exit=0   passed=669 failed=0   real 4m14.597s
```

Identical counters, identical wall time, and the wall time of two concurrent arms
is *lower* than the single live-tree run measured earlier in the same session
(4m32s). So `self_concurrent: true` is a measurement, the sandbox is faithful,
and concurrency costs nothing here.

**The number that is not 663 is the most useful result in this section.** The
live-tree run earlier in the session reported `663 passed`; these copies, taken
about forty minutes later, report `669`. Nothing regressed: another session in
this shared checkout added six cases in between, and
`test-worklist-v5.sh` grew from 9519 to 9639 lines while this plan was being
written. That is precisely why the baseline arm must be a **copy taken in the
same instant as the mutant arm** rather than a live-tree run at a different
moment. The throwaway's live-tree pass 2 would, in this window, have been
comparing two different suites and calling the difference a mutation effect. A5
in §5.2 catches that shape, and §4.1's snapshot-both-arms rule prevents it.

---

## 8. Where it lives, and its relationship to `npm run ci`

### 8.1 It is a developer tool, not a gate

Measured, not estimated: one mutation row costs two 4m32s passes. Concurrent
arms bring the wall time to roughly one pass, but the CPU cost is unchanged and
a CI runner is not a 20-core desktop. `.ci/scripts/test/run-all.sh:13-14` records
that the gate-test battery already took about 18 minutes of the Security job's
20-minute budget when it ran serially. A single mutation row is a fifth of that
budget, and mutation rows are worth having per guard, so a useful set is five to
twenty rows. That is 45 minutes to three hours, for a check whose value is
highest at the moment a case is written and lowest on the thousandth unrelated
commit.

The counter-argument deserves a hearing, because the repo does gate mutation
elsewhere: `.ci/scripts/quality/check_lint_rule_liveness.py` plants a violation
per lint rule on every CI run, and `.ci/scripts/quality/check-python-lint.sh`
plants an `F821` before it judges a single real file. Both are gates and both are
right to be. The distinguishing variable is not "is mutation gate-worthy" but
"what does one planted defect cost": those plant against a single-file `eslint`
or `ruff` invocation measured in seconds. This one plants against a 663-case
suite. Same discipline, two orders of magnitude apart in price, and the price is
what decides where it runs.

### 8.2 What *is* gated

**The tool's own controls.** `.ci/scripts/test/gates/test-mutrun.sh`, running
`mutrun` against a fixture suite of about twenty lines that finishes in
milliseconds. That gate proves the runner can tell PROVEN from NOT PROVEN from
INCONCLUSIVE, which is the part that rots silently. It never runs
`test-worklist-v5.sh`.

Registration is not optional once the file exists:
`scripts/check-ci-parity.ts:530-542` fails when a `.ci/scripts/test/gates/test-*.sh`
on disk has no `qualityGateTest` manifest entry, and
`.ci/scripts/quality/check-gate-id-convention.sh` requires the id
`gate-test:mutrun` rather than a `check:ci-*` alias. So the manifest gains:

```ts
{ id: 'gate-test:mutrun', run: '.ci/scripts/test/gates/test-mutrun.sh', gate: true,
  qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-mutrun.sh'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-security', step: 'Quality-gate unit tests' } },
```

matching the shape of `gate-test:claude-hooks` at `scripts/ci-runner/manifest.ts:375`.

### 8.3 The path, and the npm key that must not start with `check:ci-`

**`scripts/dev/mutrun.py`**, with `"dev:mutation-run": "scripts/dev/mutrun.py"`
in `package.json`.

The prefix is load-bearing. `scripts/check-ci-parity.ts:398-406` (rule R1) fails
any `check:ci-*` key in `package.json` that is not a manifest entry, and every
manifest entry with `gate: true` is scheduled by `npm run ci`. Naming this
`check:ci-mutation-run` would therefore force a four-and-a-half-minute suite,
twice, into every local `npm run ci`. `dev:` sidesteps that by saying what the
thing is.

Two related constraints checked so the choice is not accidental:

- `GATE_SHAPED` at `scripts/check-ci-parity.ts:68-69` matches only
  `.ci/scripts/{quality,security}/check-*.sh` and `.ci/scripts/test/test-*.sh`.
  `scripts/dev/mutrun.py` is outside it, so rule R2 does not pull the tool into
  the manifest either.
- `scripts/check-dead-bash.ts:9-11` reports a `.sh` whose basename no other
  tracked file mentions. Python is outside that gate entirely, which is a reason
  to give the tool a real caller rather than to rely on the gate's blindness: the
  npm key plus the gate test plus this plan are three, and `--prove-suite` is
  documented in `docs/agent-reference/TRAPS.md`'s mutation entry as the command to reach
  for.

Python rather than shell for a positive reason too: `check-python-lint.sh` lints
every tracked and untracked-but-not-ignored `.py`, so the tool is covered by
`ruff` on the day it lands with no registration step. Exact-string replacement,
occurrence counting, digesting and atomic JSON output are all one-liners there
and are all quoting hazards in bash, and the failure mode of a quoting hazard in
this specific tool is a mutation that is not the mutation the caller asked for.

### 8.4 W2, optional: a static applicability gate over recorded rows

`mutrun` can append every PROVEN row to `.ci/mutation-rows.jsonl`: suite, target,
the exact `--old` string, the selectors, the date, and the target's blob hash at
proof time. A cheap gate, milliseconds, then asserts the **static** properties:

- every recorded `old` string still occurs **exactly once** in its target;
- every recorded selector still matches a case label present in the suite source;
- the row count is above a floor, so an emptied file reds rather than passing.

Be precise about what this does and does not prove. It proves the recorded
mutation is still **applicable and still points at a case that exists**, which is
the rot that actually happens: a guard line gets reworded and the recorded proof
quietly becomes fiction. It does **not** prove the mutation still makes that case
red. The gate must say so in its own output, because a gate that overstates its
reach is the corpus's own trap.

Blob drift is **reported, not failed**: `worklist.py` changes weekly, and a gate
that reds on every edit to it would be ignored within a fortnight, which is the
precision budget in `PLAN-trap-enforcement.md:88-95`. `mutrun --list-stale`
prints the drifted rows and the exact command to re-prove each.

W2 is separable. W1 stands alone and is the whole ask.

---

## 9. Control-first test plan

Every case plants a defect and asserts the FIRE, then re-runs clean and asserts
SILENCE. House style from `PLAN-trap-enforcement.md:543-546`.

### 9.1 The fixture suite

`.ci/scripts/test/gates/fixtures/mutrun/` holds a miniature repo: a `guard.py`
with one `if` line, a `fixture-suite.sh` of about twenty lines that emits the
`worklist-v5` grammar (`  PASS: `, `  FAIL: `, `  passed=N failed=M`), and a
registry entry pointing at it. It finishes in well under a second, so the gate
can run every case below many times over.

The fixture must emit the **real** grammar rather than a simplified one. A
fixture speaking a grammar no real suite speaks would let a parser bug pass here
and fail in the only place it matters.

### 9.2 The cases

| # | Planted defect | Must produce | Must not |
|---|---|---|---|
| 1 | Nothing. Correct mutation of a real guard | `PROVEN`, exit 0 | any INCONCLUSIVE |
| 2 | The fixture's target case is rewritten so it is red with and without the defect (the 2026-08-09 shape, a `cmd \| grep -q` under `pipefail`) | `INCONCLUSIVE: broken fixture`, exit 2, naming the case | `PROVEN`. **This is the control the whole tool exists for** |
| 3 | `--old` that appears nowhere | `REFUSED` R2, exit 3, no suite run | any suite process started |
| 4 | `--old` that appears twice | `REFUSED` R3, exit 3 | a silent choice of one occurrence |
| 5 | `--new` that is a syntax error | `REFUSED` R8, exit 3, naming the compile error | a red verdict from a `SyntaxError` |
| 6 | A mutation the suite does not cover | `NOT PROVEN` A3, exit 1 | `PROVEN` |
| 7 | A correct mutation with a selector naming no case | `REFUSED` A2, exit 3 | `PROVEN`, which is the throwaway's exact failure mode |
| 8 | A mutation that reds the target case **and** three others | `INCONCLUSIVE: collateral`, listing the three | `PROVEN` |
| 8b | The same, with `--allow-collateral` naming all three | `PROVEN` | a refusal, so the escape hatch is proven usable |
| 9 | A mutation that makes the suite abort early, so the case count drops | `INCONCLUSIVE` A5 | `PROVEN` |
| 10 | The registry grammar's `summary_re` altered to a pattern that matches nothing (the throwaway's real defect) | `INCONCLUSIVE` C1, exit 2, saying the summary could not be parsed | an empty summary section and any verdict |
| 11 | `fail_re` altered so it matches nothing, on a run with `failed=3` | `INCONCLUSIVE` C2, quoting both numbers | `NOT PROVEN`, which would blame the code for a tool bug |
| 12 | `pass_re` altered to match every line | `INCONCLUSIVE` C3 | `PROVEN` |
| 13 | The fixture suite truncated so it emits four cases | `INCONCLUSIVE` C4 against its floor | `PROVEN` |
| 14 | A `--target` outside the sandbox roots, pointing at a real repo file | `REFUSED` R1, and the real file's digest is **unchanged** after the run | any write outside the run directory |
| 15 | `--baseline-from` a run whose sandbox differs by one byte | refusal naming the differing file | silent reuse |
| 16 | `SIGKILL` to a run mid-suite | the live tree's digests are unchanged and no `verdict.json` exists | a `verdict.json` that reads as a pass |

Case 14 and case 16 are the two that make the safety claims of §4.2 testable
rather than architectural. Case 16 is worth writing even though it is obviously
true by construction, because "obviously true by construction" is what the
in-tree mutation was before it stranded a neutered guard.

### 9.3 Anti-vacuity for this gate itself

`.ci/scripts/test/run-all.sh:265-275` fails any gate test that exits 0 without a
single `PASS:` line, so `test-mutrun.sh` emits one `log_pass` per case and a
final `log_pass "all tests passed"`, the shape of `test-dead-case-arms.sh`. It
must **not** end with a `passed=N failed=M` counter: that is `test-hooks.sh`'s
contract, translated by `test-claude-hooks.sh:24-38` precisely because the two
harnesses disagree, and the same correction is already recorded at
`PLAN-trap-enforcement.md:617-627`.

### 9.4 Local run commands

```bash
scripts/dev/mutrun.py --prove-suite worklist-v5          # once, background, ~5 min
bash .ci/scripts/test/gates/test-mutrun.sh
bash .ci/scripts/quality/check-python-lint.sh
npm run check:ci-gate-id-convention
bash .ci/scripts/test/gates/test-ci-parity.sh
npm run check:ci-gate-reachability-coverage
```

Read stdout and stderr separately on all of them. Note for whoever does:
`test-worklist-v5.sh` writes about 1 KB to **stderr on a fully green run**
(two `REFUSED: beefcafe has never briefed...` blocks from cases that drive a
refusal without capturing its stderr, measured today alongside `663 passed, 0
failed`). Non-empty stderr is therefore not a health signal for this suite, and
`mutrun` must not treat it as one. It records stderr per arm and reports its size
without judging it.

---

## 10. Sequencing

**W1, the runner.** `scripts/dev/mutrun.py`, `scripts/dev/mutrun-suites.json`
with the `worklist-v5` entry, the `dev:mutation-run` npm key,
`.ci/scripts/test/gates/test-mutrun.sh` with cases 1 to 16 and its fixture, the
`gate-test:mutrun` manifest entry, and the matching workflow step name required
by `check:ci-parity`. Ends with `--prove-suite worklist-v5` run for real and its
output pasted into the registry entry.

**W1.5, retire the throwaway.** Re-run the two mutations the scratchpad script
has been used for (`worklist.py`'s `--brief` id guard, and `wl_judge.py`'s order
filter for case 207) through `mutrun`, and confirm both come back PROVEN. Until
that happens the tool is unproven against the case it was built from. Coordinate
with whoever currently owns the second one rather than editing their scratchpad.

**W2, optional, the row ledger and its static gate.** Only after W1 has been used
a few times, so the recorded rows are real rather than invented to populate a
file.

**Corpus.** `docs/agent-reference/TRAPS.md`'s mutation entry (`:278-308`) gains a
`MECHANIZED:` line naming `scripts/dev/mutrun.py`, in the shape the killed-cleanup
entry already uses at `:243-245`. Under the registry design of
`PLAN-trap-enforcement.md:129-139` that becomes an `Enforced-By:
tool:scripts/dev/mutrun.py` trailer, with a `Residue:` line stating the honest
limit: the tool enforces the discipline for suites someone thought to register,
and an ad-hoc mutation typed into a terminal is still judgment.

---

## 11. Risk

1. **A tool that makes mutation cheap invites mutation-shaped busywork.** Twenty
   registered rows that nobody reads are twenty rows of maintenance. Mitigation:
   W2's ledger is opt-in and there is no coverage gate demanding a row per guard.
   The tool's value is at the moment a case is written, and the sequencing keeps
   it there.
2. **A wrong grammar in the registry silently reshapes every verdict.** This is
   the tool's own version of the defect it detects. Mitigation: C1 to C4 run on
   every arm of every invocation, and cases 10 to 13 prove each of them fires.
3. **`--allow-collateral` is an escape hatch and escape hatches get used.** A
   caller who allowlists every collateral selector turns A6 off. Mitigation: the
   verdict records the allowlist verbatim on the `VERDICT:` line, so a permissive
   run cannot look like a strict one in scrollback. Not a `BLOCKER:`-gated
   suppression, because it is per-invocation rather than committed, and
   `docs/agent-reference/suppressions.md` governs committed escape hatches.
4. **Sandbox fidelity is proven once and could rot.** A suite that grows a
   dependency on a file outside its sandbox roots would start failing in the
   baseline arm, which reads as `INCONCLUSIVE: broken fixture` and points at the
   fixture rather than at the root cause. Mitigation: the INCONCLUSIVE message
   for a baseline arm that is red **while the live tree is green** says so
   explicitly and names `--prove-suite` as the next command. Detecting that
   requires the live-tree comparison, which is why `--prove-suite` keeps it.
5. **Scratchpad growth.** Each run holds two full copies of the sandbox roots
   plus logs. `.claude/hooks/stop` is small, but a suite registered against a
   package directory would not be. Mitigation: the tool prints the run directory
   size at the end and deletes run directories older than a day at startup, in
   its own scratchpad root only.

---

## 12. Findings from this session that are outside the ask

Reported rather than fixed, because this session's mandate is the plan file and
nothing else. Both belong to the class this plan is about.

**12.1 `check_lint_rule_liveness.py` plants into the live tree, under a fixed
name, with a cleanup that does not survive the signal it will meet.** It writes
`packages/www/src/i18n/translations/zz-rule-liveness-probe.json` into the real
tree (`:101`, `:105-108`) and removes it in a Python `finally` (`:125`). Verified
today: a Python `finally` does **not** run under `SIGTERM`, and the planted file
survives. Its own comment says why that matters: "a stray locale file left behind
would be picked up by the locale-set gates as a real one." Two further details:
the name has no pid in it, and its manifest entry
(`scripts/ci-runner/manifest.ts:136`) declares no `mutex`, while `npm run ci`
schedules `availableParallelism() - 2` gates at once
(`scripts/ci-runner/run.ts:351`). `.ci/scripts/test/run-all.sh:14-31` documents
this exact hazard for two **other** scripts, including the collision between two
concurrent batteries and the `<pid>` suffix that fixed it. This gate is a third
instance of that class with neither mitigation.

**12.2 `test-worklist-v5.sh` writes to stderr on a green run.** 1018 bytes, two
`REFUSED: beefcafe has never briefed in this store...` blocks, alongside
`663 passed, 0 failed`. Benign in content, but it means "stderr is empty" is not
a usable health signal for this suite, and `.agent/TRAPS.md:110-116` records a
real defect that hid in this suite's stderr once already: `pass`/`fail` defined
below their first use, so three assertions wrote `pass: command not found` to
stderr and counted nothing while the suite reported `253 passed, 0 failed`.
(`PLAN-trap-enforcement.md:653-655` cites that record as `.agent/TRAPS.md:111-117`.
The file is right and the line is close; note that it is `.agent/TRAPS.md`, the
per-worktree corpus, not `docs/agent-reference/TRAPS.md`, which is the drift that plan's §9
is about. Verified today: `docs/agent-reference/TRAPS.md:111` is a different entry
entirely.) Worth capturing the
refusal's stderr in those cases so that the channel goes back to being quiet
enough for a surprise to be visible.

---

## 13. Two constraints raised after this plan was drafted

Both arrived from the lead while §1 to §12 were being written. Neither changes
the design, and the reason is that §4.1 already contains the fix for the first
one. Evidence below, then a ranking of the options and one honest open question.

### 13.1 Case 191 does NOT red in this design, measured

The report: a sandbox copy reds case 191 ("root resolution must not walk into a
repo NESTED in the repo", `test-worklist-v5.sh:8603`), because the copy sits
outside any git repo and `CLI_HOOK` (`:8657`) comes back empty.

That is true of **the throwaway's** sandbox, which does `cp -a "$SRC/." "$SB/"`:
a flat copy, no repo above it, no `.git` anywhere. It is not true of the sandbox
this plan specifies. §4.1 requires two things for an unrelated reason
(`wl_core.py`'s `parents[3]` arithmetic and `project_root`'s ancestor walk):
copy at the **repo-relative path**, and write a **`.git` marker file at the arm
root**. Both were in the draft before this constraint arrived.

Measured, in the two-arm run recorded at §7.3:

```
874:== 191. root resolution must not walk into a repo NESTED in the repo ==
875:  PASS: 191 CONTROL: the pre-fix ladder does resolve to the nested repo
876:  PASS: 191 FIRE: project_start anchors on the outer repo, not the nested one
877:  PASS: 191 FIRE: with no CLAUDE_PROJECT_DIR the anchor is the hook file's repo
878:  PASS: 191 FIRE: --path is identical from the outer repo and from inside the nested one
```

All four assertions of case 191 green, in an out-of-repo arm, `passed=669
failed=0`. So the constraint is real and the diagnosis is right; the conclusion
that the sandbox must move is not.

### 13.2 Recommendation among the four options: none of them

The right option is the one the plan already specifies, which is not in the list:
**an out-of-repo sandbox that is made repo-shaped**, mirrored path plus a `.git`
marker file. Ranking the four as asked:

| Option | Verdict |
|---|---|
| 1. Gitignored dir inside the worktree | Second best, and the fallback if a future case needs the *real* repo rather than a repo-shaped one. Cost: a mutated copy inside the tree, plus every tree-enumerating gate now has one more thing to be right about. `check-python-lint.sh` and `check-dead-bash.ts` both exclude gitignored paths, so it is survivable, but §12.1 is a live example of what a planted file inside the tree costs when a gate forgets |
| 2. A git worktree per run | Correct and expensive. `git worktree add` is also hook-blocked from the assistant's own Bash tool (`.claude/hooks/pre-bash/block-worktree-add.sh`), so a tool that needs one per run cannot be driven by an agent, which is most of its users |
| 3. Known-fails allowlist | Agreed, reject. It is an allowlist over the exact signal the mutant pass exists to produce, and `docs/agent-reference/suppressions.md` would require a `BLOCKER:` reason for a list whose real reason is "the sandbox is wrong" |
| 4. Mutate in place with guaranteed restoration | Reject. §4.2 measured the guarantee: a bash `EXIT` trap survives `SIGTERM` and dies on `SIGKILL`, a Python `finally` dies on both. There is no guarantee to be had |

### 13.3 The baseline must NOT run at the real path, and §7.3 is the evidence

The suggestion was that the tool be asymmetric: mutant in a sandbox, baseline at
the real path, because only a real-path green is meaningful.

The measurement says otherwise. The live tree reported `663 passed` and two arm
copies taken about forty minutes later reported `669`, because another session
added six cases in between (`test-worklist-v5.sh` grew 9519 to 9639 lines during
this session). A real-path baseline is a baseline **of a different suite** than
the mutant ran, and in a shared checkout that is the normal case rather than the
unlucky one.

What makes a green meaningful is not the path it ran at. It is that it differs
from the mutant arm in exactly one variable. Symmetric arms give that; asymmetric
arms give a comparison across two suites, two locations, and two moments in time.

Sandbox fidelity is the real question underneath the suggestion, and it is
answered by `--prove-suite` (§7.2), which **is** the real-path run: once per
suite, read-only, recorded in the registry with its date. That is the right
frequency for a property that changes when the suite grows a new dependency, not
when someone mutates a guard.

There is also a design dividend. The question "what stops the mutant pass from
touching the live copy" only needs answering if some pass legitimately touches
the live tree. With symmetric arms, nothing in `mutrun` ever opens a live file
for writing, so the answer is structural rather than a guard that can be wrong.

### 13.4 Module contamination, and why the same-directory snapshot is not needed here

Confirmed and important: each `reqcli`/`run` call spawns a fresh `python3` that
imports `wl_liveness`, `wl_checks` and friends **at call time**, so editing those
modules mid-run contaminates a long suite silently, early cases running old code
and later ones new. Separately, bash reads a script by byte offset as it
executes, so editing the suite file itself during a run produces a syntax error
naming an innocent line.

The whole-directory arm copy closes both, and closes them for the same reason:
the arm runs its own `.sh` and imports its own `wl_*.py`, and nothing it touches
is the file anyone is editing. The same-directory snapshot closes only the first,
which is exactly the gap reported.

So the snapshot technique is not needed **for this tool**. It is still the right
technique for a human or agent running the suite by hand without `mutrun`, and it
belongs in `docs/agent-reference/TRAPS.md` beside the editing-a-running-script entry rather
than in `mutrun`. Two notes for whoever writes it there: a `.v5-run-snapshot.sh`
inside `.claude/hooks/stop/` is a new `.sh` basename that no other tracked file
mentions, which is a `check-dead-bash.ts` orphan finding unless it is gitignored
(`scripts/check-dead-bash.ts:9-11`); and leave-it-and-overwrite beats a cleanup
step, for the §4.2 reason that cleanup steps are exactly as skippable as the
timeout is long.

### 13.5 Open question, not settled

**Which of the two §4.1 rules saves case 191: the `.git` marker, or the path
mirroring?** They were applied together and the result was green, so the
experiment does not separate them. It matters because if the marker is what does
it, the marker is load-bearing and needs its own assertion in `test-mutrun.sh`
(case 17: remove the marker, require case 191 to red, so the tool proves its own
sandbox shape); if the mirroring is what does it, the marker is belt-and-braces.

What would settle it: one arm run with the `.git` marker omitted and everything
else identical, about 4.5 minutes, asserting whether case 191 reds. Reading
`wl_core.project_root:309-321` suggests the marker is the load-bearing one, since
without a `.git` anywhere above it the walk falls through to `return p`. That is
a hypothesis from code, which §3 of the house rules says is not a finding until
it is run.

---

## 14. Corrections to the brief, verified today

1. **The suite takes over four minutes, not over two.** `real 4m32.695s`, 663
   cases. Two sequential arms would be about nine minutes, which is why §6.2
   treats concurrent arms as the design rather than an optimization.
2. **The throwaway's broken filter was the summary one, not the failures one.**
   Its failures filter is `grep -E '^ *FAIL'`, which matches the suite's indented
   `  FAIL:` lines. Its summary filter is `grep -E '^(passed|failed)='`, which
   matches zero lines of a real log. Same class, and §5.1's C1 covers it.
3. **The two suites do not share fixtures, so the nesting is not a race.**
   `test-hooks.sh:421-425` nests the suite, and `test-worklist-v5.sh:36` gives
   every run its own `mktemp` root, with `TMPDIR`, `CLAUDE_PROJECT_DIR` and
   `WORKLIST_TASKS_DIR` pinned underneath it at every call site that matters. The
   `HOME`-rooted fallbacks in `wl_core.py:342-349`, `:581-585` and
   `wl_report.py:121-125` key off either an env override the suite sets or the
   per-run project-root slug. §7.3 records the direct two-arm measurement.
4. **"Copy the relevant tree into a sandbox" needs one more word: at its
   repo-relative path.** A flat copy, which is what the throwaway does, breaks
   `wl_core.py`'s `parents[3]` repo-root arithmetic and `project_root`'s walk for
   a `.git` marker (`:309-321`). §4.1.
5. **"A kill must be unable to strand a mutated live tree" is a stronger
   requirement than a careful trap can meet, and the numbers differ by
   language.** Measured: a bash `EXIT` trap survives `SIGTERM` and dies on
   `SIGKILL`; a Python `finally` dies on both. A design with no restore step
   removes the dependency on which signal arrives. §4.2.
