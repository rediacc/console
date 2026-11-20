# PLAN: Fix-round speed on an open PR -- a PR freeze guard, per-box and per-file gate caches, critical-path core priority, traced account-server inputs, and signed CI receipts from one devcontainer image (the two-track dev lease is DEFERRED: on PR #605 the voided runs came from fix commits and pins bumps, not feature work, so a parallel dev track would not have saved them; it is reconsidered only after the freeze and the caches are measured on one PR)
Status: approved -- operator /ask 2026-11-20 (recorded on #527aa5b2): the plan as written, implemented inline by the lead as far as possible, with further bug-fix and optimization work taken on the way; started inside the PR #605 babysit phase on the operator's request
Owner: d778be9d
First-Seen: 2026-11-20
Depends-On: no-dep -- no box of another plan is a prerequisite. The plan rides the PR after #605: while #605 is in the babysit phase, block_focus_spawn refuses writers that are not fix work, so no writer of this plan starts before #605 merges.
Priority: P1 -- operator request. A fix round on PR #605 cost 1,400-1,800 s of wall time (/tmp/m/ciq10-18.log), and two pins bumps each forced a run with zero carries (~1,330-1,380 s each)
Concurrency: parallel -- wave 1 starts four lease writers with disjoint files: WF (freeze), WP (plan-implementation), WS (prose-style), WR (runner: core priority plus the DNS trace hole). Wave 2 starts WD (devbox and the image pin), then WC (CI container lane and the receipt writer), then WG (push-guard verification). The lead boxes run in the main checkout. Every edit under scripts/ci-runner/** changes GLOBAL_INPUTS (scripts/ci-runner/input-hash.ts:31-39), which voids every carry, so the runner edits land as one batch before M1 measures anything.
Owns: agent/plans/PLAN-two-track-merge-dev.md, .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/wl_rebase.py, .claude/hooks/stop/test-rebase-consistency.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/test-planrec.py, .claude/rediacc_hooks/git/githooks.py, .claude/rediacc_hooks/pr_freeze.py, .claude/rediacc_hooks/guards/block_pr_freeze_commit.py, .claude/rediacc_hooks/guards/test-block_pr_freeze_commit.py, .claude/rediacc_hooks/tests/test_githook_pr_freeze.py, .claude/rediacc_hooks/tests/goldens/block_pr_freeze_commit.jsonl, .ci/scripts/quality/check_plan_implementation.py, .ci/rediacc_ci/quality/plan_impl_facts.py, .ci/rediacc_ci/tests/test_plan_impl_facts.py, .ci/rediacc_ci/quality/prose_style.py, .ci/rediacc_ci/tests/test_quality_prose_style.py, scripts/ci-runner/exec.ts, scripts/ci-runner/pool.ts, scripts/ci-runner/rank.ts, scripts/ci-runner/run.ts, scripts/ci-runner/path-trace.ts, scripts/ci-runner/trace-honest.ts, scripts/ci-runner/trace-ledger.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/input-hash.ts, scripts/ci-runner/ci-receipt.ts, scripts/ci-runner/quick-clone.ts, scripts/ci-runner/learned-selftest.ts, scripts/gate-bind.ts, .ci/rediacc_ci/core/devbox.py, .ci/config/devcontainer-image.json, .devcontainer/Dockerfile, .github/workflows/ci-quality.yml, .github/workflows/ci.yml, .github/actions/setup-workspace/action.yml, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .ci/rediacc_ci/ci/gate_ledger.py, docs/agent-reference/ci-gates.md, .ci/config/gate-costs.json, .ci/config/lane-durations.json, .ci/policy/record-paths.json, private/account/tests/integration/no-live-stripe.test.ts
Live-Proof: none -- hooks, CI tooling and workflow files only, no deployed surface: the operator scope ruling recorded verbatim in closed #688f35df

## Ask

Operator, 2026-11-20, /ask answers. Scope: build (1) the PR freeze guard; (2) a plan-implementation per-box result cache, plus first claim on cores for critical-path gates; (3) a prose-style per-file findings cache, plus traced real inputs for check:ci-account-server; (4) the signed CI receipt now, with the note verbatim: "don't we have devcontainer for such things. it should be utilized for portability". So the devcontainer image is the one toolchain for local gate runs and for CI: the salt then matches exactly, and a verdict reached in one place holds in the other.

Out of scope: the async split (later), the pytest listed-directories change, and the dev-track lease (deferred until the freeze and the caches are measured on one PR).

Hard rules. Speed never comes from a weaker gate:

- no gate is removed or skipped where its inputs changed;
- no threshold is raised;
- no new carry-exempt or allowlist row is added;
- the merge condition does not change (CI Complete SUCCESS, per-commit reviews clean, Review Complete green);
- every guard or hook change ships with a control that goes red without it.

## Why the dev track is deferred

The PR #605 investigation found the voided runs were caused by commits landing on the PR branch during the babysit phase: fix commits, plus two pins bumps (898b7294e and 4b626a378). The bumps touched package-lock.json and .devcontainer/toolchain.env. Both are GLOBAL_INPUTS (scripts/ci-runner/input-hash.ts:31-39), and toolchain.env is also part of the salt (scripts/ci-runner/input-hash.ts:242-257), so each bump forced a run with zero carries. A second lease track for feature work would not have kept those commits off the branch. A freeze does. The dev track is reconsidered after M1 has measured a full PR with the freeze and the caches in place.

## Context (verified 2026-11-20 against the working tree at 073e174f7; a writer re-reads a line before relying on it)

1. Where the time goes. The ci:quick footers name check:ci-pytest as the critical path in every complete run: "floor max(CP 1512.1s, cpu 1029.3s)" in /tmp/m/ciq14.log and "max(CP 1344.7s, cpu 1015.1s)" in /tmp/m/ciq18.log, with wall about 1.13-1.19 x floor. 23-24 of 24 cores were busy for most of each run, and 161-199 gates were held back on cpu. check:ci-plan-implementation took 701-835 s under load and 239.6 s alone (/tmp/m/ciq19.log); check:ci-prose-style 167-255 s under load and 86.7 s alone; check:ci-account-server launched only after a 1,115-1,515 s queue wait in ciq14, ciq17 and ciq18 and was then the last gate to finish (1,228-1,623 s). Its prerequisite build:packages waited 1,346-1,514 s for cpu. The cheapPrereqFirst rank is in the working tree but not yet committed (scripts/ci-runner/pool.ts).
2. Never-carry. check:ci-pytest is carry-exempt, kind `cache` (.ci/policy/carry-exempt.json). check:ci-plan-implementation declares `env: {GITHUB_BASE_REF}` in its lock entry (scripts/ci-runner/gates.lock.json), so its reason is `env` (scripts/ci-runner/input-hash.ts:451) and it never carries. check:ci-prose-style declares no `paths`, so its input is the whole tree. check:ci-account-server declares no `paths`, and its trace verdict is whole-tree with the reason "network: connects to 10.255.255.254:53" (scripts/ci-runner/trace-ledger.ts:114-124).
3. The pins tool never commits. Its header says so (scripts/pins/pins.ts:28-34); it prints `git commit -F <draft> -- <paths>` lines for the caller (scripts/pins/pins.ts:357-362), and the `commit` argvs at scripts/pins/pins.ts:1310, :1521 and :1770 are selftest fixtures in temporary repos. A pins commit therefore passes through the pre-bash chain. commit-msg is still the authoritative place for the freeze, because some commits never pass through pre-bash: the review recorder commits by subprocess (.claude/hooks/stop/wl_review.py:3969), and the operator commits with `!`.
4. The commit-msg hook (.claude/rediacc_hooks/git/githooks.py:113-157) already refuses on message and staged paths (`cp.staged_paths`) and runs lease checks. It receives no Claude session id.
5. Phase events are recorded per owner. The newest event comes from `wl_standdown.active_phase` (.claude/hooks/stop/wl_standdown.py:186-202), with modes `babysit|merge` (:163), the `focus-fix:#<id>` pattern (:177), `pr_linked` (:212) and `expired` at 24 h (:238). block_focus_spawn reads them through `S.phase_fold` (.claude/rediacc_hooks/guards/block_focus_spawn.py:160-180). A phase event carries `branch` and `pr` (.claude/hooks/stop/worklist.py:299).
6. Pre-bash ORDER 30-59 is fully used. block_untagged_commit is at 37 (.claude/rediacc_hooks/guards/block_untagged_commit.py:45). Guards carry a `DEFECT` mutation tuple that check:ci-guard-mutations plants.
7. Per-box git work in plan-implementation (.ci/scripts/quality/check_plan_implementation.py:2178-2230): per newly-done box, `planrec.done_commit` and `git log -1 --format=%cI|%aI` per commit, `merge-base --is-ancestor`, `fileline_at_commit` (a `git show <commit>:<path>` per call, :2412-2427), `follow_names` (a `git log --follow` per plan path, memoized per process only, :2350-2382), and `resolve_here` through `planrec.resolve`, which runs `rev-parse` plus two `merge-base --is-ancestor` per commit pointer (.claude/hooks/stop/wl_planrec.py:478-540). The only memos live in-process (.claude/hooks/stop/wl_planrec.py:940).
8. prose-style runs `extract` twice per file: once in run_check (.ci/rediacc_ci/quality/prose_style.py:1457) and again inside `lint_text` (:932-951, called at :1465). Findings depend only on (path, text, rules, globals_). `identity_path` (:913) reads stub files and is applied after linting (:1466-1469).
9. A trace hole. `networkPeer` treats every loopback address as on-host (scripts/ci-runner/path-trace.ts:119-140), so a DNS query to a loopback stub resolver (127.0.0.53 under systemd-resolved, 127.0.0.11 inside Docker) reads as no network. In the devbox or a CI container, account-server's lookup would disappear from the trace because of the environment, not the code.
10. The toolchain today: .devcontainer/toolchain.env pins `NODE_VERSION=24`, the major only (.devcontainer/toolchain.env:44), and no Python. The image runs `nvm install 24` at build time (.devcontainer/Dockerfile:230) and apt `python3` on ubuntu-24.04 (:124). The devbox runs `devcontainer:latest`, unpinned (.ci/rediacc_ci/core/devbox.py:142). CI quality jobs run on `ubuntu-latest` with setup-node through .github/actions/setup-workspace/action.yml:75-77. The salt is `node --version`, `python3 --version`, platform, arch and toolchain.env (scripts/ci-runner/input-hash.ts:242-257). So host (v24.21.0 / 3.14.4), devbox and CI produce three different salts.
11. CI quality gates run as generated workflow steps, not through the runner. The only per-shard receipt counts lock ids and outcomes (scripts/ci/write-shard-receipt.cjs). gate_ledger keys CI rows by tree when no inputHash exists (.ci/rediacc_ci/ci/gate_ledger.py:20). Carry priors are read only from `.ci/cache/receipts/<tree>.json`. The push guard's origin check compares inputHash, verdict and findings against that archive (.claude/rediacc_hooks/guards/block_unverified_push.py:1643-1712, receipt path at :2004). Nothing in the repo uses `gh attestation` today.
12. A pull_request CI run checks out the merge commit by default, so a CI receipt describes the merge tree. A per-gate inputHash still equals the local one exactly when main changed none of that gate's inputs: the existing carry rule, unchanged.

## Design

### D1 Freeze (one predicate, two hooks)

- Module `.claude/rediacc_hooks/pr_freeze.py`, a pure core `verdict(msg, staged_paths, gitlink_ranges, phase, open_items) -> (ok, reason)`, loaded by file from githooks.py and imported by the pre-bash guard.
- The freeze binds to the branch, not the session, because a git hook has no session id. It is active when any unexpired `babysit|merge` phase event (any owner) names the current branch of the repository being committed to: the console, plus any submodule whose live branch has the same name.
- A commit is admitted when one of these holds:
  1. the Conventional Commits type is `fix`, `style` or `test`;
  2. it is `chore(reviews|state|plan|plans)`;
  3. every staged path is in .ci/policy/record-paths.json;
  4. it carries a `focus-fix:#<id>` naming an item that is open in the worklist, owned by the phase owner (`C.owned_by_me` with lineage), and whose text carries the phase's `pr:<n>` (`wl_standdown.pr_linked`);
  5. the staged diff is gitlinks only, and every commit in each bumped submodule range passes rule 1, 2 or 4, so a fix landed in private/account can be pointed at from the console.
- Escape: `worklist.py --phase <me> build` ends the phase. No other override exists.
- Unreadable phase state fails open with one stderr line, matching block_focus_spawn's UNREADABLE path. An unreadable item store under an active freeze fails closed for rule 4 only.
- The pre-bash twin, block_pr_freeze_commit, gives an early message with the same text; commit-msg remains the authority.

### D2 plan-implementation as an immutable-fact cache

Every slow per-box answer is a pure function of immutable git objects, or is computed fresh in one batched call:

- `follow_names(rel)`: keyed on (rel, `git rev-list -1 HEAD -- rel`); history behind a commit id is immutable.
- `fileline_at_commit(commit, path)`: keyed on (commit, path), the line count.
- Commit dates (`%cI`, `%aI`): keyed on sha.
- `is_ancestor(a, b)`: keyed on (a, b) when both are full shas.
- Reachability from HEAD and from origin/main, needed by `resolve_here` and `planrec.resolve`: one `git rev-list HEAD` and one `git rev-list refs/remotes/origin/main` per run, held as sets, fresh every run, never cached.
- Object existence for blob, tree and commit pointers: one `git cat-file --batch-check` per run.
- The cache file is `.ci/cache/plan-implementation/facts-v1.json` (gitignored), keyed additionally on a closure hash: the sha256 of the source of every repo module loaded when the key is formed (check_plan_implementation.py, wl_planrec.py, check_plan_citations.py, plus any other repo module in `sys.modules`).
- A per-box result layer may sit on top, keyed on the hash of every fact the box consumed plus box text, evidence line, investigation row (canonical JSON), baseline_at, base sha and absent_submodules. It is built only if P0 shows the fact cache leaves more than 30 s unloaded.
- The gate still runs every time. P-A1, P-A5 and revalidation are not cached. A missing or corrupt cache is a miss, and the cache is never a verdict source.

### D3 First claim on cores

The rank's pinned set (scripts/ci-runner/rank.ts:316-321, the long-chain gates) plus the runner's computed critical path launch at base CPU priority; every other gate launches with `nice -n 10`, prefixed in scripts/ci-runner/exec.ts before the RUSAGE wrapper (:227-237) so the whole process group inherits it. This orders CPU share only: the selected set, the grants and every verdict stay the same. Under CFS, weight 1024 against 110 gives a pinned single-thread gate about nine times the share of a niced one on a saturated machine. The cheapPrereqFirst rank already in the working tree lands first with its control (C0).

### D4 prose-style per-file cache

- Key: (rel, sha256 of the file bytes read, sha256 of .ci/config/prose-style-rules.json bytes, closure hash of prose_style.py and its repo imports, schema).
- Value: the extracted-line count, the note, and the findings serialized without `ident`.
- Recomputed on every run: identity_path, exemptions, the per-suffix vacuity floors and the baseline comparison. `--write-baseline` and `--drain` run cold. The double `extract` is folded into one call. The cache file is `.ci/cache/prose-style/files-v1.json`.

### D5 account-server's real inputs

First close the loopback-DNS hole: a `connect` to port 53 counts as network whatever the address. Then find the lookup's caller and remove it at source only if it is incidental (an update check, telemetry, a resolvable test hostname that can be a hosts entry or loopback literal), not something a test asserts. Then trace the gate in the pinned image (scripts/ci-runner/path-trace.ts) and adopt the traced `paths` with `pathsOrigin: 'traced'` once trace-honest passes in both `trace` and `sparse` modes. If the network read is real behaviour under test, the gate stays whole-tree: neither a carry-exempt row nor hand-declared paths is acceptable.

### D6 One image, signed receipts

- The image digest is pinned in .ci/config/devcontainer-image.json, outside the image's build context (a digest inside .devcontainer/ would change the context and therefore the digest). The devbox (.ci/rediacc_ci/core/devbox.py:142) and the CI container lanes both read that pin.
- Local gate runs go through `./run.sh devbox exec npm run ci:quick`, with the quick clone directory bound at the same path inside the box.
- The salt gains one term: the pinned image digest when the run is inside it, `host` otherwise. That is strictly finer: host and image receipts never stand in for each other, and nothing in the salt is relaxed.
- CI lanes move one at a time to `container: image: ghcr.io/rediacc/devcontainer@<digest>` with `credentials` and `packages: read`; container lanes skip setup-node in setup-workspace, so the image's node is the node.
- After a lane's gates, scripts/ci-runner/ci-receipt.ts computes `computeGateHashes` for that lane's lock ids at the checked-out tree inside the same container, joins them with step outcomes (the GATE_STEP_LOCK_MAP currency of scripts/ci/write-shard-receipt.cjs) and writes `{schema, repo, run, sha, tree, salt, gates: {id: {inputHash, verdict}}}`, including only gates with a non-null inputHash and verdict `pass`. The workflow attests the file (`actions/attest-build-provenance`, `id-token: write`, `attestations: write`) and uploads it.
- Local side: a runner verb downloads receipts for the branch's and main's recent runs, verifies each with `gh attestation verify <file> --repo rediacc/console --signer-workflow rediacc/console/.github/workflows/ci-quality.yml --source-digest <sha>`, and stores the verified ones as `.ci/cache/receipts/ci-<tree>.json` priors with a `ci` origin marker.
- The push guard re-runs the verification for a carried entry whose origin is a CI receipt (memoized per file digest), then applies the unchanged inputHash, verdict and findings comparison. A CI prior's findings are `[]`, because only passes are receipted.
- Threat model: this protects against self-deception (stale, edited or misattributed verdicts), not against a malicious workflow on the branch. A pull_request run executes the branch's own workflow file; the receipt writer lives under scripts/ci-runner/**, which is in every inputHash through GLOBAL_INPUTS.

## Tasks

### Freeze

- [ ] F1 [writer] Build .claude/rediacc_hooks/pr_freeze.py (the D1 predicate, a pure core plus a loader that folds phase events with `wl_store.phase_fold` and reads open items) and call it from `commit_msg` in .claude/rediacc_hooks/git/githooks.py after the lease checks; the refusal text names the admitted forms and the escape `worklist.py --phase <me> build`.
  Owns: .claude/rediacc_hooks/pr_freeze.py, .claude/rediacc_hooks/git/githooks.py, .claude/rediacc_hooks/tests/test_githook_pr_freeze.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_githook_pr_freeze.py` rc 0. The tests drive a real `git commit` in a temporary repo with a planted babysit phase event and cover: `feat(ci)` refused; `chore(pins)` refused; `fix(ci)` admitted; `chore(reviews)` admitted; a record-paths-only diff admitted; `focus-fix:#<id>` admitted for an open item with `pr:<n>` and refused for a closed item, a peer's item and `pr:<other>`; a gitlink bump whose range holds a `feat` refused and one whose range holds only fix commits admitted; a phase on another branch not freezing; an expired phase not freezing. A CONTROL test replaces the `verdict` call with `(True, "")`, asserts the `feat(ci)` case goes red, and is registered for check:ci-guard-mutations. `npm run -s check:ci-hooks-resolvable` rc 0.
- [ ] F2 [writer] Add the pre-bash twin block_pr_freeze_commit (CHAIN pre-bash, ORDER beside block_untagged_commit as the guard registry's tie rule admits), reading the message the way block_untagged_commit does (`-F <file>`, heredoc) and calling `pr_freeze.verdict` with the paths the command names; a `DEFECT` tuple disables the verdict arm.
  Owns: .claude/rediacc_hooks/guards/block_pr_freeze_commit.py, .claude/rediacc_hooks/guards/test-block_pr_freeze_commit.py, .claude/rediacc_hooks/tests/goldens/block_pr_freeze_commit.jsonl
  Depends on: F1.
  Accept: `python3 .claude/rediacc_hooks/guards/test-block_pr_freeze_commit.py` rc 0 with the F1 case table; `npm run -s check:ci-guard-mutations` rc 0, where planting the DEFECT turns the guard test red; `npm run -s check:ci-hooks-resolvable` rc 0.
- [ ] F3 [lead] Live proof on the next PR in `--phase babysit`: a `feat` commit with a throwaway subject is refused at pre-bash and by commit-msg when run from a script; a `fix` commit lands.
  Owns: none -- live run, no edit.
  Depends on: F1, F2.
  Accept: both refusal texts and the admitted commit's sha are quoted in the tick evidence.

### plan-implementation and core priority

- [x] P0 [lead] Profile before writing anything: run `python3 -m cProfile -o <mktemp path> .ci/scripts/quality/check_plan_implementation.py` once, alone, with `GITHUB_BASE_REF=main`, plus `strace -f -c -e trace=execve` on the same run; record the subprocess count by git verb, the share of wall in subprocess waits, the follow_names total, and the judged box and plan counts.
  Owns: none -- measurement only.
  Depends on: none.
  Accept: the numbers are recorded on the plan item; if git subprocesses are below 50% of unloaded wall, P1 is re-scoped to what the profile names before a writer starts.
    (ticked) 2026-11-20T11:39:48Z by d778be9d: cProfile 2026-11-20 on the clean clone: wl_planrec.done_commit 409 s of 511 s (2,732 calls), git subprocess waits 94 s; strace -f -e execve: 7,514 git processes (config --get-regexp 1,378, log -1 --format=%cI ~2,049, merge-base --is-ancestor 1,836, show 945, log --follow 88 = 39 s wall); judged 683 boxes, 28 plans. Acted on in e72055c33 67bf7d410 c2f32c02e: 8m33s -> 49 s, same verdict
- [x] P1 [writer] Implement D2 in a new module .ci/rediacc_ci/quality/plan_impl_facts.py (batched reachability sets, the cat-file batch, the fact cache with its closure-hash key) and route the gate's oracles through it at .ci/scripts/quality/check_plan_implementation.py:2178-2230; add `--no-fact-cache`.
  Owns: .ci/rediacc_ci/quality/plan_impl_facts.py, .ci/scripts/quality/check_plan_implementation.py, .ci/rediacc_ci/tests/test_plan_impl_facts.py
  Depends on: P0.
  Accept: `.ci/scripts/quality/check_plan_implementation.py --selftest` rc 0 with new controls DIFFERENTIAL (on the live tree every oracle answer from the batch and the cache equals the per-call answer for every judged box), STALE (a planted entry under a changed closure hash is ignored) and REBASE (a commit dropped from HEAD's ancestry reads unreachable despite a cached fact); `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_plan_impl_facts.py` rc 0, including a mutant that drops `origin/main` from the reachability sets and must go red; two consecutive unloaded runs (cold, warm) print byte-identical findings to a `--no-fact-cache` run, warm wall recorded beside P0's figure.
    (ticked) 2026-11-20T13:18:24Z by d778be9d: commit:fdd241b32 commit:2f176850d (+ in-run memo and parallel follow walks c2f32c02e 98a058e02, identity index eb55be31f): .ci/rediacc_ci/quality/plan_impl_facts.py caches patch-ids, commit dates and follow walks keyed on a closure hash, reachability never stored, --no-fact-cache added; cold 51.3 s, warm 22.3 s, --no-fact-cache 47.0 s with identical findings (P0 baseline 8m33s / 511 s profile); check_plan_implementation.py --selftest rc 0; pytest .ci/rediacc_ci/tests/test_plan_impl_facts.py 9 passed: DIFFERENTIAL, STALE, REBASE and the origin/main mutant live in that pytest file rather than the gate selftest
- [x] C0 [lead] Land the uncommitted cheapPrereqFirst change already in scripts/ci-runner/pool.ts after confirming its control: a selftest case where a cheap prerequisite ranks ahead of a long gate, and a mutant returning 0 from `cheap` that goes red; commit it in the runner batch.
  Owns: scripts/ci-runner/pool.ts
  Depends on: none.
  Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 with the cheap-prerequisite control listed; the mutant run is red.
    (ticked) 2026-11-20T11:41:05Z by d778be9d: commit:62c5e6733 cheapPrereqFirst in scripts/ci-runner/pool.ts:1101 with scripts/ci-runner/learned-selftest.ts:345 cases; mutant (comparator multiplied by 0): npx tsx scripts/ci-runner/run.ts --selftest rc 1, "a cheap prerequisite is admitted first" failing in slots/today and slots/learned; restored rc 0, 697 assertions
- [x] C1 [writer] Implement D3: pass a `critical` flag from the rank's pinned set and the runner's critical-path computation into the grant; scripts/ci-runner/exec.ts prefixes `nice -n 10` for non-critical gates where `wrapped` is true, and the receipt records the priority each gate ran at.
  Owns: scripts/ci-runner/exec.ts, scripts/ci-runner/rank.ts, scripts/ci-runner/run.ts, scripts/ci-runner/learned-selftest.ts
  Depends on: C0.
  Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 with two new controls (the argv for a non-pinned gate carries the nice prefix and a pinned one does not; a mutant dropping the flag is red), a simulator case in scripts/ci-runner/learned-selftest.ts showing a pinned single-core gate's simulated end improving under saturation, and the selected-set equality check (same ids with and without priority) green.
    (ticked) 2026-11-20T12:00:22Z by d778be9d: commit:7faaba292 gateSpawnArgv (scripts/ci-runner/exec.ts:40) nices non-pinned gates, receipt records niceness; npx tsx scripts/ci-runner/run.ts --selftest rc 0 (704 assertions) with the argv controls and a live +10 nice check, mutant dropping the flag rc 1; simulator case at scripts/ci-runner/sim.ts:654 (pinned one-core gate 100 s vs 200 s under 2x saturation; same gates and grants), mutant ignoring niceness rc 1. The simulator case sits in sim.ts beside the engine, whose simulate() is module-private, not in learned-selftest.ts

### prose-style and account-server

- [x] S1 [writer] Implement D4 in .ci/rediacc_ci/quality/prose_style.py run_check (:1397-1470); the one-extract refactor passes the extracted lines into the lint path, so `lint_text` keeps its public signature and gains an optional `lines` argument.
  Owns: .ci/rediacc_ci/quality/prose_style.py, .ci/rediacc_ci/tests/test_quality_prose_style.py
  Depends on: none.
  Accept: `.ci/scripts/quality/check_prose_style.py --selftest` rc 0 with new controls CONTENT (warm cache, a file edited to add an R-rule hit, the new finding fires), RULES (warm cache, a rule's pattern changed in a temporary rules file, the finding set changes) and MOVE (a planted stub chain re-keys ident with the cache warm), each with a mutant that drops its key part and goes red in the pytest file; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_prose_style.py` rc 0; on the live tree, cold and warm `npm run -s check:ci-prose-style` print the same verdict line and baselined count, warm wall recorded.
    (ticked) 2026-11-20T11:01:51Z by d778be9d: commit:4525b5203 (+ review fixes 9cb0191b6 e648197c3 0fdb501a2): run_check per-file content cache, lint_text optional lines/note; npm run -s check:ci-prose-style 40.6 s cold -> 0.56 s warm, same verdict rc 0; PYTHONPATH=.ci pytest test_quality_prose_style.py 281 passed rc 0
- [x] A1 [writer] Close the loopback-DNS hole: `networkPeer` returns `ip:53` for any connect to port 53, loopback included (scripts/ci-runner/path-trace.ts:128-140); trace-honest inherits it.
  Owns: scripts/ci-runner/path-trace.ts, scripts/ci-runner/trace-honest.ts
  Depends on: none (it lands in the runner batch with C0 and C1).
  Accept: `npx tsx scripts/ci-runner/path-trace.ts --selftest` rc 0 with new cases `127.0.0.53:53`, `127.0.0.11:53` and `[::1]:53` classed as network and `127.0.0.1:8787` still not; a mutant restoring the old loopback rule turns the 127.0.0.53 case red; `npx tsx scripts/ci-runner/trace-honest.ts --selftest` rc 0.
    (ticked) 2026-11-20T11:52:40Z by d778be9d: commit:5b4d28538 networkPeer classes any port-53 connect as network (scripts/ci-runner/path-trace.ts:126); npx tsx scripts/ci-runner/path-trace.ts --selftest 159/159 rc 0 with 127.0.0.53:53, 127.0.0.11:53, [::1]:53 network and 127.0.0.1:8787 not; mutant restoring the old loopback rule 158/159 rc 1; npx tsx scripts/ci-runner/trace-honest.ts --selftest 59/59 rc 0
- [x] A0 [lead] Find who resolves a name during check:ci-account-server: run `strace -f -e trace=connect -s 256` on `npm run check:ci-account-server` with `/proc/<pid>/cmdline` mapping, and name the process, the hostname and the call site.
  Owns: none -- investigation.
  Depends on: A1.
  Accept: the caller, the hostname and the file:line are recorded on the item with a ruling: incidental (go to A2) or under test (stop; the gate stays whole-tree).
    (ticked) 2026-11-20T12:51:48Z by d778be9d: strace -f -e trace=connect,execve,clone,clone3,sendto,sendmmsg on npm run check:ci-account-server (rc 0, 4908 tests): 2 port-53 connects to 10.255.255.254, both from a vitest worker (node .../private/account/node_modules/vitest) resolving nothing.example.invalid, call site private/account/tests/integration/no-live-stripe.test.ts:28; ruling: incidental (the assertion needs only a non-wrapper error), go to A2; recorded on #527aa5b2
- [x] A2 [writer] Remove the incidental lookup at its source as A0 names it (a loopback literal or a test hosts entry for a fixture hostname, or a disabled update check), changing nothing any test asserts.
  Owns: the files A0 names; the lead writes them into the brief, and they must fall inside this plan's Owns or the plan header is amended first.
  Depends on: A0 ruling incidental.
  Accept: `npm run -s check:ci-account-server` rc 0 with the same test count as before (the vitest summary line), and an strace run shows no port-53 connect.
    (ticked) 2026-11-20T13:07:46Z by d778be9d: commit:26e46869d (account 70a89a3): the no-live-stripe passthrough fetches http://127.0.0.1:9/x instead of https://nothing.example.invalid/x; strace -f -e trace=connect on npm run -s check:ci-account-server: rc 0, 0 port-53 connects, Tests 4911 passed (the 4908 of the A0 baseline plus the 3 of the new tests/integration/totp-step.test.ts, private/account 7be4a78 + a62fea8, the TOTP flake fix the first A2 run uncovered)
- [ ] A3 [lead] Inside the pinned image, run `npx tsx scripts/ci-runner/path-trace.ts --gate check:ci-account-server`, adopt the traced `paths` into scripts/ci-runner/manifest.ts with `pathsOrigin: 'traced'`, and regenerate the lock and the trace ledger row (scripts/ci-runner/trace-ledger.ts).
  Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts
  Depends on: A2, R1.
  Accept: `npx tsx scripts/ci-runner/trace-honest.ts --mode both --gate check:ci-account-server` rc 0; `npm run -s check:ci-gates-lock` rc 0; a planted edit under the traced paths re-selects the gate in ci:quick and an edit outside them carries it (both recorded).

### One image and signed receipts

- [ ] R0 [lead] Measure before committing to a shape: the full devcontainer image's compressed size and pull time on one hosted runner job (a temporary step in an existing ci-quality job, reverted in the same PR), and `node --version` and `python3 --version` inside the pinned digest; choose the full image or a `toolchain` stage the full image is built FROM (published from the same build, so node and python are byte-identical): if the pull exceeds 90 s per job, use the stage.
  Owns: .github/workflows/ci-quality.yml (temporary step, reverted in the same PR)
  Depends on: none.
  Accept: the size, pull time, versions and the decision are recorded on the item.
- [ ] R1 [writer] Pin the image: .ci/config/devcontainer-image.json holds `{image, digest, stage}`; .ci/rediacc_ci/core/devbox.py reads it in place of `devcontainer:latest`; if R0 chose the stage, .devcontainer/Dockerfile gains the `toolchain` stage and the full image is built FROM it; the devbox binds the ci:quick clone root at the same path; the salt gains the image term of D6 (scripts/ci-runner/input-hash.ts:242-257) from an env var the devbox and the workflow set, `host` when it is absent.
  Owns: .ci/config/devcontainer-image.json, .ci/rediacc_ci/core/devbox.py, .devcontainer/Dockerfile, scripts/ci-runner/input-hash.ts, scripts/ci-runner/quick-clone.ts
  Depends on: R0.
  Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 with a new salt control (two environments differing only in the image term yield different salts; a mutant dropping the term is red); a devbox selftest asserting the run image equals the pin, where a mutant reverting to `:latest` is red; `./run.sh devbox exec npm run ci:quick` completes and its receipt's salt differs from the host receipt's.
- [ ] R2 [writer] Move one CI lane into the container, quality-content first (it hosts check:ci-prose-style): scripts/gate-bind.ts emits `container:` from the pin for lanes listed in the pin file; .github/actions/setup-workspace/action.yml takes a `node-from-image` input that skips setup-node and checks `node --version` against the image; permissions are added per job.
  Owns: scripts/gate-bind.ts, .github/workflows/ci-quality.yml, .github/workflows/ci.yml, .github/actions/setup-workspace/action.yml
  Depends on: R1.
  Accept: `npm run -s check:ci-workflows` rc 0; the binder's own check rc 0; one PR run where the lane is green in the container and its log shows the image's node and python versions equal R0's.
- [ ] R3 [writer] Add the receipt writer scripts/ci-runner/ci-receipt.ts and its workflow steps in the container lane (write, `actions/attest-build-provenance` on the file, upload as an artifact); add the local verb `ci-receipt fetch`, which downloads, verifies with `gh attestation verify` (D6 flags) and stores `.ci/cache/receipts/ci-<tree>.json` priors; the runner's prior loader accepts them under the unchanged inputHash rule; gate_ledger fold-ci reads the receipt's inputHash when present (.ci/rediacc_ci/ci/gate_ledger.py:380).
  Owns: scripts/ci-runner/ci-receipt.ts, scripts/ci-runner/input-hash.ts, .github/workflows/ci-quality.yml, .ci/rediacc_ci/ci/gate_ledger.py
  Depends on: R2.
  Accept: `npx tsx scripts/ci-runner/ci-receipt.ts --selftest` rc 0 with controls (only `pass` verdicts with a non-null inputHash are written; a gate whose step was skipped is absent; an unverifiable file is never stored, with a stub verifier returning failure, and a mutant storing unverified files is red); live: one PR run's receipt verifies with `gh attestation verify` locally (output quoted), and after `ci-receipt fetch` a ci:quick run on the same tree carries at least one gate from the `ci` origin.
- [ ] R4 [writer] Push guard: in `_carried_refusal` (.claude/rediacc_hooks/guards/block_unverified_push.py:1643) an origin whose file is a `ci-` receipt is re-verified through the same verifier seam (memoized per sha256); an unverifiable origin is refused with the field named; a `DEFECT` tuple disables the verification arm.
  Owns: .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py
  Depends on: R3.
  Accept: `python3 .claude/rediacc_hooks/guards/test-block_unverified_push.py` rc 0 with cases for a verified CI origin admitted, a byte-altered receipt refused, a receipt signed by another workflow refused (stub verifier), and a CI origin with verdict `fail` refused; `npm run -s check:ci-guard-mutations` rc 0, with the DEFECT turning the suite red.

### Rebase consistency (operator /ask 2026-11-20: build now, first wave)

Inventory (sonnet Explore, 2026-11-20): review records, finding fixes, investigation rows and live receipts already survive a rebase through `Patch-Id` and the successor map (.ci/rediacc_ci/proof/successor.py); lease landing matches by `git cherry`; box signatures and Plan-Box trailers are content-keyed; receipts are tree-keyed and void on a moved base, which is correct. The gaps: no check reads a lease against a moved base (`behind_base_refusal` in .claude/rediacc_hooks/guards/block_unverified_push.py:853-905 judges only `commit_policy.BRANCH_SHAPE` branches at push time, and .ci/rediacc_ci/quality/branch.py:165-215 runs only on pull requests); a commit with no review record cannot be mapped to its rewritten sha; a conflict-resolved commit changes its patch-id; bare-sha plan citations go red after a rebase-merge; and `done=` in compacted plan records is untested under a rebase-merge.

- [x] RB1 [writer] A behind-base reader for leases beside .claude/hooks/stop/wl_worktrees.py: for each lease of this session with at least one commit, fetch the base itself (the lease record's `base` per repo; while the PR branch is open and frozen the base is that branch, after its merge `origin/main`), and judge behind by `merge-base --is-ancestor <base> <lease head>`, counting commits `git cherry` marks `-` as absorbed; a failed fetch allows with one NOTE line.
  Owns: .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/wl_rebase.py, .claude/hooks/stop/test-rebase-consistency.py
  Depends on: none.
  Accept: `python3 .claude/hooks/stop/test-rebase-consistency.py` rc 0 with controls on real temporary repos: a lease whose base moved reads behind; a lease at the base reads clean; a failed fetch allows with a NOTE; a rebase-merged parent (patch-equivalent commits) reads absorbed, not behind; a lease with no commits is skipped; and a mutant that drops the fetch (reading a stale ref) goes red.
    (ticked) 2026-11-20T12:15:34Z by d778be9d: commit:3af8eeddc wl_rebase.behind_base (.claude/hooks/stop/wl_rebase.py:57); python3 .claude/hooks/stop/test-rebase-consistency.py rc 0, 10 controls on real temporary repos: base moved reads behind, at the base clean, failed fetch allows with a NOTE, rebase-merged parent reads absorbed, no commits skipped, dropped fetch reads a stale ref; module mutant deleting the fetch rc 1 (BEHIND, NOTE fail)
- [x] RB2 [writer] A Stop-hook block from RB1's reader: once the PR the lease was cut beside has merged and the lease reads behind, the hook blocks with the `/branch-rebase <base>` recipe and the post-rebase proof commands (RB4), in the style of the push guard's REBASE LOCALLY text.
  Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/test-rebase-consistency.py
  Depends on: RB1.
  Accept: the RB1 test file gains a planted merged-parent fixture whose block text names `/branch-rebase` and the RB4 commands, and a control where the PR is still open (no block); `npm run -s check:ci-hooks-resolvable` rc 0.
    (ticked) 2026-11-20T12:26:56Z by d778be9d: commit:a54889467 behind_block (.claude/hooks/stop/wl_rebase.py:228) appended to worktree-unlanded after a merge; python3 .claude/hooks/stop/test-rebase-consistency.py rc 0, 26 controls: the merged-parent fixture's block names /branch-rebase main and the RB4 commands, the open-PR control blocks nothing; npm run -s check:ci-hooks-resolvable rc 0
- [ ] RB3 [writer] Widen `behind_base_refusal` (.claude/rediacc_hooks/guards/block_unverified_push.py:822-905) to judge lease branches as well as MMDD-N branches, with the base read as in RB1.
  Owns: .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py
  Depends on: RB1.
  Accept: `python3 .claude/rediacc_hooks/guards/test-block_unverified_push.py` rc 0 with a lease-branch case refused when behind and admitted at the base; a `DEFECT` tuple that drops lease branches turns the suite red under `npm run -s check:ci-guard-mutations` (rc 0).
- [x] RB4 [writer] Post-rebase proof: a verb that runs `--git verify-rebase` and `python3 .claude/hooks/stop/wl_review.py --check` after a rebase and names every dev commit with no review record (which the successor map cannot carry) and every commit whose patch-id changed (conflict-resolved), before the push.
  Owns: .claude/hooks/stop/wl_rebase.py, .claude/hooks/stop/test-rebase-consistency.py
  Depends on: RB1.
  Accept: the test file gains a REBASE control where an unreviewed dev commit is flagged and a reviewed one is not, and a conflict-resolved commit (patch-id changed) is flagged.
    (ticked) 2026-11-20T12:21:06Z by d778be9d: commit:cac6cc8be wl_rebase.rebase_proof (.claude/hooks/stop/wl_rebase.py:126) and worklist.py --git rebase-proof <snap> [base]; python3 .claude/hooks/stop/test-rebase-consistency.py rc 0, 17 controls, REBASE: an unreviewed commit flagged and a reviewed one not, a hand-resolved conflict (patch-id moved) flagged CHANGED; pairing mutant 2 of 17 fail; live on 1104-1 rc 0 (console 3883 carried, reviews ok)
- [x] RB5 [writer] Dev-lease plan citations: a plan edited from a lease cites blob ids, never a lease commit sha; check:ci-plan-citations already reads orphaned shas red after a rebase-merge (.ci/scripts/quality/check_plan_citations.py:573-626), so this box adds a write-time refusal in .claude/hooks/stop/wl_planrec.py for a commit pointer that is not reachable from the live branch or origin/main.
  Owns: .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/test-planrec.py
  Depends on: none.
  Accept: `python3 .claude/hooks/stop/test-planrec.py` rc 0 with a control where a lease-only commit pointer is refused at write time and a reachable one is accepted.
    (ticked) 2026-11-20T12:09:43Z by d778be9d: commit:239426cba commit:69594a412 wl_planrec.resolve judges a commit pointer from a lease against the main worktree branch (or origin/main only), never the lease HEAD; python3 .claude/hooks/stop/test-planrec.py rc 0, 336 controls, including RB5 (lease-only pointer refused, live-branch pointer accepted); PYTHONPATH=.ci:.claude/hooks/stop pytest .ci/rediacc_ci/tests/test_planrec_live_ref.py 3 passed (detached-main fallback included); mutant answering HEAD in a lease: 1 failed
- [x] RB6 [lead] Live test of `done=` under a rebase-merge: on a scratch branch whose plan record carries a compacted `done=<sha9>`, rebase-merge it onto main in a throwaway clone and run `npm run -s check:ci-plan-record` there; record whether R4 (.ci/scripts/quality/check_plan_record.py:1108-1125) survives, and file a fix box here if it does not.
  Owns: none -- live test in a throwaway clone.
  Depends on: none.
  Accept: the result (rc and the R4 line) is recorded on the plan item, plus a fix box when R4 fails.
    (ticked) 2026-11-20T12:30:34Z by d778be9d: live test 2026-11-20 in a scratch repo: R4 fails under a rebase-merge for a branch-only done= sha (resolve answered (False, no such commit) after the merge and a prune); all 12 current done= shas are on origin/main; result recorded on #527aa5b2 and fix box RB7 filed (.ci/scripts/quality/check_plan_record.py:1108)
- [x] RB7 [writer] R4 survives a rebase-merge: a compacted `done=<sha>` that cites a branch commit reads `no such commit` on main once the PR is rebase-merged (RB6's live test, 2026-11-20: resolve() of the pre-merge sha after the merge and a prune answered `(False, 'no such commit')`), so .ci/scripts/quality/check_plan_record.py R4 refuses on main. Fix both ends: `worklist.py --plan-compact` writes `done=` only with a commit reachable from origin/main (or defers the compaction until the merge), and R4 resolves a missing `done=` sha through the successor map (.ci/rediacc_ci/review/successor.py, patch-id) before refusing.
  Owns: .ci/scripts/quality/check_plan_record.py, .claude/hooks/stop/wl_planrec.py
  Depends on: RB6.
  Accept: `python3 .claude/hooks/stop/test-planrec.py` rc 0 with a control that rebase-merges a branch whose record carries `done=<branch sha>`, prunes the orphan, and reads R4 green through the successor map, and a mutant without the successor lookup red; a `--plan-compact` control refusing a branch-only `done=`.
    (ticked) 2026-11-20T12:43:31Z by d778be9d: commit:334616cbe commit:94f2e23ab (+ review fixes 147ba8f60 f9d4291d6 3a13377da dbe796e22): wl_planrec.compact refuses a done= not on origin/main; check_plan_record R4 resolves done= through resolve_done (.claude/hooks/stop/wl_planrec.py:330), carrying a rebase-merged sha via the successor map; python3 .claude/hooks/stop/test-planrec.py rc 0, 350 controls, including the rebase-merge + prune carry, its mutant without the successor lookup refused, and the compaction refusal; npm run -s check:ci-plan-record rc 0

### Measurement

- [ ] M1 [lead] On the next PR after every box above has landed, run it to merge in the babysit phase and record per fix round: wall, carried and ran counts, the critical path, the cpu floor, check:ci-plan-implementation, check:ci-prose-style and check:ci-account-server wall and carry state, freeze refusals, and how many gates carried from a `ci` origin; compare against /tmp/m/ciq10-18.log and put the dev-track decision to the operator with those numbers.
  Owns: none -- measurement.
  Depends on: F3, P1, C1, S1, A3 (or the A0 stop ruling), R4.
  Accept: a table of the rounds is on the plan item, and an operator question about the dev track is filed with it.

## Risks

1. Freeze false refusals: a fix commit mislabelled `feat`, a needed `chore(submodules)` pointer bump in the merge phase (.claude/commands/pr-merge.md:136), or a `chore(pins)` fix. The submodule bump is admitted by rule 5 only when the bumped ranges are fix-only. A type label is honour-based: a feature written as `fix` passes.
2. Branch-bound freeze: a peer session on the same branch is frozen by this session's phase, intended under one-branch/one-PR; a peer learns the escape from the refusal text.
3. Nice: niced gates with internal timeouts may time out on a saturated machine; M1 watches for new timeouts. Learned durations of niced gates rise, which shifts ranking (ordering only).
4. Cache staleness: covered by the closure hash and immutable keys; the residual risk is a missed key component, and the differential controls compare cached and uncached answers on the live tree every selftest run.
5. Image lanes: pull time, the private registry needing `packages: read`, docker-in-container for gates that need docker, the native node_modules ABI, and setup-workspace cache keys that include the node version. R0 measures before anything is committed.
6. Receipt value is small for the critical path: check:ci-pytest (carry-exempt) and check:ci-plan-implementation (env) never carry, receipt or not. The gain is on carry-eligible gates after a rebase or branch cut, and across machines and sessions.
7. The runner batch voids every carry once (GLOBAL_INPUTS), and switching local runs into the image changes the salt, so the first in-image run is cold.
8. A0 may find the DNS lookup is real behaviour under test; then account-server stays whole-tree and its saving is zero.

## Open questions for the lead

1. Admit `chore(submodules)` in the merge phase when every gitlink points at an ancestor of that submodule's origin/main (the /pr-merge pointer bump)? DEFAULT: admit, merge phase only.
2. Salt term: add the image digest (strictly finer, D6), or rely on node and python version equality alone? DEFAULT: add it.
