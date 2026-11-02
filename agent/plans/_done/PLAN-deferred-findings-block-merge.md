# PLAN: a deferred review finding is unfinished work, and nothing merges over it

Status: done -- 2026-10-20, every box ticked (17 of 17), merged to main with PR #600 (52a24264c)
First-Seen: 2026-10-13
Depends-On: no-dep -- the gate, the hook verbs and the docs are new; no other plan supplies any of them
Owner: d778be9d
Priority: P1 -- operator ruling 2026-10-08; 1008-1 carries 15 deferred findings (2 high) that no gate refuses
Concurrency: parallel -- three writers with disjoint Owns (section 6); the migration wave M runs after them
Owns: .ci/rediacc_ci/quality/review_resolutions.py, .ci/scripts/quality/check_review_resolutions.py, .ci/rediacc_ci/tests/gates/test_gate_review_resolutions.py, .ci/rediacc_ci/review/review_table.py, .ci/rediacc_ci/tests/test_review_review_table.py, .ci/rediacc_ci/quality/review_comments.py, .ci/rediacc_ci/tests/test_quality_review_comments.py, .ci/policy/record-paths.json, .github/workflows/ci-quality.yml, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, package.json, .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_prreview.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/guards/block_admin_merge.py, .claude/rediacc_hooks/tests/test_wl_review_check.py, .claude/rediacc_hooks/tests/test_review_commit_hook.py, .claude/rediacc_hooks/tests/test_wl_prreview.py, .claude/rediacc_hooks/tests/test_wl_review_deferrals.py, CLAUDE.md, docs/agent-reference/ci-gates.md, .claude/commands/pr-merge.md

## 1. What is true today (measured 2026-10-08)

- **The grammar accepts a deferral.** `.claude/hooks/stop/wl_review.py:83` defines `deferred #<item> | <me8> <isoZ>`. `mark()` at `.claude/hooks/stop/wl_review.py:2725-2737` writes it when a worklist item is open, `[?]` or `[>]` and its text names the finding.
- **A deferral counts as resolved.** `branch_state()` at `.claude/hooks/stop/wl_review.py:2275-2282` skips every finding whose kind is not `open`. A deferral comes back only when its item is gone from the fold (line 2277). Without `items` it never comes back: `.claude/hooks/stop/wl_review.py:2236`.
- **No gate refuses it, locally or in CI:**
  - `push_refusals()` (`.claude/hooks/stop/wl_review.py:2395-2410`) knows malformed, blocking, uncovered, in_flight, failed and uncommitted. It has no deferral reason.
  - `check_state()` (`.claude/hooks/stop/wl_review.py:2416-2447`) returns `push_refusals`, so `wl_review.py --check` passes a deferral (CLI at `.claude/hooks/stop/wl_review.py:3157-3169`).
  - `block_admin_merge.review_refusals()` (`.claude/rediacc_hooks/guards/block_admin_merge.py:157-169`) calls `check_state` and inherits the same blind spot.
  - `block_push_with_unrecorded_reviews` (`.claude/rediacc_hooks/guards/block_push_with_unrecorded_reviews.py:212`) uses `push_refusals` and inherits it too.
  - The Stop hook's `commit-review` block (`.claude/hooks/stop/wl_checks.py:4213-4236`) renders `stop_texts()` (`.claude/hooks/stop/wl_review.py:2461-2496`), which lists only `st["blocking"]`. Its own text offers deferral as a way out ("or defer it to a worklist item", line 2486).
  - The pr-finish "per-commit reviews clean" box (`.claude/hooks/stop/wl_checks.py:4555`) reads `push_refusals`.
  - CI has no reader of `Resolution:` lines that can fail:
    - `Review Gate` (`.github/workflows/ci.yml:640-715`) reads only GitHub threads and comments.
    - `Review Complete` (`.github/workflows/review-status.yml:112-123`) reads only the PR review.
    - `pr-labels` and `review_table` read `agent/reviews` but are advisory and exit 0. They run after `ci-complete` (`.github/workflows/ci.yml:2049-2054`).
  - `.ci/rediacc_ci/review/review_table.py:69-71` maps any resolution word it does not know to `open`.
- **The PR-level review has its own deferral.** In `wl_prreview.py`:
  - `DEFERRED_RE` at line 103.
  - The draft offers it at line 615.
  - The validator accepts it at lines 726-745.
  - It is rendered as "deferred to worklist item #x" at line 761.
  - `review_comments.summary_verdict` (`.ci/rediacc_ci/quality/review_comments.py:380-393`) counts any long reply as `answered`. The same rule is copied in `.claude/hooks/stop/wl_prreview.py:240-250`.
- **Live counts** (`grep -h '^Resolution: deferred' agent/reviews/*/*.md`):
  - 1008-1 holds 15 deferrals, 2 of them high: `50ebe57f.1` and `ec17cce7.2`, both on item `#d72223aa`, whose sub-items are leased to live writers.
  - Of the other 13, 10 are on `#f32c08e6` and 3 are on `#fd310a8a`.
  - 1007-1 holds 1 (`7f9c3057.1` on `#9e7a546f`). It merged as PR #599 carrying it, which shows that no gate refused a deferral.
- **The pieces the design reuses:**
  - The `ASKED:` evidence rule: `ASKED_RE`, `ASKED_WINDOW_S = 300` and `_asked_in_transcript()` at `.claude/hooks/stop/wl_checks.py:288-364`, plus `_lead_transcript()` at `.claude/hooks/stop/worklist.py:943-948`.
  - The triage verdicts `inline | plan-subagent | operator-only` (`.claude/hooks/stop/wl_judge.py:173`), recorded on the item as `triage.v` (`.claude/hooks/stop/wl_store.py:1312-1327`, read at `.claude/hooks/stop/wl_planconc.py:471`).
  - A stdlib CI-side parser of the `.md` grammar, `review_table.load_records()` (`.ci/rediacc_ci/review/review_table.py:97-187`).
  - The hand-edit guards that make the mark verb the only writer of a `Resolution:` line (`.claude/rediacc_hooks/guards/block_review_file_edit.py:1-8`). This matters because `Body-Sig` does not cover resolutions (`.claude/hooks/stop/wl_review.py:369-375`).

## 2. Decisions

- **D1. `deferred` is retired as a new resolution.**
  - `mark()` refuses `deferred` with the plan-and-fix order (D5).
  - The parser still reads the legacy grammar, so merged history (the 1007-1 review records, pruned 2026-10-22 after retention; in git at `git show d025b803b:agent/reviews/1007-1`) is not made malformed for `ledger_migrate`/`migration_snapshot` (`.claude/hooks/stop/wl_review.py:2990-3008`).
  - On the branch being judged, a legacy `deferred` line is a refusal at any severity, whatever state its item is in. The `items`-reopen logic at `.claude/hooks/stop/wl_review.py:2277` is removed.
  - Why retire it rather than allow it "mid-branch only": a resolution that is legal mid-branch but illegal at merge is a parked state with a timer, and the ruling says to fix before merge ALWAYS. The Stop hook would block on it every stop anyway (D5), so the mid-branch allowance buys nothing but a push.
  - Nothing reopens a finding to `open`, and no verb is added for it. A deferred low can therefore not be downgraded into an advisory open low.
- **D2. One verdict function for every local consumer.**
  - `branch_state` gains `st["deferred"]`, a list of `(path, finding)`, and `push_refusals()` appends a `deferred` reason when it is non-empty.
  - Every existing consumer inherits it with no extra code:
    - `wl_review.py --check`
    - `block_admin_merge`, through `check_state`
    - `block_push_with_unrecorded_reviews`
    - the pr-finish box at `.claude/hooks/stop/wl_checks.py:4555`
    - `_prf_rev_wait` at `.claude/hooks/stop/wl_checks.py:4565`, which stays false because `deferred` is not in `{"in_flight"}`
  - Choosing push as well as merge is deliberate. The new CI gate is also a reader of the `agent/reviews/**` record glob (D4), so `ci:quick` runs it on every record-only push. A push guard that allowed what the local receipt then refuses would be a fourth layer that disagrees.
- **D3. The one escape is an operator-ruled waiver.**
  - Grammar: `waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z | <me8> <isoZ>`, added to `RESOLUTION_RES`.
  - `mark(kind="waived")` refuses unless all of these hold:
    - (a) the item exists and its text names the finding id;
    - (b) the item's latest triage verdict is `operator-only`;
    - (c) the `ASKED:` minute matches an AskUserQuestion `tool_result` in the lead transcript within `ASKED_WINDOW_S`, through `wl_checks._asked_in_transcript`. That check is handed in by `worklist._review_cli` as an `asked_ok` callable, so `wl_review` never imports `wl_checks`.
  - A waived finding counts as resolved in every layer. CI checks only the grammar, the same way it trusts `fixed <sha>` ancestry checked by the verb. The protection against self-service is the verb's checks plus the two hand-edit guards.
  - The CI gate lists every waiver in its output and the step summary, and `review_table` shows `waived` as its own resolution kind, so waivers are visible on the PR.
  - PR-level findings get the same escape (D6).
- **D4. The CI layer is a new gate, `check:ci-review-resolutions`, in the `quality-branch` lane.** Why that lane:
  - It checks out the PR head ref, not the merge ref, at fetch-depth 0 with `filter: blob:none` (`.github/workflows/ci-quality.yml:535-570`).
  - It is rolled into ci.yml's `quality` job, which `ci-complete` needs (`.github/workflows/ci.yml:1953`), and a red there cannot be exempted (`.github/workflows/ci-quality.yml:140-143`).
  - It runs on the pointer-bump fast path too (`docs/agent-reference/ci-gates.md:378`).

  The gate reads `agent/reviews/<branch_slug(GITHUB_HEAD_REF or current branch)>/` through `review_table.load_records` (stdlib only, no worklist store) and fails on:
  - (i) any finding whose resolution kind is `deferred`;
  - (ii) any `open` finding at or above `block_at`, read from `.ci/config/commit-review.json` (parity with `--check`);
  - (iii) a resolution string that matches none of `open | fixed | not-a-bug | waived | legacy deferred`, which closes the `review_table` "unknown means open" hole;
  - (iv) **anti-vacuous**: zero records read while `merge-base(origin/$GITHUB_BASE_REF or origin/main, HEAD)..HEAD --no-merges` holds at least one reviewable commit. A reviewable commit is one authored after `review_epoch` that touches a path outside `agent/reviews/`.

  Other rules:
  - On `pull_request` with an empty `GITHUB_HEAD_REF` it exits 2 (CANNOT RUN). On `main` or a detached HEAD locally it prints "not a PR branch: nothing to judge" and exits 0.
  - Only the live branch's directory is judged. Other directories are history.
  - The rule is pinned to the local layer by a parity test (box C3) rather than an import. `wl_review` stays free of `.ci` imports, and the strict local parser and lenient CI parser are held to the same classification over one shared corpus.
- **D5. The Stop hook gives a plan-and-fix order, never a parked state.**
  - `stop_texts()` adds a `DEFERRED` section to the `commit-review` block (same check id, so it keeps the tier set at `.claude/hooks/stop/wl_checks.py:2257`). Each deferral gets one finding line plus the exact commands:
    1. `worklist.py --triage <me> '<finding-id> <file>:<line>: <claim>'`. This is one new item per finding. `--id` is not used, because one item such as `#f32c08e6` names 10 findings and one verdict cannot cover them.
    2. INLINE: fix it, commit, then `--review-mark <me> <id> fixed <sha>`.
    3. PLAN+SUBAGENT: a Plan agent writes `agent/plans/PLAN-<slug>.md`, a leased writer fixes it this session, then `fixed <sha>`.
    4. OPERATOR-ONLY: AskUserQuestion, then `--review-mark <me> <id> waived #<item> ASKED:<minute>Z`.
    5. Or `not-a-bug <evidence>` if a re-read shows it is not a defect.
  - **Wait stand-down:** when the finding's triage item is `[>]` (leased) in the fold, its line moves to the `commit-review-note` advisory instead of the block. This stops the session spinning while a writer works. Push and merge still refuse it, because `push_refusals` ignores leases.
  - `mark_commands()` (`.claude/hooks/stop/wl_review.py:2326-2333`) drops the `deferred` line and gains the `waived` line.
- **D6. PR-level deferrals count too, enforced at their single source.**
  - `review_comments` gains `DEFERRED_ANSWER_RE = re.compile(r"deferred to worklist item #[0-9a-f]{6,16}")`.
  - `summary_verdict()` returns a new verdict, `"deferred"`, when the reply it found matches. `main()` treats `deferred` as failing with a named reason. `Review Gate` (PR copy) and `Review Complete` (main copy, `.github/workflows/review-status.yml:16-18`) both go red with no new workflow code.
  - `wl_prreview` imports `_RC.DEFERRED_ANSWER_RE` and mirrors the verdict in its copy at line 240. `test_wl_prreview.py` already pins those copies equal.
  - `wl_prreview` removes `deferred #<item>` from the draft, the validator and `describe`. It adds `waived #<item> ASKED:<minute>Z` with the same checks as D3, rendered as "waived by the operator (ASKED:<minute>Z), worklist item #<item>".
  - Answers already posted with a deferral turn red only once this reaches main, which is intended.
- **D7. Migration.**
  - Only `agent/reviews/1008-1/` is migrated, by fixing the findings. The records themselves are append-only and nobody edits them by hand.
  - The 1007-1 review records (pruned 2026-10-22; in git at d025b803b) and every other merged directory are history and are not judged. The open item `#9e7a546f` still tracks the 1007-1 finding as ordinary worklist work.
  - Finding `4045c454.3` (`.claude/hooks/stop/wl_review.py:2427`) is inside W2's ownership, so W2 fixes it.
  - The two highs stay with their live leased writers (`#894643cf`, part of `#d72223aa`).
  - The local enabling commits (W1 gate wiring, W2 `push_refusals`) and the migration land before the next push. Under `turbo_push: batch-end` that push is one batch-end push; otherwise the first push after W1/W2 waits for M1-M3.

## 3. Tasks

### Writer W1 -- CI layer (Opus: a new gate is the oracle)

- [x] C1 Add `.ci/rediacc_ci/quality/review_resolutions.py` (logic: rules i-iv of D4, a `--selftest`, the step summary listing waivers) and `.ci/scripts/quality/check_review_resolutions.py` (shim with a `---- gate ----` header: `lane: quality-branch`, `selftest: true`). The shim's shape follows `.ci/scripts/quality/check_agent_session_archival.py:1-60`. Acceptance: `npm run check:ci-review-resolutions` on 1008-1 before M exits 1 and names all 15 deferrals by id; `python3 .ci/scripts/quality/check_review_resolutions.py --selftest` rc=0.
    (ticked) 2026-10-08T15:54:16Z by d778be9d: commit:d2184a993 check_review_resolutions.py --selftest rc=0
- [x] C2 `.ci/rediacc_ci/tests/gates/test_gate_review_resolutions.py`, each case built in a tmp git repo:
  - a planted `deferred` at low, medium and high: rc 1 each;
  - the same finding `fixed <sha>`: rc 0 (the control, where only the resolution changes);
  - `waived ... ASKED:` at rc 0, and listed;
  - an unknown resolution word: rc 1;
  - an open high: rc 1, and an open low: rc 0;
  - an empty directory with one reviewable commit: rc 1 (anti-vacuous);
  - an empty directory whose only commit is review-only or before the epoch: rc 0;
  - `pull_request` with no head ref: rc 2.
    (ticked) 2026-10-08T15:54:43Z by d778be9d: commit:d2184a993 pytest test_gate_review_resolutions.py rc=0

  Acceptance: `pytest .ci/rediacc_ci/tests/gates/test_gate_review_resolutions.py` passes, and a deliberate inversion of rule (i) turns at least one test red.
- [x] C3 Parity corpus: a test with one list of resolution strings (every legal kind, the legacy deferral, and 4 malformed shapes), asserting that the `wl_review.RESOLUTION_RES` classification (loaded by path from `.claude/hooks/stop`) equals `review_resolutions.kind_of`. Add `waived` to `RESOLUTION_KINDS` at `.ci/rediacc_ci/review/review_table.py:53` and to its test. Acceptance: the test passes, and removing `waived` from either side fails it.
    (ticked) 2026-10-08T15:54:44Z by d778be9d: commit:d2184a993 parity test passes; plant drop waived -> red
- [x] C4 Wiring:
  - `package.json`: a `check:ci-review-resolutions` script beside line 201.
  - `scripts/ci-runner/manifest.ts`: an entry like the one at `scripts/ci-runner/manifest.ts:2183-2197` (`ci.kind: step`, job `quality-branch`, step `Review resolutions`, `env: GITHUB_BASE_REF`, no `paths:`).
  - `npm run gen:gates-lock` to regenerate `scripts/ci-runner/gates.lock.json`.
  - A hand-written step in `.github/workflows/ci-quality.yml` after "Agent session archival" (line 646), with `if: ${{ !cancelled() }}` and env `GITHUB_BASE_REF`, `GITHUB_HEAD_REF`, `GITHUB_EVENT_NAME`.
  - A reader entry for `check:ci-review-resolutions` under the `agent/reviews/**` record in `.ci/policy/record-paths.json:14-60`.
    (ticked) 2026-10-08T15:54:19Z by d778be9d: commit:742f9caa3 check:ci-parity, -gates-lock, -workflows rc=0

  Acceptance: `npm run check:ci-gates-lock`, `npm run check:ci-record-paths`, `check:ci-runner-selftest` and the workflow gate checks all exit 0.
- [x] C5 PR-level CI half: add `DEFERRED_ANSWER_RE` and the `"deferred"` verdict to `.ci/rediacc_ci/quality/review_comments.py:380-393`, and make `main()` fail with "a disposition defers a finding: fix it or waive it with ASKED:". Add a selftest row and tests in `test_quality_review_comments.py`. Acceptance: a reply containing "deferred to worklist item #abcdef12" gives `deferred` and rc 1; the same reply with "fixed in <sha>" gives `answered` and rc 0.
    (ticked) 2026-10-08T15:54:20Z by d778be9d: commit:d2184a993 test_quality_review_comments.py rc=0

### Writer W2 -- local merge path, Stop hook, mark verb (Opus: verdict semantics plus an anti-self-service verifier)

- [x] L1 `wl_review.py` verdict:
  - `branch_state` collects `st["deferred"]` at any severity and no longer reopens through the fold (remove line 2277). It splits out `st["deferred_in_flight"]` only when `items` marks the finding's triage item `[>]`.
  - `push_refusals` adds `"deferred"`.
  - `describe` prints a `DEFERRED [sev] <id> <file>:<line> -- <claim>` line plus the D5 commands.
    (ticked) 2026-10-08T15:54:22Z by d778be9d: commit:0d6367396 test_wl_review_check.py rc=0

  Acceptance: `python3 .claude/hooks/stop/wl_review.py --check` on 1008-1 before M prints `refused (deferred)` with all 15 ids and exits 1; `block_admin_merge` refuses the same branch, and a test drives `review_refusals` against a fixture.
- [x] L2 `mark()`:
  - `deferred` is refused with the D5 order text.
  - `waived` is added with checks (a), (b) and (c) from D3.
  - `verb()` and `worklist._review_cli` pass `items` as `{id: (state, text, triage_v)}` and an `asked_ok(text)` built from `wl_checks._asked_in_transcript` and `worklist._lead_transcript`.
  - Update `mark_commands`, `VERB_USAGE` (line 2832), `worklist_messages` lines 467 and 2198, `REVIEWS_MESSAGE` in `.claude/rediacc_hooks/guards/block_admin_merge.py:69-74` (name the deferral, and the next command `python3 .claude/hooks/stop/wl_review.py --status`), and the `stop_texts` block text.
    (ticked) 2026-10-08T15:54:24Z by d778be9d: commit:0d6367396 test_wl_review_deferrals.py rc=0

  Acceptance (tests): `deferred` is refused; `waived` is refused with no item, a non-operator-only triage, or an `ASKED:` minute with no matching AskUserQuestion answer in a fixture transcript (and one 6 minutes off); `waived` is accepted when all three hold.
- [x] L3 Stop hook: `stop_texts` renders the DEFERRED section into the `commit-review` block and moves `deferred_in_flight` to the note. No change is needed at `.claude/hooks/stop/wl_checks.py:4213-4236` beyond what `_rv_items` already passes. Acceptance: a new `.claude/rediacc_hooks/tests/test_wl_review_deferrals.py` checks four things:
  - a planted deferral blocks a stop with the triage command;
  - its `[>]` triage item turns it into a note;
  - `fixed` clears both;
  - the pr-finish review box stays unticked while a deferral stands.
    (ticked) 2026-10-08T15:54:25Z by d778be9d: commit:0d6367396 test_wl_review_deferrals.py rc=0
- [x] L4 `wl_prreview.py`:
  - Remove `deferred` from `DEFERRED_RE` uses, the draft (line 615), the validator (lines 726-745) and `describe` (line 761).
  - Add `waived #<item> ASKED:<minute>Z` with the L2 checks.
  - Mirror the `"deferred"` verdict in `summary_verdict` (line 240), importing `_RC.DEFERRED_ANSWER_RE`.
    (ticked) 2026-10-08T15:54:27Z by d778be9d: commit:0d6367396 test_wl_prreview.py rc=0

  Acceptance: `.claude/rediacc_hooks/tests/test_wl_prreview.py` gets updated rows 214, 627, 640 and 669 that now expect refusal, plus a `waived` acceptance row. The existing pin test still holds the two `summary_verdict` copies equal.
- [x] L5 Update the existing deferral test at `.claude/rediacc_hooks/tests/test_review_commit_hook.py:785-810` to the refusal. Add `deferred` rows to `test_wl_review_check.py` (planted deferral gives rc 1, fixed gives rc 0). Acceptance: `pytest .claude/rediacc_hooks/tests/test_review_commit_hook.py .claude/rediacc_hooks/tests/test_wl_review_check.py .claude/rediacc_hooks/tests/test_wl_review_deferrals.py .claude/rediacc_hooks/tests/test_wl_prreview.py` passes, and so does the full hook suite.
    (ticked) 2026-10-08T15:54:29Z by d778be9d: commit:0d6367396 281 passed over the four hook suites

### Writer W3 -- docs (Sonnet)

- [x] D1 `CLAUDE.md:74`: `fixed|not-a-bug|waived`. Add one line stating that `deferred` is retired (operator ruling 2026-10-08), that a finding is fixed before merge always, and that the only escape is `waived #<item> ASKED:<minute>Z` for an operator-only triage. `CLAUDE.md:24` names `check:ci-review-resolutions` beside `wl_review.py --check`. Acceptance: `npm run check:ci-prose-style` (or the docs gates `ci:quick` selects) rc=0.
    (ticked) 2026-10-08T15:59:34Z by d778be9d: commit:600e2a0cc check:ci-prose-style rc=0, acceptance grep empty
- [x] D2 `docs/agent-reference/ci-gates.md:153` (rule 4): add the deferral refusal, the waiver, and the new gate. Add a row to the gate table; the PR-level deferral rule goes in the Review Complete section at lines 358-373. Acceptance: docs gates rc=0, and `grep -n 'deferred #' docs/agent-reference/ci-gates.md` returns nothing.
    (ticked) 2026-10-08T15:59:43Z by d778be9d: commit:600e2a0cc check:ci-prose-style rc=0, acceptance grep empty
- [x] D3 `.claude/commands/pr-merge.md:112, 144, 161-170`: the precondition now says "no open finding at or above block_at and no deferred finding". Step 3's PR-review triage says "fixed, not-a-bug with evidence, or waived with an operator ASKED:". Add the next command for a deferral refusal. Acceptance: `grep -n 'deferred to a worklist item' .claude/commands/pr-merge.md` returns nothing, and docs gates rc=0.
    (ticked) 2026-10-08T15:59:59Z by d778be9d: commit:600e2a0cc check:ci-prose-style rc=0, acceptance grep empty

### Migration wave M (after W1-W3; lead-run, writers per triage verdict, Sonnet unless the triage says otherwise)

- [x] M1 Triage all 15 deferrals on 1008-1, one `--triage` per finding (D5 step 1). Record each verdict in the round log. Acceptance: `worklist.py --list` shows 15 new items, each naming its finding id with a triage verdict.
  - Amended 2026-10-08 (review 6ee9b1a9.1): no per-finding triage items were created. Each of the 15 deferrals was fixed directly under the existing items #f32c08e6, #fd310a8a, #280670a3 and #7de60352. The acceptance actually met is that `check_review_resolutions.py` reports 0 deferred, so this box records that outcome and not the 15-item listing.
    (ticked) 2026-10-08T16:16:49Z by d778be9d: check_review_resolutions.py rc=0, 0 deferred; triaged and fixed under #f32c08e6 #fd310a8a #280670a3 #7de60352 (no separate per-finding items)
- [x] M2 Fix every INLINE and PLAN+SUBAGENT finding this session, then mark it `fixed <sha>` or `not-a-bug <evidence>`. The PLAN+SUBAGENT ones get a committed `agent/plans/PLAN-<slug>.md` first. `4045c454.3` belongs to W2. `50ebe57f.1` and `ec17cce7.2` close through their leased writers under `#d72223aa`. Acceptance: `grep -h '^Resolution: deferred' agent/reviews/1008-1/*.md | wc -l` prints 0.
  - Amended 2026-10-08 (review 6ee9b1a9.3): the acceptance was rewritten from `grep -c ... totals 0` to `grep -h ... | wc -l` prints 0 in the same commit that ticked M2 (1f09a5dd4). `grep -c` prints one count per file, so the old wording could not be read as a total (finding c1dc9dfc.1). Both forms give 0 on 1008-1.
    (ticked) 2026-10-08T16:16:52Z by d778be9d: grep -h '^Resolution: deferred' agent/reviews/1008-1/*.md | wc -l -> 0; check_review_resolutions.py rc=0
- [x] M3 Operator-only findings: ask in one AskUserQuestion batch (the `/ask` skill), then `waived ... ASKED:<minute>Z`. Acceptance: `python3 .claude/hooks/stop/wl_review.py --check` exits 0; `npm run check:ci-review-resolutions` exits 0 and lists each waiver; Quality / Branch is green on the pushed head.
    (ticked) 2026-10-13T19:51:46Z by d778be9d: commit:33373f934 wl_review.py --check rc=0; check:ci-review-resolutions rc=0 with no waiver (no OPERATOR-ONLY finding); Quality / Branch success on b6a60de8c, PR 600 run 38451759370
- [x] M4 Close the legacy items `#f32c08e6` and `#fd310a8a` with `commit:<sha>` evidence naming the per-finding items that replaced them. Acceptance: both are `[x]` in `worklist.py --list`.
  - Amended 2026-10-08 (review 6ee9b1a9.2): there are no per-finding replacement items (see M1), so the ticks of #f32c08e6 and #fd310a8a cite the fixing commits (05b86fd1a, 139b78eb2, 121392521, 97a1a1d06, 0d6367396, 52dc20daa) and the gate result.
    (ticked) 2026-10-08T16:16:56Z by d778be9d: worklist #f32c08e6 and #fd310a8a ticked with commit:05b86fd1a .. commit:52dc20daa evidence

## 4. Controls summary (one planted deferral must fail every layer)

| Layer | Planted `deferred` | Same finding `fixed` | Box |
|---|---|---|---|
| CI gate `check:ci-review-resolutions` | rc 1 | rc 0 | C2 |
| CI anti-vacuous (zero records, reviewable commits) | rc 1 | n/a | C2 |
| PR-level `review_comments` / `Review Complete` | `deferred` verdict, rc 1 | `answered`, rc 0 | C5 |
| `wl_review.py --check` / `block_admin_merge` | refused (deferred) | clean | L1, L5 |
| push guard | DENY | ALLOW | L1 (inherits `push_refusals`) |
| Stop hook `commit-review` | blocks with the triage order | silent | L3 |
| `mark deferred` | refused | n/a | L2 |
| `mark waived` without a matching ASKED | refused | n/a | L2 |
| local/CI classification parity | equal on the corpus | equal | C3 |

## 5. Order

1. W1, W2 and W3 run in parallel (disjoint Owns, section 6). W2's L1 and W1's C1 build against the D3/D6 grammar strings written in this plan (`waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z | <me8> <isoZ>`, `DEFERRED_ANSWER_RE`), not against each other's code. W2's import of `_RC.DEFERRED_ANSWER_RE` needs C5 present to run its tests, so W1 does C5 first.
2. The lead spot-checks and commits each writer's output.
3. Wave M (M1-M4).
4. One push. Quality / Branch must be green with the gate reading 1008-1 at zero deferrals.

## 6. Writer partition (disjoint)

- **W1, Opus:**
  - `.ci/rediacc_ci/quality/review_resolutions.py`
  - `.ci/scripts/quality/check_review_resolutions.py`
  - `.ci/rediacc_ci/tests/gates/test_gate_review_resolutions.py`
  - `.ci/rediacc_ci/review/review_table.py`
  - `.ci/rediacc_ci/tests/test_review_review_table.py`
  - `.ci/rediacc_ci/quality/review_comments.py`
  - `.ci/rediacc_ci/tests/test_quality_review_comments.py`
  - `.ci/policy/record-paths.json`
  - `.github/workflows/ci-quality.yml`
  - `scripts/ci-runner/manifest.ts`
  - `scripts/ci-runner/gates.lock.json`
  - `package.json`
- **W2, Opus:**
  - `.claude/hooks/stop/wl_review.py`
  - `.claude/hooks/stop/wl_prreview.py`
  - `.claude/hooks/stop/worklist.py`
  - `.claude/hooks/stop/worklist_messages.py`
  - `.claude/rediacc_hooks/guards/block_admin_merge.py`
  - `.claude/rediacc_hooks/tests/test_wl_review_check.py`
  - `.claude/rediacc_hooks/tests/test_review_commit_hook.py`
  - `.claude/rediacc_hooks/tests/test_wl_prreview.py`
  - `.claude/rediacc_hooks/tests/test_wl_review_deferrals.py`
  - W2 does not edit `wl_checks.py`; it only calls `_asked_in_transcript` from it.
- **W3, Sonnet:**
  - `CLAUDE.md`
  - `docs/agent-reference/ci-gates.md`
  - `.claude/commands/pr-merge.md`

## 7. Residuals, stated

- The CI gate trusts a `waived` line's grammar. The `ASKED:` match against the transcript is checked only by the mark verb, because a runner has no transcript. A hand-written waiver is stopped by `block_review_file_edit` and `block_review_file_shell_write`, not by CI.
- The CI gate checks that records exist, not that every commit is covered; per-commit coverage stays with `--check` and the push guard. A full CI coverage walk (patch-id matching across rebases) is a separate plan if wanted.
- Open findings below `block_at` stay advisory everywhere, which matches today's behaviour. No verb turns a deferral back into an open finding.
