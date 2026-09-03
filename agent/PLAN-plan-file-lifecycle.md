Status: ready
Owner: 74de73ca
Updated: 2026-09-02

# Plan files: a lifecycle nobody has to remember

Two gates and four Stop-hook changes, designed 2026-09-02 by two Plan agents working
from measurements against this tree. Written up here because those agents had no write
tool. Every number below is theirs unless marked; the ones re-checked in-session say so.

## The complaint

The operator, verbatim, across three messages:

> "I also see see too many plan files with empty []. This is bad since we may implemented
> some of them already but some of them are not. ... I feel like it only catches single
> file?"

> "it would be also great to have a CI blocker. So, even without stop hook, we can catch
> them at CI side. For the previous ones that's introduced before this branch, we can move
> them into an archive folder and exclude the archived ones but the CI gate should catch
> the escape hatch of the AI agents since they may try to cheat the system. So, the CI
> should be branch aware and github rename is allowed for archive only if the files are
> not modified/new in current branch."

> "let's also add another .github/workflows/ci.yml quality check for housekeeping of old
> plan files! If a plan file is older than 33 days, then CI should complain until someone
> deletes them from the branch."

Three asks, one subject: creation, maintenance, retirement of `agent/PLAN-*.md`.

## What is actually true right now, measured

### The corpus, through three instruments

| Instrument | Open | Done | Files |
|---|---|---|---|
| naive `grep -F -- '- [ ]'` | 93 | -- | 9 |
| `wl_planfile.raw_box_counts` (anchored, no fence tracking) | 89 | 24 | 9 |
| `wl_planfid.plan_tasks` (the REAL parser) | 88 | 24 | 8 |

**5 of 93 raw hits are false positives.** Four are mid-line prose about the grammar
(`PLAN-secret-namespace-migration.md:45`, `:1269`, and two in
`PLAN-stop-plan-box-enforcement.md`); one is a fenced code SAMPLE at
`PLAN-fix-in-session-rule.md:352`, a depiction of a line the hook prints.

**This dictates the implementation language.** A gate built on `grep` reds on 5
non-tasks. A gate on `raw_box_counts` reds on 1. Only `plan_tasks` is correct, and it is
Python in `.claude/hooks/stop/`. So the gate is Python and imports it. There is no second
parser to drift, which turns the fence rule from a test into a structural property.

### Why the Stop hook "only catches single file" -- TWO causes, and the prior plan named one

```
PLAN-branch-aware-workflows.md       open= 2  status=partially  inscope=True
PLAN-env-to-bitwarden-v2.md          open= 9  status=draft      inscope=False
PLAN-env-to-bitwarden.md             open=22  status=draft      inscope=False
PLAN-github-secrets-removal.md       open=16  status=draft      inscope=False
PLAN-handoff-sequence.md             open= 7  status=draft      inscope=False
PLAN-secret-names-one-to-one.md      open=12  status=design     inscope=False
PLAN-secret-namespace-migration.md   open=14  status=executing  inscope=True
PLAN-stop-plan-box-enforcement.md    open= 6  status=draft      inscope=False
```

1. `_pf_rows[0]` at `wl_checks.py:3758` renders exactly one row. This is the cause
   `agent/PLAN-stop-plan-box-enforcement.md` named, and it is at least REPORTED.
2. **`NOT_STARTED_STATES` exempts 6 of 8 files -- 72 of the 88 boxes -- before
   `plan_rows` ever opens them.** `wl_planfile` can see 16 boxes in 2 files, total, and
   then shows one of those two.

Cause 2 is the bigger hole and it was not known. The prior plan measured a 62-plan corpus
where `draft` genuinely meant proposal. Today `Status: draft` is this repo's DEFAULT
header on plans under active execution -- the audit found 5 DONE-but-unticked boxes
inside `draft` files. Design note 4's blocklist SHAPE is still right (a whitelist would be
vacuous); its empirical premise about the word `draft` is not.

### The premise that turned out false: there is nothing pre-existing to archive

```
$ git diff --name-status <merge-base>...HEAD -- agent/
A  agent/PLAN-branch-aware-workflows.md
A  agent/PLAN-env-to-bitwarden-v2.md
A  agent/PLAN-env-to-bitwarden.md
A  agent/PLAN-github-secrets-removal.md
A  agent/PLAN-handoff-sequence.md
A  agent/PLAN-secret-names-one-to-one.md
A  agent/PLAN-secret-namespace-migration.md
A  agent/PLAN-stop-plan-box-enforcement.md
```

**88 of 88 parsed open boxes are branch-new.** The pre-branch corpus has zero. The
operator's "previous ones that's introduced before this branch" describes work from
earlier the same day. The archive migration has an empty input set -- so the archive stays
as a FORWARD mechanism and as the hatch that must be policed, but it is off the critical
path. It also means a naive "no open boxes on files your branch touched" gate would be red
on 8 files and 88 boxes on the very branch introducing it. That gate is unshippable, and
the design below is not it.

### The age question: git dates lie here, and they lie GREEN

```
$ git rev-parse --is-shallow-repository
true
$ git log -1 --format='%h %cI' -- agent/PLAN-cold-path.md
1cf2a3733 2026-09-01T14:25:23+02:00        # the GRAFT, not the file's commit
```

Every tracked plan reports 1 day old in this checkout. `check_git_history_depth.py:6-9`
already documents the class; it reproduced. Computed instead over all 4001 reachable
commits excluding the two grafts:

- **At 33 days, ZERO `agent/PLAN-*.md` files fail today.** The oldest is 12 days.
- Structural cap: `agent/` became tracked on 2026-08-18 (`e0ad8e6c2`), so nothing under
  it can exceed 15 days.
- **38 of them share ONE bulk-add commit** (`f7a5351a9`, 2026-08-21). Zero offenders
  becomes 38 offenders within hours of each other on 2026-09-23.

So the age gate's landing problem is the inverse of the expected one: it lands green,
proves nothing, and detonates in three weeks inside a stranger's PR.

Author vs committer date diverge on **735 of 4001 commits, max skew 21.54 days** -- 65% of
a 33-day window, so `%cI` vs `%aI` is not cosmetic. `%cI` is correct: it answers "when did
this file, in its current form, enter the branch", and it errs lenient (a rebase makes a
file look fresher, never staler), which is the safe direction for a gate whose false
positive deletes a document someone needs.

**The property that dissolves the hardest sub-question:** a plan genuinely being executed
is being EDITED, an edit is a COMMIT, and a commit resets `%cI`. The last-commit
instrument auto-exempts every actually-active plan against an oracle nobody can forge by
typing a word.

## Design

### The ledger, `.ci/config/plan-boxes.json`

Regenerated by `npm run check:ci-plan-boxes -- --update`:

```json
{
  "refreshed_at": "2026-09-02T00:00:00Z",
  "plans": {
    "agent/PLAN-env-to-bitwarden.md": {
      "status": "draft", "owner": "74de73ca", "open": 22, "done": 0,
      "task_sigs": ["a1b2c3d4", "..."]
    }
  }
}
```

`task_sigs` = first 8 hex of `sha256(wl_planfid._norm(task)[:120])` -- **exactly the key
the parser already dedups on** (`wl_planfid.plan_tasks:305`). Not raw text, so re-wrapping
a line is free and rewriting its meaning is not.

Why a ledger rather than a pure diff gate, in order of weight:

1. It works on `push`, not just `pull_request`. `quality-branch` is PR-only, so a
   diff-only gate is unenforced on main.
2. "Did box X survive?" becomes set membership, not a token-overlap guess.
3. The anti-vacuity floor is free and committed, so a diff cannot silently shrink it.
4. One reviewable file: `open: 22 -> 21` beside a `- [x]` is the whole story.
5. Precedent: `.ci/config/bws-secret-map.json` and `secret-reachability.json` are this
   shape already, asserted by a gate with a `--update` regenerator.

The obvious objection -- "an agent can regenerate the ledger" -- is the point of A1: A0
makes regenerating MANDATORY, and A1 reads the BASE ledger via `git show`, which the
working tree cannot rewrite.

### Gate 1: `.ci/scripts/quality/check_plan_boxes.py`

Python, `sys.path.insert(0, .claude/hooks/stop)`, calls `wl_planfile.plan_boxes`.
Precedent: `check_gate_reachability_coverage.py` already imports from that directory.

- **A0 LEDGER MATCHES TREE.** Every `agent/PLAN-*.md` (non-recursive) and every
  `agent/archive/plans/PLAN-*.md` must equal its ledger entry. Runs on every event.
- **A1 NO BOX MAY VANISH.** *(PR only.)* Load the base ledger with
  `git show "$MERGE_BASE:.ci/config/plan-boxes.json"`. Every base-open sig must at head be
  still open, ticked in that plan, open-or-done in ANY other plan, in the archive under
  A2, or in a plan whose deletion A5 permits. Otherwise VANISHED. **This one assertion
  catches five of the enumerated cheats**, because all five are "the sig left the set with
  no legal destination".
- **A2 ARCHIVE IS APPEND-ONLY AND FOR UNTOUCHED HISTORY.**
  - A2a: every new path under `agent/archive/plans/` must appear in
    `git diff --find-renames -M100% "$MERGE_BASE"...HEAD` as **`R100`** from under
    `agent/`. **This defeats the two-commit cheat**: `git diff A...B` compares TREES, so
    edit-then-archive across any number of commits, or a rebase, all produce `R09x`.
  - A2b: no `M` or `D` on an existing archived path, except a `D` A5 permits.
- **A3 `Status:` MAY NOT CLAIM DONE OVER OPEN BOXES.** Import the same two frozensets
  from `wl_planfile` and invert ONE: `NOT_STARTED_STATES` stays an exemption (a
  proposal's boxes are a sketch); `FINISHED_STATES` becomes a TRIGGER, because in CI
  `Status: done` over live boxes is a self-contradiction AND a live silencer for the
  advisory. Same constants, one import, opposite polarities with a stated reason each --
  so a new status word cannot drift the two halves apart, which is what design note 4 was
  protecting. Green today, verified.
- **A4 NEW DEBT NAMES AN OWNER.** A plan the branch ADDS with open boxes must resolve
  `wl_checks.plan_owner`. Red today on exactly 2 files
  (`PLAN-secret-names-one-to-one.md`, `PLAN-secret-namespace-migration.md`), one header
  line each. A good red: it is what makes the ownership filter mean anything.
- **A5 WHOLE-FILE RETIREMENT.** A `D` on a plan whose base entry has `open > 0` fails
  unless content age at base exceeds `delete_days` from `.ci/config/plan-lifecycle.json`.
- **A6 ANTI-VACUITY.** `len(plans) >= 40` (69 today) and `total_open >= 1`. Empty or
  unparseable ledger, or `PLAN_BOXES_ROOT` at nothing, prints `VACUOUS INPUT` and exits 1.
  Register in `test-gate-anti-vacuity.sh`'s `REGISTRY`.

**What it deliberately does NOT assert: the mere existence of an open box.** 90 of 92
audited verdicts are legitimately-open work, and a gate that reds on them is switched off
in a week. It polices TRANSITIONS AND LIES; the ledger makes the stock visible instead.

### The cheat table

| # | Cheat | Caught by | How |
|---|---|---|---|
| 1 | Archive a file you also edited | A2a | `-M100%` reports `R09x` |
| 2 | Edit in commit 1, archive in commit 2 | A2a | tree-to-tree; commit boundaries invisible |
| 3 | Delete the box line | A1 | sig leaves open, no legal home |
| 4 | `- [ ]` -> plain `-` bullet | A1 | leaves the task set, or lands in neither open nor done |
| 5 | Rewrite the box text | A1 | sig is over `_norm(body)[:120]` |
| 6 | `Status: done` over open boxes | A3 | FINISHED inverted to a trigger |
| 7 | Wrap a box in a code fence | A1 | **the same fence rule that makes `:352` a non-finding makes fencing a cheat** |
| 8 | Add to an exemption list | none exists | there is no per-plan exemption file, by design |
| 9 | Regenerate the ledger after deleting | A1 | base ledger comes from `git show` |
| 10 | Delete the whole plan file | A5 | refused under the age threshold |
| 11 | Edit an already-archived plan | A2b | append-only |
| 12 | Rename out of the glob | A1 | destination not in the head ledger |
| 13 | Land on a branch with no PR | **partial** | A1/A2/A5 need a base ref |

Cheat 13 is the honest hole, stated in the gate header rather than hidden. Main is
ruleset-protected and bot pushes carry `is_bot` (which already skips quality), so the
exposure is believed nil -- ASSERTED, not measured. Confirm against the branch ruleset.

### The archive: `agent/archive/plans/PLAN-<slug>.md`

Flat, under the existing `agent/archive/` root, and OUTSIDE the non-recursive
`agent/PLAN-*.md` glob -- so `plan_records`, `plan_drift_rows`, `plans_block` and
`wl_planfile` all drop it with **zero code change** (verified: `wl_store.agent_plan_dir` ->
`agent_root`, `d.glob("PLAN-*.md")`). `scripts/validate-cli-examples.ts` globs
`agent/**/*.md` recursively, so archived plans stay under CLI-example linting; nothing
breaks. Not `agent/legacy/` (one orphan STATE.md, no convention). Not
`agent/archive/<branch>/` (that scheme is for session state, and it gives the gate N
directories to police instead of one).

An archived plan KEEPS its open boxes. A1 still requires the sigs findable, A2b freezes
them: the archive is a waiting room, not a shredder.

### Gate 2: `.ci/scripts/quality/check-plan-housekeeping.sh`

Bash, because the BLOCKER validator (`.ci/scripts/lib/blocker-validator.sh`) is shell-only
and `check-greenlight-closures.sh` is the closest worked example.

- Glob: `git ls-files 'agent/PLAN-*.md'`, non-recursive, tracked-only. Same glob as the
  Stop hook (asserted as a subset control), so the two cannot enforce rules about
  different sets. Excludes `docs/PLAN-*.md` -- those are published docs with a different
  lifecycle, and they are the only two files that WOULD fail at 33 days (140 and 150).
- **The shallow-clone refusal, which nothing else in this repo has.**
  `.ci/scripts/lib/age-check.sh:41-44` is the anti-pattern: it `echo 0` (silently
  "fresh") when the log answer is empty, using the exact command that lies on a shallow
  clone. Instead: in CI a shallow checkout is a HARD failure naming the required
  `fetch-depth: 0` / `filter: blob:none`; locally it is a LOUD skip of the age verdict
  only, so the floor, the allowlist liveness and the whole control battery still run.
- Floor: `>= 30` plan files (61 today), env-overridable like `BWS_MIN_MAP_ENTRIES`.
- Placement: **`quality-i18n`, last step.** It already pays the `fetch-depth: 0
  --filter=blob:none` checkout at ci-quality.yml:1646-1655, and its `if: inputs.is_bot !=
  'true'` covers PR + nightly + dispatch. A clock-driven gate NEEDS the nightly, or a plan
  crossing 33 days first surfaces by ambushing an unrelated PR. `quality-branch` is
  rejected only because it is `pull_request`-only. A new `quality-history` lane is
  rejected on cost: `.profiler-coverage-allowlist:29`'s BLOCKER makes it a 5-point wiring.
  **No checkout needs to change** -- that is the whole reason for the choice.
- Hatch: `.plan-housekeeping-allowlist`, `# BLOCKER:` + `YYYY-MM-DD  path`, with three
  re-derived liveness rules: the path must exist in the glob; the plan must actually be
  over the threshold (an exemption that suppresses nothing is red -- the converse
  direction, lifted from `check_bws_map.py:551-554`); and a hard UTC expiry that reds on
  its own date whether or not anyone looked. Rule 3 alone is what stops a dumping ground.
- **`Status: executing` does NOT auto-exempt.** A status is self-reported free text
  costing one word: no reason, no expiry, no reviewer. It converts the gate into "type
  `executing` to opt out". And the corpus will not support a whitelist -- measured
  statuses include `W1 LANDED 2026-08-27; W2 to W4 still draft`. The question dissolves
  anyway: an edit is a commit and a commit resets the clock. An "executing" plan nobody
  has committed to in 33 days is abandoned with an optimistic header, which is exactly the
  file this gate exists to find. The status IS printed in the failure line, because
  `Status: done` beside `41 days` tells the reader the answer is `git rm`.
- **WARN band at 26 days**, naming the exact date each plan goes red. This is the only
  thing that makes 2026-09-23 visible a week early, and it is the repo's existing idiom
  (`age-check.sh:22-23`).

### The seam that stops the two gates deadlocking

A5 refuses a box-carrying deletion; the age gate demands one. A 34-day-old plan with one
open box would be simultaneously must-delete and must-not-delete.

**One shared constant in one shared file, `.ci/config/plan-lifecycle.json`:**

```json
{ "archive_dir": "agent/archive/plans", "warn_days": 26, "delete_days": 33 }
```

A5 PERMITS deletion exactly when `content_age_days > delete_days`; the age gate DEMANDS
one at the same predicate. The two are complements over one number from one file, so their
sets are disjoint by construction. **Duplicating `33` into two scripts is what creates the
deadlock.** Put the file in both gates' manifest `leaves`.

Both must measure CONTENT age -- the newest commit in which the file's BLOB HASH changed,
followed through renames -- not "last commit touching the path". Otherwise archiving is a
clock reset, i.e. a cheat against the age gate. Because A2b forbids modifying an archived
plan, its blob never changes and its clock keeps ticking: it ages out on schedule, and an
agent cannot archive its way out of a deletion demand. Say this in both gate headers.

### Stop-hook changes

- **S1, the census (the actual answer to "only catches single file").**
  `wl_checks.plans_block:1267` already runs at SessionStart and PostCompact **outside the
  outq entirely**, so it is immune to the drain starvation the prior plan measured
  (position 20 of 22, shown once across six sessions in a day). Extend its line format
  with box counts and add two summary lines: `8 plan file(s) carry 88 open box(es) and 24
  ticked, tree-wide.` / `2 of them are in scope for the stop advisory; 6 are exempt by
  Status.` Bounded, queue-free, fires every session start, and it reports the 72 boxes the
  status blocklist hides -- which is the number the operator is reacting to.
- **S2, show 3 plans per stop, not 1.** `_pf_rows[0]` -> `_pf_rows[:3]`, with
  `PLAN_TASK_SHOW` shared ACROSS them rather than per plan. Design note 2's argument is
  about quoted lines being a wall; three one-line headers is not a wall, and a global
  budget preserves the note's reason rather than its number.
- **S3, demote NOT_STARTED from exempt to census.** Three tiers: FINISHED skipped;
  NOT_STARTED as a one-line census row with no quotes and no recipes; everything else
  today's full treatment. Recovers 72 of the 88 invisible boxes at one line each.
- **S4, do NOT ship `--adopt` / `T_MISSION` yet.** It asks the operator to let an
  unclaimed committed document block an unrelated session -- correctly escalated as
  decision 1 by the prior plan. With A1-A6 in CI the silenced box is caught at merge
  anyway, so the blocking rung is no longer the only backstop and can wait until the
  operator has seen S1-S3 fire. Its PARSER refactor (`plan_task_marks`, `[?]`/`[>]` as
  first-class marks) IS worth pulling forward: A1's "parked, not vanished" exit needs
  those marks to exist.

### Controls

Internal `--selftest` before any verdict, `check_bws_map.py`-style:

- **C-FENCE**: a fixture with a fenced `- [ ]`, a mid-line prose `- [ ]`, and one real box
  must yield open == 1. Then plant the naive `re.findall(r'- \[ \]', text)` and assert
  C-FENCE FAILS against it -- a defect-detector that cannot detect the historical defect
  declares itself broken.
- **C-REAL-FENCE**: against the real tree, `PLAN-fix-in-session-rule.md` must parse to 0
  open boxes despite one raw hit, and `PLAN-secret-namespace-migration.md` to 14, not 16.
- **C-PARSER-IDENTITY**: the gate's sigs must equal `wl_planfile.plan_boxes` for every
  plan, so nobody can "optimise" the import away later.
- **Sig collision count on today's 88 boxes must be zero**; if not, widen the sig to
  include the plan path.

`.ci/scripts/test/gates/test-plan-boxes.sh`, 18 cases modelled on `test-bws-map.sh`, ten
planted defects and four proving the gate stays QUIET on legitimate work:
`clean_fixture_passes`, `deleted_box_reds`, `debulleted_box_reds`, `fenced_box_reds`,
`retexted_box_reds`, **`ticked_box_passes`** (or the gate teaches agents not to tick),
`rewrapped_box_passes`, `archive_r100_passes`, `archive_edited_reds`,
**`archive_edited_two_commits_reds`** (the load-bearing case), `archive_modified_reds`,
`status_done_over_open_reds`, `status_draft_over_open_passes`, `new_plan_no_owner_reds`,
`stale_ledger_reds`, `young_delete_reds`, **`aged_delete_passes`** (the seam, proven not
to deadlock), `empty_tree_reds`.

`.ci/scripts/test/gates/test-plan-housekeeping.sh`, 10 cases, backdating with
`GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` as `test-age-check.sh:26-30` already does. The two
no existing gate has: `git clone --depth 1` with `CI=true` must red with "cannot answer",
and the same with `CI` unset must print SKIPPED and exit 0. Plus `case 2`: a plan
committed 40 days ago but AMENDED 5 days ago must pass -- the case that makes the
last-commit-vs-added-date decision testable rather than asserted.

### Wiring

Three points each, plus two easy-to-forget fourths.

- `package.json`: `"check:ci-plan-boxes": ".ci/scripts/quality/check_plan_boxes.py"` and
  `"check:ci-plan-housekeeping": ".ci/scripts/quality/check-plan-housekeeping.sh"`.
- `scripts/ci-runner/manifest.ts`: one gate entry each plus a `gate-test:` entry each with
  `qualityGateTest: true` (assertion 7 compares that set to the on-disk glob). **The
  comment goes ABOVE the opening brace** -- `wl_reggate._manifest_gate_ids` matches
  `/\{\s*id:/`, and a comment inside the brace makes the entry invisible to
  `check:ci-gate-reachability-coverage` (documented at manifest.ts:322).
- `ci-quality.yml`: `Plan checkbox ledger` in `quality-branch` (bare path, that lane's
  convention, `if: !cancelled()` since it has no `steps.setup`); `Plan file housekeeping`
  in `quality-i18n` (npm key, `if: !cancelled() && steps.setup.outcome == 'success'`,
  which 178 steps in the file already use and zero deviate from). Step names must match
  the manifest byte-for-byte.
- Fourth: register `check_plan_boxes.py` in `test-gate-anti-vacuity.sh`'s `REGISTRY`.
- Cost note: under `filter: blob:none`, reading base-side blobs triggers on-demand
  fetches. `git diff --name-status --find-renames` FIRST (trees only, free), then
  `git show` only the flagged paths plus the two ledger blobs.

## Tasks

- [ ] Land the ledger alone: `check_plan_boxes.py` with A0 and A6 only, generate `.ci/config/plan-boxes.json`, wire three points plus the anti-vacuity registry
- [ ] Add `Owner:` headers to `PLAN-secret-names-one-to-one.md` and `PLAN-secret-namespace-migration.md` so A4 is green
- [ ] Turn on A1, A3, A4, A5 with `--selftest` and `.ci/scripts/test/gates/test-plan-boxes.sh` (18 cases)
- [ ] Turn on A2 and create `agent/archive/plans/.gitkeep`; move `agent/archive/0730-2/PLAN-stop-hook-migration.md` in (0 boxes, free). Do NOT migrate anything else -- there is nothing pre-existing
- [ ] Create `.ci/config/plan-lifecycle.json` with `warn_days` 26 / `delete_days` 33, referenced by BOTH gates so their delete predicates cannot deadlock
- [ ] Write `.ci/scripts/test/gates/test-plan-housekeeping.sh` FIRST (10 cases) -- with zero live offenders it is the only evidence the age gate is not a comment
- [ ] Write `.ci/scripts/quality/check-plan-housekeeping.sh` until that selftest passes; wire it into `quality-i18n`
- [ ] Create `.plan-housekeeping-allowlist` (header comment, zero entries) and add its row to `docs/agent-reference/suppressions.md`'s Current sites table
- [ ] Delete the 19 finished-and-uncited plans to flatten the 2026-09-23 cliff (list in the age agent's report; 33 of 61 are FINISHED, 19 of those cited by nothing outside `agent/`)
- [x] Ship S1, the SessionStart census -- cheapest change here and the operator-visible half; do not let it wait on the CI work
      DONE 2026-09-03: wl_checks.plan_box_census + plans_block now carry per-plan box
      counts and two tree-wide summary lines. Live output: "10 plan file(s) carry 82 open
      box(es) and 38 ticked, tree-wide. / 3 of them are in scope for the per-stop advisory;
      7 are exempt by Status, so their boxes are counted HERE and nowhere else." That last
      clause is the measurement this whole item existed for. Nine controls in
      test-planfile.py, planted on a `draft` plan (the status the advisory DROPS) with an
      in-scope pair beside it, a two-plan case proving the totals SUM, and a prose-only
      plan proving a boxless file grows no misleading suffix. Proven able to fail: making
      every plan count as in-scope reds three of them.
      CORRECTION worth carrying: the first cut wrapped the parser import in
      try/ImportError for "blindness" and wrote a control for that arm. wl_checks:27
      already imports wl_planfile at module level, so the arm was UNREACHABLE and the
      control had to fake sys.modules to reach it -- a control for a branch production
      cannot take. Both removed rather than kept as decoration.
- [x] Ship S2 and S3, and amend `wl_planfile`'s design notes 2 and 4 to cite the measurement that overtook them
      DONE 2026-09-03, and BOTH design notes amended rather than left behind.
      S2: render_all shows up to PLAN_PLANS_SHOW plans sharing ONE PLAN_TASK_SHOW
      budget -- three plans now cost exactly as many quoted recipes as one did.
      Note 2's NUMBER moves, its REASON (the wall is quoted lines, not headers) is
      what the shared budget preserves. Proven load-bearing: removing the spend
      makes it 9 recipes instead of 3.
      S3: NOT_STARTED becomes a third tier, not an exemption -- a one-line census
      row that demands nothing. Note 4's blocklist SHAPE and its FINISHED half are
      untouched; what stopped holding is "a proposal's boxes are a sketch".
      Three existing controls asserting "a draft plan is not checked" now assert the
      new contract instead, each with the pair that a census row DEMANDS nothing --
      otherwise it is the full treatment under another name. 119 controls pass.
- [ ] Pull forward the prior plan's parser refactor (`plan_task_marks`, `[?]`/`[>]` as first-class marks); A1's "parked, not vanished" exit needs it
- [ ] Confirm cheat 13's exposure against the branch ruleset before treating it as closed
