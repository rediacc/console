# PLAN: a renet change triggers the tests that exercise it, locally and at push, from one map

Status: executing
Depends-On: no-dep -- every mechanism it extends (ci:quick, vm:check, the push guards, the Stop hook, the CI scope engine) is already on this branch
Owner: d778be9d
Updated: 2026-10-30
Priority: P1 -- a renet change in pkg/license or pkg/functions can be committed and pushed with no go test, and ceph, k8s and migrate changes have no local trigger at all
Concurrency: parallel
Owns: agent/plans/PLAN-renet-change-test-triggers.md, .ci/config/renet-test-map.json, .ci/config/proof-tiers.json, .ci/rediacc_ci/proof/**, .ci/rediacc_ci/tests/proof/**, .ci/rediacc_ci/tests/test_renet_test_map*.py, scripts/vm-check/**, .ci/rediacc_ci/vmcheck/**, scripts/ci-runner/manifest.ts, scripts/gates/check-renet-test-map.ts, scripts/gates/check-renet-chunkstore-unit.ts, .github/scripts/scope-map.cjs, .github/scripts/__tests__/scope-map*, .claude/rediacc_hooks/guards/block_renet_untested_push.py, .claude/rediacc_hooks/guards/test-block_renet_untested_push.py, .claude/rediacc_hooks/tests/goldens/block_renet_untested_push.jsonl, .claude/hooks/stop/wl_renettests.py, .claude/agents/renet-dev.md, .claude/agents/ops-vms.md, .claude/agents/e2e-local.md, .claude/agents/licensing-ops.md, private/renet/CLAUDE.md, docs/agent-reference/local-env.md, docs/agent-reference/ci-gates.md, docs/agent-session-playbook.md, .ci/rediacc_ci/drills/upgrade_converge.py
First-Seen: 2026-10-30
Worklist: #aea9d782, PR-TASK 9f92c43e

## Finding

Investigation 2026-10-30 (two read-only surveys):
- No local mechanism requires renet `go test`. `ci:quick` runs only `check:ci-renet` (gofmt, golangci-lint, govulncheck; `scripts/ci-runner/manifest.ts:3879`), the tier-map tests (`:3953`) and `go test ./pkg/chunkstore/...` (`:4113`); the first full Go run is CI `test-renet-go` after the push (`.github/workflows/ct-tests.yml:2526`).
- `vm:check --changed` maps every renet path to one side (`.ci/config/proof-tiers.json:6-17`) and always runs the same single-worker battery (`vm_check.py:1336-1377`), so a licence, functions or migrate change gets a VM proof that never exercises it; ceph, kube, migrate and multi-VM suites (`packages/e2e-tests/tests/{ceph,kube,migrate}`) have no local trigger.
- `block_vm_unverified_push.py:27` leaves submodule pushes out of scope, and `_test.go` and `tests/**` are excluded (`proof-tiers.json:57-70`).
- The Stop hook asks for nothing renet-specific before a commit; the CI scope engine (`.github/scripts/scope-map.cjs:204-249`) selects all 9 VM jobs for any renet change.
- `.claude/` carries 12 stale facts (the 12 are distinct facts; several span more than one line, so the list below names 15 file:line entries, a range counted once, in 8 files) about the deleted `nolicense` build, `bin/enforce`, `RDC_RENET_LICENSE` and `REDIACC_SKIP_MACHINE_ACTIVATION` (ops-vms.md:31-32, e2e-local.md:46, licensing-ops.md:49,58,71,73-74, private/renet/CLAUDE.md:17,163, docs/agent-reference/local-env.md:59,80,141-157, ci-gates.md:141, agent-session-playbook.md:59,90, upgrade_converge.py:63), and no agent covers renet Go development.

## Design

Operator rulings ASKED:2026-10-30 (four answers): Go tests by a path map with a receipt at push; area-mapped vm:check; a renet-dev agent; one plan built now.

1. One map, `.ci/config/renet-test-map.json`, owns every renet path rule ("one map" means one path-to-consequence source, not one file for every field): renet path globs -> the Go packages to test (the package itself plus its in-repo dependents, computed with `go list -deps` and checked by a gate so the map cannot drift from the import graph) and the names of the vm:check areas the path belongs to. The areas themselves (their drills and e2e suites) live in item 3's proof-tiers.json and are referenced by name only, so a path rule is edited in the map and an area's contents in proof-tiers.json, never both.
2. ci:quick: a renet diff runs `go test` for the mapped packages (cached per tree) and writes a tree-keyed receipt; `block_renet_untested_push.py` refuses a console push or a `-C private/renet` push whose range touches renet without a receipt covering that tree; the Stop hook (`wl_renettests.py`) names the exact command when renet changed since the last receipt.
3. Areas: proof-tiers.json gains areas (license, functions, migrate, multi-vm, ceph, kube, backup) each naming the drills and e2e suites that exercise it; `vm:check --changed` runs only the touched areas (ceph needs the ceph VMs, kube the k3s group, reported as NOT_VERIFIED with the exact command when the fleet lacks them); `scope-map.cjs` reads the same areas so a one-area change selects only its CI jobs.
4. `.claude/`: a `renet-dev` agent (build.sh and embedded assets, the key requirement, package map, function registry and tier map, generate-types regen, CLI builder pairing, the Go test map); the 12 stale facts corrected at their source; vm:check prose kept once.

## Boxes

- [x] M1: `.ci/config/renet-test-map.json` exists with a gate proving every renet Go package is reachable from some glob and every glob's packages match `go list -deps`. Accept: npm run check:ci-renet-test-map rc 0, and a planted unmapped package makes it fail.
    (ticked) 2026-10-30T17:01:55Z by d778be9d: commit:94e687110 renet-test-map.json + check:ci-renet-test-map; selftest rc 0, planted unmapped package fails
- [x] M2: ci:quick runs the mapped `go test` for a renet diff and writes a tree-keyed receipt. Accept: a renet-touching ci:quick run lists the packages it tested and the receipt names the tree.
    (ticked) 2026-10-30T17:02:23Z by d778be9d: commit:94e687110 real-tree run rc 0 after renet pointer 8e8a0e296, 6295 passed, receipt written
- [x] M3: block_renet_untested_push refuses a console or renet-submodule push touching renet without a covering receipt. Accept: its guard test rc 0 with fire cases for both push forms and silent controls.
    (ticked) 2026-10-30T17:01:59Z by d778be9d: commit:94e687110 guard test rc 0, 35 cases, 3 mutants flip
- [x] M4: the Stop hook names the exact renet test command when renet changed since the last receipt. Accept: a wl_renettests unit test fires on a planted untested renet diff and stays silent after a receipt.
    (ticked) 2026-10-30T17:02:03Z by d778be9d: commit:94e687110 test_renet_test_map_stop 8 passed; wired in wl_checks, effort renet-tests
- [x] V1: proof-tiers.json areas map renet paths to drills and e2e suites, and vm:check --changed runs only the touched areas. Accept: vm:check --changed --dry-run on a pkg/license diff lists the licence leg and not the ceph leg, and on a pkg/kube diff lists the kube suites.
    (ticked) 2026-10-30T17:02:05Z by d778be9d: commit:94e687110 vm:check --dry-run --paths: license store -> licence leg only; kube k3s -> suites 15/16/17/24 owed NOT_VERIFIED
- [x] V2: scope-map.cjs selects CI jobs from the same areas. Accept: its tests rc 0, with a one-area diff selecting only that area's jobs.
    (ticked) 2026-10-30T17:02:07Z by d778be9d: commit:94e687110 scope-map area selection; test_scope_map_areas and test_gate_scope_engine pass
- [x] A1: the renet-dev agent exists and the 12 stale facts are corrected. Accept: grep for nolicense, bin/enforce, RDC_RENET_LICENSE and REDIACC_SKIP_MACHINE_ACTIVATION across .claude/, private/renet/CLAUDE.md and docs/agent-reference/ returns only historical mentions, and check:ci-skill-size rc 0.
    (ticked) 2026-10-30T14:11:43Z by d778be9d: commit:370e7923d (+58bb68b09 renet CLAUDE.md pointer) renet-dev agent, 12 stale facts corrected; check:ci-skill-size rc 0, check:ci-agent-model-roster rc 0
