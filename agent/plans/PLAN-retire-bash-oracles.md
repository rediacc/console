# PLAN: retire the bash hook oracles, transform the remaining bash into Python

Status: APPROVED 2026-09-24 by the operator (/ask): run as one big-bang; use sonnet for any sub-agent task it can handle; re-judge the three tree exemptions per file; reverse the 2026-09-21 ruling BUT keep the real-bash benefit for some cases (task A0). Worklist #52383b75. -- hold lifted 2026-10-04: the 2026-09-26 ruling held it until CI is green; main CI is green (01d3583e1) and the operator asked for parallel turbo
Depends-On: no-dep -- related, not ordered: its G1 closes box W1P6 of PLAN-tooling-transformation.md and supersedes that plan's 2026-09-21 oracle ruling
Owner: d778be9d
Priority: P2 -- seed: Status approved, 15 open box(es)
Concurrency: parallel -- the 2026-09-26 run-alone ruling (limited token budget) is lifted: operator 2026-10-04 asked for parallel turbo with writer_cap 10; Owns: decides overlaps
Owns: .ci/config/language-policy-baseline.json

## Tasks

- [x] A0 Select the oracle cases whose value is real bash execution (bash's own parsing/quoting/heredoc/pipeline semantics and version-specific behaviour, the 2026-09-21 examples) and keep them as a small, justified real-bash semantics suite; everything else becomes goldens
    (ticked) 2026-10-03T10:12:10Z by d778be9d: b9714c304: .claude/rediacc_hooks/tests/test_bash_semantics.py kept real-bash suite; 2026-10-03 run 257 passed rc=0
- [x] A1 Freeze hook goldens from the oracles over the full corpus plus every EDGE_CASES entry; the current ports match 100 percent before anything is deleted
    (ticked) 2026-10-03T10:12:11Z by d778be9d: b9714c304: guard goldens .claude/rediacc_hooks/tests/goldens/*.jsonl; test_guard_matches_golden passed 2026-10-03
- [x] A2 Retarget the three hook differentials, guardcorpus/hookcases, the mention-anchoring gate, check_policy_inventory, doc-providers and the language-policy allowlist from the oracles to the goldens; add the regolden verb and the golden-drift control
    (ticked) 2026-10-03T10:12:13Z by d778be9d: b9714c304 + c8f92eaa0: differentials and gates retargeted to goldens/live guards, regolden verb (goldenio), test_golden_drift.py control
- [x] A3 Delete .claude/oracles/ (bash, both Python forwarders, lib/sanctioned.py), every TWIN constant and the bash driver; consolidate pattern_for and the pgrep loop shared by the two running-script guards
    (ticked) 2026-10-03T10:12:14Z by d778be9d: d5d296dea: .claude/oracles/ deleted, TWIN constants gone, bash driver removed; pattern_for consolidated in .claude/rediacc_hooks/runningscript.py:25 (e2a4d3d25)
- [x] A4 Rule-T fixes on the hook side (block_ssh_file_write empty command and jq null, the shellscan.target_root tab defect, and every copied bug the 47 PORT NOTE re-read finds), each with an intentional golden delta and a failing-first test
    (ticked) 2026-10-04T17:20:43Z by d778be9d: commit:0866fa941 the named hook-side fixes were in the tree; block_long_sleep's octal note and dead KNOWN_DIVERGENCES are gone; regolden 0 changed; 575 tests pass
- [ ] A5 Phase A acceptance: full .claude hook suite, DEFECT control over all guards, language-policy, hook-integrity, docs-gen and dead-python gates, the live chain on real commands, wall time measured before and after
- [x] B0 Inventory every tracked .sh into agent/plans/PLAN-retire-bash-oracles.inventory.tsv; close the 15 unclassified C/D files, re-check group D DELETE verdicts against naming tests, re-judge the media/breakpoint/tutorials tree exemptions file by file
    (ticked) 2026-10-08T12:56:00Z by d778be9d: commit:8bca2ba93 agent/plans/PLAN-retire-bash-oracles.inventory.tsv holds one row per tracked .sh, 190 of 190 (plus 35 GONE); exempt trees re-judged per file; the DELETE verdict rechecked; check:ci-language-policy rc=0
- [ ] B1 Cut over the CUTOVER-READY live twins (assert-job-succeeded, detect-pointer-bump, initialize, then lib/common.sh and its 181+ source sites); retire run-legacy.sh as its verb table empties
- [ ] B2 Port groups C and D-port in dependency order under rule T, each with a differential for right behaviour and intentional deltas for wrong behaviour, wired in the same change
- [ ] B3 Golden-then-delete every twinned bash file (groups A and B after cutover), draining its bashFiles line, with the same regolden verb as A2
- [x] B4 Rule-T fixes in the .ci ports: the 24 plan-named reproduced behaviours, the sweep's 8-13 bugs, and the promote retry gap #4175e786
    (ticked) 2026-10-04T17:20:45Z by d778be9d: commit:d2c44c127 landed in e07adce45 and d2c44c127; the full .ci suite re-covers those tests
- [ ] B5 Port the out-of-policy scripts (drills, ops, worktree, eslint-heap, json generator, backup-storage); prove the drills with a live run on the ops VMs
- [ ] G1 Empty and delete .ci/config/language-policy-baseline.json (closes PLAN-tooling-transformation W1P6, ed0c365d); every remaining allowlist entry carries a BLOCKER reason
- [ ] G2 Fix check:ci-bash-lib-ported (add log.py to its module list, recognise class methods), port its 8 real gaps, retire it with the last library
- [ ] G3 Regenerate gates.lock.json, the gen-docs regions, gate-bind steps and the registries; correct the TRAPS.md and CLAUDE.md prose that calls the oracles the spec

## 0. Rulings this plan executes, and the one it supersedes

- Operator 2026-09-24 (this ask): retire `.claude/oracles/`, port the remaining bash to Python, one plan, one big-bang.
- Operator 2026-09-24, same day: "instead of migrating remaining bash files 1-1 to python, fix the bugs when we transform when possible". Recorded as Rule T below.
- **SUPERSEDED: operator ruling 2026-09-21** (`agent/plans/PLAN-tooling-transformation.md:1423`), which kept the 47 oracles as a permanent exemption (`tree:.claude/oracles/`). It scored them 4.65 against goldens at 3.50. Its reasons were that real bash execution caught bash 5.3 vs 5.2 diagnostic wording and empty-pipeline output, and that "equivalence to bash stays the spec".
  - Why that no longer holds: no hook runs bash in production. The only live bash on the hook path is `chain-head.sh`, a toolchain check that hands off to Python. So a bash 5.2 vs 5.3 difference in an oracle's stderr is a property of a file nothing executes.
  - The differential proves the port MATCHES bash, not that it is CORRECT, and Rule T makes "matches bash" the wrong target wherever bash is wrong.
  - What survives from that ruling is its golden mechanism. The same day's second ruling retires a licensed script's twin by "freezing the twin's outputs as goldens (header carries the twin's blob sha) and deleting the bash". This plan applies that mechanism to the hooks too.

### Rule T: transform, do not transliterate

A port matches bash where bash is right and deliberately differs where bash is wrong. Every deliberate difference:
1. is listed in this plan (tasks A4 and B4) or added to it by the writer who finds it;
2. is recorded as an INTENTIONAL delta on the frozen golden or differential case (`intentional: "<reason>"`), never as a silent re-record;
3. has its own test that fails on the bash behaviour.

The "N TWIN BEHAVIOURS REPRODUCED RATHER THAN FIXED" paragraphs in PLAN-tooling-transformation.md become this plan's fix list rather than permanent facts.

## 1. Verified facts (2026-09-24, each checked, not taken from a report)

### Hooks

- **Live bash on the hook path.** Only `.claude/hooks/chain-head.sh`, registered for five events in `.claude/settings.json`. It checks python3 and jq, then pipes the event to `rediacc_hooks/lifecycle.py`. `.claude/hooks/profile/bash_env.sh` is machine-local BASH_ENV wiring and not part of the hook chain. No oracle executes at runtime.
- **What `.claude/oracles/` holds (54 tracked files).**
  - Bash oracles: 38 in `pre-bash/`, 8 in `pre-edit/`, 1 in `pre-ask/` and 2 in `post-bash/`.
  - `lib/`: `pre-bash/lib/command-scan.sh`, plus a forwarder at `lib/sanctioned.py`.
  - `stop/`: two Python forwarders of 13 and 17 lines, `worklist.py` and `wl_planfid.py`. They exist only so two oracles can resolve sibling modules (`stop/README.md`).
  - Two READMEs.
- **Every bash oracle has a Python port whose `TWIN` names it.** Six guards were never bash (`TWIN = None`).
- **`KNOWN_DIVERGENCES`** is declared only by `.claude/rediacc_hooks/guards/block_long_sleep.py:83`, and it is empty.
- **The mutant control needs no bash.** `test_the_differential_can_fail` (`.claude/rediacc_hooks/tests/test_guards_differential.py:549`) plants each port's `DEFECT` and compares the port with itself-with-the-bug. It already covers the `TWIN = None` guards, and so does `test_every_guard_discriminates` (`:530`).
- **What the oracles cost.**
  - They account for 5,844 of the suite's 8,467 cases (`.claude/oracles/README.md`).
  - The guard differential sets the suite's single-worker floor: 294.65 s (`.ci/rediacc_ci/check_pytest.py:100`).
  - A `-k` subset took 5 min 48 s this session, and its first run produced 5 false divergences from shared `/tmp` fixture contention.
  - Every guard fix is made twice. This session hit it on `block_self_matching_pgrep` and on `block_bash_write_to_running_script`, with bash escaping as its own bug source.
- **Who reads the oracles.**
  - Tests and harness: `.claude/rediacc_hooks/tests/test_guards_differential.py:67`, `.claude/rediacc_hooks/tests/test_post_bash_differential.py:31`, `test_shellscan_differential.py` (via `command-scan.sh`), `guardcorpus.py`, `.claude/rediacc_hooks/tests/hookcases.py:1273` and `:1578`, `.claude/rediacc_hooks/tests/test_settings_collapse.py:163`, `.claude/rediacc_hooks/tests/test_wl_priority_ladder.py:40`, `.claude/rediacc_hooks/tests/test_wl_cadence.py:143`, `.claude/rediacc_hooks/tests/test_hooks_delegates.py:67`.
  - Gates and policy: `.ci/scripts/quality/check_policy_inventory.py:50,492,816,885`; `check:ci-guard-mention-anchoring` (`.ci/scripts/quality/check_guard_mention_anchoring.py:45-50`, which reads its patterns from the oracle sources, a residue it states itself); `.ci/policy/.language-policy-allowlist` (`tree:.claude/oracles/`).
  - Docs: `scripts/lib/doc-providers.ts:396-402`, which leaves `.claude/oracles/` out of the hook-guards region on purpose.

### The rest of the bash

- **Language policy.** `.ci/config/language-policy-baseline.json` still lists 138 `bashFiles` that ruling 7 says must go. The count was 521 on 2026-09-07.
  - `.ci/policy/.language-policy-allowlist` exempts four trees: `.ci/media/`, `.ci/breakpoint/`, `.ci/tutorials/` and `.claude/oracles/`.
  - It also exempts 14 named files:
    - `.ci/bootstrap.sh`, `.ci/config/constants.sh`
    - `.ci/docker/web/entrypoint.sh`, `.ci/docker/service/env.sh`, `.ci/docker/run-in-tts.sh`
    - `test/lib/git-fixture.sh`, `test/mutate-check.sh`, `test/proxies/proxy-lib.sh`, `test/fixtures/mutate-check/fixture-suite.sh`, `test/gates/test-toolchain.sh`
    - `version/inject-env.sh`, `infra/ci-env.sh`
    - `.claude/hooks/chain-head.sh`, `.claude/hooks/profile/bash_env.sh`
- **The 138, sorted by the lead's mechanical match.** A file counts as twinned when a module with the same name exists under `.ci/rediacc_ci/`, and as wired when a workflow, package.json or manifest names it. The scratch tables are `baseline138.tsv` and `twinunwired71.tsv`.
  - **Group A: twin exists, bash not directly wired. 71 files, 12,673 lines.**
    - A differential test still executes the bash for all 71 (the lead's grep). So none can be deleted now; all are golden-then-delete.
    - Three are also cutover-first, because `.ci/legacy/run-legacy.sh:47-48` still sources them: `.ci/lib/account.sh`, `.ci/lib/local-common.sh` (also sourced at `.ci/media/media-entry.sh:50`) and `.ci/lib/service.sh`.
    - An investigator reported 51 of these as DELETE-NOW. That is wrong for exactly this reason.
  - **Group B: twin exists, bash still live. 20 files, 8,147 lines.**
    - Ready to cut over: `assert-job-succeeded.sh` (`.github/workflows/ci.yml:1953`), `detect-pointer-bump.sh` (`.github/workflows/ci.yml:159`), `initialize.sh` (`.github/workflows/ci-quality.yml:60`, `.github/workflows/ci.yml:1884`) and `lib/common.sh` (181+ `source` sites).
    - Blocked on a recorded divergence: `discover-epics.sh`, `delete-r2-channel.sh` (silent failure) and `renet-root-tests.sh`.
    - The rest are pre-cutover or not yet assessed: the `private/*` renet suites, `claude-review-gate.sh`, `epic-context.sh`, `build-packages.sh`, `update-homebrew-tap.sh`, `cleanup-versions.sh`, `release-state-validator.sh`, `toolchain.sh` and `write-release-sentinel.sh`. Each gets a per-file divergence read before cutover.
  - **Group C: no twin, live. 22 files, 9,233 lines. Verdict: port.**
    - The large ones: `security/check-workflow-gates.sh` (1,189 lines), `test/test-install-methods.sh` (1,374), `test/gates/test-runner-advice.sh` (970), `test/test-linux-packages.sh` (762), `ci/profiler/sampler-linux.sh` (685), `quality/check-submodule-branches.sh` (597) and `test/gates/test-run-sh.sh` (591).
    - Also the seven `test/proxies/proxy-*.sh`, and the e2e runners: `run-e2e.sh`, `run-account-e2e.sh`, `start-account-for-e2e.sh`, `run-unit.sh` and `seed-smoke-test.sh`.
  - **Group D: no twin, not directly wired. 25 files, 10,388 lines. Verdict per file: port or delete.**
    - The investigator's DELETE list must be re-checked the way group A was, because a test naming a file means golden-then-delete: `emit-advisory.sh`, `check-profiler-coverage.sh`, `check-trap-registry.sh`, `test/lib/test-helpers.sh`, `workflow-rule.sh`, `probe-receipt-stability.sh`, `profiler-control.sh`, `test-install-sh-config.sh` and `test-rdc-sh-env.sh`.
    - The investigator covered only 32 of the 47 files in C and D. Task B0 classifies the rest.
- **Outside the language policy's scope** (scripts/, packages/, programs/, .devcontainer and the repo root), an investigator classed 17 files as keep-bash, with evidence, and 24 as port.
  - Keep-bash:
    - root `run.sh` and `rdc.sh`, which exec Python early, and `media.sh`;
    - the `.devcontainer/*` entrypoints and lifecycle scripts;
    - `packages/www/public/install.sh`, the curl-piped installer;
    - `scripts/lib/env-file.sh`, a shim, and `scripts/pre-commit-check.sh`.
  - Port: `scripts/drills/*` (4,127 lines), `scripts/ops/*` (1,904), `scripts/dev/worktree.sh` (807), `scripts/eslint-heap.sh`, `packages/json/generate.sh` (1,764), `packages/json/test-templates.sh`, `programs/backup-storage/*` and `packages/www/scripts/measure-page-density.sh`.
  - `packages/json/templates/**/*.sh` stay bash. They ship inside Rediaccfile templates to machines, so they are a template contract.
- **The Rule T fix list: bash defects reproduced on purpose.**
  - 24 are named in PLAN-tooling-transformation.md: 4 in `account.py`, 6 in `local_common.py`, 7 in `devbox.py` and 7 in `account_lifecycle.py` (at `:1337`, `:1351`, `:1373` and `:1406`).
  - The sweep found 8 to 13 more in `.ci/rediacc_ci/**`:
    - `.ci/rediacc_ci/ci/assert_ci_complete.py:12` drops `RUN_SH_TESTS` from both tiers on a pointer bump;
    - `.ci/rediacc_ci/release/check_soak_period.py:10` aborts silently;
    - `.ci/rediacc_ci/ci/cancel_older_runs.py:38` dies on an unbound variable when given `--timeout abc`;
    - `.ci/rediacc_ci/ci/dispatch_watchdog.py:140` parses octal;
    - `.ci/rediacc_ci/housekeeping/cleanup_versions.py:66` and `:72` carry arithmetic hazards;
    - `.ci/rediacc_ci/ci/derive_image_tag.py:79` has false help text;
    - `.ci/rediacc_ci/ci/assert_channel_for_event.py:11` fails open.
  - Hook side: `.claude/rediacc_hooks/guards/block_ssh_file_write.py:7` has no empty-command guard and treats `jq -r`'s string `null` as a value; `.claude/rediacc_hooks/guards/block_untagged_commit.py:142` pins the tab defect it inherits from `shellscan.target_root`.
- **Found while planning, already fixed this session.**
  - `aws s3 --quiet` hid a production promote's failure. It is now `--only-show-errors` in the promote, promote-hotfix and upload-repos twins; 68 tests pass.
  - `deploy_proxy.py` staged a renet that was not executable. It is fixed as a deliberate twin delta, the first Rule T change.
  - Still open: a single transient R2 `IncompleteRead` aborts a promote (#4175e786). It becomes a Rule T fix under task B4.

## 2. Target end state

- **Gone:** `.claude/oracles/`, every `TWIN` constant, the bash side of the three hook differentials, `tree:.claude/oracles/` in the language-policy allowlist, and the oracle-pattern residue in `check:ci-guard-mention-anchoring`.
- **How every hook guard is judged:**
  - frozen goldens;
  - the existing oracle-free controls: discriminate, DEFECT and corpus size;
  - its own `EDGE_CASES`.
- **Language-policy baseline:** `bashFiles` is empty, and the file is deleted along with its reader. That closes PLAN-tooling-transformation's terminal box W1P6 (`ed0c365d`).
- **The allowlist** holds only files that must stay bash, each with a `BLOCKER:` reason. Valid reasons: a bootstrap that runs before Python exists, a container or remote runtime without the repo's Python, the user-facing installer, the template contract, or BASH_ENV.
- **The media, breakpoint and tutorials tree exemptions** are re-judged file by file in task B0, not carried over wholesale.

## 3. Phase A: hook oracles

### A0. Keep the real-bash benefit where it is real (operator, 2026-09-24: "reversing, but there should be some that we need to benefit. Not all of them but some.")

- **What a bash execution can prove that Python cannot:** how bash itself tokenises, quotes, expands and runs the command line a guard reasons about. Examples: a heredoc terminator, a quoted `;`, a `$(...)` span, an empty pipeline's output, and a diagnostic whose wording differs between bash 5.2 and 5.3 (the 2026-09-21 examples).
- **What it cannot add:** the guard's own policy decision. The Python IS that decision now.
- **The selection** scores every oracle case by whether its verdict depends on bash interpreter semantics:
  - it exercises a shellscan/command-scan construct (heredoc, quoting, substitution, pipeline, redirect);
  - or its twin's output came from bash itself rather than the guard's message.
  - The Python judge scores it, and a human-readable list is recorded in this plan.
- **The kept cases** move to ONE suite, `tests/test_bash_semantics.py`. It does not run twin guards. It runs a real `bash -c` or `bash -n` over the construct and asserts the fact the Python scanner relies on ("bash reads this heredoc as ending at line 3"). So a bash upgrade that changes the fact fails loudly, and the scanner's assumption is re-examined.
- **Expected size:** tens of cases, not thousands. `shellscan`'s differential is the main source.
- **The count and the list** are recorded here before A3 deletes anything.
- **Recorded 2026-09-24 by the A4 writer.** `.claude/rediacc_hooks/tests/test_bash_semantics.py` holds 77 rows, one per probe in A0 section 3's nine tables.
  - Three A0 rows carry two or three probes and are split into lettered rows: Q7a/b, X1a-c, X2a/b.
  - A0 numbers its separator table S1-S6, which collides with the S1-S3 safe divergences, so those rows are SEP1-SEP6.
  - Each row names the corpus and EDGE_CASES entries it replaces in `source`, and the Python that leans on it in `relies_on`. The source list therefore lives beside the probe instead of being copied here.
  - The suite has 257 tests: 77 real-bash facts, 77 reliance checks, 70 in-process scanner-agreement checks, 29 Rule T guard verdicts, two real-repository checks (L12 and L15) and two anti-vacuity controls.
  - All 257 pass on bash 5.3.9, because A4 fixed every `contradicted` row.
  - The one kept divergence is S3 (row Q11). It is PINNED as a passing assertion instead of an `xfail(strict=True)`, because `check:ci-pytest` counts an xfail as a test that did not pass.

### A1. Freeze the goldens before anything is deleted (sonnet writer; the harness design reviewed by the lead)

- A new `.claude/rediacc_hooks/tests/goldens/` holds one JSONL per guard stem, plus `post-bash.jsonl` and `shellscan.jsonl`.
  - Each record holds the case key (the stable label and payload hash the harness already builds), the env variant, rc, normalized stdout and normalized stderr.
- Recording:
  - The existing bash driver records them (`.claude/rediacc_hooks/tests/test_guards_differential.py:386`, `DRIVER`). It runs once, over the full corpus plus every guard's `EDGE_CASES`, on the full cross product (`REDIACC_GUARD_DIFF_FULL=1`).
  - Normalization is the harness's own: bytes, `/tmp/tmp.X` and fixture paths. Nothing new is invented.
- About 78 percent of cases assert silence: rc 0 and empty streams. Those are stored as a per-stem list of case keys marked `"silent": true`, not as full records.
- The file header records the oracle tree sha, the bash version and corpus statistics. This is the 2026-09-21 ruling's header carrying the twin's blob sha.
- **The gate on this task:** the CURRENT ports must match 100 percent of the goldens. That is exactly today's differential, restated. Any mismatch stops the phase.

### A2. Retarget every reader (same writer)

- **Guard differential.** `test_guards_differential.py` compares each port with its golden instead of `bash_results`. `test_every_port_has_a_present_twin` becomes `test_every_port_has_goldens`. The DEFECT control does not change, since it is already port-only. `build_cases(twinned=...)` collapses to a single list.
- **The other two differentials.** `test_post_bash_differential.py` and `test_shellscan_differential.py` get the same treatment. The scripted `git` and `gh` call log is recorded in the golden too.
- **Regolden verb.** A guard whose behaviour changes on purpose re-records through ONE verb, `--regolden <stem> --reason "<why>"`, which refuses without a reason.
- **Golden-drift control.** A test fails when a golden changes without an `intentional` reason in the diff.
- **Oracle paths dropped from:** `guardcorpus.py`, `hookcases.py`, `test_settings_collapse.py`, `test_wl_priority_ladder.py`, `test_wl_cadence.py`, `test_hooks_delegates.py` and `check_policy_inventory.py`.
- **Mention anchoring.** `check_guard_mention_anchoring.py` extracts its patterns from the Python module constants. It already runs the LIVE guard, so only the pattern source moves, and its residue paragraph goes.
- **Docs.** `scripts/lib/doc-providers.ts:396-402` drops the oracle exclusion; then regenerate. The language-policy allowlist line is removed.

### A3. Delete and consolidate

- **Deleted:**
  - `.claude/oracles/` in full, including both Python forwarders and `lib/sanctioned.py`;
  - every `TWIN = ...` constant;
  - the `DRIVER` and `bash_results` fixture, together with the `XDIST_GROUP` serialization that exists only for the bash side.
- **Consolidated:** `.claude/rediacc_hooks/guards/block_bash_write_to_running_script.py:16` and `block_edit_of_running_script.py` share `pattern_for` and the pgrep loop only because twins existed. Both move into one `rediacc_hooks` helper. That is the "P6 change, once there is no twin left" the docstring promised.
- **The 47 `PORT NOTE`s are re-read:**
  - (ii) bash semantics that are the intended contract stay, as documentation;
  - (iii) duplication that exists only for a twin is removed;
  - (i) copied bugs go to A4.
- **The `this-worktree` fixture, decided 2026-09-24 by the A4 writer (W-A's open question).**
  - Before: the `this-worktree` ENVS variant of `block_merge_with_unpushed`, `block_untagged_commit` and `block_unverified_push` snapshotted the LIVE checkout (`_snapshot_this_worktree`). Every commit anyone landed moved its goldens: the unpushed-commit list, the epic list from `agent/pr/<branch>.md`, the tree the refusal names.
  - Decision: a fixed synthetic repository, `_synthetic_this_worktree` in `test_guards_differential.py`. It is built by `_build_repo` with the pinned commit dates W-A introduced, and keeps the real shape: an `MMDD-N` branch, three commits ahead of its remote-tracking ref, an `agent/pr/<branch>.md` in `worklist.py --publish` format, and no pre-push receipt.
  - The fixture key `this-worktree-snapshot` and the env label are unchanged, so the guards' `ENVS` did not move.
  - The one-time re-record is tagged `intentional`: 20 records in `block_merge_with_unpushed`, 31 in `block_untagged_commit`, none in `block_unverified_push`, whose answers did not depend on the live tree.
  - `_git_read` was deleted with the snapshot builder, its only caller.

### A4. Rule T fixes, hook side

Each fix changes behaviour, re-records its golden as `intentional`, and adds a test that fails first.
- `block_long_sleep`: the octal note is historical, since both sides already force base 10. The note goes and the case stays.
- `.claude/rediacc_hooks/guards/block_ssh_file_write.py:7`: guard against an empty command, and treat `jq -r`'s `null` as absent.
- `.claude/rediacc_hooks/guards/block_untagged_commit.py:142`: fix the tab defect at its source, `shellscan.target_root`.
- Any further category (i) items found by the A3 re-read are added here before the writer closes.

## 4. Phase B: the remaining bash

- **B0: classify, before any writer** (read-only haiku Explore fan-out).
  - Output: one row per tracked `.sh` into `PLAN-retire-bash-oracles.inventory.tsv`, with category, reason, twin, callers, the tests naming it and its known Rule T defects.
  - Close the 15 files in groups C and D that the investigator skipped.
  - Re-check group D's DELETE verdicts against the tests that name each file.
  - Re-judge the 64 files under the media, breakpoint and tutorials tree exemptions one by one: keep with a `BLOCKER:` reason, port, or delete.
- **B1: cutover** (sonnet, mechanical).
  - Order: `assert-job-succeeded`, `detect-pointer-bump`, `initialize`, then the 181+ `source` sites of `lib/common.sh`.
  - `common.sh` goes last because it is the base library that `.ci/lib/{service,local-common,account}.sh` source.
  - `.ci/legacy/run-legacy.sh` loses its `source` lines as each verb it dispatches moves to Python. It is itself in group C, since `./run.sh` already routes verb by verb, and it is deleted once its verb table is empty.
- **B2: port groups C and D-port under Rule T** (sonnet writers). Dependency order:
  1. the libraries they source;
  2. the seven `test/proxies/proxy-*.sh`, which share `proxy-lib.sh` (currently allowlisted and re-judged in B0);
  3. the gate runners;
  4. the e2e and install runners;
  5. `sampler-linux.sh` last, because it samples `/proc` at a fixed rate and its timing must be measured, not assumed.

  Each port lands with a differential for the behaviour bash gets right, intentional deltas for what it gets wrong, and its workflow, manifest and package.json wiring flipped in the same change.
- **B3: golden-then-delete, every twinned bash file** (groups A and B, after cutover).
  1. Freeze the differential's bash side as goldens, with the blob sha in the header.
  2. Switch the test to port-vs-golden.
  3. Delete the `.sh`.
  4. Drain its `bashFiles` line.
  5. Lower any floor to the measured count in the same change.

  `.ci/rediacc_ci/tests/differential.py` and the `BASH_TWIN` machinery in `tests/gates/harness.py` gain the same regolden verb, so hooks and `.ci` share one golden format.
- **B4: Rule T fixes in the `.ci` ports**, each an intentional golden delta with a test that fails first. The list is section 1's, plus the promote retry gap #4175e786. A fix that needs an operator decision is parked as a `[?]` with a default rather than silently kept. Example: `assert_channel_for_event` failing open, with `DEFAULT: fail closed`.
- **B5: port the out-of-policy scripts** that B0 classes as port. The `scripts/drills/*` batteries run against real machines, so their port is proven by a live drill run on the ops VMs, not only by a differential.

## 5. Gates

- **`check:ci-language-policy`.**
  - The allowlist loses `tree:.claude/oracles/`. Its baseline shrinks to empty and is then deleted.
  - From then on the gate refuses ANY new `.sh` outside the allowlist, and every allowlist entry needs a `BLOCKER:` reason checked by `check:ci-suppression-liveness`.
  - That is the "no new bash" gate this plan needs. It already exists; it only loses its baseline.
- **`check:ci-bash-lib-ported`** (`.ci/rediacc_ci/quality/bash_lib_migration_complete.py`).
  - Its baseline holds 59 gaps across 5 libraries. The gate prints 9 libraries because it also counts the 4 complete ones.
  - An investigator classifies 51 of the gaps as ported but unwired:
    - 39 `devbox.sh` methods, which the gate misses because it does not see class methods;
    - 1 in `service.sh`, 2 in `blocker-validator.sh` and 3 in `toolchain.sh`;
    - 6 in `common.sh`, 5 of them log functions that live in `.ci/rediacc_ci/log.py`, which the gate's module list omits.
  - The other 8 genuinely need a port.
  - Fixes: add `log.py` to the module list, recognise class methods, port the 8, and retire the gate together with the last library.
- **Retired with the oracles:** the bash-side assertions in the three hook differentials, and the `check:ci-hook-integrity` bash twin, which goes through B3.
- **New:** the golden-drift control. **Retargeted:** mention anchoring.
- **Relied on unchanged:**
  - `check:ci-gate-bind`, which now also compares the manifest's `ci.step` and `ci.job` with the header (fixed this session);
  - `check:ci-parity`, `check:ci-gates-lock`, `gate-test:docs-gen`;
  - `check:ci-dead-python`, `check:ci-python-env-registry` and `check:ci-python-types`.

## 6. Regenerated artifacts

- `npm run gen:gates-lock`
- `npx tsx scripts/gen/gen-docs.ts --write`, which covers the CLAUDE.md tables, the doc-registry regions and the ci-gates regions
- `npx tsx scripts/gate-bind.ts --write` for every flipped step
- the language-policy baseline drain
- the `check:ci-bash-lib-ported` drains
- the Python env and types registries, through their own write verbs

The TRAPS.md and CLAUDE.md prose that calls the oracles the spec is corrected in the same change.

## 7. Writer fan-out (at most 4 live writers, counting the ones already live)

- **The cap at approval time:** the babysitter, plus any writer still live then (today: the stop-hook writer and biome wave 3). The fan-out takes the free slots and queues the rest. Each writer is leased to its worklist item.
- **Model routing, per the operator (2026-09-24):** sonnet for every writer task it can handle. That is the default here, a deliberate exception to CLAUDE.md's "sonnet is an escalation tier". Opus only where the artifact IS the new oracle: the golden-drift control and the A0 selection judge. The lead reviews both.
- **W-A, golden and harness (sonnet; A0's selection and the drift control on opus). Phase A.**
  - Owns `.claude/oracles/**`, the hook differentials, `guardcorpus.py`, `hookcases.py` and `tests/goldens/**`.
  - Also owns the `TWIN` lines and the A3/A4 hunks of `guards/*.py`, `shellscan.py`, `check_guard_mention_anchoring.py`, `check_policy_inventory.py`, `doc-providers.ts` and the allowlist.
- **W-B, cutover (sonnet). Task B1.** Owns the B1 call sites in workflows and the manifest, one directory at a time.
- **W-C, port swarm (sonnet, up to 2). Tasks B2 and B5.** Each owns one directory: `.ci/scripts/test/**`, `.ci/scripts/{security,quality}/**` or `scripts/**`.
- **W-D, golden-then-delete and gates (sonnet; the G2 gate change on opus). Tasks B3, B4, G1 and G2.**
  - Owns `.ci/rediacc_ci/tests/differential.py`, `tests/gates/harness.py` and the `.ci` goldens.
  - Owns the language-policy baseline, `bash_lib_migration_complete.py` and its baseline.
  - Owns the Rule T hunks in the `.ci` ports.
- **B0 runs first,** read-only, because the file lists of W-B and W-C come out of it.
- **Every writer prompt forbids** `git checkout/restore/stash/clean/commit/push`, and any sync or regenerate script except the named generators.
- **Edits are targeted, never whole-file copies.** A whole-file copy reverted committed fixes this session.

## 8. Verification (there is no rollback; the proof is the gates and live runs)

1. **Before any deletion,** the goldens match the current ports 100 percent, and every B3 differential is green on both its bash and its port.
2. **After,** all of these run green:
   - the full `.claude` and `.ci` suites, and `npm run ci`;
   - each port against its goldens, with the count of intentional deltas equal to the plan's list;
   - the live hook chain, on real commands;
   - M-live style real runs of the release-path ports: items 9 to 12 of this campaign;
   - a drill run on the ops VMs.
3. **Counts, recorded before and after:**
   - `git ls-files '*.sh' | wc -l`;
   - `bashFiles` = 0, and the baseline file is gone;
   - the allowlist equals the keep-bash list, each entry with its reason;
   - hook-suite wall time.
4. **Nothing silent:** every intentional delta is named in a golden along with its reason, and a golden that changes without a reason fails the drift control.

## 9. Risks

- **Goldens freeze today's bash behaviour, bugs included.** Mitigated by Rule T and the intentional-delta requirement: the freeze is the starting point, not the spec.
- **Stderr that differs by bash version,** the 2026-09-21 reason. Once the ports are the only implementation, their stderr is the product's.
- **Concurrency.** The false divergences seen today came from shared `/tmp` fixtures.
  - The temp-leak writer's work lands first: `runtmp`, `pytest_tmp.py`, and `--dist loadgroup` at `pyproject.toml:408`.
  - Goldens remove the bash side's fixture needs entirely.
- **Scope.** About 40k lines of bash across groups A to D, plus scripts/. The change is ONE plan on one PR branch, landing in the order A, B0, B1 to B5, with each phase green before the next. Descoping is forbidden; any piece that genuinely cannot be done is named out loud with its reason.


## 10. Writer fan-out, 2026-10-08 (opus Plan agent; the lead verified the load-bearing claims before spawning)

This plan is ready to run, but read section 2 first. Eleven inventory rows are classified wrong in ways that would break the cutover. Five boxes also depend on operator decisions (D1-D7 in section 6), so four units cannot start until those are made.

### 1. How a golden-then-delete works in this repo today

**The golden machinery is built, and the regolden verb the plan asks for already exists.**

- **Seam.** `.ci/rediacc_ci/tests/differential.py:224-237` defines three modes, chosen by `REDIACC_CI_REGOLDEN`:
  - unset (compare): the answer comes from the golden, and the `.sh` is never read;
  - `bash`: record from the twin while it still exists;
  - `port`: record from the port, for a Rule-T delta.
- **Where goldens live.** `GOLDEN_DIR = .ci/rediacc_ci/tests/goldens/twins` (`:254`). Files are named `golden_stem` (`:280-285`), for example `release.check-edge-manifest.jsonl`.
- **Call shapes.**
  - `twin_call` / `twin_run` (`:529-591`) wrap any harness, including written files and extras.
  - `twin_tuple` / `twin_result` (`:619-688`) cover harnesses that return extra values.
  - `twin_streams` (`:691-722`) replaces a direct `bash_streams` call.
- **Format.** It is shared with the hooks: `goldenio.py` is loaded by path from `.claude/rediacc_hooks/tests/goldenio.py` (`:240-252`). `write_recorded` (`:737-786`) stamps the header with `twin` and `twin_blob` (the `git hash-object` from `:725`), and marks every moved record `intentional: <reason>` through `diff_and_mark`.
- **Regolden verb.** `.ci/rediacc_ci/tests/regolden.py` is invoked as `PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden <twin.sh>... --source bash|port --reason "<why>" [-k expr]` (`:1-20`). It refuses:
  - a missing `--reason`;
  - `--source bash` when the `.sh` is gone;
  - a recording run that is not green;
  - a twin that no module names.

  `modules_naming` (`:38-51`) finds test modules through `SEAM_RE`. It also finds gate tests through `BASH_TWIN = "<path>"`, which routes to `gates/test_twin_parity.py`.
- **Gate-test twins.** `.ci/rediacc_ci/tests/gates/harness.py:525-579` freezes a `BASH_TWIN`'s verdict, its PASS count and its case set. While the twin still exists, a golden that disagrees with it fails as stale. Once the twin is gone, the golden answers instead.
- **Drift controls.**
  - `.ci` side: `.ci/rediacc_ci/tests/test_twin_goldens.py`.
  - Hook side: `.claude/rediacc_hooks/tests/test_golden_drift.py`.
- **Switching a test to port-vs-golden.** Replace `old = diff.bash_streams("bash %s" % TWIN, ...)` with `old = diff.twin_call(TWIN, ["bash"], lambda: diff.bash_streams(...), work=(repo.parent,))`.
  - Worked example: commit 0866fa941, in `test_release_check_existing_release.py`.
  - Tests that read `TWIN.read_text()` must be deleted or salvaged into plain assertions, using the rules in `agent/plans/PLAN-deletion-budget.md:145-152` (DB16).
- **Reference commits.** 6eb239b4d (14 twins), 50dd86fb0 (15) and 0866fa941 (12). Each one in the same change:
  - drains `language-policy-baseline.json`;
  - lowers the shfmt floor (`.ci/rediacc_ci/security/shfmt.py:97`, now `"167"`);
  - drains the `.dead-bash-allowlist`, em-dash, shell-declared-commands, python-types and secret-supply entries.
- **Baseline.** `.ci/config/language-policy-baseline.json` holds 89 `bashFiles`: 45 GOLDEN-THEN-DELETE, 33 CUTOVER-READY, 10 PORT and 1 KEEP-BASH, which is `upload-media-to-r2.sh`.
  - It is read by `.ci/scripts/quality/check_language_policy.py:70-72`.
  - It is drained with `--write-baseline`, which refuses to absorb new paths (`:366-410`).
  - A deleted file that is still baselined is a red (`:782-790`).
  - Deleting the file switches the gate to STRICT mode (`:748-768`), which is G1 with no further code change.
- **Hidden dependency.** That gate shells out to `.ci/scripts/lib/blocker-validator.sh` (`:251-300`). It has to be repointed to `rediacc_ci.core.blocker_validator` before that library can go.
- **Already frozen.** 26 twins have goldens, and every `twin_blob` matches the file today (checked with `git hash-object`). They are the 15 `release/*.sh`, 9 deploy scripts, `build-cli`, `build-pkg-repo` and `test-media-r2`.
- **Why they were not deleted.** 0866fa941 says: "Every .ci/scripts/release/*.sh stays on disk ... those ports wait for the operator's real cd-v2, promote-stable and backfill-release-sentinel runs (operator rule, 2026-10-01)". `agent/plans/PLAN-deletion-budget.md:143` repeats the rule.

### 2. Inventory corrections that change the work

| Row | Inventory says | Code says |
|---|---|---|
| `run-e2e.sh`, `test-install-methods.sh`, `test-linux-packages.sh`, `test-rdc-update.sh` | PORT ("carried") | Already ported under `.ci/rediacc_ci/testrun/` and wired: `.github/workflows/ci.yml:978,1896`, `.github/workflows/ct-tests.yml:568`, `.github/workflows/ct-update-flow.yml:70`. What is left are readers of the dead text: `.ci/rediacc_ci/ci/budget_report.py:1015-1033` still parses `run-e2e.sh`'s `E2E_SHARD_GREP_BUCKETS` (a live Rule-T bug); `.ci/rediacc_ci/proxies/linux_packages.py:57` and `.ci/rediacc_ci/proxies/rdc_update.py:51` still read the .sh. These are golden-then-delete. |
| `test-blocker-golden-corpus.sh`, `test-media-r2.sh`, `test-runner-advice.sh`, `test-run-sh.sh` | PORT | Python ports carry `BASH_TWIN` (`.ci/rediacc_ci/tests/gates/test_gate_blocker_golden_corpus.py:34`, `.ci/rediacc_ci/tests/gates/test_gate_media_r2.py:24`, `.ci/rediacc_ci/tests/gates/test_gate_runner_advice.py:41`, `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py:32`). `scripts/ci-runner/manifest.ts:5174-5210` still runs the .sh. These are golden-then-delete. |
| `scripts/dev/worktree.sh` | PORT | Port `.ci/rediacc_ci/dev/worktree.py` exists; `.ci/rediacc_ci/core/run_verbs.py:42` still routes to the .sh. This is a cutover. |
| `upload-to-r2.sh` | GOLDEN-THEN-DELETE, "No .sh caller" | **Wrong.** The live port sources it at runtime: `.ci/rediacc_ci/deploy/upload_to_r2.py:7-14,442-460` runs `write_once_guard` as bash, together with `common.sh` and `release-state-validator.sh`. `write_once_guard_check.py` drives the same function. Not porting it was a deliberate ruling (the v1.1.16/17 sealed-but-empty incident). Decision D5. |
| `lib/toolchain.sh` | CUTOVER-READY | Two KEEP-BASH files source it: `.ci/bootstrap.sh:87`, which runs before the Python toolchain exists, and `.ci/scripts/test/gates/test-toolchain.sh:25` (bare runner). It is also used at `.github/actions/setup-node-npm/action.yml:34` and `.github/workflows/ci-quality.yml:247-248` (4 sites). It should be KEEP-BASH. Decision D2. |
| `lib/common.sh` | CUTOVER-READY, "181+ sites" | 76 files really source it (`git grep -E '^\s*(source|\.)\s+.*lib/common\.sh'`), and about 67 of those die in this plan. The remaining consumers: KEEP-BASH `.ci/docker/service/env.sh:14`, `.ci/media/tools/upload-r2.sh:62` and `.ci/media/verify.sh:278`; workflow steps `.github/workflows/cd-v2.yml:734` and `.github/workflows/promote-stable.yml:173` (`gh_retry`). No Python CLI offers gh-retry: neither `.ci/rediacc_ci/core/ghx.py:561-597` nor `.ci/rediacc_ci/core/common.py:640-658` has the verb. Decision D3. |
| `.ci/lib/local-common.sh` | CUTOVER-READY | KEEP-BASH `rdc.sh:18` sources it (uses `check_node_version`, `ensure_deps` and `log_*`), and so does `.ci/media/media-entry.sh:50`. Also `.ci/rediacc_ci/setup/bridge.py:31-38` PRELUDE (which also sources `devbox.sh`, `service.sh` and `toolchain.sh`), `.ci/scripts/test/gates/test-run-sh.sh:117-119`, and 4 `*_shadow_driver.py`. Deletable, but rdc.sh and media-entry.sh need edits. |
| `ci-pull-images.sh`, `ci-start-elite.sh`, `ci-stop-elite.sh` | CUTOVER-READY | They are a path contract for the vendored breakpoint tree: `.ci/breakpoint/scripts/start-origin.sh:88`, `.ci/breakpoint/scripts/pull-service-images.sh:38` and `.ci/breakpoint/scripts/stop-breakpoint.sh:240` test `-x` on these exact paths. The tree is drift-locked by `MANIFEST.sha256` and copied downstream. Decision D4. |
| `test/lib/test-helpers.sh` | GOLDEN-THEN-DELETE | KEEP-BASH `.ci/media/verify.sh:141` sources it. |
| `version/inject-env.sh` | KEEP-BASH | Its BLOCKER names only bash sourcers that die in W2 (`build-cli-executables.sh`, `build-cli-musl.sh`). A Python twin exists (`version/inject_env.py`), and `.ci/rediacc_ci/build/build_cli_musl.py:90` can call it, since the alpine container installs python3 (`build_cli_musl.py` line 22 of its script: `apk add ... python3`). Challenge it: delete it in W2. |
| `probe-receipt-stability.sh` | GOLDEN-THEN-DELETE | There is no port and no test drives it, so nothing can be frozen. Port it (42 lines) or delete it with operator OK. |
| `test-run-sh.sh` | PORT | Runs on the bare `ubuntu-slim` job (`.github/workflows/ci.yml:602-630`) next to KEEP `test-toolchain.sh`. Section 4 of it tests `local-common.sh`'s `gate_lane_decide`. Decision D6. |

### 3. Writer units (sonnet), with disjoint ownership

Every writer follows the same per-file recipe:

1. If no golden exists, convert the call sites to `diff.twin_*` and freeze with `regolden ... --source bash --reason "B3 freeze"`.
2. Run the module in compare mode.
3. Repoint every live caller.
4. Delete the `.sh` (`rm`; no git verbs).
5. Re-run the module.
6. Report a drain list for the lead-owned files below.

Rule-T deltas use `--source port -k <expr> --reason`. No writer edits a lead-reserved file.

**Lead-reserved (serial passes L1/L2/L3):**
- `.ci/config/language-policy-baseline.json`, `.ci/policy/.language-policy-allowlist`, `.ci/policy/.dead-bash-allowlist`, `tests/goldens/allowlist/**`
- `.ci/policy/.w7p5a-real-run-blocklist`, `-leg-blocklist`, `.ci/shadow/w7p5a-status.json`, `.ci/shadow/twin-parity.ledger.jsonl`, `tests/test_w7p4b_ledgers.py`, `test_w7p5a_dry_run_ledgers.py`
- `security/shfmt.py` (the floor), `quality/bash_lib_migration_complete.py` (LIBS/ALIASES), `quality/pipefail_grep_q.py`, `quality/scope_scripts_reachability.py`
- `.ci/config/{secret-supply,inline-suppressions-baseline,python-types-baseline,python-env-registry,env-manifest}.json`, `.ci/config/shards/quality-pytest.json`
- `scripts/data/{em-dash-surfaces-baseline,shell-declared-commands-baseline,literal-sources}.json`
- `.ci/scripts/ci/greenlight.cjs`, `tests/gates/trace_checker.cjs.fixture`
- `scripts/ci-runner/manifest.ts`, `gates.lock.json`, root `package.json` (after W10), `.ci/policy/README.md`, `scripts/data/doc-registry.md`, `.ci/README.md`, CLAUDE.md, TRAPS.md

| Unit | Wave | .sh deleted | Also owns (edits) | Drop |
|---|---|---|---|---|
| **W1** blocker, gate twins, hooks, media seam | 1 | `lib/blocker-validator.sh`, `test/gates/test-blocker-golden-corpus.sh`, `test/gates/test-runner-advice.sh`, `pr/sync-epic-block.sh`, `test/manual/probe-receipt-stability.sh` (ported), `deploy/sync-media-from-r2.sh`, `deploy/sync-media-to-r2.sh`, `test/gates/test-media-r2.sh`, `test/lib/test-helpers.sh` | `scripts/quality/check_language_policy.py` (validator becomes `core.blocker_validator`); `.ci/rediacc_ci/quality/vendored_blocker_derivation.py:66`; `.ci/rediacc_ci/quality/pr_description.py:179,360`; `quality/gh_retry_shell.py`; `scripts/gates/check-pr-epic-block.ts`; `.claude/skills/pr-epics/{SKILL,body}.md`; hook guards `block_raw_pr_body_edit.py` (`:10,85,103,602,741`) and `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:77-80` (all rows to module spellings) plus `test-block_host_toolchain_run.py`, their `.claude/.../goldens/<stem>.jsonl` and `hookcases.py` (`--regolden <stem> --reason`); `.ci/media/r2.sh:32,43`; `.ci/media/verify.sh:141`; `scripts/lib/doc-providers.ts:1354-1355`; the tests `test_gate_{blocker_golden_corpus,runner_advice,media_r2,media_helpers}.py`, `test_runtmp.py`, `test_pr_sync_epic_block.py`, `test_core_blocker_validator.py`, `test_deploy_sync_media_{from,to}_r2.py` | 9 |
| **W2** build and testrun twins | 1 | `build/{build-cli-executables,build-cli-musl,build-cli,build-linux-pkg,build-pkg-repo,build-renet,canonicalise-gpg-key,ensure-nfpm,prepare-cli-assets}.sh`, `test/{test-linux-packages,run-e2e,test-install-methods,test-rdc-update}.sh`, `version/inject-env.sh` | `.ci/rediacc_ci/build/build_cli_executables.py:694`, `.ci/rediacc_ci/build/build_linux_packages.py:96`, `.ci/rediacc_ci/build/build_linux_pkg.py:387,397`, `.ci/rediacc_ci/build/build_cli_musl.py:90,113` (the container script runs the modules); `.ci/media/bridge.sh:123`; `.ci/rediacc_ci/ci/budget_report.py:1015-1033` (read the bucket table from `testrun/e2e.py`, Rule-T fix with a test); `.ci/rediacc_ci/proxies/linux_packages.py:57`, `.ci/rediacc_ci/proxies/rdc_update.py:51`; `test_build_*`, `test_testrun_*`, `test_proxies_{linux_packages,rdc_update,ensure_nfpm}.py`, `test_version_inject_env.py`, `test_ci_budget_report.py`, `gates/test_gate_installmethods_*`, `test_gate_releaseversion_{inject_env,build_version,closure_untagged}.py`, `test_gate_e2e_coverage.py` | 14 |
| **W3** ci/version | 1 | `ci/{generate-tag,assert-ci-complete,dispatch-release}.sh`, `version/{resolve-version,detect-bump-type}.sh`, `deploy/deploy-proxy.sh` | `.ci/rediacc_ci/ci/initialize.py:126-150,523-533` (run the modules; drop the `*_LINE` constants; `ci.initialize.jsonl` regolden `--source port`); `.ci/rediacc_ci/ci/generate_tag.py:123,136,158` (drop build-cli/musl from the path lists; changing the list moves closure tags, so this is an intentional delta); `.ci/rediacc_ci/deploy/deploy_proxy.py:138`; `.ci/rediacc_ci/quality/ci_job_aggregation.py:267` (target `assert_ci_complete.py`); `test_ci_{generate_tag,initialize,assert_ci_complete,dispatch_release}.py`, `test_version_*`, `test_deploy_deploy_proxy.py`, `gates/test_gate_{ci_complete_tiers,ci_job_aggregation,generate_tag_inputs,detect_bump_type,dispatch_release}.py` | 6 |
| **W4** Worker deploys | 1 | `deploy/{deploy-edge,deploy-www,deploy-account,set-account-worker-secrets,set-preview-worker-secrets,set-www-worker-secrets,resolve-account-deploy-config}.sh` | `.github/workflows/cd-deploy-worker.yml:182` and `.ci/rediacc_ci/deploy/resolve_www_deploy_target.py:42,44` (emit module names); `scripts/gates/check-worker-secret-names.ts:83-85`, `scripts/gates/check-builder-env-contract.ts:125-139`, `scripts/gates/check-backup-bucket-conformance.ts:26` (parse the `.py` ports); their tests | 7 |
| **W5** release tree (only after D1 = yes) | 1 | the 15 `release/*.sh`, `docker/cleanup-staging.sh`, `housekeeping/cleanup-versions.sh` | `.ci/rediacc_ci/quality/staging_tag_guard.py:105-110,378-395` (scan `.py` callers; the target becomes `cleanup_staging.py`); `.github/workflows/housekeeping.yml`; `release/backfill_*` excluded (W7); `test_release_*`, `test_docker_cleanup_staging.py`, `test_quality_staging_tag_guard.py`, `test_housekeeping_cleanup_versions.py` (freeze needed, 2073 lines), `gates/test_gate_{assert_edge_tag_exists,mark_production,releaseversion_attestation,housekeeping_phases,preview_worker_reaping}.py` | 17 |
| **W6** promote, purge, verify | 1 | `deploy/{promote-r2-to-stable,promote-r2-to-stable-hotfix,promote-docker-to-stable-hotfix,simulate-promotion,verify-edge-endpoints,verify-stable-endpoints,wait-for-preview-worker,cf-purge-urls,delete-r2-channel,purge-media-cache,upload-repos-to-r2}.sh` | `PURGE_SCRIPT*` in `.ci/rediacc_ci/deploy/promote_r2_to_stable.py:212`, `.ci/rediacc_ci/deploy/promote_r2_to_stable_hotfix.py:69`, `.ci/rediacc_ci/deploy/simulate_promotion.py:149`, `.ci/rediacc_ci/deploy/upload_repos_to_r2.py:135` (call `cf_purge_urls` in process); `.ci/rediacc_ci/tests/gates/test_gate_simulate_promotion_serverside.py:28-83`; `.github/workflows/cleanup-r2-staging.yml:29` comment; the matching `test_deploy_*`, `test_gate_skip_release_channel_pointer.py`, `test_gate_edge_verify_retries.py` | 11 |
| **W7** R2 state (wave 2, after W1 and W5; D5) | 2 | `deploy/{upload-to-r2,write-release-sentinel,clone-d1,test-d1-migrations}.sh`, `lib/{release-state-validator,emit-advisory}.sh`, `test/assert-r2-sentinel.sh` | `deploy/upload_to_r2.py` (port `write_once_guard`, freezing goldens over `write_once_guard_check`'s 4 cases first), `deploy/write_once_guard_check.py`, `.ci/rediacc_ci/release/backfill_write_sentinel.py:28`, `.ci/rediacc_ci/deploy/test_d1_migrations.py:116`, `core/release_state_validator.py` docstrings, `.github/workflows/backfill-release-sentinel.yml:7`; their tests plus `test_core_advisory.py`, `gates/test_gate_emit_advisory.py` | 7 |
| **W8** .ci/lib, setup, dev | 1 | `.ci/lib/{account,devbox,local-common,service}.sh`, `setup/{build-packages,install-deps}.sh`, `scripts/dev/worktree.sh`, `test/gates/test-run-sh.sh` (per D6) | `setup/bridge.py` (call `core.local_common` and `core.devbox` directly), `setup/shadow_driver.py`, `dev/shadow_driver.py`, `core/{account_lifecycle,devbox,local_common,local_common_actions,service,common_stub}_shadow_driver.py`, `.ci/rediacc_ci/core/local_common.py:794`, `.ci/rediacc_ci/core/run_verbs.py:42`, `.ci/rediacc_ci/native.py:137`; `rdc.sh:18,48,72` (`python3 -m rediacc_ci.core.local_common` verbs; keep within the `check:ci-rdc-native` ceiling); `.ci/media/media-entry.sh:50`; `.github/actions/setup-workspace/action.yml:101,105,117`; `.github/workflows/ci.yml:627`; `test_core_{account,devbox,local_common,service}.py`, `test_setup_*`, `test_dev_worktree.py`, `gates/test_gate_run_sh.py` | 8 |
| **W9** private renet and licence | 1 | `private/{renet-csi-sanity,renet-ebpf-e2e,renet-integration,renet-root-tests,license-e2e}.sh` | `.github/workflows/ct-tests.yml:2462,2470,2478,2559,2659` (`sudo env PYTHONPATH=.ci python3 -m ...`; sudo drops PYTHONPATH); a new `private/license_e2e.py`; `.ci/rediacc_ci/proxies/license_e2e.py:37-39`, `.ci/rediacc_ci/drills/license.py:11`; `test_private_*`, `test_proxies_license_e2e.py` | 5 |
| **W10** B5, out of policy | 1 | `packages/json/{generate,test-templates}.sh`, `scripts/eslint-heap.sh`, `programs/backup-storage/{local-roundtrip,start-local-plane}.sh`, `packages/www/scripts/measure-page-density.sh` | `packages/json/package.json:6-7`; root `package.json:339-342` (W10 owns it until it finishes, then the lead); `.ci/scripts/quality/check_lint_scope_coverage.py:110`, `.ci/rediacc_ci/quality/env_file_adoption.py:68,370`; `docs/backup-storage/09-local-roundtrip-proof.md:144`; `docs/agent-reference/TRAPS.md:952` is lead-owned, so W10 reports it | 6 |

Wave 1 has 9 live writers, inside the writer cap of 10. W7 runs alone in wave 2.

**Ordering constraints:**
- W7 depends on W1 (removes `blocker-validator.sh`, the other sourcer of `emit-advisory.sh`).
- W7 depends on W5 (removes `.ci/scripts/housekeeping/cleanup-versions.sh:1337` and `.ci/scripts/release/advance-contract-floor.sh:49`, sourcers of `release-state-validator.sh`).
- W2 and W3 are coupled only through `generate_tag.py`, which only W3 edits.
- W3's `deploy-proxy.sh` calls W2's `build-renet.sh`. Either order works, because the state is consistent at the end of the wave.

**Wave 3 (only after D2/D3/D4, small):** a W11 owns:
- `lib/common.sh`: add a `gh-retry` verb to `core/common.py`; repoint `.github/workflows/cd-v2.yml:734` and `.github/workflows/promote-stable.yml:173`; inline `log_*` into `.ci/docker/service/env.sh` and the media `upload-r2.sh` / `.ci/media/verify.sh:278` (W1 has finished with `verify.sh` by then);
- `toolchain.sh` and the elite trio, per their decisions.

**Lead passes:**
- **L0 (now, parallel with wave 1).** A5: full `.claude/rediacc_hooks/tests`, `test_guards_differential.py::test_the_differential_can_fail` (DEFECT), `test_bash_semantics.py`, `test_golden_drift.py`, `npm run check:ci-language-policy check:ci-hook-integrity check:ci-dead-python check:ci-guard-mention-anchoring`, `test_gate_docs_gen.py`, real events piped through `.claude/hooks/chain-head.sh`, and wall time against the recorded 294.65 s floor (plan section 1). Also run `/ask` for D1-D7.
- **L1 (after wave 1).** `check_language_policy.py --write-baseline`, then every lead-reserved registry from the writers' drain lists. Lower the shfmt floor to the measured count. Drop the LIBS rows for deleted libraries. Remove `manifest.ts` entries for the 4 gate twins, then `npm run gen:gates-lock`, `npx tsx scripts/gate-bind.ts --write`, and `npx tsx scripts/gen/gen-docs.ts --write`.
- **L2 (after wave 2).** The same steps for W7.
- **L3 (G1/G2/G3, after wave 3).**
  - Allowlist the survivors with `BLOCKER:` (`upload-media-to-r2.sh`, plus `toolchain.sh` / `common.sh` / the elite shims if kept), then delete the baseline file to enter strict mode.
  - G2: retire `check:ci-bash-lib-ported` (`.github/workflows/ci-quality.yml:297`, `package.json:188`) only if no library remains. Otherwise shrink it.
  - G3: CLAUDE.md and TRAPS.md already have no oracle-as-spec prose (grep is empty). The sweep is the about 18 stale `.claude/oracles` mentions (`git grep -l '\.claude/oracles' -- ':!agent'`) and comment repoints.

### 4. Acceptance per unit

The common prefix is `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q -n 16`. Every unit also runs `.ci/rediacc_ci/tests/test_twin_goldens.py` and `.ci/rediacc_ci/tests/gates/test_twin_parity.py`, plus ruff on the files it touched. Writers should expect `check:ci-language-policy`, `check:ci-shell-format` and the registry gates to be red on drained-but-not-yet-ratcheted entries until L1; they report those, they do not fix them.

| Unit | Named tests (plus the module tests listed above) | Gates | `git ls-files '*.sh' \| wc -l` |
|---|---|---|---|
| W1 | `test_gate_blocker_golden_corpus.py`, `test_gate_runner_advice.py`, `test_gate_media_r2.py`, `test_core_blocker_validator.py`, `test_quality_pr_description.py`, `.claude/rediacc_hooks/tests/test_guards_differential.py -k "raw_pr_body or host_toolchain"` | `check:ci-vendored-blocker-derivation`, `check:ci-pr-epic-block`, `check:ci-guard-mention-anchoring`, `check:ci-breakpoint-drift` | 190 -> 181 |
| W2 | `test_build_*.py`, `test_testrun_*.py`, `test_ci_budget_report.py` | `check:ci-proxy-linux-packages`, `check:ci-proxy-rdc-update`, `check:ci-release-key-canonical` | -14 |
| W3 | `test_ci_initialize.py`, `test_ci_generate_tag.py`, `gates/test_gate_ci_complete_tiers.py` | `check:ci-job-aggregation` | -6 |
| W4 | `test_deploy_{deploy_*,set_*,resolve_*}.py` | `check:ci-worker-secret-names`, `check:ci-builder-env-contract`, `check:ci-backup-bucket-conformance` | -7 |
| W5 | `test_release_*.py`, `test_housekeeping_cleanup_versions.py`, `test_quality_staging_tag_guard.py` | `check:ci-staging-tag-guard` | -17 |
| W6 | `test_deploy_{promote_*,simulate_promotion,verify_*,wait_for_preview_worker,cf_purge_urls,delete_r2_channel,purge_media_cache,upload_repos_to_r2}.py`, `gates/test_gate_simulate_promotion_serverside.py` | `check:ci-gh-retry-reads` | -11 |
| W7 | `test_deploy_upload_to_r2.py`, `test_deploy_write_once_guard_check.py`, `test_core_release_state_validator.py`, `test_core_advisory.py` | `test:write-once-guard` | -7 |
| W8 | `test_core_{account,devbox,local_common,service}.py`, `test_setup_*.py`, `gates/test_gate_run_sh.py` | `check:ci-rdc-native`, `check:ci-scope-scripts-reachability` | -8 |
| W9 | `test_private_*.py`, `test_proxies_license_e2e.py` | - | -5 |
| W10 | `test_quality_page_density.py`, plus new tests for each port | `check:ci-lint-scope-coverage`, `check:ci-env-file-adoption` | -6 |

**Totals.** 190 -> 100 after waves 1 and 2 (90 removed). The remainder is the 96 KEEP-BASH rows (with `inject-env.sh` moved out) plus the 5 decision-pending files and `upload-media-to-r2.sh`. If D2-D4 all choose "delete", the floor is about 94.

The lead's final check is `npm run ci`, plus `check:ci-{language-policy,dead-bash,policy-inventory,w7p5a-real-run-blockers,secret-supply,em-dash-surfaces,shell-declared-commands,inline-suppressions,python-types,python-env-registry,dead-python,gate-bind,gates-lock,parity,suppression-liveness,greenlight-closures,pipefail-grep-q}`.

### 5. What needs real machines

- **B5 drills.** The ports exist (50dd86fb0), but the live run on the ops VMs is still owed. It is operator-run.
- **W9.** The renet sudo suites and `license-e2e` cannot run locally (they need `private/renet`, sudo and `/var/lib/rediacc`). They are proven by a dispatched full-suite ct-tests run (`ct-tests.yml` License Enforcement job, `inputs.full_suite == 'true'`) on GitHub-hosted runners, not on the ops VMs.
- **W4, W5, W6 and W7 touch production paths.** These are cd-deploy-worker, cd-v2, promote-stable, cd-stage and backfill. They are the 19 operator-run rows of `agent/plans/PLAN-w7p5a-real-run-dispatch.md:76`. Deleting the twins does not change what runs (the modules already run), but W4 and W7 change live code paths. Their proof is the next real edge deploy and release, with a rollback step named first.

### 6. Operator decisions, with a recommended default for each

- **D1. Lift the 2026-10-01 hold on the release twins?** Default: yes. v1.3.2's CD already ran the Python modules (3ce2c1994, 82700f4a0). The 13 blocklist entries go in L1 together with their `w7p5a-status.json` rows.
- **D2. `toolchain.sh`.** Default: KEEP-BASH, with the BLOCKER "sourced by bootstrap.sh before the Python toolchain exists". Moves the 4 `ci-quality.yml` sites and the `setup-node-npm` site to `python3 -m rediacc_ci.core.toolchain`.
- **D3. `common.sh`.** Default: delete in wave 3 (W11). This costs a new `gh-retry` verb and edits to 3 KEEP-BASH files, plus churn across 57 test files that reference it.
- **D4. Elite trio.** Default: keep 3-line exec shims, allowlisted with "path contract of the vendored breakpoint tree". Do not edit the drift-locked breakpoint tree.
- **D5. `write_once_guard`.** Default: port it to Python, behind goldens frozen from the bash. This reverses an explicit earlier ruling, so it needs the operator's yes.
- **D6. `test-run-sh.sh` on the bare runner.** Default: point the job step at a stdlib-only Python entry, or move the step into a bootstrapped job. Otherwise it stays KEEP like `test-toolchain.sh`, and then `local-common.sh` cannot be deleted.
- **D7. `upload-media-to-r2.sh` and `probe-receipt-stability.sh`.** Default: allowlist the first, port the second.

### 7. What not to do

- Do not delete `upload-to-r2.sh`, `release-state-validator.sh` or `emit-advisory.sh` in wave 1.
- Do not touch `.ci/breakpoint/**`.
- Do not hand-edit `language-policy-baseline.json` to absorb anything. Drain it only with `--write-baseline`.
- Do not tick G2 as "retired" if any library is kept. The box wording needs an operator re-ruling to "shrink".

## Remaining (operator)

The plan's only open decision is whether to run it as described. A few individual Rule T fixes will surface in B4 as `[?]` items with a default, the first being `assert_channel_for_event` failing open (`DEFAULT: fail closed`).
