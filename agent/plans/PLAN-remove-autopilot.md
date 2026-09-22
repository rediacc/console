# PLAN: remove Autopilot completely
Status: done
First-Seen: 2026-09-22
Operator ask: remove the GitHub-side CI autonomy feature ("Autopilot", docs/ci-overhaul/03-v2-autonomy.md, `.github/workflows/autopilot.yml`) completely. Designed by a read-only Plan subagent; every path/line below was opened and read, not inferred from grep alone.

Landed 07e97e99a (the mechanical bulk: 738 files deleted, package.json/manifest.ts/gates.lock.json/labels.yml/env-manifest.json/secret-supply.json/docs all updated) plus 4e5781b7b (the follow-up drain: three more shrink-only baselines and registries the removal agent found beyond the plan's original scope).
Independently re-verified the same session: zero leftover `rediacc_ci.autopilot` imports, `gen-gates-lock`/`gen-docs`/`check:ci-parity`/`check:ci-dead-bash`/`check:ci-shape-duplication`/`check:ci-label-inventory` all green.

## 0. Scope check performed first

- `packages/www/public/assets/tutorials/...` and `packages/www/src/data/tutorial-*`:
  confirmed coincidental. The one hit (`tutorial-storage-management.en.vtt`: "...from install to autopilot storage...") is marketing copy for automated storage, not the CI feature. **Excluded from scope, untouched.**
- `.ci/rediacc_ci/tests/goldens/{review-comments,review-report-replies,review-turn-capacity,
  cleanup-cf-preview}`: zero occurrences of the string "autopilot" inside them despite living beside the real autopilot goldens alphabetically. They belong to the unrelated Claude-Review quality gates (`review_comments.py`, `review_turn_capacity.py`) and `cleanup_cf_preview.py`. **Excluded, untouched.**
- `.ci/shadow/w7p6-review-status.observations.jsonl`: the `cmd` field proves this shadows
  `.ci/rediacc_ci/review/review_status.py` (general Claude-Review status tracking, used by the babysitter loop, not Autopilot). **Excluded, untouched**, despite the name-adjacency to the 18 shadow files that genuinely are Autopilot's.

## 1. True dependency map

### (a) Autopilot-only, safe to delete outright

| path | what | lines/files |
|---|---|---|
| `.github/workflows/autopilot.yml` | the workflow | 1173 |
| `.ci/rediacc_ci/autopilot/*.py` (17 files incl. `__init__.py`) | the harness | 6490 |
| `.ci/rediacc_ci/quality/autopilot_no_bypass.py` | gate | 413 |
| `.ci/rediacc_ci/quality/autopilot_breakpoint_alignment.py` | gate | 404 |
| `.ci/rediacc_ci/security/autopilot_workflow_invariants.py` | gate | 414 |
| `.ci/scripts/quality/check_autopilot_breakpoint_alignment.py` | entrypoint | 40 |
| `.ci/scripts/quality/check-autopilot-no-bypass.sh` | still-bash, never cut over (see 1c) | 108 |
| `.ci/scripts/ci/autopilot-guide-comment.cjs` | PR comment writer | 124 |
| `.ci/scripts/autopilot/` (exfil-tripwire.cjs, validate-handoff.cjs, handoff.schema.json, prompts/fix-round.md, prompts/review-response.md) -- confirmed consumed ONLY by autopilot_push.py (node validate-handoff.cjs / node exfil-tripwire.cjs subprocess calls at push.py:217,222,304) | 919 |
| `.ci/rediacc_ci/tests/test_autopilot_*.py` (16 files) + test_quality_autopilot_no_bypass.py + test_security_autopilot_workflow_invariants.py | 18 files | 11794 |
| `.ci/rediacc_ci/tests/gates/test_gate_autopilot_*.py` -- 5 files, not 4: _breakpoint_alignment.py (153), _guide_comment.py (474, previously unlisted), _harness.py (3630 -- the big one, covers push+validate-handoff+exfil-tripwire together), _no_bypass.py (115), _workflow_invariants.py (502) | 5 files | 4874 |
| `.ci/rediacc_ci/tests/goldens/{autopilot-gate,autopilot-push,autopilot-workflow-invariants,compose-prompt,fetch-review-threads,finish,linked-sub-prs,post-escalation,resolve-model-args,restore-trusted-config,review-payload,review-reply,state-comment,submodule-prs,sweep-campaigns,sweep-collect,update-state}` -- 17 dirs, 667 files, not "~150+" | 667 files | 9860 |
| `.ci/shadow/w7p2-autopilot-no-bypass.observations.jsonl`, w7p6-autopilot-gate..., w7p6-autopilot-push..., w7p6-check-autopilot-workflow-invariants..., plus 14 more w7p6-<module>.observations.jsonl (compose-prompt, fetch-review-threads, finish, linked-sub-prs, post-escalation, resolve-model-args, restore-trusted-config, review-payload, review-reply, state-comment, submodule-prs, sweep-campaigns, sweep-collect, update-state) -- bash/Python parity proof logs for a migration that becomes moot once both sides are gone | 18 files | small |
| `docs/ci-overhaul/03-v2-autonomy.md` | the v2 design doc itself | 365 |

**Total: ~738 files deleted, ~37,000 lines removed.** This is the outright-delete set.

### (b) Shared infrastructure Autopilot merely used -- do NOT delete

- `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` (secret): also read by `claude-mention.yml`, `claude-review-reusable.yml`, `watchdog-monitor.yml`. **Keep.**
- `.ci/rediacc_ci/tests/goldens/allowlist/{corpus,ts-records,bash-pairs}/profiler-coverage-allowlist.*` (3 of 53 files in that dir): this is a generic allowlist-gate golden corpus (test_core_allowlist.py) that happens to snapshot `.profiler-coverage-allowlist`'s current content, which includes 4 autopilot rows.
**Do not hand-edit these goldens** -- fix the source allowlist file (1c below) and regenerate through whatever mechanism test_core_allowlist.py uses; hand-editing a golden here risks drifting the corpus from the real file it mirrors.
- `hookio`/`shellscan` (`.claude/rediacc_hooks/`), gitx.py, Controls, controls_first -- generic libraries autopilot's gates imported like everyone else. Nothing to do here beyond the citation notes in section 4.

### (c) Genuinely depends on / cites Autopilot, and needs a companion edit

- `.claude/hooks/stop/calibrate-judge-rules.py` SHAPE_CASES cites `.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh:40` and `:47` as duplication-detector fixture coordinates.
That path does not exist in the tree today -- it's a pre-existing dangling citation from an earlier bash-to-Python port wave, not something this removal creates.
Not machine-checked (no gate validates SHAPE_CASES coordinates), so it will not turn CI red either way. **Out of scope for this removal**; flagged so nobody "fixes" it thinking it's new breakage. If touched at all, it needs a real still-existing duplication example, not a repoint to another dead path.
- `.github/labels.yml` declares `autopilot` and `autopilot-blocked` (lines 45-52). These ARE removable by file diff -- but check_label_inventory.py:62 documents in its own source that removing a declaration while the label still exists live makes the gate fail "for the length of one PR" (live-but-undeclared direction). **Ordering-critical**, see section 5.
- `docs/agent-reference/ci-gates.md:290` table lists `autopilot-blocked` as one of four kill-switch labels -- needs its row/mention dropped.
- `docs/agent-reference/ci-gates.md:128` cites "a fully-green autopilot-driven PR" as the motivating example for the Claude-Review 3-attempt terminal rule. The rule is general (any fully-green PR with nothing to push triggers the same terminal state); only the illustrative wording names Autopilot. Reword, don't restructure.
- `.ci/policy/.profiler-coverage-allowlist` rows 32-35: `autopilot.yml:finish`, `:gate`, `:model`, `:sweeper`. Hand-remove these 4 lines (source file); `.ci/policy/README.md`'s table (rows 32-35 there) and `scripts/data/doc-registry.md`'s AUTOPILOT_* rows are both downstream of `npx tsx scripts/gen/gen-docs.ts --write` -- do not hand-edit the generated tables.
- `.ci/config/language-policy-baseline.json` line 74 names `.ci/scripts/quality/check-autopilot-no-bypass.sh`. This file is shrink-only and generated (its own `_comment` says so). After deleting the .sh, drain it with `python3 .ci/scripts/quality/check_language_policy.py --write-baseline`. Do not hand-edit.
- `.ci/config/python-env-registry.json`: AST-derived, generated, "shrink-only" by its own `note`. After deleting `.ci/rediacc_ci/autopilot/*.py`, drain with `python3 .ci/scripts/quality/check_python_env_registry.py --write-baseline`.
- `.ci/config/env-manifest.json`: hand-maintained (no `--write` mode in env_manifest.py), but has an explicit tombstone shard exactly for this situation -- the gate's own message: "the entry, or move it to `tombstone` if the name is retired for good." Move (not delete) AUTOPILOT_ALLOW_STATE, _ALLOW_FINISH, _ALLOW_MODEL, _ALLOW_PUSH, _ALLOW_SUBMODULES, _APPLIER_ALLOWLIST, _AUTHOR_ALLOWLIST, _BOT_LOGIN, _EFFORT, _ENABLED, _GIT_EMAIL, _GIT_NAME, _LABEL, _MAX_ROUNDS, AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE, AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE, GITHUB_AUTOPILOT_APP_ID, GITHUB_AUTOPILOT_PRIVATE_KEY (~17 names) into the tombstone shard, with a tombstone_proof_sites entry if the gate's clause-4 check demands one.
- `.ci/config/secret-supply.json`, `.ci/config/bws-secret-map.json`, `.ci/config/bws-unrequested.json`: hand-maintained, each carries GITHUB_AUTOPILOT_APP_ID / GITHUB_AUTOPILOT_PRIVATE_KEY entries. Read check_secret_supply.py / check_bws_map.py for the exact removal shape (tombstone vs. delete -- not verified as deeply as env-manifest.json's mechanism) before editing.
- `.github/workflows/ci.yml` label-guide job (~line 458): a second step, "Post the autopilot guide" (~lines 485-490), calls autopilot-guide-comment.cjs. Delete this ONE step; keep the job and its sibling "Post the label guide" step untouched -- they serve the unrelated, still-live label guide.
- `docs/ci-overhaul/README.md` (lines 69, 80), `04-decisions.md` (lines 11, 104, 155), `05-execution-guide.md` (line 81, "Wave C: PR-C, the autopilot"), `PROMPT.md` (line 10), `09-env-residue.md` (line 218, a cron-residue table row) all describe Autopilot as real/current.
Read each section before editing -- these files cover the whole ci-overhaul program (Waves A/B, the W7 Python port), of which Autopilot (Wave C) was one deliverable; edit only the Autopilot-specific paragraphs/rows, leave the rest.

### Confirmed NOT genuinely dependent (mention-only, leave untouched)

- `.claude/skills/pr-epics/body.md` (lines 14, 24): cites `.ci/scripts/autopilot/submodule-prs.sh` as the historical origin of the epic-block marker idiom.
That path was already stale before this task -- the real file is `.ci/rediacc_ci/autopilot/submodule_prs.py` (post-port). pr-epics does not invoke anything under `.ci/rediacc_ci/autopilot/`; it only documents a convention borrowed from it. No functional break either way. Optional courtesy wording fix, not required.
- `.claude/rediacc_hooks/guards/block_raw_pr_body_edit.py` and its bash twin `.claude/oracles/pre-bash/block-raw-pr-body-edit.sh`: cite `.ci/scripts/autopilot/submodule-prs.sh`'s header as "the lesson" that motivated this general (non-autopilot) PR-body-write guard.
Purely historical citation in a docstring; the guard's actual logic (worklist-epics/pushed-head markers) has zero code dependency on autopilot. **Do not touch** -- the oracle .sh twin is explicitly required to stay byte-identical to the pre-port original until the P6 cutover.
- `.claude/hooks/stop/worklist.py:1878` (GITHUB_ACTIONS == "true": sys.exit(0)), worklist_messages.py:399 (V_AGENT_STATE message), wl_store.py:2320, wl_checks.py:354: all cite a historical Autopilot-related incident (an App reported blocked after it had already been created) as the WHY for a general Stop-hook behavior.
The behavior itself (refuse-to-stop-with-open-items in CI, STATE.md rewrite discipline, citable-extension list) is general-purpose and used by things other than Autopilot. **Do not touch.**
- `.claude/rediacc_hooks/tests/wlfix.py` and test_wl_stuck_and_blockers.py: use "autopilot" as flavor text in fixture strings ("Wave C autopilot" as an arbitrary task title; a fictional STATE.md body mentioning "the rediacc-autopilot App" for an unrelated compaction-recovery test). Coincidental word reuse, not a dependency. **Do not touch.**
- `.ci/rediacc_ci/gitx.py` (comment) and `.ci/rediacc_ci/deploy/deploy_account.py` / `deploy_www.py` (comments): cite linked_sub_prs.SUB_REPOS / autopilot/sweep_collect.py as prior-art examples of a pattern (hardcoded submodule lists; an error-status-printing convention).
Once those files are deleted these become dangling citations to a deleted path -- same class as the pr-epics one. Optional low-priority citation repair, not required for correctness (no gate validates code-comment citations the way plan citations are validated).
- `docs/ci-overhaul/06-progress.md` and `10-ci-port-baseline.md`: dated, "Measured at `<sha>`" historical snapshots of the porting effort (e.g., a literal file listing that includes check-autopilot-breakpoint-alignment.sh as of that measurement).
Rewriting these would falsify the historical record they exist to preserve. **Leave untouched**, same rationale this repo already applies to frozen agent/ archives, even though these particular files live under docs/ rather than agent/.
- `agent/` worklist jsonl, plan/report history, `agent/shadow/*.observations.jsonl`: frozen per this repo's own convention (a session report/record is frozen once written). **Not touched.**

## 2. CI registration cleanup -- exact wiring

Two registered gates, both `kind: 'test'` (no dedicated workflow step of their own -- they ride the broad pytest suite):

1. `package.json:35` -- `"check:ci-autopilot-workflow": "PYTHONPATH=.ci python3 .ci/rediacc_ci/security/autopilot_workflow_invariants.py"`
2. `package.json:296` -- `"check:ci-autopilot-bp-align": ".ci/scripts/quality/check_autopilot_breakpoint_alignment.py"`
3. `scripts/ci-runner/manifest.ts:4231-4241` -- the check:ci-autopilot-workflow GateSpec
4. `scripts/ci-runner/manifest.ts:4282-4292` -- the check:ci-autopilot-bp-align GateSpec
5. `scripts/ci-runner/gates.lock.json:4564-4574` and `:4618-4628` -- generated, do not hand-edit; regenerate with `npx tsx scripts/gen/gen-gates-lock.ts --write` after (3) and (4) are gone, then verify with `npx tsx scripts/gen/gen-gates-lock.ts` (no flags).
6. `.github/workflows/ci.yml` label-guide job -- one step ("Post the autopilot guide") to delete, per section 1c.

Confirmed: no `.github/workflows/*.yml` step invokes `npm run check:ci-autopilot-workflow` or `check:ci-autopilot-bp-align` directly (the original survey's "a `.github/workflows/*.yml` step each" guess was wrong for these two specifically -- their blocker: text in the manifest says so explicitly: they ride check:ci-pytest / quality-security / "Python package tests" through their gate-test files). Deleting those gate-test files (section 1a) IS the removal of their CI execution path; no separate workflow edit is needed for these two beyond the manifest/package.json/lock triple.

After (3)-(5): run `npx tsx scripts/gen/gen-docs.ts --write`, which will shrink `docs/agent-reference/ci-gates.md`'s generated regions (if any reference these ids -- verify), shrink `.ci/policy/README.md`'s .profiler-coverage-allowlist table from rows 32-35 down (once (1c)'s source-file edit lands), and shrink `scripts/data/doc-registry.md`'s AUTOPILOT_* rows.

Then `npx tsx scripts/gen/gen-docs.ts` (no flags, verify mode) must exit 0.

## 3. Doc cleanup

- **Delete** `docs/ci-overhaul/03-v2-autonomy.md` outright -- it has no subject left once the code is gone.
- **Edit** `docs/ci-overhaul/{README.md,04-decisions.md,05-execution-guide.md,PROMPT.md,09-env-residue.md}` at the lines named in section 1c -- strike the Autopilot-specific paragraphs/rows only.
- **Edit** `docs/agent-reference/ci-gates.md` at lines 128 and 290 per section 1c.
- **Leave untouched**: `docs/ci-overhaul/06-progress.md`, `10-ci-port-baseline.md`, all of `agent/`.

## 4. The GitHub-side kill switch and repo config -- operator-side, not a file diff

Confirmed by grepping every tracked .yml/.ts/.json for these names: none of the Actions variables are declared in any tracked file (there is no `.github/variables.yml` analog to `labels.yml`). These are pure repo Settings, and this PR cannot delete them:

- Variables: AUTOPILOT_ENABLED, AUTOPILOT_ALLOW_STATE, AUTOPILOT_ALLOW_FINISH, AUTOPILOT_ALLOW_MODEL, AUTOPILOT_ALLOW_PUSH, AUTOPILOT_ALLOW_SUBMODULES, AUTOPILOT_AUTHOR_ALLOWLIST, AUTOPILOT_APPLIER_ALLOWLIST, AUTOPILOT_LABEL, AUTOPILOT_MAX_ROUNDS, AUTOPILOT_BOT_LOGIN, AUTOPILOT_GIT_NAME, AUTOPILOT_GIT_EMAIL, AUTOPILOT_EFFORT, AUTOPILOT_APP_ID (org-level, console-scoped)
- Secret: AUTOPILOT_PRIVATE_KEY (repo/org secret, sourced from Bitwarden Secrets Manager via `private/account`'s rotation system -- a separate submodule-side follow-up, out of console's scope, same shape as agent/plans/PLAN-rotation-gh-removal.md)
- Labels (declared in a tracked file, but the LIVE instance is not): autopilot, autopilot-blocked -- see ordering below, this one DOES interact with the file diff.
- The `rediacc-autopilot` GitHub App itself: uninstall from the org, and remove its bypass actor entry from console's branch ruleset (not tracked in any file -- no `.github/rulesets/*` exists in this repo; confirmed by search).
- The Bitwarden Secrets Manager item backing AUTOPILOT_PRIVATE_KEY, and `private/account/rotation-manifest.json`'s entry for it -- separate submodule PR, not actioned by this plan.

## 5. Ordering -- why, and what stays gate-green at every step

Two facts drive the sequencing:

1. `check_label_inventory.py:62`, verbatim: removing a label's declaration from `.github/labels.yml` while the label still exists live "would sit live and undeclared for the length of one PR and fail." So: delete the live GitHub labels (`gh label delete autopilot`, `gh label delete autopilot-blocked`) BEFORE merging the `labels.yml` edit -- not after.
This has zero coupling to the rest of the removal and can happen any time before the doc/registration commit lands; doing it first removes the only footgun in this whole plan.
2. Every "shrink-only generated" file (gates.lock.json, language-policy-baseline.json, python-env-registry.json) is compared against the TRACKED SOURCE on every CI run.
There is no safe order to split "delete the source file" from "drain the derived registry" across two commits -- the intermediate commit is red either way (an orphaned registry entry on one side, or a dangling leaves:/manifest reference on the other).
The repo's own check:ci-dead-bash (flags an unreferenced bash file) and check:ci-parity (flags a manifest entry whose resolved leaf doesn't match package.json/disk) are exactly the two gates that would catch whichever half of a split commit was wrong. File deletion and its registration/registry update must land in the same commit.

Given that constraint, this removal is not meaningfully splittable into gate-green intermediate commits beyond the two genuinely independent pieces:

- **Pre-step (any time, no coupling):** operator deletes the live labels, Actions variables/secrets, and the App/ruleset bypass actor. Do this FIRST.
- **The mechanical bulk (one big-bang commit):** delete all of section 1(a)'s ~738 files, edit all of section 1(c) and section 2's registrations, run the four regenerators (gen-gates-lock.ts --write, gen-docs.ts --write, check_language_policy.py --write-baseline, check_python_env_registry.py --write-baseline), hand-edit env-manifest.json/secret-supply.json/bws-secret-map.json/bws-unrequested.json, and remove the ci.yml step and labels.yml blocks -- all together. This matches this repo's own stated preference ("ask for the big-bang, not permission to patch one thing"): the pieces are load-bearing on each other (pytest collection breaks if the Python modules go without their tests in the same commit; the lock/registry regenerators only produce a clean diff once their sources are already gone), so splitting it does not buy safety, only more red intermediate states.
- **Doc-only commit (optional, separable either direction):** section 3's edits have no gate coupling to the code commit and can be its own commit, before or after, for review clarity if the PR is large enough to want that.
- **Separate submodule follow-up (not part of this PR):** `private/account`'s rotation-manifest.json and the Bitwarden item for AUTOPILOT_PRIVATE_KEY.

## 6. Blast radius

- **Files deleted outright: ~738** (1 workflow, 26 Python/JS/schema/markdown source and gate files, 23 test files, 667 golden fixtures, 18 shadow observation logs, 1 doc).
- **Lines removed: ~37,000** (workflow 1173 + harness 6490 + 3 gate modules 1231 + entrypoints/scripts 1191 + top-level tests 11794 + gate-test ports 4874 + goldens 9860 + doc 365).
- **Files edited, not deleted: ~16** (package.json, manifest.ts, gates.lock.json [regenerated], ci.yml, labels.yml, docs/agent-reference/ci-gates.md, .ci/policy/README.md [regenerated], scripts/data/doc-registry.md [regenerated], .ci/policy/.profiler-coverage-allowlist, .ci/config/language-policy-baseline.json [regenerated], .ci/config/python-env-registry.json [regenerated], .ci/config/env-manifest.json, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json, plus the 5 docs/ci-overhaul files in section 3).

This is far larger than the initial survey's estimate (which undercounted goldens by ~4.5x and missed one of the five gate-test files), mostly because of test/golden volume, not hidden extra subsystems -- the actual source surface (harness + gates + scripts) the survey named was accurate.

## 7. Verification / acceptance criteria

- [x] `grep -ril autopilot .` (excluding .git, node_modules) returns ONLY: the confirmed-unrelated packages/www tutorial hits, the frozen agent/ archives, the two flavor-text test fixtures (wlfix.py, test_wl_stuck_and_blockers.py), the historical docs/ci-overhaul/{06-progress,10-ci-port-baseline}.md snapshots, and the deliberately-kept historical-lesson comments in block_raw_pr_body_edit.py / its oracle twin, worklist.py/worklist_messages.py/wl_store.py/wl_checks.py, gitx.py, deploy_account.py, deploy_www.py, calibrate-judge-rules.py, and pr-epics/body.md -- nothing else.
- [x] `npx tsx scripts/gen/gen-gates-lock.ts` (verify mode) exits 0.
- [x] `npx tsx scripts/gen/gen-docs.ts` (verify mode) exits 0.
- [x] `python3 .ci/scripts/quality/check_language_policy.py` exits 0.
- [x] `python3 .ci/scripts/quality/check_python_env_registry.py` exits 0.
- [x] `python3 .ci/scripts/quality/check_env_manifest.py` exits 0.
- [x] `npm run check:ci-parity` exits 0.
- [x] `npm run check:ci-dead-bash` exits 0.
- [x] `npm run check:ci-label-inventory` and `check:ci-label-refs` exit 0 (only after the live labels are already deleted per section 5).
- [x] `npm run check:ci-pytest` exits 0 with no collection errors (proves no leftover import of a deleted `.ci/rediacc_ci/autopilot/*` module anywhere).
- [x] Full CI green on the PR.

## 8. Tasks

- [x] Delete the live GitHub labels `autopilot` and `autopilot-blocked` (`gh label delete`), and remove the Actions variables, the AUTOPILOT_PRIVATE_KEY secret, and the rediacc-autopilot App's ruleset bypass actor, on the live repo -- BEFORE the labels.yml edit below merges.
- [x] Delete `.github/workflows/autopilot.yml`.
- [x] Delete `.ci/rediacc_ci/autopilot/` (17 files).
- [x] Delete `.ci/rediacc_ci/quality/autopilot_no_bypass.py`, `.ci/rediacc_ci/quality/autopilot_breakpoint_alignment.py`, `.ci/rediacc_ci/security/autopilot_workflow_invariants.py`.
- [x] Delete `.ci/scripts/quality/check_autopilot_breakpoint_alignment.py`, `.ci/scripts/quality/check-autopilot-no-bypass.sh`, `.ci/scripts/ci/autopilot-guide-comment.cjs`, `.ci/scripts/autopilot/` (5 files).
- [x] Delete the 18 test_autopilot_*.py / test_quality_autopilot_no_bypass.py / test_security_autopilot_workflow_invariants.py files and the 5 test_gate_autopilot_*.py files.
- [x] Delete the 17 `.ci/rediacc_ci/tests/goldens/{autopilot-*,compose-prompt,fetch-review-threads,finish,linked-sub-prs,post-escalation,resolve-model-args,restore-trusted-config,review-payload,review-reply,state-comment,submodule-prs,sweep-campaigns,sweep-collect,update-state}` directories (667 files) -- leave `goldens/allowlist` alone (shared).
- [x] Delete the 18 `.ci/shadow/{w7p2-autopilot-no-bypass,w7p6-autopilot-gate,w7p6-autopilot-push,w7p6-check-autopilot-workflow-invariants,w7p6-<each-remaining-module>}.observations.jsonl` files.
- [x] Remove check:ci-autopilot-workflow / check:ci-autopilot-bp-align from package.json (lines 35, 296) and scripts/ci-runner/manifest.ts (~4231-4241, ~4282-4292).
- [x] Regenerate scripts/ci-runner/gates.lock.json (gen-gates-lock.ts --write).
- [x] Remove the "Post the autopilot guide" step from the label-guide job in .github/workflows/ci.yml.
- [x] Remove the autopilot / autopilot-blocked blocks from .github/labels.yml.
- [x] Remove the 4 autopilot.yml:* lines from .ci/policy/.profiler-coverage-allowlist.
- [x] Drain .ci/config/language-policy-baseline.json (check_language_policy.py --write-baseline) and .ci/config/python-env-registry.json (check_python_env_registry.py --write-baseline).
- [x] Move the ~17 AUTOPILOT_*/GITHUB_AUTOPILOT_* names to the tombstone shard in .ci/config/env-manifest.json; remove the matching entries from .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/config/bws-unrequested.json per their own gates' rules.
- [x] Regenerate scripts/data/doc-registry.md, docs/agent-reference/ci-gates.md's generated regions, and .ci/policy/README.md (gen-docs.ts --write); hand-edit ci-gates.md's prose at lines 128 and 290.
- [x] Delete docs/ci-overhaul/03-v2-autonomy.md; edit the Autopilot-specific paragraphs/rows in README.md, 04-decisions.md, 05-execution-guide.md, PROMPT.md, 09-env-residue.md.
- [x] Run every check in section 7 and the full CI suite; fix anything still red.
- [x] (Separate PR, private/account submodule) retire the AUTOPILOT_PRIVATE_KEY rotation entry and its Bitwarden Secrets Manager item.
