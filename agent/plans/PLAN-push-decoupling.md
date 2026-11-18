# PLAN: push decoupling -- pinned receipts, shared locks, a `Needs:` box tag, and the gate-cost remainder
Status: approved -- operator /ask 2026-11-18 chose remedies 1, 3 and 4 in one plan; rejected: remedy 2 (live runners bound to a sha) and remedy 5 (smaller push batches)
Owner: d778be9d
First-Seen: 2026-11-18
Depends-On: PLAN-ciquick-cpu.md, PLAN-vmcheck-incremental.md -- remedy 4 adds only what those two lack; every box below states its own `Depends on:` clause, so remedies 1 and 3 start at once
Priority: P1 -- on 1104-1 a push cycle costs about 3 h of gate wall, and 42 of 59 commits waited 70 min on average to land
Concurrency: parallel -- each box names its files, and boxes with no `Depends on:` edge between them own disjoint files
Live-Proof: bench -- box L3 edits the enterprise-proof runner, so the bench proof is run again with the lock in place
Owns: agent/plans/PLAN-push-decoupling.md, scripts/ci-runner/quick-clone.ts, scripts/ci-runner/run.ts, scripts/ci-runner/path-trace.ts, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_plandeps.py, .claude/hooks/stop/wl_boxready.py, .claude/hooks/stop/test-*.py, .claude/rediacc_hooks/tests/test_wl_*.py, .claude/commands/writers-now.md, docs/agent-reference/plan-records.md, .ci/rediacc_ci/core/resource_lock.py, .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/drills/backup_check_trigger.py, .ci/rediacc_ci/drills/lib.py, .ci/rediacc_ci/drills/license.py, .ci/rediacc_ci/drills/transfer.py, .ci/rediacc_ci/drills/universe.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/enterprise/proof.py, .ci/rediacc_ci/release/local.py, .ci/rediacc_ci/release/local_gates.py, .ci/rediacc_ci/gitx.py, .ci/rediacc_ci/tests/**, .ci/scripts/quality/check_record_paths.py, .ci/scripts/quality/check_plan_live_proof.py, .ci/policy/carry-exempt.json, .ci/config/proof-tiers.json, packages/e2e-tests/src/base/bridge-global-setup.ts, rdc.sh

## Context (measured 2026-11-18 on 1104-1)

- One push cycle costs about 3 h of gate wall time.
- 14 of 15 ci:quick reruns judged a HEAD that a later commit had already moved, so the receipt each one wrote spoke for a tree nobody was pushing.
- 42 of 59 commits waited 70 min on average to land, because the main checkout freezes landings while a receipt builds.
- A records-only `worklist.py --review-commit` after a green receipt forces a hand re-run of the readers. Seen 2026-11-18: the receipt for tree 27aae46c was refused against f58c7963.
- The wall of one ci:quick run is set by pytest: 37454 passed in 1272 s.
- gates.lock.json holds 113 whole-tree gates of 399 after commits 434f1d3b3a and 22efb11ea6, and 20 gates declare `names: ['**']`.

The cause is one coupling stated three ways. A receipt is tied to whatever HEAD the main checkout holds when the run ends. The fleet, bench and the dev gateway are shared with no common lock, so the only safe schedule is one run at a time in one tree. A plan box does not say what it waits for, so every live box is treated as waiting for a push.

## Out of scope, by the ruling

- **Remedy 2, live runners bound to a sha.** Not chosen. A live runner keeps reading the main checkout; only the gate runs and the two drills of R5 and R6 move to a pinned clone.
- **Remedy 5, smaller push batches.** Not chosen. `turbo_push`, `batch_size` and the push cadence in CLAUDE.md stay as they are.

## Design 1: pinned receipts and locks

**D1.1 `ci:quick --commit <sha>`.** The kept clone already resets to the HEAD captured at start (`prepareClone`, scripts/ci-runner/quick-clone.ts:597-664) and the run only logs when HEAD moved (:969-973). With `--commit <sha>` the captured head is the named commit instead of the live HEAD: it must be an ancestor of the live branch tip, the clone resets to it, and the whole receipt is archived as `.ci/cache/receipts/<tree>.json`. `block_unverified_push.read_receipt` reads that copy first (.claude/rediacc_hooks/guards/block_unverified_push.py:1832-1853), so the guard needs no change. A pinned run never writes `.ci/cache/prepush-receipt.json` over a newer tree's receipt.

**D1.2 Automatic advance.** When HEAD moved during a run, or `--commit` named an ancestor, the runner follows the lane with the pass `planAdvance` already plans (scripts/ci-runner/run.ts:4853, called at :5403): record-only movement runs only the record readers and appends an `advances` step, and any other movement carries every gate whose input hash is unchanged and runs the rest. `worklist.py --review-commit` (.claude/hooks/stop/worklist.py:3711) starts the records-only advance itself after its commit, and reports the advanced tree or the refusal.

**D1.3 The Stop hook reads trees.** `green_receipt_on_unpushed_head` (.claude/hooks/stop/wl_checks.py:2751-2790) compares `receipt.head` with HEAD's commit sha, so a record-only commit after a green run reads as no receipt. It compares HEAD's tree with the receipt's `headTree` and with the last tree of its `advances` chain instead, reading the archive copy first like the guard. The RECEIPT IN FLIGHT hold (`JUDGE_RECEIPT_IN_FLIGHT`, .claude/hooks/stop/worklist_messages.py:3360; `RECEIPT_ORDERS` and `sanitize_next_action`, .claude/hooks/stop/wl_judge.py:1453-1519; the landing hold at .claude/hooks/stop/wl_checks.py:2860) no longer fires for ci:quick, because the clone judges a pinned tree and D1.2 brings the receipt forward. It stays for vm:check until R5 has landed and R7 relaxes it for a pinned run.

**D1.4 vm:check and the backup drill from a pinned clone.** vm:check refuses a lease (`lease_refusal`, .ci/rediacc_ci/drills/vm_check.py:4487-4498) because a run restarts the shared dev gateway and rebuilds the CLI from the live tree on each rdc call. `--commit <sha>` runs it from the kept clone at that commit, with the clone's own `bin/renet` build, its own CLI build and its own gateway record (port and `.account-server` state under the clone), and files the receipt under the pinned tree. The lease refusal stays. `record_drill` (.ci/rediacc_ci/drills/backup_check_trigger.py:381-384) reads `HEAD^{tree}` of the checkout it is given, so the backup drill gains the same `--commit` entry and records the pinned tree.

**D1.5 One fleet lock.** Only vm:check takes `rediacc-vm-check.lock` today (`LOCK_NAME`, .ci/rediacc_ci/drills/vm_check.py:98; `lock_path` and `Lock`, :1300-1345). The e2e-local setup resets the VMs with no lock (`opsManager.resetVMs()`, packages/e2e-tests/src/base/bridge-global-setup.ts:377-400, VMs .1, .11 and .12), a hand-run drill uploads renet to .11 with none, and `./rdc.sh ops up|down` takes none. A new module `.ci/rediacc_ci/core/resource_lock.py` holds one flock per named resource in the directory `lock_path` already picks, with a payload of pid, session, purpose and start time, a bounded wait that prints the holder, and a `python3 -m rediacc_ci.core.resource_lock run --resource <name> -- <argv>` wrapper for callers that are not Python. The resource `fleet` keeps the file name `rediacc-vm-check.lock`, so `wl_checks.vm_check_running` (.claude/hooks/stop/wl_checks.py:2671) keeps reading it. The `rdc.sh` wrapper takes it for `ops up|down`; the shipped CLI is not changed.

**D1.6 One bench lock per region.** `deploy_bench.py`, `deploy_proxy.py --target bench`, `reset_bench.py` and the enterprise-proof runner (`.ci/rediacc_ci/enterprise/proof.py`) take no lock today (no `flock` in any of the four). Each takes the resource `bench-<region>` for the region it acts on, so a reset cannot land under a deploy or a proof.

**D1.7 Drill identities.** `drill-license-%d@rediacc.io` and `drill-transfer-%d@rediacc.io` take `int(time.time())` (.ci/rediacc_ci/drills/license.py:215, .ci/rediacc_ci/drills/transfer.py:43), so two runs in one second share a user. `EMAIL = "drill-universe@rediacc.io"` is fixed (.ci/rediacc_ci/drills/universe.py:23), so two concurrent universe drills share one. Each takes a per-run token (seconds plus pid plus four random hex) from one helper.

**D1.8 `release:local --commit <sha>`.** `base_context` reads `HEAD`, `HEAD^{tree}` and `HEAD:private/account` of the checkout (.ci/rediacc_ci/release/local.py:1210-1216), and the gates judge that head (`ci_quick_refusal`, .ci/rediacc_ci/release/local_gates.py:118; `vm_check_refusal`, :364-385; `origin_main_refusal` and `live_ancestor`, :496-533). With `--commit <sha>` the context and every gate take the named commit, which must be an ancestor of the branch tip, and the release clone under `.ci/cache/release/<sha>` is built from it.

## Design 3: the `Needs:` box tag

**D3.1 Grammar.** An indented sub-line under a box, never on the box line, because the signature is the sha256 of the normalized first 120 characters of the box line (`box_sig`, .claude/hooks/stop/wl_planrec.py:848-855) and the line must stay byte-identical:

    Needs: none|bench-deploy|verified-vmcheck|pushed-head

`none` is a box provable from a lease or the main checkout as it stands. `bench-deploy` needs the branch's code on bench. `verified-vmcheck` needs a VERIFIED vm:check receipt on the tree. `pushed-head` needs the branch tip on origin. A later `(corrected ...)` line supersedes an earlier value, as for the two existing tags.

**D3.2 Parser.** Beside `box_github_wait` in .claude/hooks/stop/wl_plandeps.py: `_TAG_RE` (:934) gains `Needs`, the `GitHubWait` reading (:938-953) gains a `needs` field, the phrase scrub (:1041) strips the value so `pushed-head` is never searched for a phrase, and `github_wait_findings` (:1046) reports an unknown value. A box with no `Needs:` line derives one: `pushed-head` from a valid tag of any kind in `GITHUB_ONLY_KINDS` (:930), and from a route tag the class of its runners (`deploy-bench`, `bench-cli`, `d1-migrations` and `deploy-proxy-bench` give `bench-deploy`; `vm-check`, `hostinger` and `e2e-local` give `verified-vmcheck`; `www-local` gives `none`). A stated value that contradicts a valid tag is a finding.

**D3.3 Readiness.** `.claude/hooks/stop/wl_boxready.py` reads the value: a `none` box is startable with no receipt and no push, a `verified-vmcheck` box once `vm_tier.admit` admits the tree, a `bench-deploy` box once the recorded bench deploy is at the branch, and a `pushed-head` box once the tip is on its upstream. The Stop hook and `/writers-now` stop treating every live box as waiting on a push.

**D3.4 Phrases and the untagged boxes.** `tiers.live.github_waits` (.ci/config/proof-tiers.json:429-439) gains four phrases: "PR CI", "PR head", "post-merge" and "pushed branch". About 12 open boxes name one of them and carry no tag; each gets a tag line and a `Needs:` line as indented sub-lines, in the commit that adds the phrases. By signature, read from `.ci/config/plan-boxes.json`:

| Plan | Box signatures |
|---|---|
| PLAN-health-checks-local.md | 85f55665, 2f4e8cf6 |
| PLAN-scope-bws-signing-key-to-consuming-step.md | 79fbc186 |
| PLAN-ci-vm-image-followups.md | 9071fc1d |
| PLAN-enterprise-isolation.md | cc583290, 3c1ed10a |
| PLAN-enterprise-tenants.md | cbb8a648 |
| PLAN-product-domain-rename.md | bd0c8a21 |
| PLAN-website-routing-and-mail.md | 3285fb52 |
| PLAN-vmcheck-incremental.md | 0f19515b |
| PLAN-d1-eu-jurisdiction.md | 7a79f65c |
| PLAN-proxy-cd-six-targets.md | e098f28f |

**D3.5 Consumers.** .claude/commands/writers-now.md:39 routes by the tag and now by `Needs:`. docs/agent-reference/plan-records.md:161-168 documents the third sub-line, and its line 168 still says `LP8_ENFORCED` is False and the findings print as advisory, while `LP8_ENFORCED = True` at .ci/scripts/quality/check_plan_live_proof.py:154.

## Design 4: the gate-cost remainder

The boxes for this remedy already exist and are not repeated here:

- PLAN-ciquick-cpu.md W2.5 and W2.6 take the whole-tree count from 113 to 80 or fewer.
- PLAN-ciquick-cpu.md W3.2 and W3.3 make the declared sets honest and wire the planned gate-paths-honest gate (PLAN-ciquick-cpu W3.3).
- PLAN-ciquick-cpu.md W4.1, W4.2 and W4.3 select pytest by impact, which is what moves the 1272 s wall.
- PLAN-vmcheck-incremental.md V3 proves the per-leg rerun of vm:check on the fleet.

What they lack is the design of the W2.2 remainder, in three waves.

**Wave 1, four parallel writers (boxes F1 to F4).**

- A, check_record_paths.py: `scripts/ci-runner/manifest.ts` and `scripts/ci-runner/trace-ledger.ts` hold other gates' path lists as data, so they are not scan code of their own (a `NOT_SCAN_CODE` set); and a `declared` tier reads each gate's lock `paths`, `names` and `lists`, so a gate whose declared inputs cover a record path is a record reader. That closes the hole where the 20 `names: ['**']` gates are not counted as record readers.
- B, path-trace.ts: a fixture's own index read is counted as foreign today (`INDEX_PATH`, scripts/ci-runner/path-trace.ts:199; `foreignIndexReader`, :766); `--recurse-submodules` folds to names plus the gitlink paths; pathspec and `--format` folding; `git diff --quiet <file>` is content of that file; a history `refs` field; extension folding; and kind-aware folding for carry-exempt gates.
- C, gate-side walkers: a gate that walks the disk lists untracked build directories and so reads as whole-tree; each moves to a tracked listing. `file_modes` (.ci/rediacc_ci/gitx.py:361-366) runs `ls-files -s`, which reads as content, and moves to `--format`.
- D, .ci/policy/carry-exempt.json: one `kind` per row (clock, history, network or cache), 26 rows today.

**Wave 2, the re-trace G (PLAN-ciquick-cpu.md W2.6).** Seven steps in the kept clone, each a re-trace of the gates the previous change unblocked, each ending with the whole-tree count read from gates.lock.json:

| Step | Expected whole-tree count |
|---|---|
| start | 113 |
| G1 | 106 |
| G2 | about 99 |
| G3 | about 81 |
| G4 | about 74 |
| G5 | about 67 |
| G6 | about 35 |
| G7 | about 31 |

A step that misses its count by more than 5 names the gates that stayed and why; no rule is loosened to reach a number.

**Wave 3.** PLAN-ciquick-cpu.md W3.3, the planned gate-paths-honest gate (PLAN-ciquick-cpu W3.3).

## Boxes

Order: remedy 1 with the locks, then remedy 3, then remedy 4.

### Remedy 1: pinned receipts
- [ ] R1 [writer] `ci:quick --commit <sha>` judges a pinned ancestor of the branch tip in the kept clone and archives its receipt per tree (D1.1)
    Owns: scripts/ci-runner/quick-clone.ts, .ci/rediacc_ci/tests/gates/test_gate_ci_runner.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_ci_runner.py` exits 0 with three new cases: a pinned ancestor writes `.ci/cache/receipts/<its tree>.json` and leaves a newer `prepush-receipt.json` alone; a sha that is not an ancestor of the tip is refused before the clone is touched; a lease is still refused.
- [ ] R2 [writer] A run whose HEAD moved, or that judged a pinned ancestor, follows its lane with the carry and advance pass by itself (D1.2)
    Owns: scripts/ci-runner/run.ts, scripts/ci-runner/quick-clone.ts
    Depends on: R1.
    Needs: none
    Accept: `npx tsx scripts/ci-runner/run.ts --selftest` exits 0 with new controls: record-only movement appends one `advances` step and runs only the readers; a code movement carries the gates with an unchanged input hash and runs the rest; a rename from code to a record path does not advance. run.ts is also owned by PLAN-ciquick-cpu.md W1.1, so this lands when W1.1 has no open edit there.
- [ ] R3 [writer] `worklist.py --review-commit` starts the records-only advance after its commit and prints the advanced tree or the refusal (D1.2)
    Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/stop/test-review-mark.py
    Depends on: none.
    Needs: none
    Accept: `python3 .claude/hooks/stop/test-review-mark.py` exits 0 with two new cases: after a green whole receipt the verb's commit leaves a receipt the push guard admits at the new tree, with no hand re-run; with no green receipt the verb commits and starts nothing.
- [ ] R4 [writer] The Stop hook compares trees through `advances`, and the receipt-in-flight hold no longer fires for ci:quick (D1.3)
    Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/test-release-hold.py, .claude/hooks/stop/test-wl_worktrees.py
    Depends on: R2.
    Needs: none
    Accept: `python3 .claude/hooks/stop/test-release-hold.py` and `python3 .claude/hooks/stop/test-wl_worktrees.py` exit 0 with new cases: a record-only commit after a green receipt still reads as a green receipt on an unpushed head; a code commit does not; a landing order is kept while ci:quick runs and still rewritten while vm:check runs.
- [ ] R5 [writer] `vm:check --commit <sha>` runs from the kept clone with its own renet build, CLI build and gateway record, under the shared fleet lock (D1.4, D1.5)
    Owns: .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_drills_vm_check.py, .ci/rediacc_ci/tests/test_vm_check_list_evidence.py
    Depends on: L1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_drills_vm_check.py .ci/rediacc_ci/tests/test_vm_check_list_evidence.py` exits 0 with new cases on the fake host: a pinned run builds and reads only clone paths, files its receipt under the pinned tree, and leaves the main checkout's gateway record untouched; a lease is still refused; the lock file name is unchanged.
- [ ] R6 [writer] The backup drill takes `--commit <sha>` and `record_drill` records the pinned tree and pointers (D1.4)
    Owns: .ci/rediacc_ci/drills/backup_check_trigger.py, .ci/rediacc_ci/tests/test_drills_backup_check_trigger.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_drills_backup_check_trigger.py` exits 0 with new cases: a receipt taken from a clone at an ancestor names that tree and its submodule pointers while the main checkout sits at a later commit; a call with no pin records what it records today.
- [ ] R7 [writer] The receipt-in-flight hold stands down for a pinned vm:check and stays for an unpinned one (D1.3)
    Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/test-release-hold.py
    Depends on: R4, R5.
    Needs: none
    Accept: `python3 .claude/hooks/stop/test-release-hold.py` exits 0 with new cases: a lock payload naming a pinned commit keeps a landing order; a payload with no pin rewrites it as today; an unreadable payload counts as unpinned.
- [ ] R8 [writer] `release:local --commit <sha>` builds its context and judges every gate at the named ancestor (D1.8)
    Owns: .ci/rediacc_ci/release/local.py, .ci/rediacc_ci/release/local_gates.py, .ci/rediacc_ci/tests/test_release_local.py, .ci/rediacc_ci/tests/test_release_local_gates.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_release_local.py .ci/rediacc_ci/tests/test_release_local_gates.py` exits 0 with new cases: the context's head, tree and account gitlink are the pinned commit's while HEAD is later; the ci-quick and vm-check refusals read the pinned tree's receipts; a sha that is not an ancestor of the tip is refused.

### Remedy 1: locks and identities
- [ ] L1 [writer] One named-resource lock module with a wrapper entry; the `fleet` resource keeps the vm:check lock file (D1.5)
    Owns: .ci/rediacc_ci/core/resource_lock.py, .ci/rediacc_ci/tests/test_core_resource_lock.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_core_resource_lock.py` exits 0: a second holder of one resource waits and prints the first holder's pid, purpose and start time; two different resources do not block each other; the wrapper returns its child's exit code and frees the lock when the child is killed; `fleet` resolves to the path `vm_check.lock_path` returns.
- [ ] L2 [writer] Every fleet user takes the `fleet` lock: the e2e-local setup before its VM reset, the drill harness before a renet upload, and `./rdc.sh ops up|down` (D1.5)
    Owns: packages/e2e-tests/src/base/bridge-global-setup.ts, .ci/rediacc_ci/drills/lib.py, rdc.sh, .ci/rediacc_ci/tests/test_fleet_lock_users.py
    Depends on: L1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_fleet_lock_users.py` exits 0: with the lock held by a test process, `./rdc.sh ops down` under a 2 s wait exits non-zero naming the holder before any VM command, and the drill upload helper does the same; a source check finds the lock taken before `resetVMs` in the setup, and `BRIDGE_TEST_SKIP_RESET=1` still takes it for the suite.
- [ ] L3 [writer] One lock per bench region for the bench deploy, the bench proxy deploy, the bench reset and the enterprise-proof runner (D1.6)
    Owns: .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/enterprise/proof.py, .ci/rediacc_ci/tests/test_bench_lock_users.py
    Depends on: L1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_bench_lock_users.py .ci/rediacc_ci/tests/test_ops_deploy_bench.py .ci/rediacc_ci/tests/test_ops_reset_bench_region.py .ci/rediacc_ci/tests/test_deploy_deploy_proxy.py .ci/rediacc_ci/tests/test_enterprise_proof.py` exits 0: each of the four waits on a held `bench-<region>` and names the holder; a reset of one region does not block a deploy to another; a proxy deploy to a target other than bench takes no bench lock; a dry run takes none.
- [ ] L4 [writer] The license, transfer and universe drills take a per-run identity from one helper (D1.7)
    Owns: .ci/rediacc_ci/drills/license.py, .ci/rediacc_ci/drills/transfer.py, .ci/rediacc_ci/drills/universe.py, .ci/rediacc_ci/tests/test_drills_identity.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_drills_identity.py .ci/rediacc_ci/tests/test_drills_universe_transfer.py .ci/rediacc_ci/tests/test_drills_license_seed.py` exits 0: two drills built in the same second under a frozen clock get different emails for each of the three; the email keeps its `drill-<name>-` prefix and the rediacc.io domain.
- [ ] LP-bench [live] Fresh bench receipt for the enterprise-proof runner with the region lock in place, after L3 lands
  Accept: live-proof bench enterprise-proof
- [ ] M1 [live] One real cycle on the branch: `ci:quick --commit` on a commit, two lease landings while it runs, then the push admitted on the advanced receipt; and an e2e-local start that waits while vm:check holds the fleet
    Depends on: R1-R5, L1, L2.
    Needs: verified-vmcheck
    Accept: the tick evidence holds the pinned receipt path, the `advances` step, the guard's admit line for the pushed tree with no second whole run, the two landed shas with their times inside the run's window, and the e2e-local wait line naming the vm:check holder.

### Remedy 3: the `Needs:` tag
- [ ] N1 [writer] Parse and derive `Needs:` beside the two existing box tags, and judge it in the plan live-proof gate (D3.1, D3.2)
    Owns: .claude/hooks/stop/wl_plandeps.py, .claude/hooks/stop/test-plandeps.py, .claude/rediacc_hooks/tests/test_wl_plandeps_box_edges.py, .ci/scripts/quality/check_plan_live_proof.py, .ci/rediacc_ci/tests/test_quality_plan_live_proof_needs.py
    Depends on: none.
    Needs: none
    Accept: `python3 .claude/hooks/stop/test-plandeps.py` and `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_plandeps_box_edges.py .ci/rediacc_ci/tests/test_quality_plan_live_proof_needs.py` exit 0 with cases for: each of the four values on a sub-line; an unknown value is a finding; a `Needs:` on the box line is a finding; the value is not searched for phrases; the derivation from each wait kind and each runner class; a stated value that contradicts a valid tag; a `(corrected ...)` line that supersedes; a box signature unchanged by adding the sub-line.
- [ ] N2 [writer] Box readiness reads `Needs:`, so a `none` box starts with no receipt and no push (D3.3)
    Owns: .claude/hooks/stop/wl_boxready.py, .claude/rediacc_hooks/tests/test_wl_boxready.py
    Depends on: N1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_boxready.py` exits 0 with one case per value and state: `none` ready on an unpushed tree; `verified-vmcheck` held without an admitting receipt and ready with one; `bench-deploy` held while bench is behind the branch; `pushed-head` held until the tip is on its upstream; a box with no line uses the derived value.
- [ ] N3 [writer] Add the four phrases of D3.4 to the wait list and tag the boxes of the D3.4 table in the same commit, each box line byte-identical
    Owns: .ci/config/proof-tiers.json, agent/plans/PLAN-health-checks-local.md, agent/plans/PLAN-scope-bws-signing-key-to-consuming-step.md, agent/plans/PLAN-ci-vm-image-followups.md, agent/plans/PLAN-enterprise-isolation.md, agent/plans/PLAN-enterprise-tenants.md, agent/plans/PLAN-product-domain-rename.md, agent/plans/PLAN-website-routing-and-mail.md, agent/plans/PLAN-vmcheck-incremental.md, agent/plans/PLAN-d1-eu-jurisdiction.md, agent/plans/PLAN-proxy-cd-six-targets.md
    Depends on: N1.
    Needs: none
    Accept: `npm run check:ci-plan-live-proof`, `npm run check:ci-plan-boxes` and `npm run check:ci-plan-record` exit 0; `git diff` of the ten plan files shows only added indented lines; a sweep with the four phrases added prints every open box that names one and has no tag, and that list is empty.
- [ ] N4 [writer] The two consumers document and route by `Needs:`, and the stale advisory sentence of docs/agent-reference/plan-records.md:168 is corrected (D3.5)
    Owns: .claude/commands/writers-now.md, docs/agent-reference/plan-records.md
    Depends on: N1.
    Needs: none
    Accept: `npm run check:ci-prose-style` and `npm run check:ci-doc-region-parity` exit 0; `grep -c "LP8_ENFORCED. is False" docs/agent-reference/plan-records.md` prints 0; both files name the four values and the derivation rule, and writers-now.md starts a `none` box without waiting for a push.

### Remedy 4: the W2.2 remainder, wave 1
- [ ] F1 [writer] check_record_paths.py: the manifest and the trace ledger are not scan code, and a `declared` tier reads each gate's lock `paths`, `names` and `lists` (wave 1 A)
    Owns: .ci/scripts/quality/check_record_paths.py, .ci/rediacc_ci/tests/test_quality_record_paths_declared.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_record_paths_declared.py` and `npm run check:ci-record-paths` exit 0: a fixture gate with `names: ['**']` and no literal cite is reported as an undeclared record reader; the same gate with a narrowed declaration is not; a record glob that appears only inside manifest.ts or trace-ledger.ts makes neither file a reader.
- [ ] F2 [writer] path-trace.ts folding: a fixture's own index read, submodule recursion, pathspec and `--format`, `git diff --quiet <file>`, a history `refs` field, extensions, and kind-aware folding for carry-exempt gates (wave 1 B)
    Owns: scripts/ci-runner/path-trace.ts, .ci/rediacc_ci/tests/test_path_trace.py
    Depends on: PLAN-ciquick-cpu.md#W2.5.
    Needs: none
    Accept: `npx tsx scripts/ci-runner/path-trace.ts --selftest` exits 0 with one new control per fold, each beside a control that must stay whole-tree: a `git log` read is still history, and an index read by a process with no name-only listing is still foreign.
- [ ] F3 [writer] Gate-side walkers read a tracked listing instead of walking untracked build directories, and `gitx.file_modes` reads modes through `--format` (wave 1 C)
    Owns: .ci/rediacc_ci/gitx.py, .ci/rediacc_ci/tests/test_gitx.py, and each gate script under .ci/scripts/quality/ or scripts/gates/ that the trace ledger names as listing an untracked build directory, except check_record_paths.py
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_gitx.py` exits 0 with `file_modes` returning the same map as before on a fixture holding a 755 file, a 644 file and a gitlink; each changed walker's own gate exits 0 with and without a populated `node_modules/` and `dist/` beside it, and the report lists every walker changed.
- [ ] F4 [writer] Every row of carry-exempt.json carries exactly one kind of clock, history, network or cache (wave 1 D)
    Owns: .ci/policy/carry-exempt.json
    Depends on: none.
    Needs: none
    Accept: `python3 -c "import json,sys;r=json.load(open('.ci/policy/carry-exempt.json'))['exempt'];sys.exit(0 if r and all(x.get('kind') in ('clock','history','network','cache') for x in r) else 1)"` and `npx tsx scripts/ci-runner/run.ts --selftest` exit 0. PLAN-ciquick-cpu.md W2.6 names the kinds of 11 rows; this box covers every row, and W2.6 adds no second kind to one.
- [ ] M2 [live] The plan's own measure, one push cycle on the branch after the boxes above and the pointed boxes of Design 4
    Depends on: M1, N2, N3, F1-F4, PLAN-ciquick-cpu.md#W2.6, PLAN-ciquick-cpu.md#W3.3, PLAN-ciquick-cpu.md#W4.3, PLAN-vmcheck-incremental.md#V3.
    Needs: verified-vmcheck
    Accept: the tick evidence holds, against the Context numbers: gate wall for the cycle, the count of ci:quick reruns that judged a moved HEAD, the mean wait from a writer's report to its landing, the whole-tree count after G7 beside the table of Design 4, and the pytest wall with its selected count.

## Risks

- **A pinned receipt for a tree nobody pushes.** The archive is keyed by tree and the guard re-hashes each carried gate against its origin receipt, so a stale receipt is unused, never wrong.
- **The clone's gateway and the main checkout's gateway on one machine.** R5 gives the clone its own port and state file; M1 is the first real proof that the two do not collide.
- **A lock nobody releases.** A flock dies with its holder, and the wrapper frees it on a killed child (L1's test). The wait is bounded and names the holder.
- **A wrong `Needs: none`.** A box started too early fails its own Accept; the derivation from an existing tag and the contradiction finding (N1) keep a stated value honest.
- **Shared files with PLAN-ciquick-cpu.md.** run.ts (R2 against W1.1), path-trace.ts (F2 after W2.5) and carry-exempt.json (F4 against W2.6) are named in the boxes that touch them.
