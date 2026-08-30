# PLAN: judge gate-worthiness scoring and surface scope beyond Quality
Status: draft
Owner: 9d92d9b6
Updated: 2026-08-30

Two defects in the Stop hook's regression-gate arm, designed together because
they share one root cause: the judge rules on a fix it cannot see.

## 0. The incident that started this

Commit 186a81e0c is a three-line ruff-format correction to
.claude/hooks/stop/wl_git.py. No functional change. It was found by CI, in the
step "Python lint + format (ruff)". The judge fired:

  "A FIX LANDED AND NO REGRESSION GATE PROTECTS IT ... Write a new gate (or
   extend check:ci-shell-format) to verify .claude/hooks files are formatted
   per ruff rules."

Every clause of that is wrong. check:ci-python-lint already exists
(package.json:128), is a manifest gate (scripts/ci-runner/manifest.ts:1137),
runs .ci/scripts/quality/check-python-lint.sh, which enumerates
`git ls-files --cached --others -- '*.py' ':!:private/**'` and runs both
`ruff check` and `ruff format --check` over it. It covers this file. It caught
this defect. check:ci-shell-format is the shell gate and has nothing to do with
Python.

The judge could not have known, because of what it was shown.

## 1. What the judge is actually shown today

  wl_reggate.py:194        the changed-file list is computed
  wl_reggate.py:197        ... and used only for the docs-only filter
  wl_reggate.py:199        ... then discarded: the description is `sha[:7] subj`
  wl_checks.py:5180-5186   the prompt gets those subjects plus a flat dump of
                           every check:* key in package.json
  worklist_messages.py:1759  "(2) EXISTING COVERAGE: would any gate in the list
                           below have FAILED against the tree BEFORE the fix?"

The model is asked a question about a diff it has never seen, against 217 key
names with no path scope attached. It answered from the word "format" in the
subject line. Nothing in the machinery could catch that, because
apply_regression_verdict (wl_reggate.py:564-655) verifies only that a CITED key
EXISTS, never that it COVERS.

## 2. The two failures, named

F1  NO PROPORTIONALITY. apply_regression_verdict has branches for
    applicable=false (:592), a cited key (:596), recurring=false (:619), a `[?]`
    deferral (:621), and a proven new gate (:626). There is no branch that
    weighs how big the defect was. `recurring`, a single model boolean, is the
    only input, and it defaults toward true.

    Measured on the live store (125 settled fix-sets across
    /tmp/claude-worklist/*.reggate-*): proven 60, covered 58, not-applicable 6,
    one-off 1. The mechanism has said "no gate warranted" 7 times in 125.

F2  THE COVERED BRANCH IS A RUBBER STAMP. wl_reggate.py:596-598 settles the
    moment `eg in keys`. Any real key name ends the finding. 58 of 125 settles
    took that path with zero verification that the named gate covers anything.

    The same store shows the mirror-image rot on the proven side: eight sampled
    judge-named `artifact` paths from `proven` settles were all checked and all
    eight DO NOT EXIST. They settled because prove_new_gate matched some other
    changed check script by glob. The recorded evidence is fiction.

F3  SURFACE MONOCULTURE. Store surfaces: gates 88, hooks 17, none 11, unit 6,
    e2e 2, ops 1, install 0. 99 of 125 findings were routed to the Quality lane
    or to nowhere. ci.yml has 26 top-level jobs; `quality` is one of them.

Note what is NOT broken: the class-sweep arm already carries the proportionality
the reggate arm lacks. wl_classsweep.py:157 lists "pure formatting" among the
applicable=false cases, with a worked rationale. Over-firing is specific to
wl_reggate, and wl_classsweep's rubric is the model to copy.

## 3. Problem 1 design: the coverage witness and the gate-worthiness score

New module: .claude/hooks/stop/wl_gateworth.py
New suite:  .claude/hooks/stop/test-gateworth.py, invoked from
            .claude/hooks/test-hooks.sh alongside the block at :1881-1960
            (required by .ci/scripts/quality/check_test_file_orphans.py)

The design is two-stage on purpose. Stage A is decisive and needs no model.
Stage B is a weighted score and only runs on the residual band where no
artifact settles the question. This mirrors the repo's own posture: verify
claims against artifacts, score only what artifacts cannot answer.

### 3.1 Inputs (all computed before the judge call)

wl_reggate.fix_signals (wl_reggate.py:165-255) gains a sixth return value:
the repo-relative changed-path list per unit. The data is already computed at
:194 and thrown away at :199. Commit units use `git diff-tree --name-only -r`
per sha; tick units use `git status --porcelain` intersected with the tick's
evidence paths (_EVIDENCE_PATH, wl_reggate.py:147). The single caller is
wl_checks.py:2762.

### 3.2 Stage A: the COVERAGE WITNESS (deterministic, decisive)

The repo already demands that a gate author plant the defect and watch the gate
go red. Stage A turns that discipline around: instead of asking the session to
prove a NEW gate fires on the defect, it proves whether an EXISTING gate does.

WITNESS_TABLE, a hand-verified list of (path glob, gate id, argv template).
The template reads the file content on stdin so no worktree, checkout or
node_modules is needed:

  '**/*.py'                  check:ci-python-lint   ruff format --config ruff.toml --check -
  '**/*.py'                  check:ci-python-lint   ruff check --config ruff.toml --stdin-filename <path> -
  '**/*.sh'                  check:ci-shell-format  shfmt -d -
  '**/*.sh'                  check:ci-shell-lint    shellcheck -
  '.github/workflows/*.yml'  check:ci-actionlint    actionlint -
  '**/*.go'                  check:ci-go-*          gofmt -l
  '**/*.ts', '**/*.tsx'      check:lint             eslint --stdin --stdin-filename <path>

Binaries resolve through .ci/scripts/lib/toolchain.sh (toolchain_load /
toolchain_check), the same pinned resolver check-python-lint.sh uses at its
resolve_ruff. A binary that is absent or off-pin yields UNAVAILABLE, never
COVERED.

For each changed path with a table row, run the witness twice:
  pre  = git show <sha>^:<path>  | <witness>
  post = git show <sha>:<path>   | <witness>

  pre != 0 and post == 0  ->  COVERED-VERIFIED by <gate id>
  pre == 0                ->  BLIND: the gate does not see this defect
  witness cannot run      ->  UNAVAILABLE (falls through to Stage B, never
                              settles on its own)

Verified by hand on the incident, 2026-08-30:
  git show 186a81e0c^:.claude/hooks/stop/wl_git.py | ruff format --check -  -> 1
  git show 186a81e0c:.claude/hooks/stop/wl_git.py  | ruff format --check -  -> 0
COVERED-VERIFIED by check:ci-python-lint. Cost: milliseconds. No model call.

WHY NOT USE manifest.ts `paths:` GLOBS. Only 23 of 331 entries declare `paths`,
check:ci-python-lint is not one of them, and .claude/agents/gate-author.md
explicitly forbids adding `paths` to make an entry cheaper. A declarative index
would have missed exactly this case. The witness is empirical and cannot be
wrong about what it just observed.

WHY A HAND TABLE IS ACCEPTABLE. Same argument manifest.ts makes for itself at
its own header: "MAINTENANCE IS BY RULE, NOT BY HAND". A row is a claim that a
gate id exists and its binary resolves, so a new gate
check:ci-witness-table-liveness asserts every row's gate id is a live manifest
id with gate: true and every argv template resolves through toolchain.sh. A
stale row fails the gate rather than rotting into a false COVERED. (This is the
one new gate this plan proposes, and it is a gate about the judge, which is the
case where a new gate is clearly warranted under the very rules below.)

### 3.3 Stage B: the gate-worthiness score

Runs only when Stage A did not return COVERED-VERIFIED.

DETERMINISTIC FACTORS, computed in wl_gateworth from the diff and the marker:

  D1  witness returned BLIND for a matching gate                        +2
  D2  `git diff -w` over the fix range is empty (whitespace only)       -3
  D3  exactly 1 file changed and net line delta <= 5                    -1
  D4  >= 3 files changed, or >= 2 distinct top-level directories        +2
  D5  a changed path is in the HIGH-BLAST table:                        +3
      .claude/hooks/pre-bash/**, .ci/scripts/security/**,
      .github/workflows/**, install.sh, .ci/scripts/deploy/**,
      **/*auth*, **/*credential*, **/*secret*, **/*token*
  D6  the diff adds or removes a destructive verb: rm -rf, --force,
      force-push, prune, DROP, chmod 777, git clean                     +3
  D7  a previously settled fix-set in the marker touched one of these
      same paths (recurrence OBSERVED, not predicted)                   +3
  D8  the fix-set subject matches ^revert                               -2
  D9  the commit body names a check:* key or a CI step as the finder    -2

D7 requires one small change: the settle record at wl_checks.py:5356-5366
already stores verdict, existing_gate, blind_spot, surface, artifact and at.
Add `paths`. Without it, observed recurrence is not computable.

JUDGE FACTORS. Two new enum fields on the regression_gate object, answered on
the same call at no extra cost, the same contract `surface` already has
(wl_judge.py:126-133):

  blindness: 'by-construction' | 'incidental' | 'none'
      by-construction  +3   the i18n shape: no gate could see it, ever
      incidental        0   a gate could have seen it and did not
      none             -2   an existing gate does see this class
  severity: 'data-loss' | 'security' | 'user-visible' | 'internal' | 'cosmetic'
      data-loss        +4   security +4   user-visible +1
      internal          0   cosmetic -3
  recurring (existing boolean)      true +2, false -2

ROUTING:

  score >= 4   MANDATE                 today's behaviour, R_REGGATE_BLOCK
  1 <= s <= 3  REBUT-AND-VERIFY        a new, softer block
  score <= 0   PROPORTIONATE-NO-GATE   settle, with the breakdown recorded

HARD OVERRIDES, which no negative factor can cancel:

  H1  severity in {data-loss, security}          -> MANDATE, unconditionally
  H2  D7 fired (recurrence observed on a path)   -> never settles below
                                                    REBUT-AND-VERIFY
  H3  Stage A returned UNAVAILABLE               -> never settles as covered;
                                                    the score decides
  H4  a malformed or missing regression_gate object still blocks, exactly as
      today (wl_reggate.py:590, wl_checks.py:5346)

Replay of the incident with the witness disabled (H3 path), to show the score
alone also gets it right: D2 -3, D3 -1, D9 -2, blindness none -2, severity
cosmetic -3, recurring true +2 = -9. PROPORTIONATE-NO-GATE.

Replay of a synthetic security fix (a pre-bash guard with a bypass):
D1 +2, D5 +3, blindness by-construction +3, severity security +4, recurring
true +2 = +14, and H1 fires anyway. MANDATE.

### 3.4 REBUT-AND-VERIFY, the middle exit

New message M.R_REGGATE_REBUT_FIRST. It does not demand a gate. It says: the
score puts this in the band where an existing gate probably covers it, so name
the gate you believe covers this class in one line, or say in one line why no
gate is warranted. It is carried forward by a wl_rules.Demand (the plumbing at
wl_rules.py:34-89, exactly as wl_classsweep uses it at :318) with TTL 120 and
max_fires 2, after which it auto-settles as 'proportionate-unrebutted'. A
session cannot be walled in by this band.

On the next stop the named gate is put through the witness. A cited gate the
witness shows is BLIND is reported as such, which is strictly stronger than
today's R_REGGATE_HALLUCINATED (worklist_messages.py:1477), which only checks
that the name exists.

### 3.5 Where it plugs in

  wl_judge.py:110-147     add `blindness` and `severity` to the
                          regression_gate schema and to its required list.
  wl_judge.py:126-133     the `surface` enum grows (see section 4).
  wl_judge.py:601         _REGGATE_MARKER unchanged; the new questions ride the
                          existing REGGATE_PROMPT so judge_schema_for (:604)
                          keeps requiring the object when the prompt asks.
  wl_reggate.py:165-255   fix_signals returns changed paths per unit.
  wl_reggate.py:564       apply_regression_verdict takes a `worth` argument.
                          New branch order:
                            1  malformed              (:590, unchanged)
                            2  applicable false       (:592, unchanged)
                            3  NEW worth COVERED-VERIFIED -> settle
                               'covered-verified' with the witness note.
                               DELIBERATELY ABOVE the cited-key branch: an
                               observation outranks a citation.
                            4  cited key              (:596-618) plus, when the
                               table has a row for that gate, a witness run. A
                               cited-but-blind gate no longer settles.
                            5  recurring false        (:619, unchanged)
                            6  deferred token         (:621, unchanged)
                            7  proven new gate        (:626-639, unchanged)
                            8  NEW worth NO-GATE      -> settle 'proportionate'
                            9  NEW worth REBUT-VERIFY -> block with
                               R_REGGATE_REBUT_FIRST + Demand
                           10  else                   -> block (:647, today's
                               R_REGGATE_BLOCK)
  wl_checks.py:2762       unpack the sixth return value.
  wl_checks.py:5177-5186  build the prompt: add the changed-path block and the
                          Stage A result AS A STATED FACT, e.g. "check:ci-
                          python-lint FAILS on the pre-fix blob of
                          .claude/hooks/stop/wl_git.py and PASSES on the post-
                          fix blob". Note this alone would likely have fixed
                          the model's answer; the deterministic route means the
                          outcome no longer depends on that.
  wl_checks.py:5335-5343  pass `worth` into apply_regression_verdict.
  wl_checks.py:5356-5366  add `paths`, `score`, `factors` and `route` to the
                          settle record, so the mechanism is calibratable the
                          way calibrate-judge-rules.py already calibrates the
                          rules.
  worklist_messages.py:1746  REGGATE_PROMPT gains the paths block, the witness
                          fact, and questions (5) blindness and (6) severity.
  worklist_messages.py:1449  R_REGGATE_BLOCK keeps its three exits. New
                          R_REGGATE_REBUT_FIRST beside it.

### 3.6 Why this is not a rubber stamp

The paranoia in this machinery was paid for (wl_reggate.py:3-8, the i18n
cross-locale bug that every gate was blind to by construction; wl_classsweep.py
:8-25, five defects in one night each fixed at one site). Nothing here weakens
those cases:

  - A by-construction blind spot scores +3 and is the exact shape the i18n
    lesson describes. It cannot fall into the no-gate band with anything else
    positive.
  - Security and data-loss are hard overrides. No amount of "it was one line"
    reaches them.
  - Observed recurrence (D7) is an artifact, not a prediction, and it floors
    the route.
  - Stage A can only ever settle on a witness that ACTUALLY FIRED on the
    pre-fix blob. An unavailable tool never settles anything.
  - Fail-closed is untouched: a missing or malformed regression_gate object
    still blocks at wl_checks.py:5346.

And it closes a rubber stamp that exists TODAY: 58 of 125 settles took the
unverified `eg in keys` path. After this change a cited gate is verified where
a witness exists.

## 4. Problem 2 design: surfaces beyond the Quality lane

### 4.1 What ci.yml actually looks like, verified

26 top-level jobs. scripts/ci-runner/manifest.ts holds 331 entries; 315 point
at ci-quality.yml, 1 at ci-build-renet.yml. The manifest IS the Quality
inventory.

BUT: 117 of those entries are `gate-test:*` ids running
.ci/scripts/test/gates/test-*.sh, and those drive the scripts belonging to the
NON-Quality jobs, offline, with fixtures: test-ci-complete-tiers.sh,
test-dispatch-release.sh, test-simulate-promotion-serverside.sh, seven
test-breakpoint-*.sh, four test-installmethods-*.sh, seven
test-releaseversion-*.sh, test-label-*.sh, test-review-*.sh, test-greenlight*.sh.
All 117 are scheduled by `npm run ci` and by `npm run ci:quick`, the pre-push
battery enforced at .claude/hooks/pre-bash/block-unverified-push.sh:71.

So the local battery ALREADY reaches nearly every non-Quality job's logic. The
judge has simply never been told it exists: 0 of 125 settles routed there.

### 4.2 Local battery audit, per job

  COVERED OFFLINE by gate-test:* cases already in `npm run ci`:
    initialize, label-guide, run-sh-tests, review-gate (logic; the live GitHub
    read cannot run offline), check-release-state, breakpoint-lifecycle,
    validate-install, validate-promote, ci-complete, finalize-release-sentinel
  PARTIAL, source invariants local and the real build is not:
    build-renet, build-cli, update-flow-test, package-tests
  NOT LOCAL, and correctly so (credentials, Docker registries, KVM, R2,
  Cloudflare, or a live machine):
    stripe-sandbox, build-docker, build-docker-fast, stage-artifacts,
    ops-tests, elite-run-test, deploy-preview, smoke-test-preview, and the e2e
    half of `tests`
  THE REFERENCE CASE:
    quality

  THREE SCRIPTS WITH NO TEST AT ALL. Verified by grepping every filename
  through .ci/scripts/test/gates/:
    .ci/scripts/ci/cancel-older-runs.sh    (job cancel-watchdog)   0 references
    .ci/scripts/ci/dispatch-watchdog.sh    (job cancel-watchdog)   0 references
    .ci/scripts/ci/assert-job-succeeded.sh (job pipeline-sentinel) 0 references
  These are three missing CASES in the existing battery, not a missing battery.
  Recommendation: three test-*.sh files under .ci/scripts/test/gates/, wired as
  gate-test:* manifest entries. Small, offline, and it uses the machinery that
  is already there.

  ONE WIRING GAP. .ci/scripts/test/run-unit.sh is fast, offline, and is the
  `tests` job's unit lane (ct-tests.yml:211). It is not in the manifest, and
  wl_reggate.CHECK_SCRIPT_GLOBS (wl_reggate.py:47-63) cannot see
  packages/*/__tests__/**, so a fix whose right home is a unit test can only
  ever settle through the weak prove_named_artifact existence check
  (wl_reggate.py:365-395). Six fix-sets in the store routed to `unit`.
  Recommendation, minimal: extend CHECK_SCRIPT_GLOBS with
  packages/*/__tests__/**/*.test.ts and packages/*/src/**/*.test.ts, and prove
  by running the single file through its package's test key. Do NOT add
  run-unit.sh to the manifest as a gate; that changes what `npm run ci` costs
  and is a separate decision.
  Note check:ci-test-scripts-reachable already guarantees no package's suite is
  invisible to BOTH CI and the omissions record, so this is a judge-side
  blindness, not a CI-side one.

  VERDICT ON "SHOULD ANOTHER JOB GET AN `npm run ci` EQUIVALENT": no. The
  scoping is deliberate and correct. Quality is uniquely well instrumented
  because Quality is the lane whose questions can be answered fast and offline.
  Everything else either already has its logic tested in that same battery, or
  genuinely needs the real CI environment.

### 4.3 The surface enum grows, and question (4) is rewritten

wl_judge.py:126-133 currently offers gates | e2e | ops | install | unit |
hooks | none. Three values are added:

  pipeline     the defect is in a script owned by a NON-Quality ci.yml job
               (.ci/scripts/ci/**, .ci/scripts/deploy/**, .ci/breakpoint/**).
               Home: a .ci/scripts/test/gates/test-*.sh case wired as a
               gate-test:* manifest entry. 117 of these already exist.
  workflow     the defect is in the job graph itself: needs, if, permissions,
               concurrency, an output nobody reads. Home:
               check:ci-workflow-invariants, check:ci-workflow-gates or
               check-ci-job-aggregation.sh, plus a gate-test case. NOT a new
               check-*.ts.
  runtime-only the defect is observable only in the real CI environment.
               Legitimate artifacts: a step assertion added to the owning job,
               or a `[?]` operator deferral. This is what `none` is being
               abused for today (11 of 125).

No new proving machinery is needed for `pipeline`: CHECK_SCRIPT_GLOBS already
contains ".ci/scripts/test/gates/test-*.sh" (wl_reggate.py:60) and
prove_new_gate accepts suite gates ON CHANGE at wl_reggate.py:453. The routing
at wl_reggate.py:633-639 already handles any surface that is not gates/none.

worklist_messages.py:1768-1788, question (4), is rewritten to ask the routing
question in the right order:

  FIRST: which ci.yml JOB would have caught this? `quality` is one of 26.
  THEN: map job to surface.
    quality                              -> gates
    run-sh-tests, initialize, ci-complete,
    label-guide, review-gate, check-release-state,
    finalize-release-sentinel, pipeline-sentinel,
    validate-promote, breakpoint-lifecycle       -> pipeline
    build-renet, build-docker, build-cli,
    stage-artifacts                              -> runtime-only unless the
                                                    defect is visible in the
                                                    source, then gates
    validate-install, update-flow-test,
    package-tests                                -> install
    tests (unit half)                            -> unit
    tests (e2e half)                             -> e2e
    ops-tests                                    -> ops
    deploy-preview, smoke-test-preview,
    stripe-sandbox, elite-run-test               -> runtime-only
    (a .claude/hooks script, no ci.yml job owns it) -> hooks
  The line "Answering `gates` for a BEHAVIOURAL defect is the failure to avoid"
  stays, and gains a sibling: answering `gates` for a defect that lives in a
  CI SCRIPT is the same failure. The Quality lane cannot run initialize.sh
  against a real workflow event; a gate-test can, with fixtures.

The job list is GENERATED into the prompt, not hand-typed: a helper in
wl_gateworth greps `^  [a-z-]*:$` out of .github/workflows/ci.yml and pairs
each job with its `uses:` or first `run:` line, capped at 26 rows. A hand-typed
list rots; this one cannot disagree with the file.

### 4.4 Skill and agent documentation

  .claude/skills/testing/SKILL.md:12-19  the table gains pipeline, workflow and
      runtime-only rows. "ci.yml has six regression surfaces" becomes accurate.
      The "Coverage of the surfaces themselves" section gains: the pipeline
      surface is covered by check:ci-test-gate-wiring and by check-ci-parity's
      assertion 7, which compares the qualityGateTest set against the on-disk
      glob run-all.sh uses.
  .claude/skills/testing/pipeline.md     NEW. Where a gate-test lives, how
      run-all.sh selects it, how to wire the gate-test:* manifest entry, and
      the fixture idiom the existing 117 use. Cites test-ci-complete-tiers.sh
      and test-simulate-promotion-serverside.sh as the two models to copy.
  .claude/skills/testing/gates.md:20     "`ci.yml:479` calls `ci-quality.yml`,
      so a wired key is reachable from `npm run ci`" is true but reads as if
      Quality is the whole of CI. Reframe: quality is job 4 of 26, and a
      check:ci-* key is the right instrument only for a defect the Quality lane
      can see without running the product or the pipeline.
  .claude/agents/gate-author.md          add a short "before you write a gate"
      section: run the witness first. If an existing gate fails on the pre-fix
      blob and passes on the post-fix blob, the gate you were about to write is
      a second assertion of a fact the tree already asserts.
  .claude/hooks/stop/wl_classsweep.py:189-195  section (4) of SWEEP_PROMPT
      gains a non-Quality bullet: a CI-script defect's siblings live in the
      other scripts of the same lane (.ci/scripts/ci/, .ci/scripts/deploy/,
      .github/workflows/), and the search should name that directory. This arm
      already has proportionality at :157 and does not otherwise change.

## 5. Verification plan

The mechanism must be proved on BOTH directions, on the real tree, with the
planted-defect discipline the repo demands of any gate.

V1  REPLAY THE INCIDENT. In test-gateworth.py, a case that pins commit
    186a81e0c and asserts:
      witness('.claude/hooks/stop/wl_git.py', '186a81e0c') == COVERED-VERIFIED
      and the gate id is check:ci-python-lint
    Then feed a synthesised regression_gate object matching what the judge
    actually returned that day (existing_gate='', recurring=true,
    gate_needed=true, surface='gates') into apply_regression_verdict with the
    computed `worth`, and assert the return is
      ('settle', 'covered-verified', <note naming check:ci-python-lint>)
    and NOT ('block', ...). This is the exact scenario the operator flagged.

V2  THE SAME CASE WITH THE WITNESS DISABLED. Force UNAVAILABLE (H3) and assert
    the score alone still lands at PROPORTIONATE-NO-GATE, with the factor
    breakdown printed. This proves the score is not carried by the witness.

V3  A GENUINELY NOVEL SECURITY FIX STILL MANDATES. Construct a synthetic
    fixture: a one-line change to a file under .claude/hooks/pre-bash/ that
    removes a bypass condition from a guard, with severity='security' and
    blindness='by-construction'. Assert:
      - Stage A returns BLIND or UNAVAILABLE, never COVERED-VERIFIED (the
        witness for *.sh is shfmt and shellcheck, and neither sees a logic
        bypass, which is the point)
      - the route is MANDATE
      - H1 fires independently, so flipping every negative factor on (make it
        whitespace-adjacent, single file, tiny) STILL yields MANDATE
    That last assertion is the anti-rubber-stamp control and it is the one that
    matters most.

V4  THE i18n LESSON STILL FIRES. A fixture standing in for the cross-locale
    bug: blindness='by-construction', severity='user-visible', recurring=true,
    no witness row for the path. Score = 3+1+2 = 6. Assert MANDATE. This is the
    incident wl_reggate.py:3-8 exists for and it must survive the change.

V5  THE MIDDLE BAND IS BOUNDED. Fire REBUT-AND-VERIFY three times against the
    same Demand and assert it auto-settles as 'proportionate-unrebutted' on the
    third, per wl_rules.Demand's max_fires. A band that can wall a session in
    is worse than the over-firing it replaces.

V6  CITED-BUT-BLIND IS CAUGHT. Feed existing_gate='check:ci-shell-format' for
    the wl_git.py Python fix. Today wl_reggate.py:597 settles it as 'covered'.
    Assert that after the change it does NOT settle, because the witness for
    that gate does not fire on a .py blob.

V7  ANTI-VACUITY, in the module itself. If the witness table matches ZERO rows
    for a fix-set whose paths are all *.py, that is a broken table, not a
    finding: refuse and report. If Stage A is asked about zero changed paths,
    refuse. Print the counts on success, per gate-author.md.

V8  BACKTEST AGAINST THE STORE. A one-shot script (not a gate) replays all 125
    settled fix-sets from /tmp/claude-worklist/*.reggate-* through the new
    routing and prints the confusion table: how many 'proven' settles would now
    be PROPORTIONATE-NO-GATE, how many 'covered' would now be cited-but-blind.
    The result is a calibration input for the weights, not a pass/fail. The
    precedent is .claude/hooks/stop/calibrate-judge-rules.py.

V9  THE JUDGE SCHEMA STILL ROUND-TRIPS. test-judge-schema.py already exercises
    the schema; add the two new enums and the three new surface values, and
    assert judge_schema_for still promotes regression_gate to required when
    _REGGATE_MARKER is present (wl_judge.py:604-628).

V10 END TO END. Run .claude/hooks/stop/test-worklist-v5.sh (check:ci-hook-
    worklist-suite), .claude/hooks/test-hooks.sh, and
    npm run check:ci-python-lint over the new module. Then npm run ci:quick.

## 6. Sequencing

  S1  wl_reggate.fix_signals returns paths; wl_checks unpacks it; settle record
      stores `paths`. No behaviour change. Ships alone, proves the plumbing.
  S2  wl_gateworth.py Stage A only, plus the witness table and its liveness
      gate. Wire it into the PROMPT only (state the witness result as a fact),
      not yet into the routing. This is reversible and observable: the store
      will show whether the model's answers improve on the fact alone.
  S3  Stage B scoring, the schema fields, and the three new routes in
      apply_regression_verdict. Behind WORKLIST_GATEWORTH=off so a bad
      calibration can be turned off without turning the judge off.
  S4  V8 backtest, then tune weights once against the 125-row store.
  S5  Surface enum, prompt question (4) rewrite, generated job inventory,
      pipeline.md, SKILL.md and gates.md edits.
  S6  The three missing gate-tests (cancel-older-runs, dispatch-watchdog,
      assert-job-succeeded) and the CHECK_SCRIPT_GLOBS unit-test widening.
      Independent of everything above; can ship in any order.

## 7. Risks

  R1  The witness table is a second place that knows about gates. Mitigated by
      check:ci-witness-table-liveness, and by the table being SMALL (seven
      rows, covering the blanket formatters and linters only). It is explicitly
      not an attempt to model all 331 gates.
  R2  Weights are guesses until V8 runs. Mitigated by shipping Stage A first,
      by the env kill switch, and by recording the score and factors on every
      settle so the next calibration has data.
  R3  A session could learn to answer severity='cosmetic' to buy an exit. Two
      answers: the deterministic factors are the majority of the negative
      weight and a session cannot influence them, and D5/D6/D7 are path and
      diff facts. Also worth stating plainly: the judge is a separate model
      instance reading the session's message, not the session itself.
  R4  Adding fields to the judge schema costs prompt tokens on every fix stop.
      Measured budget headroom exists (wl_judge.py:34, $0.25 against a
      measured $0.0566 for a trivial schema-constrained call), and Stage A
      removes work from the model rather than adding it.
