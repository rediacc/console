# PLAN: retire the bash hook oracles, transform the remaining bash into Python

Status: done -- 2026-10-20, every box ticked (15 of 15), merged to main with PR #600 (d35df2ab1)
First-Seen: 2026-10-11
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
- [x] A5 Phase A acceptance: full .claude hook suite, DEFECT control over all guards, language-policy, hook-integrity, docs-gen and dead-python gates, the live chain on real commands, wall time measured before and after
    (ticked) 2026-10-08T23:06:15Z by d778be9d: commit:9c6175791 -- hook suite 10956 passed in 290.5s on a clone; its 14 failures are clone-only (submodule symlink and missing private/account, detached HEAD) and the 3 files re-run 520 + 543 passed in the live tree; DEFECT control 69 passed; bash_semantics 257, golden_drift 3, docs_gen 7 passed; check:ci-language-policy, -hook-integrity, -dead-python, -guard-mention-anchoring rc=0; live chain-head: git worktree add BLOCKED rc=2, ls rc=0; guard differential 65.8s against 294.65s before
- [x] B0 Inventory every tracked .sh into agent/plans/PLAN-retire-bash-oracles.inventory.tsv; close the 15 unclassified C/D files, re-check group D DELETE verdicts against naming tests, re-judge the media/breakpoint/tutorials tree exemptions file by file
    (ticked) 2026-10-08T12:56:00Z by d778be9d: commit:a577aa05a agent/plans/PLAN-retire-bash-oracles.inventory.tsv holds one row per tracked .sh, 190 of 190 (plus 35 GONE); exempt trees re-judged per file; the DELETE verdict rechecked; check:ci-language-policy rc=0
- [x] B1 Cut over the CUTOVER-READY live twins (assert-job-succeeded, detect-pointer-bump, initialize, then lib/common.sh and its 181+ source sites); retire run-legacy.sh as its verb table empties
    (ticked) 2026-10-08T19:34:43Z by d778be9d: commit:389b4135a common.sh deleted with its sourcers (also 6eb239b4d, 3bfab056e); check:ci-language-policy rc=0, .ci suite 13333 passed
- [x] B2 Port groups C and D-port in dependency order under rule T, each with a differential for right behaviour and intentional deltas for wrong behaviour, wired in the same change
    (ticked) 2026-10-08T22:36:31Z by d778be9d: commit:08bde4c6f commit:a72984c47 commit:f36f3bbbf commit:05e9225bb -- no PORT row left without a port (section 12); check:ci-language-policy STRICT rc=0, 80 bash files all allowlisted
- [x] B3 Golden-then-delete every twinned bash file (groups A and B after cutover), draining its bashFiles line, with the same regolden verb as A2
    (ticked) 2026-10-08T22:36:34Z by d778be9d: commit:08bde4c6f commit:a72984c47 commit:f36f3bbbf commit:05e9225bb -- frozen goldens first, then deletion; check:ci-dead-bash, -language-policy, -bash-lib-ported rc=0
- [x] B4 Rule-T fixes in the .ci ports: the 24 plan-named reproduced behaviours, the sweep's 8-13 bugs, and the promote retry gap #4175e786
    (ticked) 2026-10-04T17:20:45Z by d778be9d: commit:d2c44c127 landed in e07adce45 and d2c44c127; the full .ci suite re-covers those tests
- [x] B5 Port the out-of-policy scripts (drills, ops, worktree, eslint-heap, json generator, backup-storage); prove the drills with a live run on the ops VMs
  - Amended 2026-10-08 (reviews 48e04cab.2 and 48e04cab.3): "the ops VMs" and "the local fleet" are the same machines (`./rdc.sh ops up` provisions them); the license drill ran there on the basic fleet, where legs needing .12 or Ceph are refused honestly, as 57eb32e04 records. "selftests rc 1" is the expected result, not a failure: every drill `--selftest` plants one assertion that cannot pass and MUST exit non-zero (`.ci/rediacc_ci/drills/lib.py`, PROVE THE INSTRUMENT).)
  - Amended 2026-10-09 (reviews 2cedd2cc.2 and 2cedd2cc.3): the tick names two runs. "license 44/44 (legs a-f)" is the full-fleet run that 68c262cbc and 48e04cabd record, with every leg run and passed; the basic-fleet run in 57eb32e04 is a separate one, where the preflight refused the legs needing .12 or Ceph by name, so they never ran and are not counted in any pass total (leg f 5/5 there). The selftest rule is shown, not only asserted: `./run.sh drill license --legs f --selftest` exits 1 with "1 assertions: 0 passed, 1 failed" and "selftest fired as designed".)
    (ticked) 2026-10-08T19:52:42Z by d778be9d: commit:57eb32e04 live drills all green (universe 42/42, transfer 33/33, backup 86/86, license 44/44, backup_roundtrip 8/8), selftests rc 1, drill-verdicts rc=0
- [x] G1 Empty and delete .ci/config/language-policy-baseline.json (closes PLAN-tooling-transformation W1P6, ed0c365d); every remaining allowlist entry carries a BLOCKER reason
    (ticked) 2026-10-08T22:36:36Z by d778be9d: commit:05e9225bb -- baseline deleted; check:ci-language-policy STRICT rc=0 (80 bash files, all allowlisted); suppression-liveness rc=0; plants rc=1
- [x] G2 Fix check:ci-bash-lib-ported (add log.py to its module list, recognise class methods), port its 8 real gaps, retire it with the last library
  - Amended 2026-10-09 (review 80544cbd.1): "retire it with the last library" has not come due. The last library is `.ci/scripts/lib/toolchain.sh`, which operator ruling D9 keeps ("Keep the gate for toolchain (Recommended)", ASKED:2026-10-08T19:13Z), so the gate stays alive to guard it. The box closes on the fix and the 0-gap port, and the retirement is owed only when toolchain.sh goes.)
    (ticked) 2026-10-08T22:36:39Z by d778be9d: commit:05e9225bb commit:08bde4c6f -- check:ci-bash-lib-ported rc=0 (1 library, 17 functions); retirement waits on toolchain.sh, kept by operator D9 ASKED:2026-10-08T19:13Z
- [x] G3 Regenerate gates.lock.json, the gen-docs regions, gate-bind steps and the registries; correct the TRAPS.md and CLAUDE.md prose that calls the oracles the spec
    (ticked) 2026-10-08T22:36:42Z by d778be9d: commit:05e9225bb -- check:ci-gates-lock, -gate-bind, -prose-style rc=0; breakpoint-blocker.sh repointed with its MANIFEST regenerated, check:ci-breakpoint-drift rc=0

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

This plan is ready to run, but read section 2 first. Twelve rows of the section 2 table correct inventory verdicts that are wrong in ways that would break the cutover. Five boxes also depend on operator decisions (D1-D7 in section 6), so four units cannot start until those are made.

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
- **Already frozen.** 26 twins have goldens, and every `twin_blob` matches the file today (checked with `git hash-object`). They are 14 of the `release/*.sh`, 9 deploy scripts, `build-cli`, `build-pkg-repo` and `test-media-r2`.
- **Why they were not deleted.** 0866fa941 says: "Every .ci/scripts/release/*.sh stays on disk ... those ports wait for the operator's real cd-v2, promote-stable and backfill-release-sentinel runs (operator rule, 2026-10-01)". `agent/plans/PLAN-deletion-budget.md:143` repeats the rule.

### 2. Inventory corrections that change the work

| Row | Inventory says | Code says |
|---|---|---|
| `run-e2e.sh`, `test-install-methods.sh`, `test-linux-packages.sh`, `test-rdc-update.sh` | PORT ("carried") | Already ported under `.ci/rediacc_ci/testrun/` and wired: `.github/workflows/ci.yml:978,1896`, `.github/workflows/ct-tests.yml:568`, `.github/workflows/ct-update-flow.yml:70`. What is left are readers of the dead text: `.ci/rediacc_ci/ci/budget_report.py:1015-1033` still parses `run-e2e.sh`'s `E2E_SHARD_GREP_BUCKETS` (a live Rule-T bug); `.ci/rediacc_ci/proxies/linux_packages.py:57` and `.ci/rediacc_ci/proxies/rdc_update.py:51` still read the .sh. These are golden-then-delete. |
| `test-blocker-golden-corpus.sh`, `test-media-r2.sh`, `test-runner-advice.sh`, `test-run-sh.sh` | PORT | Python ports carry `BASH_TWIN` (`.ci/rediacc_ci/tests/gates/test_gate_blocker_golden_corpus.py:34`, `.ci/rediacc_ci/tests/gates/test_gate_media_r2.py:24`, `.ci/rediacc_ci/tests/gates/test_gate_runner_advice.py:41`, `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py:32`). `scripts/ci-runner/manifest.ts:5174-5210` still runs the .sh. These are golden-then-delete. |
| `scripts/dev/worktree.sh` | PORT | Port `.ci/rediacc_ci/dev/worktree.py` exists; `.ci/rediacc_ci/core/run_verbs.py:42` still routes to the .sh. This is a cutover. |
| `upload-to-r2.sh` | GOLDEN-THEN-DELETE, "No .sh caller" | **Wrong.** The live port sources it at runtime: `.ci/rediacc_ci/deploy/upload_to_r2.py:7-14,442-460` runs `write_once_guard` as bash, together with `common.sh` and `release-state-validator.sh`. `write_once_guard_check.py` drives the same function. Not porting it was a deliberate ruling (the v1.1.16/17 sealed-but-empty incident). Decision D5. |
| `lib/toolchain.sh` | CUTOVER-READY | Two KEEP-BASH files source it: `.ci/bootstrap.sh:87`, which runs before the Python toolchain exists, and `.ci/scripts/test/gates/test-toolchain.sh` (bare runner). It is also used at `.github/actions/setup-node-npm/action.yml:34` and `.github/workflows/ci-quality.yml:247-248` (4 sites). It should be KEEP-BASH. Decision D2. |
| `lib/common.sh` | CUTOVER-READY, "181+ sites" | 76 files really source it (`git grep -E '^\s*(source|\.)\s+.*lib/common\.sh'`), and about 67 of those die in this plan. The remaining consumers: KEEP-BASH `.ci/docker/service/env.sh:14`, `.ci/media/tools/upload-r2.sh:62` and `.ci/media/verify.sh`; workflow steps `.github/workflows/cd-v2.yml:734` and `.github/workflows/promote-stable.yml:173` (`gh_retry`). No Python CLI offers gh-retry: neither `.ci/rediacc_ci/core/ghx.py:561-597` nor `.ci/rediacc_ci/core/common.py:640-658` has the verb. Decision D3. |
| `.ci/lib/local-common.sh` | CUTOVER-READY | KEEP-BASH `rdc.sh:18` sources it (uses `check_node_version`, `ensure_deps` and `log_*`), and so does `.ci/media/media-entry.sh:50`. Also `.ci/rediacc_ci/setup/bridge.py:31-38` PRELUDE (which also sources `devbox.sh`, `service.sh` and `toolchain.sh`), `.ci/scripts/test/gates/test-run-sh.sh`, and 4 `*_shadow_driver.py`. Deletable, but rdc.sh and media-entry.sh need edits. |
| `ci-pull-images.sh`, `ci-start-elite.sh`, `ci-stop-elite.sh` | CUTOVER-READY | They are a path contract for the vendored breakpoint tree: `.ci/breakpoint/scripts/start-origin.sh:88`, `.ci/breakpoint/scripts/pull-service-images.sh:38` and `.ci/breakpoint/scripts/stop-breakpoint.sh:240` test `-x` on these exact paths. The tree is drift-locked by `MANIFEST.sha256` and copied downstream. Decision D4. |
| `test/lib/test-helpers.sh` | GOLDEN-THEN-DELETE | KEEP-BASH `.ci/media/verify.sh` sources it. |
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
| **W1** blocker, gate twins, hooks, media seam | 1 | `lib/blocker-validator.sh`, `test/gates/test-blocker-golden-corpus.sh`, `test/gates/test-runner-advice.sh`, `pr/sync-epic-block.sh`, `test/manual/probe-receipt-stability.sh` (ported), `deploy/sync-media-from-r2.sh`, `deploy/sync-media-to-r2.sh`, `test/gates/test-media-r2.sh`, `test/lib/test-helpers.sh` | `scripts/quality/check_language_policy.py` (validator becomes `core.blocker_validator`); `.ci/rediacc_ci/quality/vendored_blocker_derivation.py:66`; `.ci/rediacc_ci/quality/pr_description.py:179,360`; `quality/gh_retry_shell.py`; `scripts/gates/check-pr-epic-block.ts`; `.claude/skills/pr-epics/{SKILL,body}.md`; hook guards `block_raw_pr_body_edit.py` (`:10,85,103,602,741`) and `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:77-80` (all rows to module spellings) plus `test-block_host_toolchain_run.py`, their `.claude/.../goldens/<stem>.jsonl` and `hookcases.py` (`--regolden <stem> --reason`); `.ci/media/r2.sh:32,43`; `.ci/media/verify.sh`; `scripts/lib/doc-providers.ts:1354-1355`; the tests `test_gate_{blocker_golden_corpus,runner_advice,media_r2,media_helpers}.py`, `test_runtmp.py`, `test_pr_sync_epic_block.py`, `test_core_blocker_validator.py`, `test_deploy_sync_media_{from,to}_r2.py` | 9 |
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
- W7 depends on W5 (removes `.ci/scripts/housekeeping/cleanup-versions.sh` and `.ci/scripts/release/advance-contract-floor.sh`, sourcers of `release-state-validator.sh`).
- W2 and W3 are coupled only through `generate_tag.py`, which only W3 edits.
- W3's `deploy-proxy.sh` calls W2's `build-renet.sh`. Either order works, because the state is consistent at the end of the wave.

**Wave 3 (only after D2/D3/D4, small):** a W11 owns:
- `lib/common.sh`: add a `gh-retry` verb to `core/common.py`; repoint `.github/workflows/cd-v2.yml:734` and `.github/workflows/promote-stable.yml:173`; inline `log_*` into `.ci/docker/service/env.sh` and the media `upload-r2.sh` / `.ci/media/verify.sh` (W1 has finished with `verify.sh` by then);
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

## 11. W11, wave 3: common.sh, local-common.sh, test-run-sh.sh, toolchain.sh, the elite trio (operator D2/D3/D4/D6/D7 defaults, ASKED:2026-10-08T13:48Z)

Read-only design dated 2026-10-08. Every claim below was checked against the tree. Today the tree has 114 tracked `.sh` files (`git ls-files '*.sh' | wc -l`).

### 11.1 Facts that change what section 10 assumed

1. **Real `common.sh` sourcers now.** `git grep -nE '^\s*(source|\.)\s+.*lib/common\.sh'` finds:
   - KEEP-BASH files: `.ci/docker/service/env.sh:14`, `.ci/media/tools/upload-r2.sh:62`, `.ci/media/verify.sh`.
   - `.ci/lib/local-common.sh`.
   - W7's files (W7 deletes them): `deploy/{clone-d1:16,test-d1-migrations:34,upload-to-r2:25,write-release-sentinel:32}.sh` and `.ci/scripts/test/assert-r2-sentinel.sh`.
   - `.ci/scripts/infra/ci-pull-images.sh`.
   - Workflows: `.github/workflows/cd-v2.yml:734` and `.github/workflows/promote-stable.yml:173`.
   - Test heredocs and doc examples: `.ci/README.md:113,136`, `.ci/rediacc_ci/tests/test_drills_lib.py:87`, `.ci/rediacc_ci/tests/test_quality_release_state.py:130,195,259`, `.ci/rediacc_ci/tests/test_quality_renet_types.py:109`.

   So `common.sh` cannot go until W7 has committed, `local-common.sh` is gone, and `ci-pull-images.sh` is a shim.

2. **Python that breaks in production when `common.sh` disappears.** This is not in section 10.
   - `.ci/rediacc_ci/version/bump.py:351` and `.ci/rediacc_ci/release/update_homebrew_tap.py:555` raise `MissingSourceError` if `.ci/scripts/lib/common.sh` is absent.
     - `bump.py` runs on every build: `.github/workflows/ci-build-docker.yml:83,183` and `.github/workflows/ci-quality.yml:925`.
     - `update_homebrew_tap` runs in the release job at `.github/workflows/cd-v2.yml:794`.
   - `.ci/rediacc_ci/release/mark_production.py:67` (run at `.github/workflows/promote-stable.yml:314`) and `.ci/rediacc_ci/housekeeping/retry_failed_runs.py:78` (run at `.github/workflows/housekeeping.yml:86`) choose their logger by testing whether `common.sh` exists.
     - Deleting the file would silently move info lines to stdout with no glyph.
3. **Many test files copy `common.sh` into fixtures unconditionally.** About 50 test files do `shutil.copy2(COMMON...)`. Examples: `.ci/rediacc_ci/tests/test_build_cli.py:102`, `.ci/rediacc_ci/tests/test_ci_detect_pointer_bump.py:222`, `.ci/rediacc_ci/tests/test_deploy_deploy_edge.py:92`, `test_private_*.py`, and the `for rel in (... COMMON_REL ...)` loops in `test_build_*`.
   - These copies happen even where the twin is already deleted.
   - Others read it live: `.ci/rediacc_ci/tests/test_core_common.py:29`, `.ci/rediacc_ci/tests/test_log.py:40,370,390`, `.ci/rediacc_ci/tests/test_proc.py:33,70`, `.ci/rediacc_ci/tests/test_env_create_e2e_env.py:690`, `.ci/rediacc_ci/tests/test_infra_ci_env.py:250`.
   - Some use it as a real gate subject: `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py:114`.
4. **Python already runs on the bare `ubuntu-slim` runner.**
   - `.github/workflows/ci.yml:138` runs `python3 -m rediacc_ci.ci.sibling_runs` on the ubuntu-slim job at `:115`.
   - `.github/workflows/ci.yml:495` runs `cancel_older_runs` on the slim job at `:472`.
   - The bash twin itself calls `python3 -m rediacc_ci.core.run_verbs arms` (`.ci/scripts/test/gates/test-run-sh.sh`).
   - The pytest port's imports are stdlib only: `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py` imports `os`, `re`, `paths` and `harness`, and `.ci/rediacc_ci/tests/gates/harness.py:18-29` is stdlib only. Its tests all take `gate` only (`:295-624`). Only the `gate` fixture is pytest (`.ci/rediacc_ci/tests/gates/conftest.py:29-54`).
5. **The toolchain Python verbs already match the bash.** Checked on this tree:
   - `diff <(.ci/scripts/lib/toolchain.sh --env) <(PYTHONPATH=.ci python3 -m rediacc_ci.core.toolchain pairs)` is empty, and the same holds for `--report` against `report`.
   - `pin npm` gives `11.20.0` from both.
   - One gate pins the old spelling: `.ci/rediacc_ci/quality/lockfile.py:512` requires the literal `toolchain_pin_for npm` in the setup-node-npm composite, and `:684` holds the fixture copy.
6. **Constraints on `rdc.sh`.**
   - It is 173 lines against `CEILING = 185` (`.ci/rediacc_ci/quality/rdc_native.py:42`).
   - It must keep the literal `rediacc_ci.native` (`.ci/rediacc_ci/quality/rdc_native.py:196`).
   - `check:ci-rdc-sh-env` allows only `export` of PATH, REDIACC_CONFIG and NODE_COMPILE_CACHE (`.ci/rediacc_ci/security/rdc_sh_env_check.py:7-8,98`). So PYTHONPATH must be a command-prefix assignment, never `export`.
   - That gate's layer 2 writes a stub `local-common.sh` into a fixture (`.ci/rediacc_ci/security/rdc_sh_env_check.py:112-121,257`).
   - Python and bash compute the same deps hash on this tree (`72ab0943…e8e5`), so the stamp files stay compatible.
   - Importing `rediacc_ci.core.local_common` costs about 0.08-0.10 s.
7. **The `gh-retry` verb belongs in `core/gh_retry.py`, which has no `main` yet.** `gh()` at `:60` retries only transient failures (3 attempts, 5 s then 15 s). A "release not found" therefore fails at once. That is an intentional Rule-T improvement over `_gh_probe`'s blind three tries.
8. **Keeping the elite trio as shims trips the drift control.**
   - `.ci/rediacc_ci/tests/test_twin_goldens.py:109-113` requires a live twin's blob to equal its golden's `twin_blob`. A file whose body becomes a shim at the same path fails that check.
   - `regolden --source bash` on a shim would record the Python as if it were bash.
   - Both need an explicit "shimmed twin" carve-out.
9. **Gates that read `local-common.sh` as their subject:**
   - `scripts/gates/check-bootstrap-idempotency.ts:56` (`HELPER_FILE`).
   - `scripts/gates/check-native-rebuild.ts:91`, which scans `.ci/lib/*.sh`; that directory empties completely.
   - `.ci/rediacc_ci/quality/setup_idempotency.py:257-278,738,806` (in flight, owned by L1b).
   - `.ci/rediacc_ci/tests/gates/test_gate_plant_proofs.py:27` uses `test-run-sh.sh` as its real bash subject.
10. **`.ci/lib/` disappears.** `.ci/rediacc_ci/core/devbox.py:1870` builds bind sources as `<.ci/lib>/../../.devcontainer/...` (`self.lib_dir`, `:569`).

### 11.2 Excluded files (owned by live writers; W11 must not edit them)

- **W7:**
  - The bash files: `.ci/scripts/deploy/{upload-to-r2,write-release-sentinel,clone-d1,test-d1-migrations}.sh`, `.ci/scripts/lib/{release-state-validator,emit-advisory}.sh`, `.ci/scripts/test/assert-r2-sentinel.sh`.
  - The Python: `deploy/upload_to_r2.py`, `deploy/write_once_guard_check.py`, `release/backfill_write_sentinel.py`, `deploy/test_d1_migrations.py`, `core/release_state_validator.py`.
  - The workflow: `.github/workflows/backfill-release-sentinel.yml`.
  - The tests: `test_deploy_{upload_to_r2,write_once_guard_check,clone_d1,test_d1_migrations,write_release_sentinel}.py`, `test_core_{release_state_validator,advisory}.py`, `gates/test_gate_emit_advisory.py`, `test_quality_release_state.py`.
  - Any residual `common.sh` copy left in these files passes to W11-B only after W7 commits.
- **L1a / L1b (working-tree diff right now):**
  - `.ci/config/{env-manifest,inline-suppressions-baseline,language-policy-baseline,python-env-registry,python-types-baseline,secret-supply}.json`
  - `.ci/policy/{.dead-bash-allowlist,.language-policy-allowlist,.w7p5a-real-run-blocklist,.w7p5a-real-run-leg-blocklist,README.md}`, `.ci/shadow/w7p5a-status.json`
  - `.ci/rediacc_ci/quality/{account_probes,bash_lib_migration_complete,devbox_exec,gh_retry_shell,setup_idempotency}.py`, `.ci/rediacc_ci/security/shfmt.py`
  - `tests/gates/test_gate_{gate_anti_vacuity,greenlight}.py`, `tests/test_quality_{account_probes,devbox_exec}.py`, `tests/test_w7p4b_ledgers.py`, `tests/test_w7p5a_dry_run_ledgers.py`
  - `.ci/scripts/ci/greenlight.cjs`, `.ci/scripts/quality/check_{account_probes,devbox_exec}.py`
  - `scripts/data/{em-dash-surfaces-baseline,shell-declared-commands-baseline}.json`, `scripts/gates/check-em-dash-surfaces.ts`
- **Lead-reserved (section 10.3):**
  - `scripts/ci-runner/manifest.ts`, `gates.lock.json`, root `package.json`
  - `.ci/README.md`, CLAUDE.md, TRAPS.md, `scripts/data/doc-registry.md`
  - `.ci/config/lane-durations.json`, `quality/{pipefail_grep_q,scope_scripts_reachability}.py`, `tests/gates/trace_checker.cjs.fixture`
- Do not touch `.ci/breakpoint/**` (drift-locked).

### 11.3 Writer units (3 sonnet writers, disjoint files)

**W11-A: D6, entry points and `local-common.sh`**

Files to delete:
- `.ci/lib/local-common.sh`
- `.ci/scripts/test/gates/test-run-sh.sh`

Files A owns:
- **The bare runner.** A new `.ci/rediacc_ci/tests/gates/run_bare.py`, stdlib only:
  - `python3 -m rediacc_ci.tests.gates.run_bare <module>` imports the module.
  - It runs every `test_*(gate)` against a fresh `harness.Harness(module, name)`.
  - It applies the two teardown refusals from `conftest.py:44-54`: a recorded `no()` without `tally_finish`, and zero passes.
  - It refuses a module with zero tests, or a test that takes any argument other than `gate`.
  - It exits 1 on any failure.
  - Its own pytest test proves it imports with `sys.modules['pytest'] = None`.
- `.github/workflows/ci.yml:627`: change to `PYTHONPATH=.ci python3 -m rediacc_ci.tests.gates.run_bare rediacc_ci.tests.gates.test_gate_run_sh`.
- `tests/gates/test_gate_run_sh.py`:
  - `LANE_SNIPPET` becomes `PYTHONPATH=.ci python3 -m rediacc_ci.core.local_common lane-decide`.
  - The `LOCAL_COMMON` body-inspection control reads `gate_lane_should_route` in `core/local_common.py` instead.
- `tests/gates/test_gate_plant_proofs.py` (retarget its real bash subject) and `quality/plant_proofs.py` if a vacuity floor fires.
- `.ci/rediacc_ci/core/local_common.py`:
  - A new composite verb `prepare-cli`: `check_node_version(toolchain.node_floor())`, then `ensure_deps`, `ensure_packages_built`, `ensure_cli_built`, `ensure_renet_built`, stopping at the first failure.
  - Consider importing `core.devbox` lazily (`:65`) if the timing budget needs it.
- `rdc.sh`:
  - Line 18 becomes inline `log_{info,warn,error,step}` with the same glyphs, tty/NO_COLOR rule and `echo -e`.
  - Move the python3 check from `:39-43` above the `--native` branch, so it covers both paths.
  - Lines 48 and 72-75 become one `PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" python3 -m rediacc_ci.core.local_common prepare-cli >&2`.
  - No `export`. Stay at or under 185 lines.
- `.ci/rediacc_ci/native.py:134-160`: the `_PREPARE_PROGRAM` bash becomes in-process `local_common` calls.
- `.ci/rediacc_ci/setup/bridge.py:35-40`:
  - The PRELUDE drops `local-common.sh` (and drops `toolchain.sh` too if `constants.sh` does not need it).
  - Add in-process routing for local-common function names, mirroring `_devbox_words`. That includes `check_node_version "$NODE_VERSION_MIN"`, resolved through `toolchain.node_floor()`.
  - **Keep the `bridge.call("<name>"` spellings** at `.ci/rediacc_ci/setup/machine.py:265,325,359,361,373,381` and `.ci/rediacc_ci/dev/www.py:48,54`. The in-flight `.ci/rediacc_ci/quality/setup_idempotency.py:684` regex and `.ci/rediacc_ci/setup/port_parity.py:399` both match those tokens.
- `.ci/media/media-entry.sh:50`:
  - Inline `log_*` (`log_debug` included, gated on `DEBUG=true`).
  - Add three wrappers: `ensure_deps`, `ensure_packages_built`, `check_node_version`, each calling `python3 -m rediacc_ci.core.local_common <verb>`.
  - Check every call site in `tutorials.sh` and `bridge.sh` that relied on the bash `exit 1` inside the function.
- `.ci/rediacc_ci/security/rdc_sh_env_check.py`: the fixture swaps the stub `local-common.sh` for a PATH-shimmed `python3` that no-ops `-m rediacc_ci.core.local_common`.
- Shadow drivers lose their bash halves: `core/local_common_shadow_driver.py`, `core/local_common_actions_shadow_driver.py`, `.ci/rediacc_ci/dev/shadow_driver.py:135-140,208`, `.ci/rediacc_ci/setup/shadow_driver.py:137`.
- `tests/test_core_local_common.py`: switch to `diff.twin_call` and drop the sourcer-list assertion at `:294-296`.
- `scripts/gates/check-bootstrap-idempotency.ts:56` and `scripts/gates/check-native-rebuild.ts:91`: point them at `def ensure_deps` in `core/local_common.py`. If they cannot be made non-vacuous, report them for retirement.
- `.ci/rediacc_ci/core/devbox.py:1870`: bind from `<root>/.devcontainer` directly. This is a Rule-T fix and needs its own test.
- Tests: `test_native.py`, `test_dev_www.py`, `test_setup_*.py`, `test_security_rdc_sh_env_check.py`, `test_core_devbox.py`, `gates/test_gate_media_entry.py` if it moves.

**W11-B: D3, `common.sh` and gh-retry**

Files to delete:
- `.ci/scripts/lib/common.sh` (last, gated, see 11.4).

Files B owns:
- `.ci/rediacc_ci/core/gh_retry.py`: add `main()`.
  - Usage: `python3 -m rediacc_ci.core.gh_retry <what> -- <gh args>`.
  - Success: print stdout with trailing newlines stripped (parity with `$(...)`) and exit 0.
  - Each transient retry: one warn line.
  - Final failure: an error line `<what>: gh failed after N attempts (last exit rc)`, gh's last stderr indented 4 spaces on stderr, exit 1.
  - Tests go in `tests/test_ci_gh_retry.py`.
- `.github/workflows/cd-v2.yml:716-718,734-735` and `.github/workflows/promote-stable.yml:169-175`: point both at the verb. Keep `2>&1 >/dev/null` and the `grep -qi 'release not found'`.
- Rule-T fixes, each with its own test and golden handling:
  - `.ci/rediacc_ci/version/bump.py:351` and `.ci/rediacc_ci/release/update_homebrew_tap.py:555`: drop `common.sh` from the sources they require.
  - `.ci/rediacc_ci/release/mark_production.py:55-80` and `.ci/rediacc_ci/housekeeping/retry_failed_runs.py:70-100`: always use the `rediacc_ci.log` world and delete the fallback world. Re-record the affected golden rows with `--source port` and a reason.
- `.ci/docker/service/env.sh:14`: source `.ci/config/well-known.generated.sh` directly (it needs `WK_ADMIN_EMAIL_DEFAULT`, `:47`) and inline `log_step`/`log_info`. Update `core/service_shadow_driver.py` and `tests/test_core_service.py` for the sandbox.
- `.ci/media/tools/upload-r2.sh:62`: inline `log_*` and `require_{cmd,var,file}`, and source `well-known.generated.sh` (it needs `WK_MEDIA_ORIGIN`).
- `.ci/media/verify.sh`, plus its Python port preludes `.ci/rediacc_ci/tests/gates/media_verify.py:160` and `.ci/rediacc_ci/tests/gates/test_gate_media_pool.py:182`: replace the `source common.sh` with an inline `set -euo pipefail` and `log_*` prelude. Comments at `:207-229,462`; `.ci/rediacc_ci/tests/gates/test_gate_media_venv.py:23`.
- Freeze, then convert to goldens: `tests/test_core_common.py`, `test_log.py`, `test_proc.py`, `core/common_stub_shadow_driver.py` and its test, `test_quality_renet_types.py`.
- The vestigial-copy sweep: every test file in 11.1 item 3 that is not W7's, plus `.ci/rediacc_ci/tests/ops_cf_harness.py:193`. Guard each copy behind `diff.regolden_mode(TWIN) == "bash"`, or drop it.
- Two gates that name `common.sh`:
  - `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py:114`: retarget to a live subject.
  - `.ci/rediacc_ci/quality/silent_failure_patterns.py:21,248`: the remedy text points at a deleted helper; repoint it to `python3 -m rediacc_ci.core.common r2-count-objects`.
- Later, after W7 commits: W7's test files in the sweep.

**W11-C: D2 toolchain and D4 elite shims**

No files deleted; the three elite files are rewritten in place as shims.

Files C owns:
- `.github/actions/setup-node-npm/action.yml:34-35`: `pin="$(PYTHONPATH=.ci python3 -m rediacc_ci.core.toolchain pin npm)"`.
  - Precedent that python3 works in the windows and mac matrix jobs: `.github/workflows/ci-build-cli.yml:109,114`.
- `.github/workflows/ci-quality.yml:247-248,2206-2207,2447-2448,2590-2591`: `... toolchain pairs >> "$GITHUB_ENV"` and `... toolchain report`. Comments at `:244,1791`.
- `.ci/rediacc_ci/quality/lockfile.py:512,684` (the needle and `FIXTURE_COMPOSITE`) and its test.
- `.ci/rediacc_ci/core/run_verbs.py:496,539` (hint text, optional).
- `.ci/scripts/infra/{ci-pull-images,ci-start-elite,ci-stop-elite}.sh`: freeze, then replace each body with one effective line, so the lead can list it as `shim:`:
  ```
  PYTHONPATH="${BASH_SOURCE[0]%/*}/../..${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.infra.<module> "$@"
  ```
  Keep the executable bit; the breakpoint scripts test `-x` (`.ci/breakpoint/scripts/start-origin.sh:88-106`, `.ci/breakpoint/scripts/pull-service-images.sh:38-59`, `.ci/breakpoint/scripts/stop-breakpoint.sh:240`).
- `tests/test_infra_ci_{pull_images,start_elite,stop_elite}.py`: switch to `twin_call`, salvage the `TWIN.read_text` and `bash -n` cases per DB16, and add shim-contract tests:
  - one effective line;
  - names an importable module;
  - run from `/tmp` with no `GITHUB_TOKEN`, `ci-pull-images.sh` exits 1 with the port's refusal on stderr.
- `tests/test_twin_goldens.py` and `tests/differential.py`/`regolden.py`: a `SHIMMED_TWINS` carve-out. In it, the blob check is replaced by a shim-shape assertion, and `--source bash` is refused.

### 11.4 Order

1. **Freeze first (A, B and C in parallel, before any deletion or body edit).**
   - A: `PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden .ci/scripts/test/gates/test-run-sh.sh --source bash --reason "B3 freeze (W11)"`. This routes through `gates/test_twin_parity.py` and must run while `local-common.sh` exists. Then `regolden .ci/lib/local-common.sh --source bash -k <new cases>`, which extends `lib.local-common.jsonl` without touching W8's 18 lane records.
   - B: `regolden .ci/scripts/lib/common.sh --source bash --reason ...`. Run it module by module or with `-k`. `modules_naming` (`.ci/rediacc_ci/tests/regolden.py:38-51`) matches the basename `common.sh`, which also hits every `local-common.sh` module. Check `git diff --stat` so that only `lib.common.jsonl` is new.
   - C: `regolden .ci/scripts/infra/ci-{pull-images,start-elite,stop-elite}.sh --source bash`.
2. **Repoint (in parallel).** A builds the bare runner, `rdc.sh`, the bridge, `media-entry.sh` and native. B does gh_retry and the workflows, the four Rule-T readers, env.sh, upload-r2.sh and verify.sh. C does the toolchain sites and the shims.
3. **A deletes** `local-common.sh` and `test-run-sh.sh`.
4. **B deletes `common.sh`**, gated on all three: W7 committed, A's deletion done, and C's `ci-pull-images.sh` shim in place. B then sweeps the vestigial copies, W7's tests included.

### 11.5 Verification per unit

Prefix: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q -n 16`. Every unit also runs `test_twin_goldens.py`, `gates/test_twin_parity.py` and ruff.

**W11-A**
- Tests: `test_core_local_common.py`, `gates/test_gate_run_sh.py`, the new `test_run_bare`, `test_native.py`, `test_setup_*.py`, `test_dev_www.py`, `test_core_devbox.py`, `test_security_rdc_sh_env_check.py`, `gates/test_gate_media_entry.py`, `gates/test_gate_plant_proofs.py`.
- Gates: `npm run check:ci-rdc-native check:ci-rdc-sh-env check:ci-scope-scripts-reachability check:ci-bootstrap-idempotency check:ci-plant-proofs`; also `npx tsx scripts/gates/check-native-rebuild.ts`.
- Bare-runner proof:
  - `env -i PATH=/usr/bin:/bin HOME="$HOME" bash -c 'PYTHONPATH=.ci python3 -m rediacc_ci.tests.gates.run_bare rediacc_ci.tests.gates.test_gate_run_sh'` exits 0 and takes well under 60 s (the job's `timeout-minutes: 5`).
  - The same run with pytest blocked passes.
  - The PR's `Entry Point (run.sh)` job is green on ubuntu-slim.
- `rdc.sh` live checks:
  - `./rdc.sh --help` exits 0, and stdout carries no `→`/`✓`: `./rdc.sh --help 2>/dev/null | grep -c '[→✓]'` returns 0.
  - `./rdc.sh config list -o json | python3 -m json.tool` (stdout is pure JSON).
  - `REDIACC_SKIP_MACHINE_ACTIVATION=1 ./rdc.sh --version` (the tutorial path).
  - Touch a package source: the next run rebuilds, the run after does not (stamp compatibility).
  - `PATH` without python3 gives a named error and exit 1.
  - Warm `time ./rdc.sh --version` five times before and after; the budget is at most +150 ms.
- Others:
  - `./run.sh setup --check` keeps the same rows, and exit 1 means only the pending-deps report (as in W8).
  - `./run.sh provision status`.
  - `bash -n .ci/media/media-entry.sh rdc.sh`.
- Count: -2 `.sh`.

**W11-B**
- Tests: `test_ci_gh_retry.py` cases:
  - success passthrough;
  - a 404 prints `release not found` with no retry;
  - a 5xx retries twice with injected sleep;
  - exit 1.
- More tests: `test_core_{common,ghx,service}.py`, `test_log.py`, `test_proc.py`, `test_version_bump.py`, `test_release_{update_homebrew_tap,mark_production}.py`, `test_housekeeping_retry_failed_runs.py`, `gates/test_gate_media_{pool,venv,r2,helpers}.py`, `gates/test_gate_swallowed_failures.py`. Then the **full `.ci` suite** after the deletion, because the copy sweep is only proven by a full run.
- Gates: `check:ci-gh-retry-reads` (read-only here; the floor at `.ci/rediacc_ci/quality/gh_retry_shell.py:1273` belongs to L1b), `check:ci-workflows`, `check:ci-swallowed-failures`, `check`, `check:ci-shell-format`.
- Live checks:
  - `GH_TOKEN=… PYTHONPATH=.ci python3 -m rediacc_ci.core.gh_retry "release lookup" -- release view v0.0.0-nope --repo rediacc/console`: exit is non-zero and stderr contains `release not found`.
  - The `pr list … --json number --jq length` form prints a number.
  - `PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --help` from a tree with no `common.sh`.
  - `.ci/scripts/test/gates/test-media-r2.sh`.
- The production proof is the next real `cd-v2` retry and `promote-stable` run (section 10.5 rule).
- Count: -1.

**W11-C**
- Tests: `test_core_toolchain.py`, `test_quality_lockfile.py`, `test_infra_ci_{pull_images,start_elite,stop_elite,env}.py`, `test_twin_goldens.py`.
- Gates: `check:ci-lockfile`, `check:ci-workflows`, `check:ci-breakpoint-drift`.
- Live checks:
  - `diff <(.ci/scripts/lib/toolchain.sh --env) <(PYTHONPATH=.ci python3 -m rediacc_ci.core.toolchain pairs)` is empty, and the same for report.
  - `bash -n` on the three shims.
  - `(cd /tmp && env -u GITHUB_TOKEN .ci/scripts/infra/ci-pull-images.sh)` exits 1 with the port's message.
- Live proof: a breakpoint dispatch with `services: onprem`, run by the operator.
- Count: 0.

### 11.6 Lead drains (L3; every W11 writer reports these and does not fix them)

- `language-policy-baseline.json` (`--write-baseline`):
  - drop `common.sh`, `local-common.sh` and `test-run-sh.sh`;
  - move `toolchain.sh` to `file:` with `BLOCKER: sourced by .ci/bootstrap.sh:87 before the Python toolchain exists and by .ci/scripts/test/gates/test-toolchain.sh on the bare runner`;
  - add the three elite files as `shim:` with `BLOCKER: path contract of the drift-locked .ci/breakpoint tree`;
  - add `deploy/upload-media-to-r2.sh` as `file:` (D7).
- Correct the stale BLOCKER texts for `well-known.generated.sh` (it names `common.sh`) and `ci-env.sh` (it names `ci-start-elite.sh` as a sourcer).
- Lower the shfmt floor (-3).
- `bash_lib_migration_complete.py`: drop the LIBS rows for `common.sh` and `local-common.sh`. `toolchain.sh` stays, so G2 can only shrink the gate; changing the box wording needs the operator.
- `.dead-bash-allowlist`, em-dash, secret-supply, inline-suppressions, python-types and python-env-registry: add `run_bare.py` and the `gh_retry` `main`.
- `shell-declared-commands-baseline`: `scripts/gates/check-shell-declared-commands.ts` scans only files that contain `lib/common.sh`, so it goes vacuous. Retire or retarget it (operator call).
- `.ci/scripts/ci/greenlight.cjs:80,214-513`: the `common.sh` closures.
- `.ci/rediacc_ci/quality/gh_retry_shell.py:74` (the stale `IMPLEMENTATION`) and the floor at `:1273`.
- `.ci/rediacc_ci/quality/setup_idempotency.py:257-278,738,806` (it reads `local-common.sh`).
- `scripts/ci-runner/manifest.ts:5039-5043`: point `gate-test:run-sh` at the bare entry or the pytest module. Also `:1491` and `:3534` (the `common.sh` paths).
- Then run `npm run gen:gates-lock`, `npx tsx scripts/gate-bind.ts --write` and `npx tsx scripts/gen/gen-docs.ts --write`.
- `lane-durations.json` (`battery:test-run-sh.sh`), `.ci/shadow/twin-parity.ledger.jsonl`, `trace_checker.cjs.fixture`.
- `.ci/README.md:113,136` tell authors to `source common.sh`; CLAUDE.md and TRAPS.md.

### 11.7 Risks

- **`rdc.sh` is user-facing.** These behaviours must not change:
  - stdout stays CLI-only, so `-o json` pipelines keep parsing;
  - `exec node` stays last (signals);
  - the `~/.local/bin/rdc` symlink rule;
  - the `--native` delegation;
  - the export allowlist.

  What does change:
  - python3 becomes required on every call, the same precedent as `run.sh:25-30`. It may be absent on Windows Git Bash; the moved python3 check names it.
  - The CLI process no longer inherits `CI_OS`, `CI_ARCH`, `CI_TEMP` and `LOCAL_*_DIR`. `packages/cli/src` reads none of them (grep found nothing), but diff the env dump from `rdc_sh_env_check` before and after anyway.
  - Each call costs about 0.1 s more; the timing budget above bounds it.
- **Deleting `common.sh` without the four reader fixes reds every build** (`bump.py`) and the release Homebrew step.
- **Shimmed twins conflict with the drift control and with `regolden --source bash`.** That is why the carve-out in 11.3 is needed.
- **`.ci/lib/` vanishes.** That makes the `.ci/rediacc_ci/core/devbox.py:1870` path fix, and the two TS gates that scanned that directory, load-bearing.
- **Media verbs:** a bash `ensure_deps` failure used to `exit` inside the function. A wrapper only returns non-zero, so a call site inside `if` or `||` behaves differently. Every call site needs a review.

## Remaining (operator)

The plan's only open decision is whether to run it as described. A few individual Rule T fixes will surface in B4 as `[?]` items with a default, the first being `assert_channel_for_event` failing open (`DEFAULT: fail closed`).

## 12. Closing the eight open boxes (read-only design, 2026-10-08, operator order "move them to the head of promoted and complete")

Every count below was measured on this tree with W11-B uncommitted. The B5 ports and the G2 gate fix are already done. What is left is about 8 bash files, one live drill run, the baseline deletion, two operator rulings (D8, D9) and the regeneration/tick pass. Nothing needs an operator-only power unless the CLI's ancestry check rejects the two override variables (see 12.2).

### 12.1 Measurements

- **`git ls-files '*.sh' | wc -l` = 106.** It becomes 105 once W11-B's deletion of `.ci/scripts/lib/common.sh` is staged.
- **Transient red, not a defect:** `check_language_policy.py` exits 1 right now with "1 NEW bash file(s): .ci/scripts/lib/common.sh". The deletion is unstaged, so `git ls-files` still lists the file, but the working-tree baseline already dropped it. It clears when W11-B is committed.
- **Libraries left under `.ci/scripts/lib`:** `blocker-validator.sh`, `emit-advisory.sh` and `toolchain.sh`. `check_bash_lib_ported.py` reports "3 librar(ies), 26 bash function(s): every one has a Python twin (18 by name, 8 through ALIASES)".
- **Goldens whose twin still exists:** `infra.ci-{pull-images,start-elite,stop-elite}` (shims, carved out by `.ci/rediacc_ci/tests/differential.py:727` `SHIMMED_TWINS`) and `test.gates.test-{blocker-golden-corpus,media-r2,runner-advice}`.
- **Not frozen yet:** there is no `lib.blocker-validator.jsonl` and no `lib.emit-advisory.jsonl`. The seams are `.ci/rediacc_ci/tests/test_core_blocker_validator.py:36` and `.ci/rediacc_ci/tests/test_core_advisory.py:19`.

### The 11 remaining baseline entries (working tree)

| Entry | Verdict | Evidence |
|---|---|---|
| `deploy/upload-media-to-r2.sh` | KEEP-BASH, `file:` (two effective lines) | Cross-repo caller `private/growth/video_pipeline/publish.py`. That repo is a separate gitignored GitLab repo (`.gitignore:81`), so this PR cannot change it. Its local caller is `packages/www/scripts/publish-tutorial-video-to-r2.ts:28`. |
| `infra/ci-{pull-images,start-elite,stop-elite}.sh` | KEEP, `shim:` | One-line `exec python3 -m rediacc_ci.infra.*` shims (W11-C, 1baf0b358). They are a path contract for the drift-locked breakpoint tree (section 10, row 2). |
| `lib/toolchain.sh` | KEEP-BASH, `file:` (D2) | `.ci/bootstrap.sh:87` sources it before Python exists. |
| `lib/blocker-validator.sh` | Not ported away yet | Nothing in production runs it any more: since ec431be68 `check_language_policy` validates in process. It survives only because tests read it: `.ci/rediacc_ci/tests/test_core_allowlist.py:126,153,680`, `.ci/rediacc_ci/tests/gates/test_gate_breakpoint_portability.py:40,452-472`, `.ci/rediacc_ci/tests/gates/test_gate_shadow_gate.py:71`, `.ci/rediacc_ci/tests/gates/test_gate_emit_advisory.py:37`, `.ci/rediacc_ci/tests/gates/test_gate_runner_advice.py:50`, `test_blocker_implementations.py`, plus the two gate twins. |
| `lib/emit-advisory.sh` | Not ported away yet | Its only real sourcer is `blocker-validator.sh`. The W7 note (0c05c1622) says the breakpoint tree sources it; that is wrong. `.ci/breakpoint/lib/breakpoint-blocker.sh:6` only mentions it in a comment. |
| `test/gates/test-blocker-golden-corpus.sh` | Twin with a port and a golden (ec431be68) | Also read as data by `.ci/rediacc_ci/quality/vendored_blocker_derivation.py:66` (`CORPUS_REL`) and `.ci/rediacc_ci/tests/gates/test_gate_shadow_gate.py:70`. Run by `scripts/ci-runner/manifest.ts:5169-5173`. |
| `test/gates/test-runner-advice.sh` | Twin with a port and a golden | Read by `.ci/rediacc_ci/tests/gates/test_gate_plant_proofs.py:47` (`DEBT_SUBJECT`) and `.ci/config/plant-proof-baseline.json`. Run by `scripts/ci-runner/manifest.ts:5195-5200`. |
| `test/gates/test-media-r2.sh` | Twin with a port and a golden | Run by `.ci/rediacc_ci/tests/gates/test_gate_media_docs.py:59` and `scripts/ci-runner/manifest.ts:5182`. It is the only remaining sourcer of `.ci/media/verify.sh` (`verify.sh`), so deleting it leaves `verify.sh` dead. |
| `test/lib/test-helpers.sh` | Library kept for its sourcers | Sourced by `test-toolchain.sh`, `media/verify.sh` and the two gate twins. `gates/test_gate_media_helpers.py` uses it as its subject. |

### Per box: what is done and what is left

- **A5 (Phase A acceptance).** Not run yet. In the dirty tree, `check:ci-hook-integrity` and `check:ci-guard-mention-anchoring` printed green verdicts ("51 guard(s) … refuse commands"); `check:ci-language-policy` is the transient red above.
  - **Left:** the full run listed in 12.4 step 2, after W11-B commits.
  - **"Before" wall time:** 294.65 s (plan section 1). `.ci/rediacc_ci/check_pytest.py:110` already notes that the same fixture "is 233s of test time now".
- **B1 (cutover).**
  - `assert-job-succeeded`, `detect-pointer-bump` and `initialize`: deleted in 6eb239b4d.
  - `run-legacy.sh`: deleted in 3bfab056e.
  - `common.sh`: W11-B, uncommitted. The only `source …lib/common.sh` lines left are frozen heredoc keys inside the `twin_streams` goldens (`.ci/rediacc_ci/tests/test_drills_lib.py:87`, `.ci/rediacc_ci/tests/test_quality_release_state.py:133,198`, `.ci/rediacc_ci/tests/test_quality_renet_types.py:114`).
  - **Left:** commit W11-B plus the integration writer's output. Then the box ticks.
- **B2 (port groups C and D-port).** Every PORT row in the inventory is GONE except three, and those three already have ports, so the remaining work is B3's. **Left:** none beyond B3, so B2 ticks with B3.
- **B3 (golden-then-delete).** **Left:** units U1, U2 and U3 below. The shimmed trio is closed by the `SHIMMED_TWINS` carve-out.
- **B5 (out-of-policy scripts).** Every port is done:
  - drills and ops: 50dd86fb0 and 882658c69;
  - `worktree.sh`: ec17cce72;
  - eslint-heap, the json generator and test-templates, backup-storage and page density: 7c9e38822.
  - No `scripts/drills`, `scripts/ops/*.sh` or `packages/json/*.sh` remain.
  - **Live proof so far:** the license drill ran live on the Ceph fleet on 2026-10-01, with all legs a-f and port 43/43 (47085176d, worklist #87037302). But `drills/license.py` changed after that run (68c262cbc, 1b5757eab, 15bf298bd, 532b17721), so the proof is stale.
  - `backup_roundtrip.py` and `backup_local_plane.py` (7c9e38822) have never run live.
  - CI's `ct-tests.yml` `test-drills` job (`:2837`, full-suite only) covers universe, transfer and backup (`:2880-2952`).
  - **Left:** one live run, in 12.2.
- **G1 (delete the baseline).** **Left:**
  - Delete the 8 files in U1-U3, then delete the baseline file. Deleting it is strict mode with no code change (`.ci/scripts/quality/check_language_policy.py:15,702-723`).
  - Allowlist the 5 survivors.
  - Fix the stale BLOCKER texts:
    - `constants.sh` cites `rdc.sh:17` and `scripts/dev/worktree.sh`. `rdc.sh` no longer sources it and `worktree.sh` is gone. The real sourcers are `.ci/media/media-entry.sh:49`, `.github/workflows/cd-deploy-account.yml:261` and `.github/workflows/ct-tests.yml:179`.
    - `well-known.generated.sh` names `common.sh`.
    - `ci-env.sh` names `ci-start-elite.sh`, which is now a shim.
    - `bootstrap.sh` cites `rdc.sh:41`; the line is now `rdc.sh:33`.
    - `test-toolchain.sh`'s reason ("pytest not on that runner") is false since W11-A's `run_bare.py`.
  - `.ci/rediacc_ci/tests/test_docker_run_in_image.py:446` reads the baseline file and will break when it is deleted.
  - Tick PLAN-tooling-transformation W1P6 (`:4186`) in the same commit.
- **G2 (bash-lib gate).**
  - Done: `log.py` is counted, class methods are recognised (`.ci/rediacc_ci/quality/bash_lib_migration_complete.py:64`), and the baseline is gone with 0 gaps (`:5`).
  - **Left:** remove the LIBS/PREFIXES/ALIASES rows for the two deleted libraries.
  - Literal retirement is impossible while `toolchain.sh` is KEEP. Section 10.7 says it needs an operator re-ruling (D9 below).
- **G3 (regenerate, correct the prose).**
  - The prose half is already clean. `CLAUDE.md` and `TRAPS.md` contain no oracle-as-spec text: the grep for "oracle" there hits only unrelated uses (`CLAUDE.md:153`, `docs/agent-reference/TRAPS.md:1076,1086,1667`).
  - Stale present-tense mentions of `.claude/oracles`, to fix:
    - `docs/ci-overhaul/12-remaining-work.md:102` ("must not 'finish the job' by removing them");
    - `.ci/rediacc_ci/quality/pipefail_grep_q.py:55`;
    - `scripts/data/doc-registry-preport.json:704-706` ("is kept as the differential").
  - The rest are past-tense history and can stay.
  - `.ci/breakpoint/lib/breakpoint-blocker.sh:3,30,45` cite the deleted validator, but the file is drift-locked. Leave it and record why.
  - **Left:** the regeneration commands in 12.4.

### 12.2 Live infrastructure: what was probed

Probe results:
- `virsh -c qemu:///system list --all` returns an empty table, so no VMs are defined.
- `virsh net-list` shows `default` and `renet11`, both active. `pool-list` shows `tmp`, active.
- `~/.renet/disks/ubuntu-24.04-minimal-cloudimg-amd64.img` exists, and so do `~/.renet/staging/.ssh/id_rsa` and `~/.config/rediacc/`.
- The user is in the `libvirt` and `docker` groups. `free -m` shows 35,452 MB available against the full fleet's 21,504 MB (`ops-vms.md`). There are 24 cores, and 149 GB is free on `/`.
- `REDIACC_ALLOW_CLUSTER_OPS` and `REDIACC_ALLOW_GRAND_REPO` are both set in this session's environment (names only checked).

What this means:
- **B5 is likely completable by an agent.** The two overrides are present, which matches the restart the operator did for #87037302 on 2026-10-01. The CLI's ancestry check is the one thing that could not be verified read-only.
- **Fallback if the ancestry check rejects them:** legs c-f and the headless drills still run. Legs a and b need the operator to restart the session with both variables exported, the same as on 2026-10-01.

The smallest honest path, run by one opus `ops-vms` agent in the background with no tracked-file edits:
1. `PROVISION_CEPH_CLUSTER=1 ./rdc.sh ops up` (about 40 min).
2. `./run.sh drill universe`, `./run.sh drill transfer`, `./run.sh drill backup`, `./run.sh drill license`.
3. Each drill again with `--selftest`; each of those must exit non-zero.
4. `PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_local_plane` (background), then `PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_roundtrip`.
5. `npm run check:ci-drill-verdicts`.
6. `./rdc.sh ops down`.

Record the exit codes and assertion counts on a worklist item.

Other live proofs that belong to other runs (section 10.5) and do not block these boxes: the release-path ports are proven by the next real `cd-v2`/`promote-stable` run, and the shims by a breakpoint dispatch.

### 12.3 Writer units

The integration writer owns `.ci/**`, `scripts/**` (except doc-registry), `package.json`, the workflows, `.ci/config` and `.ci/policy`. So U1-U3 start only after it reports and W11-B is committed. The B5 runner (U0) can start now because it edits nothing. At most 4 run at once.

**U0, B5 live drills (opus, the `ops-vms` agent).** Owns no files. Steps as in 12.2. Acceptance: every drill exits 0, every `--selftest` exits non-zero, `backup_roundtrip` exits 0, the fleet is torn down.

**U1, the BLOCKER chain (opus, because it retargets two gates).** Deletes 4 files: `lib/blocker-validator.sh`, `lib/emit-advisory.sh`, `test/gates/test-blocker-golden-corpus.sh`, `test/gates/test-runner-advice.sh`.
- **Freeze first, while all four exist:**
  - `PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden .ci/scripts/lib/blocker-validator.sh .ci/scripts/lib/emit-advisory.sh --source bash --reason "B3 freeze (section 12)"`
  - Check `git diff --stat`: only `lib.blocker-validator.jsonl` and `lib.emit-advisory.jsonl` should be new. `modules_naming` matches by basename (`regolden.py`), so use `-k` if other modules get pulled in.
  - Confirm `test_twin_goldens.py` passes for the two gate-twin goldens frozen in ec431be68.
- **Retarget:**
  - `.ci/rediacc_ci/quality/vendored_blocker_derivation.py:66,237,479,505`: read the corpus from the Python port's table in `gates/test_gate_blocker_golden_corpus.py` or its golden.
  - `.ci/rediacc_ci/tests/gates/test_gate_shadow_gate.py:70-71`: make the pilot pair `core.blocker_validator` or `core.allowlist` against `scripts/lib/blocker-validator.ts`.
  - `.ci/rediacc_ci/tests/gates/test_gate_breakpoint_portability.py:40,452-472`: run `check_subset` against `core/allowlist.py`'s pattern list (its copy is at `:69`).
  - `.ci/rediacc_ci/tests/test_core_allowlist.py:126,153,680` and `test_blocker_implementations.py`: replace the bash halves with goldens or delete them per DB16.
  - `gates/test_gate_emit_advisory.py`: retire it per DB16, or retarget to `log.py` and `advisory.py`.
  - `.ci/rediacc_ci/tests/gates/test_gate_runner_advice.py:50`; `.ci/rediacc_ci/tests/gates/test_gate_plant_proofs.py:47` (needs a new real subject).
  - Docstring and comment lines: `.ci/rediacc_ci/core/allowlist.py:6`, `.ci/rediacc_ci/security/audit.py:23`, `.ci/rediacc_ci/log.py:19-20`.
- **Report to the lead, do not edit:** `scripts/ci-runner/manifest.ts:5169-5200` (two `gate-test` entries), `plant-proof-baseline.json`, `.ci/config/lane-durations.json:294,296`, the LIBS/PREFIXES/ALIASES rows, the inline-suppressions row at `:672`, `.ci/policy/.runner-advice-allowlist:9`, `.ci/policy/.profiler-coverage-allowlist:9` and the allowlist header at `:47`.
- **Acceptance:**
  - `pytest -q -n 16 test_core_{blocker_validator,advisory,allowlist}.py test_blocker_implementations.py gates/test_gate_{blocker_golden_corpus,runner_advice,shadow_gate,breakpoint_portability,vendored_blocker_derivation,plant_proofs,emit_advisory}.py test_twin_goldens.py gates/test_twin_parity.py`
  - `npm run check:ci-vendored-blocker-derivation check:ci-plant-proofs check:ci-breakpoint-drift check:ci-bash-lib-ported`
  - The file count drops by 4.

**U2, the media seam (opus, because it decides the coverage probe).** Deletes `test/gates/test-media-r2.sh` and the then-dead `.ci/media/verify.sh`.
- **Freeze first:** confirm `test.gates.test-media-r2.jsonl`'s `twin_blob` matches with `test_twin_goldens.py`. If it does not, run `regolden .ci/scripts/test/gates/test-media-r2.sh --source bash --reason …` before the deletion.
- **Edits:**
  - `.ci/rediacc_ci/tests/gates/test_gate_media_docs.py:46,59`: pick the "one fast test" for coverage from a remaining subject.
  - `.ci/media/coverage.sh:70-76`: once the bash gate directory empties, measure through the Python port root only, and keep it non-vacuous.
  - Docstrings: `.ci/media/r2.sh:13`, `.ci/rediacc_ci/tests/gates/media_verify.py:1,126`, `.ci/rediacc_ci/tests/gates/media_verify_ext.py:1`.
  - `scripts/quality/check_gate_id_convention.py`, `.ci/rediacc_ci/tests/test_quality_dead_python.py:110`.
- **Report to the lead:** `scripts/ci-runner/manifest.ts:5182-5186`, `.ci/config/lane-durations.json:295`, the `doc-providers` media seam.
- **Acceptance:**
  - `pytest gates/test_gate_media_{docs,r2,pool,venv,helpers,portable}.py test_twin_goldens.py gates/test_twin_parity.py`
  - `bash -n .ci/media/*.sh`, `npm run check:ci-dead-bash`
  - The file count drops by 2.

**U3, `test-toolchain.sh` and `test-helpers.sh` (sonnet; the oracle is the existing pytest port). Operator decision D8, default: port.**
- **Step 1 (parallel with U1 and U2):**
  - `gates/run_bare.py`: supply a stdlib `tmp_path` (a fresh `tempfile.TemporaryDirectory()` as a `pathlib.Path`, removed afterwards). Keep the refusal for any other argument (`run_bare.py` docstring). Add a test for this.
  - Point `.github/workflows/ci.yml:630` at `PYTHONPATH=.ci python3 -m rediacc_ci.tests.gates.run_bare rediacc_ci.tests.gates.test_gate_toolchain`. The module takes `(gate, tmp_path)` at `:68,93,114`.
  - Delete `test-toolchain.sh`.
- **Step 2 (after U1 and U2):** `test-helpers.sh` has no sourcers left. Delete it, and retire or retarget `gates/test_gate_media_helpers.py` per DB16.
- **Report to the lead:** `scripts/ci-runner/manifest.ts:5073-5085` (`gate-test:toolchain`) and both allowlist entries.
- **Acceptance:**
  - `env -i PATH=/usr/bin:/bin HOME="$HOME" bash -c 'PYTHONPATH=.ci python3 -m rediacc_ci.tests.gates.run_bare rediacc_ci.tests.gates.test_gate_toolchain'` exits 0, and still exits 0 with pytest blocked.
  - `pytest test_run_bare* gates/test_gate_toolchain.py`
  - The file count drops by 2.
  - The Entry Point job is green on the PR.

**Expected count:** 105 → 97 (U1 −4, U2 −2, U3 −2).

**Operator decisions to put through `/ask`, with a default each:**
- **D8.** Port `test-toolchain.sh` and delete `test-helpers.sh`? Default: yes. The alternative is two `file:` entries whose reasons are no longer true.
- **D9.** G2 reworded to "retire with the last *retired* library; `toolchain.sh` (KEEP-BASH, D2) keeps its twin check"? Default: yes. Since W11-C the workflows read the Python `toolchain pairs/report` while `bootstrap.sh` reads the bash, and this gate is what keeps the two complete.

### 12.4 Order for the lead

1. **Now:** start U0 in the background. When the integration writer reports, commit W11-B plus its output, then `--plan-investigate` and `--plan-tick` B1 citing that commit and 6eb239b4d / 3bfab056e. Run `/ask` for D8 and D9.
2. **A5:** run the following, then tick A5 with the before and after times.
   - `pytest -q -n 16 .claude/rediacc_hooks/tests`
   - `test_guards_differential.py::test_the_differential_can_fail` (`:1112`), `test_bash_semantics.py`, `test_golden_drift.py`
   - `npm run check:ci-language-policy check:ci-hook-integrity check:ci-dead-python check:ci-guard-mention-anchoring`
   - `pytest gates/test_gate_docs_gen.py`
   - real events piped through `.claude/hooks/chain-head.sh`
   - `time` the guard differential, against the 294.65 s "before"
3. **Spawn U1, U2 and U3 step 1** (with U0, that is 4 live).
4. **After each unit, the lead runs** `--write-baseline`, the LIBS rows, `manifest.ts` removals, `lane-durations`, the plant-proof baseline and the shfmt / em-dash / inline-suppressions / secret-supply / dead-bash drains, then:
   - `npm run gen:gates-lock`
   - `npx tsx scripts/gate-bind.ts --write`
   - `npm run shard:place`
   - `npx tsx scripts/gen/gen-docs.ts --write`

   Commit each unit separately.
5. **U3 step 2,** then the same lead pass.
6. **G1:**
   - Allowlist `toolchain.sh` (`file:`), the three elite shims (`shim:`) and `upload-media-to-r2.sh` (`file:`), each with a BLOCKER.
   - Correct the 5 stale BLOCKER texts.
   - Fix `.ci/rediacc_ci/tests/test_docker_run_in_image.py:446`.
   - Delete `.ci/config/language-policy-baseline.json`; `check:ci-language-policy` must print "language policy STRICT".
   - Run `check:ci-suppression-liveness`.
   - Tick G1 and PLAN-tooling-transformation W1P6.
7. **G2 (per D9):** drop the two library rows, tick.
8. **G3:** the three stale-prose fixes. Show the empty grep for oracle-as-spec text in `CLAUDE.md` and `TRAPS.md`. Regenerate once more, then run `check:ci-{gates-lock,gate-bind,parity,plan-record}`.
9. **Final checks:** the full `.ci` pytest (`PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q -n 16 .ci/rediacc_ci/tests`), then `npm run ci`.
10. **Last ticks:** B2 and B3 (citing the U1-U3 commits) and B5 (citing U0's run). Each tick goes through `--plan-investigate` then `--plan-tick`, in the same commit as `plan-boxes.json`.
