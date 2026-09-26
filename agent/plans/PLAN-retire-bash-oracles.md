# PLAN: retire the bash hook oracles, transform the remaining bash into Python

Status: APPROVED 2026-09-24 by the operator (/ask): run as one big-bang; use sonnet for any sub-agent task it can handle; re-judge the three tree exemptions per file; reverse the 2026-09-21 ruling BUT keep the real-bash benefit for some cases (task A0). Worklist #52383b75.
Depends-On: no-dep -- related, not ordered: its G1 closes box W1P6 of PLAN-tooling-transformation.md and supersedes that plan's 2026-09-21 oracle ruling
Owner: d778be9d
Priority: P2 -- seed: Status approved, 15 open box(es)
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: .ci/config/language-policy-baseline.json

## Tasks

- [ ] A0 Select the oracle cases whose value is real bash execution (bash's own parsing/quoting/heredoc/pipeline semantics and version-specific behaviour, the 2026-09-21 examples) and keep them as a small, justified real-bash semantics suite; everything else becomes goldens
- [ ] A1 Freeze hook goldens from the oracles over the full corpus plus every EDGE_CASES entry; the current ports match 100 percent before anything is deleted
- [ ] A2 Retarget the three hook differentials, guardcorpus/hookcases, the mention-anchoring gate, check_policy_inventory, doc-providers and the language-policy allowlist from the oracles to the goldens; add the regolden verb and the golden-drift control
- [ ] A3 Delete .claude/oracles/ (bash, both Python forwarders, lib/sanctioned.py), every TWIN constant and the bash driver; consolidate pattern_for and the pgrep loop shared by the two running-script guards
- [ ] A4 Rule-T fixes on the hook side (block_ssh_file_write empty command and jq null, the shellscan.target_root tab defect, and every copied bug the 47 PORT NOTE re-read finds), each with an intentional golden delta and a failing-first test
- [ ] A5 Phase A acceptance: full .claude hook suite, DEFECT control over all guards, language-policy, hook-integrity, docs-gen and dead-python gates, the live chain on real commands, wall time measured before and after
- [ ] B0 Inventory every tracked .sh into agent/plans/PLAN-retire-bash-oracles.inventory.tsv; close the 15 unclassified C/D files, re-check group D DELETE verdicts against naming tests, re-judge the media/breakpoint/tutorials tree exemptions file by file
- [ ] B1 Cut over the CUTOVER-READY live twins (assert-job-succeeded, detect-pointer-bump, initialize, then lib/common.sh and its 181+ source sites); retire run-legacy.sh as its verb table empties
- [ ] B2 Port groups C and D-port in dependency order under rule T, each with a differential for right behaviour and intentional deltas for wrong behaviour, wired in the same change
- [ ] B3 Golden-then-delete every twinned bash file (groups A and B after cutover), draining its bashFiles line, with the same regolden verb as A2
- [ ] B4 Rule-T fixes in the .ci ports: the 24 plan-named reproduced behaviours, the sweep's 8-13 bugs, and the promote retry gap #4175e786
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

## Remaining (operator)

The plan's only open decision is whether to run it as described. A few individual Rule T fixes will surface in B4 as `[?]` items with a default, the first being `assert_channel_for_event` failing open (`DEFAULT: fail closed`).
