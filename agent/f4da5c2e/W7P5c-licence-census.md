Status: measured
Owner: f4da5c2e (writer W7P5-c)
Date: 2026-09-09
Measured-At: 2026-09-09T18:14Z

# W7P5-c: the per-file deletion licence, measured

**NOTHING WAS DELETED.** This is the licence census and the prepared drain. Deletion is a
driver action gated on an operator sign-off that has not been given.

## 0. The licence, and what each condition was measured with

The box grants a per-file deletion licence on THREE conditions, all required:

1. **C1** a shadow ledger asserting `equivalence holds` at K=5 with >=2 distinct
   fingerprints;
2. **C2** the Python side LIVE (tracked entry point, registered as a `gate: true` leaf,
   green);
3. **C3** no tracked file referencing the twin's basename.

Commands, all run against the real tree at the timestamp above:

```sh
# C1, per ledger (81 tracked + 1 untracked at time of measurement)
for f in .ci/shadow/*.observations.jsonl; do
  p=$(basename "$f" .observations.jsonl)
  npx tsx scripts/lib/shadow-gate.ts --pair "$p" --assert --k 5; echo "$? $p"
done

# C2, per twin: the entry point is `check_<snake>.py` beside the twin, and it must be a
# `gate: true` leaf in scripts/ci-runner/gates.lock.json with a package.json key.

# C3, per twin: `git grep -I -n -F -- <basename>`, then every hit classified with
# Python `tokenize` + `ast` so a mention inside a MODULE DOCSTRING is not counted as a
# reference. This mattered enormously: see section 3.
```

## 1. Headline

| question | answer |
|---|---|
| bash quality twins carrying a shadow ledger | **77** of 82 tracked `.ci/scripts/quality/*.sh` |
| bash GATE TESTS carrying a shadow ledger | **0** of 149 |
| ledgers passing `--assert --k 5` | **81 of 82** (the one failure is the permanent carve-out) |
| twins licensed on ALL THREE conditions TODAY | **23** |
| twins waiting only on ledger accrual | **0** |

**The driver's expectation is refuted.** The schedule was assumed to be throughput-limited
by ledger accrual at K=5. It is not: **every ledger that exists already passes K=5**, and
was already passing before this session. Not one file in the census is waiting on a CI run.

The real constraint is **coverage, not accrual**: 149 bash gate tests (45,099 lines, 73% of
the duplicate-maintenance surface) have **no ledger at all**, and 5 quality gates have none
either. Recording a first ledger row needs a clean tree and a committed port; accruing to
K=5 needs five distinct specimen trees. Both are writer work, not merge-rate work.

## 2. Licensed TODAY: 23 files, 4,068 lines

All 23 satisfy C1, C2 and C3. All 23 npm keys resolve to the Python entry point, and 22 of
23 exit 0 when driven locally with `CI=true`.

```
.ci/scripts/quality/check-account-portal.sh
.ci/scripts/quality/check-account-probes.sh
.ci/scripts/quality/check-audit-coverage.sh
.ci/scripts/quality/check-autopilot-breakpoint-alignment.sh
.ci/scripts/quality/check-battery-clean-tree.sh
.ci/scripts/quality/check-ci-watch-recipe.sh
.ci/scripts/quality/check-cli-contract.sh
.ci/scripts/quality/check-compose-env.sh
.ci/scripts/quality/check-drill-verdicts.sh
.ci/scripts/quality/check-e2e-coverage.sh
.ci/scripts/quality/check-greenlight-closures.sh
.ci/scripts/quality/check-host-toolchain-coverage.sh
.ci/scripts/quality/check-lockfile.sh
.ci/scripts/quality/check-regions-sync.sh
.ci/scripts/quality/check-release-bump-skip.sh
.ci/scripts/quality/check-review-cap-coherence.sh
.ci/scripts/quality/check-rubric-calibration.sh
.ci/scripts/quality/check-setup-idempotency.sh
.ci/scripts/quality/check-shell-size.sh
.ci/scripts/quality/check-silent-failure-patterns.sh
.ci/scripts/quality/check-subscription-schema.sh
.ci/scripts/quality/check-tracked-sidecars.sh
.ci/scripts/quality/check-www-build-token.sh
```

**One caveat on `check-lockfile.sh`.** Its Python entry point exits 1 today:
`private/account/package-lock.json (npm@10 cannot resolve)`. The BASH TWIN FAILS
IDENTICALLY, so this is not a port defect; it is uncommitted state in the `private/account`
submodule. It does mean `check:ci-lockfile` cannot be green in a full CI run until that is
resolved, so if C2's "green in one full CI run" is read strictly, batch 1 is **22 files**
and `check-lockfile.sh` joins the next batch.

**Three of the 23 are registered as `ci: { kind: 'test' }` rather than `kind: 'step'`.**
`check:ci-autopilot-bp-align`, `check:ci-regions-sync` and `check:ci-release-bump-skip` are
driven by a gate test rather than a named workflow step. That is a legitimate second shape,
they are `gate: true`, and both harnesses have ALREADY been retargeted to the Python
(`test-autopilot-breakpoint-alignment.sh:36` sets `GATE=...check_autopilot_breakpoint_alignment.py`,
`test-regions-sync.sh:40` sets `SUT=...check_regions_sync.py`). Note the sequencing though:
two of those harnesses run inside `run-all.sh`, so the gate-test half of W7P5-c must not
delete them before their coverage moves.

## 3. Why the other 54 are blocked, and why it is NOT ledger accrual

C1 blocks exactly ONE file. C2 blocks 11. **C3 blocks 53.** The census table is section 6.

The C3 blockers are overwhelmingly **prose living in Python module docstrings** - the
"Ported from `X.sh`, which is NOT deleted; see INVARIANT 5" header every port carries, plus
the `DRIVEN, on this tree` evidence blocks that quote the twin's command line. Those are
inert and were classified as such. What remains after that are real references:

- `TWIN = ...` / `GATE_REL = ...` constants in differential tests that READ the twin;
- `.ci/scripts/test/gates/test-*.sh` harnesses still naming the bash gate;
- a handful of genuine executing call sites.

**One genuine executing call site found, and it is a live one:**

```
.github/workflows/autopilot.yml:252
  PR_NUMBER="$PR" .ci/scripts/quality/check-resolved-threads.sh >/dev/null 2>&1 || rc=$?
```

That is a workflow invoking the BASH gate, not the port, while `ci.yml:624` invokes the
Python. Both exist. Worth a driver decision independently of any deletion.

## 4. The prepared drain, first batch

The shape the box records: **delete a batch -> reseed in the same commit -> repeat.** A
port alone changes nothing; a deletion is a pure subtraction and the only legal reseed; a
new `.sh` is refused even when the total shrinks; a missing baseline is STRICT MODE.

**Baseline count confirmed at 515**, and the driver's note is right against the tree: it is
515 both in the worktree AND at HEAD, and the file is CLEAN (no diff). The plan's
"521 committed / 520 worktree" is stale.

`check_language_policy.py` is green today: `584 bash file(s) under .ci, .claude -- 515
frozen (shrink-only, none added), 69 exempt`. Its `covered` set equals its baseline set in
BOTH directions, verified by importing the gate's own `bash_corpus` / `exemption_for` /
`read_baseline`.

**Simulated drain, composition asserted rather than sizes compared:**

```
SIMULATED DRAIN: 515 -> 492
  ADDED side (must be empty): 0 []
  REMOVED side: 23
```

**The exact `.ci/config/language-policy-baseline.json` lines that come out** (line numbers
as of this measurement; the anchor is the string, not the number):

```
131:    ".ci/scripts/quality/check-account-portal.sh",
132:    ".ci/scripts/quality/check-account-probes.sh",
134:    ".ci/scripts/quality/check-audit-coverage.sh",
135:    ".ci/scripts/quality/check-autopilot-breakpoint-alignment.sh",
137:    ".ci/scripts/quality/check-battery-clean-tree.sh",
141:    ".ci/scripts/quality/check-ci-watch-recipe.sh",
143:    ".ci/scripts/quality/check-cli-contract.sh",
147:    ".ci/scripts/quality/check-compose-env.sh",
154:    ".ci/scripts/quality/check-drill-verdicts.sh",
155:    ".ci/scripts/quality/check-e2e-coverage.sh",
162:    ".ci/scripts/quality/check-greenlight-closures.sh",
164:    ".ci/scripts/quality/check-host-toolchain-coverage.sh",
167:    ".ci/scripts/quality/check-lockfile.sh",
180:    ".ci/scripts/quality/check-regions-sync.sh",
181:    ".ci/scripts/quality/check-release-bump-skip.sh",
188:    ".ci/scripts/quality/check-review-cap-coherence.sh",
192:    ".ci/scripts/quality/check-rubric-calibration.sh",
195:    ".ci/scripts/quality/check-setup-idempotency.sh",
196:    ".ci/scripts/quality/check-shell-size.sh",
197:    ".ci/scripts/quality/check-silent-failure-patterns.sh",
200:    ".ci/scripts/quality/check-subscription-schema.sh",
204:    ".ci/scripts/quality/check-tracked-sidecars.sh",
207:    ".ci/scripts/quality/check-www-build-token.sh",
```

Drop `check-lockfile.sh` (line 167) if batch 1 is 22 rather than 23; the drain is then
515 -> 493.

**Two cautions for whoever executes the drain.**

1. `--write-baseline` REWRITES the whole file. `.ci/config/language-policy-baseline.json`
   is a contended singleton, and another writer landing a port between the deletion and the
   reseed would be silently absorbed. The tool already refuses a reseed that would ADD a
   path (`would-grow`, `check_language_policy.py:486`), which closes the composition trap
   in the tool - but diff the OLD and NEW sets anyway and assert the ADDED side is empty.
2. **The gate does not check what its message says.** Its own text is explicit:
   "THIS GATE CHECKS STATE, NOT COMMIT BOUNDARIES: it reads `git ls-files` and nothing
   else, so a drain landing one commit AFTER the deletion goes green here and CI never
   learns the two were split." Riding the same commit is advice that keeps HEAD green
   between the two, not a property anything enforces. This is TRAPS entry 85's shape.

## 5. The blockers, each verified rather than inherited

### 5.1 `docs/agent-reference/TRAPS.md:2463` -> `JUDGMENT-ONLY`. CONFIRMED, and driven.

F3 at `.ci/rediacc_ci/quality/trap_registry.py:32-33` reads: "The disposition is either
>=1 pointer or the single token JUDGMENT-ONLY, and JUDGMENT-ONLY requires a non-empty
Residue." The entry's Residue is non-empty (three lines).

Not taken on faith. `TRAP_CORPUS` is an env seam (`trap_registry.py:222`), so the REAL gate
was driven against a modified COPY in the scratchpad, leaving `TRAPS.md` untouched:

| run | corpus | exit | output |
|---|---|---|---|
| control 0 | unmodified copy | **0** | `85 entries (floor 85), 39 JUDGMENT-ONLY, ... 23 file` |
| **the substitution** | `Enforced-By: JUDGMENT-ONLY` | **0** | `85 entries (floor 85), 40 JUDGMENT-ONLY, ... 22 file` |
| control A | `:149999` (deletion-equivalent dangling pointer) | **1** | `names file:...:149999, which does not resolve` |
| control B | `JUDGMENT-ONLY` + emptied Residue | **1** | `is JUDGMENT-ONLY with an empty Residue` |

Both controls fire, so the green is not vacuous. `JUDGMENT-ONLY` count moves 39 -> 40 and
live file pointers 23 -> 22, which is the shape a reader should expect.

**The substitution must REPLACE the pointer, not join it.** `trap_registry.py:577-579`
refuses a MIX: `Enforced-By: JUDGMENT-ONLY, gate:x` is a finding.

### 5.2 `.ci/config/language-policy-baseline.json`. CONFIRMED, count corrected.

`check_language_policy.py:917-935` returns 1 on a baselined bash file gone from the tree.
Baseline is **515**, in the worktree and at HEAD, clean. See section 4.

### 5.3 `.ci/scripts/test/gates/test-run-all-parallel.sh`. CONFIRMED.

231 lines. Hard-fails at lines 44-47:

```sh
RUNNER="$REPO_ROOT/.ci/scripts/test/run-all.sh"
if [[ ! -x "$RUNNER" ]]; then
    log_fail "$RUNNER is missing or not executable; this gate has nothing to prove"
fi
```

Registration to remove with it: `scripts/ci-runner/manifest.ts:6756-6761` and
`scripts/ci-runner/gates.lock.json:6703-6709`. **There is no `package.json` key** for
`gate-test:run-all-parallel` - it is a direct `run:` script - so only two of the usual
three wiring sites apply.

### 5.4 `.ci/rediacc_ci/tests/test_battery.py`. CONFIRMED, and STRONGER than briefed.

It is not merely that `TWIN` is `run-all.sh` (line 36). Line 198 READS THE TWIN'S SOURCE AT
TEST RUNTIME and executes a program extracted from it:

```python
twin_source = TWIN.read_text(encoding="utf-8")
start = twin_source.index('python3 - "$GATES_LOCK" "$1" <<\'CLASSIFY\'')
program = twin_source[twin_source.index("\n", start) + 1 : twin_source.index("\nCLASSIFY", start)]
```

Deleting `run-all.sh` does not leave a stale constant; it makes this test raise. The test's
own docstring states the claim it keeps honest ("the two runners must not decide isolation
separately"), so it cannot simply be dropped - the claim needs somewhere else to live.

### 5.5 `run-all.sh` is NOT licensed today, on condition 1.

Worth stating plainly because the box reads otherwise. **`run-all.sh` has NO shadow ledger
in any twin position** - no `.ci/shadow/*.observations.jsonl` names it in `old.cmd`. The
box's "the licence is granted at `27 == 27`" is not a K=5 shadow licence, and under the
box's own three conditions C1 fails outright. It is baselined at line 418.

### 5.6 The permanent carve-out `w7p2-stagingtag`. CONFIRMED, not re-recorded.

```
shadow-gate assert w7p2-stagingtag: 15 row(s), 12 distinct clean tree(s), 9 distinct finding set(s)
✗ tree 81c433126706 is DISQUALIFIED: a row against it recorded MISMATCH_FINDINGS
✗ tree a6bfc896de2b is DISQUALIFIED: a row against it recorded MISMATCH_FINDINGS
✗ tree baa7e1438139 is DISQUALIFIED: a row against it recorded MISMATCH_FINDINGS
✗ w7p2-stagingtag: equivalence NOT established
```

It clears the K=5 bar (12 trees) and the distinct-evidence bar (9 fingerprints) and still
fails, because three tree ids recorded `MISMATCH_FINDINGS`. `assertEquivalent`
(`scripts/lib/shadow-gate.ts:1131-1146`) disqualifies a tree id permanently: the id IS the
content of both implementations, so re-running cannot clear it. Needs a human sign-off line
in the deletion commit. **Nothing was re-recorded.**

`check-staging-tag-guard.sh` is also the ONLY one of the 77 twins still named as a
`gates.lock` leaf (`check:ci-staging-tag-guard`), so its Python side is not live either. It
fails C1, C2 and C3.

## 6. The full census, 77 rows

| bash twin | C1 ledger K=5 | C2 python live | C3 no live ref | licensed | what blocks it |
|---|---|---|---|---|---|
| `check-account-portal.sh` | Y | Y | Y | **YES** | - |
| `check-account-probes.sh` | Y | Y | Y | **YES** | - |
| `check-agent-browser-exit.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/quality/agent_browser_exit.py`, `.ci/rediacc_ci/tests/test_quality_agent_browser_exit.py` |
| `check-audit-coverage.sh` | Y | Y | Y | **YES** | - |
| `check-autopilot-breakpoint-alignment.sh` | Y | Y | Y | **YES** | - |
| `check-autopilot-no-bypass.sh` | Y | N | N | no | entry point untracked; 2 live ref(s): `.ci/scripts/test/gates/test-autopilot-no-bypass.sh`, `scripts/dev/secret-rename.py` |
| `check-battery-clean-tree.sh` | Y | Y | Y | **YES** | - |
| `check-branch.sh` | Y | N | N | no | not a gates.lock leaf; 3 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py`, `.ci/rediacc_ci/tests/test_quality_branch.py`, `.ci/scripts/test/gates/test-swallowed-failures.sh` |
| `check-ci-job-aggregation.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/tests/test_quality_ci_job_aggregation.py`, `.ci/scripts/test/gates/test-ci-job-aggregation.sh` |
| `check-ci-scans-tracked-paths.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/quality/ci_scans_tracked_paths.py` |
| `check-ci-watch-recipe.sh` | Y | Y | Y | **YES** | - |
| `check-claude-attribution.sh` | Y | N | N | no | not a gates.lock leaf; 3 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py`, `.ci/rediacc_ci/tests/test_quality_claude_attribution.py`, `.ci/scripts/test/gates/test-swallowed-failures.sh` |
| `check-cli-contract.sh` | Y | Y | Y | **YES** | - |
| `check-cli-doc-coverage.sh` | Y | Y | N | no | 2 live ref(s): `scripts/ci-runner/gates.lock.json`, `scripts/ci-runner/manifest.ts` |
| `check-command-tree.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_command_tree.py` |
| `check-commit-identity.sh` | Y | N | N | no | not a gates.lock leaf; 6 live ref(s): `.ci/config/commit-identity.json`, `.ci/rediacc_ci/quality/commit_identity.py`, `.ci/rediacc_ci/tests/test_quality_commit_identity.py` ... |
| `check-compose-env.sh` | Y | Y | Y | **YES** | - |
| `check-config-migrations.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_config_migrations.py` |
| `check-content-quality.sh` | Y | Y | N | no | 1 live ref(s): `scripts/gates/check-suppression-liveness.ts` |
| `check-control-vacuity.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/quality/control_vacuity.py`, `.ci/rediacc_ci/tests/test_quality_control_vacuity.py` |
| `check-dead-case-arms.sh` | Y | Y | N | no | 4 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_dead_case_arms.py`, `.ci/rediacc_ci/tests/gates/test_gate_media_helpers.py`, `.ci/scripts/test/gates/test-dead-case-arms.sh` ... |
| `check-devbox-exec.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_devbox_exec.py` |
| `check-devcontainer-scripts.sh` | Y | Y | N | no | 1 live ref(s): `.ci/config/plant-proof-baseline.json` |
| `check-drill-verdicts.sh` | Y | Y | Y | **YES** | - |
| `check-e2e-coverage.sh` | Y | Y | Y | **YES** | - |
| `check-editorconfig.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_editorconfig.py` |
| `check-gate-id-convention.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_gate_id_convention.py` |
| `check-git-op-conditionals.sh` | Y | Y | N | no | 5 live ref(s): `.ci/rediacc_ci/quality/git_op_conditionals.py`, `.ci/rediacc_ci/tests/test_quality_git_op_conditionals.py` |
| `check-go-deps.sh` | Y | Y | N | no | 9 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_go_deps_probe_failure.py`, `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py`, `.ci/scripts/test/gates/test-go-deps-probe-failure.sh` ... |
| `check-go-module-sync.sh` | Y | Y | N | no | 2 live ref(s): `.ci/scripts/test/gates/test-go-module-sync.sh` |
| `check-go-tool-path.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/gitx.py` |
| `check-greenlight-closures.sh` | Y | Y | Y | **YES** | - |
| `check-hook-integrity.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/tests/test_quality_hook_integrity.py`, `.claude/rediacc_hooks/tests/test_dispatch.py` |
| `check-host-toolchain-coverage.sh` | Y | Y | Y | **YES** | - |
| `check-label-inventory.sh` | Y | Y | N | no | 9 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_label_inventory.py`, `.ci/rediacc_ci/tests/gates/test_gate_review_labels.py`, `.ci/rediacc_ci/tests/test_quality_label_inventory.py` ... |
| `check-label-references.sh` | Y | Y | N | no | 6 live ref(s): `.ci/rediacc_ci/quality/label_references.py`, `.ci/rediacc_ci/tests/gates/test_gate_label_references.py`, `.ci/rediacc_ci/tests/test_quality_label_references.py` ... |
| `check-lockfile.sh` | Y | Y | Y | **YES** | - |
| `check-mutate-check.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_mutate_check.py` |
| `check-no-app-admin-perm.sh` | Y | Y | N | no | 4 live ref(s): `.ci/rediacc_ci/quality/workflows.py`, `.ci/rediacc_ci/tests/test_quality_no_app_admin_perm.py`, `.ci/scripts/quality/check-workflows.sh` ... |
| `check-no-otlp-creds.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_no_otlp_creds.py` |
| `check-npmrc.sh` | Y | Y | N | no | 2 live ref(s): `.ci/scripts/quality/check_ci_gate_prerequisites.py`, `scripts/ci-runner/run.ts` |
| `check-peer-deps.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_peer_deps.py` |
| `check-pipefail-grep-q.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_pipefail_grep_q.py` |
| `check-plan-housekeeping.sh` | Y | Y | N | no | 5 live ref(s): `.ci/config/plan-lifecycle.json`, `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py`, `.ci/scripts/quality/check_policy_inventory.py` |
| `check-pool-writer-safety.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_pool_writer_safety.py` |
| `check-pr-description.sh` | Y | N | N | no | not a gates.lock leaf; 2 live ref(s): `.ci/rediacc_ci/tests/test_quality_pr_description.py`, `.github/workflows/ci-quality.yml` |
| `check-probe-parity.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_probe_parity.py` |
| `check-profiler-coverage.sh` | Y | Y | N | no | 4 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_profiler_coverage.py`, `.ci/rediacc_ci/tests/test_quality_profiler_coverage.py`, `.ci/scripts/quality/check_policy_inventory.py` ... |
| `check-python-lint.sh` | Y | Y | N | no | 6 live ref(s): `.ci/rediacc_ci/setup/tools.py`, `.ci/rediacc_ci/tests/test_core_dockerx.py`, `.ci/rediacc_ci/tests/test_quality_python_lint.py` ... |
| `check-regions-sync.sh` | Y | Y | Y | **YES** | - |
| `check-release-bump-skip.sh` | Y | Y | Y | **YES** | - |
| `check-release-key-canonical.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_release_key_canonical.py` |
| `check-release-signing-coverage.sh` | Y | Y | N | no | 2 live ref(s): `.ci/scripts/build/build-linux-pkg.sh` |
| `check-release-state.sh` | Y | N | Y | no | not a gates.lock leaf |
| `check-renet-tier-map.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/tests/test_quality_renet_tier_map.py` |
| `check-renet-types.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_renet_types.py` |
| `check-resolved-threads.sh` | Y | N | N | no | not a gates.lock leaf; 5 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py`, `.ci/rediacc_ci/tests/test_quality_resolved_threads.py`, `.ci/scripts/test/gates/test-swallowed-failures.sh` ... |
| `check-review-cap-coherence.sh` | Y | Y | Y | **YES** | - |
| `check-review-comments.sh` | Y | N | N | no | not a gates.lock leaf; 11 live ref(s): `.ci/rediacc_ci/quality/review_report_replies.py`, `.ci/rediacc_ci/tests/gates/test_gate_review_status.py`, `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py` ... |
| `check-review-report-replies.sh` | Y | N | N | no | not a gates.lock leaf; 9 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_review_status.py`, `.ci/rediacc_ci/tests/test_blocker_implementations.py`, `.ci/rediacc_ci/tests/test_quality_review_report_replies.py` ... |
| `check-review-turn-capacity.sh` | Y | Y | N | no | 3 live ref(s): `.ci/rediacc_ci/quality/control_vacuity.py`, `.ci/rediacc_ci/tests/test_quality_review_turn_capacity.py`, `.ci/scripts/quality/check-control-vacuity.sh` |
| `check-rubric-calibration.sh` | Y | Y | Y | **YES** | - |
| `check-scope-scripts-reachability.sh` | Y | Y | N | no | 2 live ref(s): `.ci/rediacc_ci/quality/scope_scripts_reachability.py`, `.ci/rediacc_ci/tests/test_quality_scope_scripts_reachability.py` |
| `check-script-exec-bit.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/tests/test_quality_script_exec_bit.py` |
| `check-setup-idempotency.sh` | Y | Y | Y | **YES** | - |
| `check-shell-size.sh` | Y | Y | Y | **YES** | - |
| `check-silent-failure-patterns.sh` | Y | Y | Y | **YES** | - |
| `check-staging-tag-guard.sh` | N | N | N | no | ✗ tree 81c433126706 is DISQUALIFIED: a row against it recorded MISMATC; entry point untracked; 5 live ref(s): `.ci/rediacc_ci/tests/test_quality_staging_tag_guard.py`, `.github/workflows/ci-quality.yml`, `package.json` ... |
| `check-submodule-branches.sh` | Y | N | N | no | not a gates.lock leaf; 10 live ref(s): `.ci/legacy/run-legacy.sh`, `.ci/rediacc_ci/tests/gates/test_gate_shell_counter_increment.py`, `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py` ... |
| `check-subscription-schema.sh` | Y | Y | Y | **YES** | - |
| `check-swallowed-failures.sh` | Y | Y | N | no | 3 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py`, `.ci/rediacc_ci/tests/test_quality_swallowed_failures.py`, `.ci/scripts/test/gates/test-swallowed-failures.sh` |
| `check-toolchain-env-dockerfile-sync.sh` | Y | Y | N | no | 1 live ref(s): `.ci/rediacc_ci/quality/toolchain_pins.py` |
| `check-toolchain-pins.sh` | Y | Y | N | no | 4 live ref(s): `.ci/rediacc_ci/quality/host_toolchain_coverage.py`, `.ci/rediacc_ci/quality/toolchain_pins.py`, `.ci/scripts/quality/check-host-toolchain-coverage.sh` |
| `check-tracked-sidecars.sh` | Y | Y | Y | **YES** | - |
| `check-trap-registry.sh` | Y | Y | N | no | 3 live ref(s): `.ci/rediacc_ci/tests/gates/test_gate_trap_registry.py`, `.ci/rediacc_ci/tests/test_quality_trap_registry.py`, `.ci/scripts/test/gates/test-trap-registry.sh` |
| `check-workflows.sh` | Y | Y | N | no | 7 live ref(s): `.ci/config/bws-unrequested.json`, `.ci/rediacc_ci/quality/workflows.py`, `.ci/rediacc_ci/tests/gates/workflow_rule.py` ... |
| `check-www-build-token.sh` | Y | Y | Y | **YES** | - |

## 7. Corrections to the planning figures

Re-measured against the tree. The magnitude is right; the attributions are not.

| plan claim | measured | note |
|---|---|---|
| 62,233 lines duplicate-maintained | **61,754** | 140 gate tests + all 82 quality gates |
| 141 of 149 gate tests have a Python replacement | **140 of 149** | name-matched `test-x.sh` -> `test_gate_x.py` |
| 43,510 lines of gate tests | **43,031** (140) / **45,099** (all 149) | |
| 75 of 77 quality gates, 18,723 lines | **18,723 is ALL 82** quality gates | the 77 LEDGERED twins are 18,366 lines |
| baseline 521 committed / 520 worktree | **515 both, clean** | driver's note is correct |

The nine bash gate tests with no name-matched Python counterpart:
`test-autopilot-breakpoint-alignment.sh`, `test-autopilot-no-bypass.sh`,
`test-ci-job-aggregation.sh`, `test-commit-identity.sh`, `test-gate-paths-exist.sh`,
`test-go-module-sync.sh`, `test-plan-housekeeping.sh`, `test-regions-sync.sh`,
`test-toolchain.sh`.

The five quality gates with no ledger: `announce-gate-skips.sh`, `browser-smoke.sh`,
`page-density.sh`, `run-external-gate.sh`, `typecheck-workers.sh`.

## 8. Instrument controls

Every green above was checked against a planted red first.

- **`assertEquivalent` can fail on tree count.** A real green ledger truncated to 4 rows in
  the scratchpad: `4 distinct tree(s) carry an EQUIVALENT row; 5 are required`, exit 1.
- **`assertEquivalent` can fail the distinct-evidence rule.** The same 5 rows with every
  fingerprint forced equal: `all 5 counted tree(s) produced the same finding fingerprint`,
  exit 1.
- **Unplanted, the same pair returns exit 0.** Plants lived only in the scratchpad; no
  ledger in `.ci/shadow/` was modified.
- **The trap-registry seam can fail**, two ways, section 5.1.
- **The C2 probe was wrong once and was fixed, not believed.** Its first form looked for
  `.ci/rediacc_ci/quality/<mod>.py` as a `gates.lock` leaf and returned 6/77, which reads
  like a catastrophic finding. The leaf is actually the `check_<snake>.py` entry point
  beside the twin (the `_cipath` routing landed in `aaba93b29`). Corrected: 66/77.
- **The C3 probe was wrong twice.** It first counted Python DOCSTRINGS as code (0/77
  clean), then missed `#` comments in `.npmrc`, `Dockerfile`, `.toml` and `//` in `.jsonc`
  (22/77). Final form uses `tokenize` + `ast`, with two controls: the executing call site
  at `autopilot.yml:252` must stay LIVE (it does) and `.npmrc:1` must become inert (it
  does). 24/77 clean.
- **A conservative `-P` execution-context sweep** over all 23 licensed twins surfaced 12
  apparent invocations; every one was AST-confirmed to sit inside a docstring or comment.

## 9. Reproducing this census

The scripts live in the session scratchpad rather than in the repo. They were deliberately
NOT added under `.ci/rediacc_ci/tests/`: a non-test module there risks a red from the new
`dead_python` gate and from pytest collection, which is a cost the driver did not ask me to
pay. If the census should be re-run every merge, that is worth reconsidering as a tracked
tool, and it is the driver's call.

```
/tmp/claude-1000/-home-developer-console/f4da5c2e-8ce0-4880-939c-fa85f310fc66/scratchpad/
  assert.tsv     one row per ledger: exit code, pair, summary line, first refusal
  census1.py     ledger -> bash twin, from every row's old.cmd
  census2.py     joins C1, the gates.lock leaves and the baseline
  refs.py        first C3 attempt, kept because it shows the docstring trap
  refs3.py       C3 final form: tokenize + ast, with its two controls asserted inline
  census.json    the full 82-row artifact behind section 6
  licensed.txt   the 23 twins
  TRAPS-*.md     the four trap-registry corpora from section 5.1
  ctrlA/B.jsonl  the two planted ledgers from section 8
```
